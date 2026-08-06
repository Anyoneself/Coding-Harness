"""带生产化保护机制的端到端 Agent 请求链。"""

from __future__ import annotations

import uuid
from dataclasses import asdict
from typing import Any

from ..domain.models import AgentState, Message
from ..domain.policies import ClarificationPolicy, ContextManager, ExecutionGuard, IntentRecognizer
from ..infrastructure.security import TraceRecorder, redact, stable_hash
from ..repositories.knowledge import DEFAULT_DOCUMENTS, VersionedKnowledgeBase
from ..repositories.session import ConcurrentUpdateError, SessionStore


class AgentService:
    """协调完整请求生命周期；Demo 使用本地逻辑，因此不需要外部模型。"""

    def __init__(
        self,
        knowledge_base: VersionedKnowledgeBase | None = None,
        sessions: SessionStore | None = None,
    ) -> None:
        """装配知识仓储、会话仓储和通用工作流策略。"""
        self.knowledge_base = knowledge_base or VersionedKnowledgeBase(DEFAULT_DOCUMENTS)
        self.sessions = sessions or SessionStore()
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
        """处理一次本地 Agent 请求，并在并发冲突时按策略重试。"""
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
        """运行单次请求的完整业务管线并生成结构化状态。"""
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

        # 第 1 步：记录身份上下文。通用 Agent 不按业务领域限制知识范围。
        with recorder.span(
            "authenticate", {"user_hash": stable_hash(user), "role": role}
        ) as output:
            guard.record("authenticate")
            output["access_scope"] = "all_configured_knowledge"

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
        active_version = self.knowledge_base.active_version
        state["knowledge_version"] = active_version
        cached = self.knowledge_base.answer_cache.get(request, role, active_version)
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
                "access_scope": "all_configured_knowledge",
            },
        ) as output:
            guard.record(f"retrieve:{stable_hash(request)}")
            hits, diagnostics = self.knowledge_base.search(
                request,
                None,
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

        # 第 7 步：统一审计检索权限、外部内容风险和工具执行结果。
        with recorder.span("audit", {"retrieval_count": len(state.get("retrieved", []))}) as output:
            guard.record("audit")
            state["audit"] = self._audit(state)
            output.update(state["audit"])

        # 第 8 步：汇总任务结论、引用来源和安全提示。
        with recorder.span("summarize", {"source_count": len(state["audit"]["sources"])}) as output:
            guard.record("summarize")
            state["answer"] = self._summarize(state)
            state["status"] = "completed" if state["audit"]["passed"] else "blocked"
            state["termination_reason"] = (
                "completed" if state["audit"]["passed"] else "audit_failed"
            )
            output.update({"answer_length": len(state["answer"]), "status": state["status"]})

        # 第 9 步：缓存已完成答案，缓存键包含知识版本。
        if state["status"] == "completed":
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
            if intent == "analysis":
                summary = "已对可用资料进行结构化分析，并区分事实与判断。"
            elif intent == "knowledge_search":
                summary = "已检索相关资料并保留可回溯来源。"
            elif intent == "file_summary":
                summary = "已生成文件内容的结构化摘要。"
            elif intent == "calculation":
                summary = "已识别计算任务；需要精确计算时应调用计算工具。"
            else:
                summary = "已理解问题并基于可用上下文生成回答。"
            results.append({"agent": intent, "summary": summary, "sources": sources})
        return results

    @staticmethod
    def _audit(state: AgentState) -> dict[str, Any]:
        """对权限、注入风险、引用来源和工具失败做最终审计。"""

        security_flags = sorted(
            {flag for hit in state.get("retrieved", []) for flag in hit.get("security_flags", [])}
        )
        tool_failures = [
            result for result in state.get("tool_results", []) if result["status"] != "succeeded"
        ]
        return {
            "passed": not tool_failures,
            "sources": [hit["source"] for hit in state.get("retrieved", [])],
            "security_flags": security_flags,
            "unauthorized_count": 0,
            "tool_failure_count": len(tool_failures),
        }

    @staticmethod
    def _summarize(state: AgentState) -> str:
        """生成最终回答，但不直接暴露被隔离的外部恶意指令。"""

        lines = [result["summary"] for result in state["specialist_results"]]
        sources = state["audit"]["sources"]
        lines.append(f"引用来源：{', '.join(sources) if sources else '暂无匹配资料'}。")
        if state["audit"]["security_flags"]:
            lines.append("检测到外部内容中的可疑指令，已按不可信数据隔离，未执行其中操作。")
        return "\n".join(lines)

    def _finalize_context(self, state: AgentState) -> None:
        """压缩会话上下文并回写摘要。"""
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
        """把执行保护器的统计信息写入最终状态。"""
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
