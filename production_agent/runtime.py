"""带生产化保护机制的端到端 Agent 请求链。"""

from __future__ import annotations

import json
import re
import sqlite3
import threading
import uuid
from collections.abc import Callable
from dataclasses import asdict
from typing import Any

from .models import AgentState, IntentResult, Message, ToolResult
from .retrieval import DEFAULT_DOCUMENTS, VersionedKnowledgeBase
from .security import TraceRecorder, redact, stable_hash


class ConcurrentUpdateError(RuntimeError):
    """保存会话时发现版本已过期，说明存在并发更新。"""


class LoopDetectedError(RuntimeError):
    """工作流没有取得进展，或者已经超过执行预算。"""


class SessionStore:
    """使用 compare-and-swap 乐观锁更新 SQLite 会话状态。"""

    def __init__(self, database: str = ":memory:") -> None:
        self._connection = sqlite3.connect(database, check_same_thread=False, isolation_level=None)
        self._connection.execute("PRAGMA journal_mode=WAL")
        self._connection.execute(
            """
            CREATE TABLE IF NOT EXISTS agent_sessions (
                session_id TEXT PRIMARY KEY,
                version INTEGER NOT NULL,
                state_json TEXT NOT NULL
            )
            """
        )
        self._lock = threading.RLock()

    def load(self, session_id: str) -> tuple[int, dict[str, Any]]:
        """读取会话当前版本和持久化状态；新会话版本为 0。"""

        with self._lock:
            row = self._connection.execute(
                "SELECT version, state_json FROM agent_sessions WHERE session_id = ?",
                (session_id,),
            ).fetchone()
        if row is None:
            return 0, {}
        return int(row[0]), json.loads(row[1])

    def save(self, session_id: str, expected_version: int, state: dict[str, Any]) -> int:
        """只有数据库版本等于 expected_version 时才允许写入。"""

        payload = json.dumps(state, ensure_ascii=False, sort_keys=True)
        with self._lock:
            # BEGIN IMMEDIATE 保证版本检查和写入处于同一个事务中。
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                if expected_version == 0:
                    # 新会话只能被创建一次；并发创建时只有一个请求成功。
                    cursor = self._connection.execute(
                        """
                        INSERT OR IGNORE INTO agent_sessions(session_id, version, state_json)
                        VALUES (?, 1, ?)
                        """,
                        (session_id, payload),
                    )
                    if cursor.rowcount != 1:
                        raise ConcurrentUpdateError(
                            f"session {session_id} was created concurrently"
                        )
                    next_version = 1
                else:
                    # 旧版本不匹配时 UPDATE 行数为 0，从而阻止后到请求覆盖新状态。
                    cursor = self._connection.execute(
                        """
                        UPDATE agent_sessions
                        SET version = version + 1, state_json = ?
                        WHERE session_id = ? AND version = ?
                        """,
                        (payload, session_id, expected_version),
                    )
                    if cursor.rowcount != 1:
                        raise ConcurrentUpdateError(
                            f"session {session_id} expected version {expected_version}"
                        )
                    next_version = expected_version + 1
                self._connection.execute("COMMIT")
                return next_version
            except Exception:
                self._connection.execute("ROLLBACK")
                raise


class IdempotencyStore:
    """每个幂等键只执行第一次写操作，后续重试直接重放结果。"""

    def __init__(self) -> None:
        self._records: dict[str, ToolResult] = {}
        self._lock = threading.RLock()

    def execute(
        self,
        tool_name: str,
        key: str,
        operation: Callable[[], dict[str, Any]],
    ) -> ToolResult:
        with self._lock:
            # 如果已经有结果，说明这是网络重试或工作流重跑，不再执行副作用。
            existing = self._records.get(key)
            if existing is not None:
                return ToolResult(
                    tool_name=existing.tool_name,
                    idempotency_key=existing.idempotency_key,
                    status=existing.status,
                    output=existing.output,
                    replayed=True,
                )
            try:
                # 只有首次请求会真正执行数据库写入或外部 API 调用。
                output = operation()
                result = ToolResult(tool_name, key, "succeeded", output)
            except Exception as exc:
                result = ToolResult(
                    tool_name,
                    key,
                    "failed",
                    {"error_type": type(exc).__name__, "message": str(exc)},
                )
            self._records[key] = result
            return result


