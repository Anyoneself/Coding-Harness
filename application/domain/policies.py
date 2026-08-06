"""本地 Agent 工作流使用的领域规则和执行保护策略。"""

from __future__ import annotations

from .models import IntentResult, Message


class LoopDetectedError(RuntimeError):
    """工作流重复执行相同动作或超过预算。"""


class ExecutionGuard:
    """通过最大步数和重复动作检测阻止 Agent 死循环。"""

    def __init__(self, max_steps: int = 12, max_repeats: int = 2) -> None:
        """配置执行步数和相同动作的最大允许次数。"""
        self.max_steps = max_steps
        self.max_repeats = max_repeats
        self.steps = 0
        self.actions: list[str] = []

    def record(self, action: str) -> None:
        """记录一次工作流动作，并在超出限制时中止执行。"""
        self.steps += 1
        if self.steps > self.max_steps:
            raise LoopDetectedError("maximum workflow steps exceeded")
        self.actions.append(action)
        if self.actions.count(action) > self.max_repeats:
            raise LoopDetectedError(f"repeated action without progress: {action}")


class IntentRecognizer:
    """识别与具体业务领域无关的通用任务意图。"""

    INTENT_KEYWORDS = {
        "knowledge_search": ("知识库", "资料", "文档", "检索", "查找"),
        "analysis": ("分析", "比较", "评估", "调研", "核验"),
        "file_summary": ("pdf", "文件", "摘要"),
        "calculation": ("计算", "多少", "公式"),
    }

    def recognize(self, request: str) -> IntentResult:
        """从用户请求中提取意图和设备相关实体。"""
        lowered = request.lower()
        intents = [
            intent
            for intent, keywords in self.INTENT_KEYWORDS.items()
            if any(keyword.lower() in lowered for keyword in keywords)
        ] or ["question_answering"]
        entities: dict[str, str] = {}
        matched_keyword_count = sum(
            keyword.lower() in lowered
            for keywords in self.INTENT_KEYWORDS.values()
            for keyword in keywords
        )
        return IntentResult(
            intents=tuple(dict.fromkeys(intents)),
            entities=entities,
            confidence=min(0.98, 0.72 + matched_keyword_count * 0.06),
            missing_fields=(),
        )


class ClarificationPolicy:
    """根据缺失信息和置信度决定是否向用户澄清。"""

    def decide(self, request: str, result: IntentResult) -> tuple[bool, str, str]:
        """返回是否澄清、澄清问题和触发规则。"""
        if result.missing_fields:
            fields = "、".join(result.missing_fields)
            return True, f"请补充以下信息：{fields}。", "required_fields_rule"
        if result.confidence < 0.55:
            return True, "你的目标还不够明确，请说明希望查询、分析还是执行操作。", "ambiguity_signal"
        return False, "", "not_required"


class ContextManager:
    """裁剪旧对话，同时保留固定信息、近期消息和结构化摘要。"""

    def __init__(self, recent_messages: int = 6) -> None:
        """设置压缩后保留的近期普通消息数量。"""
        self.recent_messages = recent_messages

    def compact(
        self,
        messages: list[Message],
        previous_summary: str = "",
        pinned_facts: list[str] | None = None,
    ) -> tuple[list[Message], str]:
        """压缩超出窗口的旧消息，并保留固定消息与事实。"""
        pinned_facts = pinned_facts or []
        pinned = [message for message in messages if message.get("pinned")]
        regular = [message for message in messages if not message.get("pinned")]
        if len(regular) <= self.recent_messages:
            return pinned + regular, previous_summary
        old = regular[: -self.recent_messages]
        recent = regular[-self.recent_messages :]
        facts = [
            f"{message.get('role', 'unknown')}: {message.get('content', '')[:100]}"
            for message in old
        ]
        summary_parts = [part for part in (previous_summary, *pinned_facts, *facts) if part]
        return pinned + recent, " | ".join(summary_parts)[-1200:]