class ToolExecutor:
    """工具权限、确认和幂等由执行器控制，不交给 LLM 自行决定。"""

    TOOL_POLICIES = {
        "create_repair_ticket": {
            "roles": {"investment", "ir", "operations"},
            "requires_confirmation": True,
        }
    }

    def __init__(self, idempotency: IdempotencyStore | None = None) -> None:
        self.idempotency = idempotency or IdempotencyStore()
        self.created_ticket_count = 0
        self._counter_lock = threading.Lock()

    def execute(
        self,
        tool_name: str,
        *,
        user: str,
        role: str,
        session_id: str,
        operation_id: str,
        arguments: dict[str, Any],
        confirmed: bool,
    ) -> ToolResult:
        policy = self.TOOL_POLICIES.get(tool_name)
        normalized = json.dumps(arguments, ensure_ascii=False, sort_keys=True)
        # request/operation ID 保证“同一次请求重试”幂等，
        # 不会误伤用户之后主动发起的另一笔同参数业务操作。
        key = stable_hash(f"{user}|{session_id}|{operation_id}|{tool_name}|{normalized}")
        # 第一道防线：角色必须在工具白名单中。
        if policy is None or role not in policy["roles"]:
            return ToolResult(tool_name, key, "blocked", {"reason": "tool_not_allowed"})
        # 第二道防线：写操作必须获得明确确认。
        if policy["requires_confirmation"] and not confirmed:
            return ToolResult(tool_name, key, "blocked", {"reason": "confirmation_required"})

        def create_ticket() -> dict[str, Any]:
            # 这里模拟真正的工单写入；计数器用于测试是否发生重复写入。
            with self._counter_lock:
                self.created_ticket_count += 1
            return {
                "ticket_id": f"TKT-{key[:8].upper()}",
                "device_model": arguments["device_model"],
                "fault_code": arguments["fault_code"],
                "created_by": user,
            }

        return self.idempotency.execute(tool_name, key, create_ticket)


class ExecutionGuard:
    """通过最大步数和重复动作检测阻止 Agent 死循环。"""

    def __init__(self, max_steps: int = 12, max_repeats: int = 2) -> None:
        self.max_steps = max_steps
        self.max_repeats = max_repeats
        self.steps = 0
        self.actions: list[str] = []

    def record(self, action: str) -> None:
        # 每个节点或工具调用都必须消耗一步预算。
        self.steps += 1
        if self.steps > self.max_steps:
            raise LoopDetectedError("maximum workflow steps exceeded")
        self.actions.append(action)
        # 同一动作连续反复出现，通常意味着模型没有根据工具结果调整策略。
        if self.actions.count(action) > self.max_repeats:
            raise LoopDetectedError(f"repeated action without progress: {action}")


class IntentRecognizer:
    """同时完成多标签意图识别、实体抽取、置信度和缺失槽位判断。"""

    INTENT_KEYWORDS = {
        "industry_research": ("行业", "市场", "建筑", "调研"),
        "company_research": ("公司", "公告", "财报", "核验"),
        "fault_diagnosis": ("故障", "维修", "诊断", "故障码", "e102"),
        "create_ticket": ("创建工单", "生成工单", "提交工单"),
        "file_summary": ("pdf", "文件", "摘要"),
    }

    def recognize(self, request: str) -> IntentResult:
        lowered = request.lower()
        # 一个请求可以命中多个意图，不能只选择分数最高的单标签。
        intents = [
            intent
            for intent, keywords in self.INTENT_KEYWORDS.items()
            if any(keyword.lower() in lowered for keyword in keywords)
        ]
        if not intents:
            intents = ["company_research"]

        entities: dict[str, str] = {}
        # 提取设备型号和故障码，后续检索和工具调用直接使用结构化字段。
        for known_model in ("MX-100", "MX-200"):
            if known_model.lower() in lowered:
                entities["device_model"] = known_model
        code_matches = re.findall(r"\b[A-Z]{1,4}[-_]?\d{2,6}\b", request, re.I)
        for candidate in code_matches:
            normalized = candidate.upper().replace("_", "-")
            if normalized != entities.get("device_model"):
                entities["fault_code"] = normalized
                break

        missing: list[str] = []
        # 不同意图拥有不同必填槽位，缺失时应进入澄清节点。
        if "fault_diagnosis" in intents and "fault_code" not in entities:
            missing.append("fault_code")
        if "create_ticket" in intents:
            for field in ("device_model", "fault_code"):
                if field not in entities:
                    missing.append(field)

        matched_keyword_count = sum(
            keyword.lower() in lowered
            for keywords in self.INTENT_KEYWORDS.values()
            for keyword in keywords
        )
        confidence = min(0.98, 0.5 + matched_keyword_count * 0.08)
        return IntentResult(
            intents=tuple(dict.fromkeys(intents)),
            entities=entities,
            confidence=confidence,
            missing_fields=tuple(dict.fromkeys(missing)),
        )


class ClarificationPolicy:
    """确定性规则负责硬拦截，低置信度负责提示语义歧义。"""

    CONFIRMATION_WORDS = ("确认创建", "确认提交", "同意创建", "立即创建")

    def decide(self, request: str, result: IntentResult) -> tuple[bool, str, str]:
        # 必填字段缺失属于确定性问题，直接由规则决定必须澄清。
        if result.missing_fields:
            fields = "、".join(result.missing_fields)
            return True, f"请补充以下信息：{fields}。", "required_fields_rule"
        # 创建工单属于有副作用的写操作，没有确认就不能继续。
        if "create_ticket" in result.intents and not any(
            word in request for word in self.CONFIRMATION_WORDS
        ):
            return True, "工单属于写操作，请明确回复“确认创建”。", "write_confirmation_rule"
        # 低置信度类似模型给出的软信号，用于处理表达模糊但无固定规则的情况。
        if result.confidence < 0.55:
            return (
                True,
                "你的目标还不够明确，请说明希望查询、分析还是执行操作。",
                "ambiguity_signal",
            )
        return False, "", "not_required"


class ContextManager:
    """裁剪旧对话，同时保留固定信息、近期消息和结构化摘要。"""

    def __init__(self, recent_messages: int = 6) -> None:
        self.recent_messages = recent_messages

    def compact(
        self,
        messages: list[Message],
        previous_summary: str = "",
        pinned_facts: list[str] | None = None,
    ) -> tuple[list[Message], str]:
        pinned_facts = pinned_facts or []
        # pinned 消息通常是系统规则或用户已确认事实，永远不能被普通裁剪删除。
        pinned = [message for message in messages if message.get("pinned")]
        regular = [message for message in messages if not message.get("pinned")]
        if len(regular) <= self.recent_messages:
            return pinned + regular, previous_summary

        old = regular[: -self.recent_messages]
        recent = regular[-self.recent_messages :]
        # 旧消息压缩成摘要，避免只保留最近 N 轮导致关键决策完全丢失。
        facts = [
            f"{message.get('role', 'unknown')}: {message.get('content', '')[:100]}"
            for message in old
        ]
        summary_parts = [part for part in (previous_summary, *pinned_facts, *facts) if part]
        summary = " | ".join(summary_parts)[-1200:]
        return pinned + recent, summary


ROLE_PROFILES: dict[str, dict[str, Any]] = {
    "investment": {
        "label": "投研",
        "allowed_domains": ["行业研究", "公司研究", "设备维修"],
    },
    "ir": {
        "label": "IR",
        "allowed_domains": ["公司研究", "设备维修"],
    },
    "operations": {
        "label": "中后台",
        "allowed_domains": ["设备维修"],
    },
}


class AgentService:
    """协调完整请求生命周期；Demo 使用本地逻辑，因此不需要外部模型。"""

    def __init__(
        self,
        knowledge_base: VersionedKnowledgeBase | None = None,
        sessions: SessionStore | None = None,
        tools: ToolExecutor | None = None,
    ) -> None:
        self.knowledge_base = knowledge_base or VersionedKnowledgeBase(DEFAULT_DOCUMENTS)
        self.sessions = sessions or SessionStore()
        self.tools = tools or ToolExecutor()
        self.intent_recognizer = IntentRecognizer()
        self.clarification = ClarificationPolicy()
        self.context = ContextManager()

    def handle(
        self,
        *,
        user: str,
        role: str,
        request: str,
        session_id: str,
        request_id: str | None = None,
        conflict_retries: int = 1,
    ) -> AgentState:
        request_id = request_id or str(uuid.uuid4())
        last_error: ConcurrentUpdateError | None = None
        # 并发冲突时重新读取最新会话并重跑流程；写工具依靠幂等键不会重复执行。
        for _ in range(conflict_retries + 1):
            # 第一步：读取会话快照和当前版本。
            version, persisted = self.sessions.load(session_id)
            # 第二步：基于该快照执行完整 Agent 工作流。
            state = self._run_pipeline(
                user=user,
                role=role,
                request=request,
                session_id=session_id,
                request_id=request_id,
                session_version=version,
                persisted=persisted,
            )
            try:
                # 第三步：使用读取时的版本做 compare-and-swap 保存。
                next_version = self.sessions.save(
                    session_id,
                    version,
                    self._session_payload(state),
                )
                state["persisted_session_version"] = next_version
                return state
            except ConcurrentUpdateError as exc:
                # 版本冲突表示另一请求已先保存，进入下一轮重新读取，而不是覆盖它。
                last_error = exc
        raise last_error or ConcurrentUpdateError("session update failed")

    def _run_pipeline(
        self,
        *,
        user: str,
        role: str,
        request: str,
        session_id: str,
        request_id: str,
        session_version: int,
        persisted: dict[str, Any],
    ) -> AgentState:
        # 初始化 Trace、循环保护器和本轮结构化状态。
        recorder = TraceRecorder(request_id, session_id)
        guard = ExecutionGuard()
        messages: list[Message] = list(persisted.get("messages", []))
        messages.append({"role": "user", "content": request})
        state: AgentState = {
            "request_id": request_id,
            "session_id": session_id,
            "expected_session_version": session_version,
            "user": user,
            "role": role,
            "request": request,
            "messages": messages,
            "conversation_summary": persisted.get("conversation_summary", ""),
            "pinned_facts": list(persisted.get("pinned_facts", [])),
            "step_count": 0,
            "action_history": [],
            "remaining_budget": guard.max_steps,
            "specialist_results": [],
            "tool_results": [],
            "status": "running",
        }

        # 第 1 步：身份鉴权。根据角色加载知识域和工具权限边界。
        with recorder.span(
            "authenticate", {"user_hash": stable_hash(user), "role": role}
        ) as output:
            guard.record("authenticate")
            profile = ROLE_PROFILES.get(role)
            if profile is None:
                raise PermissionError(f"unknown role: {role}")
            state["allowed_domains"] = list(profile["allowed_domains"])
            output["allowed_domain_count"] = len(profile["allowed_domains"])

        # 第 2 步：理解请求。输出多意图、实体、置信度和缺失字段。
        with recorder.span("understand", {"request_length": len(request)}) as output:
            guard.record("understand")
            intent_result = self.intent_recognizer.recognize(request)
            state["intents"] = list(intent_result.intents)
            state["entities"] = intent_result.entities
            state["intent_confidence"] = intent_result.confidence
            state["missing_fields"] = list(intent_result.missing_fields)
            output.update(
                {
                    "intents": list(intent_result.intents),
                    "confidence": intent_result.confidence,
                    "missing_fields": list(intent_result.missing_fields),
                }
            )

        # 第 3 步：决定是否澄清。规则负责必填项和写操作确认。
        with recorder.span("clarify", {"intents": state["intents"]}) as output:
            guard.record("clarify")
            required, question, reason = self.clarification.decide(request, intent_result)
            state["clarification_required"] = required
            state["clarification_question"] = question
            output.update({"required": required, "reason": reason})

        # 需要澄清时立即进入终态，不能带着不完整参数继续检索或写入。
        if state["clarification_required"]:
            state["status"] = "needs_clarification"
            state["termination_reason"] = "clarification_required"
            state["answer"] = state["clarification_question"]
            messages.append({"role": "assistant", "content": state["answer"]})
            self._finalize_context(state)
            self._finalize_guard(state, guard)
            state["trace"] = recorder.to_dicts()
            return state

        # 第 4 步：读取知识版本并检查答案缓存。
        # 写操作不使用答案缓存，避免跳过确认、审计或真实执行。
        active_version = self.knowledge_base.active_version
        state["knowledge_version"] = active_version
        read_only = "create_ticket" not in state["intents"]
        cached = (
            self.knowledge_base.answer_cache.get(request, role, active_version)
            if read_only
            else None
        )
        if cached is not None:
            state["answer"] = cached
            state["status"] = "completed"
            state["termination_reason"] = "cache_hit"
            messages.append({"role": "assistant", "content": cached})
            self._finalize_context(state)
            self._finalize_guard(state, guard)
            state["trace"] = recorder.to_dicts()
            return state

        # 第 5 步：执行带 ACL、分区过滤、RRF 融合和注入防护的知识检索。
        with recorder.span(
            "retrieve",
            {
                "knowledge_version": active_version,
                "domain_count": len(state["allowed_domains"]),
            },
        ) as output:
            guard.record(f"retrieve:{stable_hash(request)}")
            hits, diagnostics = self.knowledge_base.search(
                request,
                set(state["allowed_domains"]),
                state["entities"].get("device_model", "*"),
            )
            state["retrieved"] = [asdict(hit) for hit in hits]
            output.update(
                {
                    "hit_ids": [hit.document_id for hit in hits],
                    "candidate_documents": diagnostics.candidate_documents,
                    "total_documents": diagnostics.total_documents,
                    "fusion_method": diagnostics.fusion_method,
                    "security_flag_count": sum(len(hit.security_flags) for hit in hits),
                }
            )

        # 第 6 步：只为识别出的专业意图运行对应 specialist。
        # 不盲目增加 Agent 数量，减少不必要的通信和错误传播。
        with recorder.span("specialists", {"intents": state["intents"]}) as output:
            guard.record("specialists:" + ",".join(state["intents"]))
            state["specialist_results"] = self._run_specialists(state)
            output["specialist_count"] = len(state["specialist_results"])

        # 第 7 步：如果包含写意图，在独立执行器中做权限、确认和幂等检查。
        if "create_ticket" in state["intents"]:
            with recorder.span("tool:create_repair_ticket", {"write": True}) as output:
                arguments = {
                    "device_model": state["entities"]["device_model"],
                    "fault_code": state["entities"]["fault_code"],
                }
                guard.record(
                    "tool:create_repair_ticket:"
                    + stable_hash(json.dumps(arguments, sort_keys=True))
                )
                result = self.tools.execute(
                    "create_repair_ticket",
                    user=user,
                    role=role,
                    session_id=session_id,
                    operation_id=request_id,
                    arguments=arguments,
                    confirmed=True,
                )
                state["tool_results"].append(asdict(result))
                output.update({"status": result.status, "replayed": result.replayed})

        # 第 8 步：统一审计检索权限、外部内容风险和工具执行结果。
        with recorder.span("audit", {"retrieval_count": len(state.get("retrieved", []))}) as output:
            guard.record("audit")
            state["audit"] = self._audit(state)
            output.update(state["audit"])

        # 第 9 步：汇总专业结论、工具结果、引用来源和安全提示。
        with recorder.span("summarize", {"source_count": len(state["audit"]["sources"])}) as output:
            guard.record("summarize")
            state["answer"] = self._summarize(state)
            state["status"] = "completed" if state["audit"]["passed"] else "blocked"
            state["termination_reason"] = (
                "completed" if state["audit"]["passed"] else "audit_failed"
            )
            output.update({"answer_length": len(state["answer"]), "status": state["status"]})

        # 第 10 步：只缓存已完成的只读答案，缓存键包含知识版本。
        if read_only and state["status"] == "completed":
            self.knowledge_base.answer_cache.set(request, role, active_version, state["answer"])

        # 返回前裁剪上下文、记录预算消耗，并生成脱敏 Trace。
        messages.append({"role": "assistant", "content": state["answer"]})
        self._finalize_context(state)
        self._finalize_guard(state, guard)
        state["trace"] = recorder.to_dicts()
        return state

    @staticmethod
    def _run_specialists(state: AgentState) -> list[dict[str, Any]]:
        """根据多意图运行必要的专业处理器，并统一返回结构化结果。"""

        sources = [hit["source"] for hit in state.get("retrieved", [])]
        results = []
        for intent in state["intents"]:
            if intent == "industry_research":
                summary = "对行业资料进行多源交叉核验，并区分事实与分析判断。"
            elif intent == "company_research":
                summary = "优先核验公司公告和可回溯来源。"
            elif intent == "fault_diagnosis":
                summary = "先按故障码精确匹配，再结合维修手册和已解决工单诊断。"
            elif intent == "create_ticket":
                summary = "诊断信息完整且获得明确确认后创建维修工单。"
            else:
                summary = "对授权文件生成结构化摘要。"
            results.append({"agent": intent, "summary": summary, "sources": sources})
        return results

    @staticmethod
    def _audit(state: AgentState) -> dict[str, Any]:
        """对权限、注入风险、引用来源和工具失败做最终审计。"""

        allowed = set(state["allowed_domains"])
        unauthorized = [
            hit["document_id"]
            for hit in state.get("retrieved", [])
            if hit.get("domain") not in allowed
        ]
        security_flags = sorted(
            {flag for hit in state.get("retrieved", []) for flag in hit.get("security_flags", [])}
        )
        tool_failures = [
            result for result in state.get("tool_results", []) if result["status"] != "succeeded"
        ]
        return {
            "passed": not unauthorized and not tool_failures and bool(allowed),
            "sources": [hit["source"] for hit in state.get("retrieved", [])],
            "security_flags": security_flags,
            "unauthorized_count": len(unauthorized),
            "tool_failure_count": len(tool_failures),
        }

    @staticmethod
    def _summarize(state: AgentState) -> str:
        """生成最终回答，但不直接暴露被隔离的外部恶意指令。"""

        lines = [result["summary"] for result in state["specialist_results"]]
        if state.get("tool_results"):
            tool = state["tool_results"][-1]
            if tool["status"] == "succeeded":
                replay = "（幂等重放）" if tool["replayed"] else ""
                lines.append(f"已创建工单 {tool['output']['ticket_id']}{replay}。")
        sources = state["audit"]["sources"]
        lines.append(f"引用来源：{', '.join(sources) if sources else '暂无匹配资料'}。")
        if state["audit"]["security_flags"]:
            lines.append("检测到外部内容中的可疑指令，已按不可信数据隔离，未执行其中操作。")
        return "\n".join(lines)

    def _finalize_context(self, state: AgentState) -> None:
        # 压缩历史消息，控制 Token，同时保留近期对话和 pinned 事实。
        messages, summary = self.context.compact(
            state["messages"],
            state.get("conversation_summary", ""),
            state.get("pinned_facts", []),
        )
        state["messages"] = messages
        state["conversation_summary"] = summary

    @staticmethod
    def _finalize_guard(state: AgentState, guard: ExecutionGuard) -> None:
        # 将循环保护器的运行数据写回 State，方便 Trace 和故障定位。
        state["step_count"] = guard.steps
        state["action_history"] = guard.actions
        state["remaining_budget"] = guard.max_steps - guard.steps

    @staticmethod
    def _session_payload(state: AgentState) -> dict[str, Any]:
        """只持久化跨轮需要的事实，不保存全部临时执行状态。"""

        # Trace 只保留阶段名称和终止原因，完整文档与敏感参数不会写入会话。
        return {
            "messages": state.get("messages", []),
            "conversation_summary": state.get("conversation_summary", ""),
            "pinned_facts": state.get("pinned_facts", []),
            "last_request_id": state["request_id"],
            "last_status": state["status"],
            "last_knowledge_version": state.get("knowledge_version"),
            "last_answer_hash": stable_hash(state.get("answer", "")),
            "trace_summary": redact(
                {
                    "stages": [
                        event["stage"]
                        for event in state.get("trace", [])
                        if event["status"] != "started"
                    ],
                    "termination_reason": state.get("termination_reason"),
                }
            ),
        }
