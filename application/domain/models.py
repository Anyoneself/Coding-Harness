"""Agent 运行过程中共享的状态和结果模型。

这里故意不只保存 messages。messages 只是提供给模型的对话上下文，
其他字段才是路由、恢复、并发控制、审计和评估所依赖的系统事实。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal, TypedDict


class Message(TypedDict, total=False):
    # pinned=True 表示该消息是安全规则或关键事实，裁剪上下文时不能删除。
    role: Literal["system", "user", "assistant", "tool"]
    content: str
    pinned: bool
    tool_call_id: str


@dataclass(frozen=True)
class IntentResult:
    # 一个请求可以同时包含多个通用意图，例如“检索资料并进行分析”。
    intents: tuple[str, ...]
    entities: dict[str, str]
    confidence: float
    missing_fields: tuple[str, ...] = ()


@dataclass(frozen=True)
class RetrievalHit:
    # 同时保留稀疏、语义和融合分数，方便观察检索问题出在哪一层。
    document_id: str
    source_type: str
    domain: str
    title: str
    content: str
    source: str
    sparse_score: float
    dense_score: float
    fused_score: float
    knowledge_version: int
    security_flags: tuple[str, ...] = ()


@dataclass(frozen=True)
class ToolResult:
    # replayed=True 表示本次没有重复执行写操作，而是返回了首次执行结果。
    tool_name: str
    idempotency_key: str
    status: Literal["succeeded", "failed", "blocked"]
    output: dict[str, Any]
    replayed: bool = False


@dataclass(frozen=True)
class TraceEvent:
    # Trace 只保存阶段摘要，不保存完整 Prompt、文档原文或敏感身份信息。
    request_id: str
    session_id: str
    stage: str
    status: Literal["started", "succeeded", "failed", "blocked"]
    timestamp: str
    duration_ms: float | None = None
    input_summary: dict[str, Any] = field(default_factory=dict)
    output_summary: dict[str, Any] = field(default_factory=dict)
    error_type: str | None = None


@dataclass(frozen=True)
class SessionEvent:
    # 事件序号在单次请求内递增，便于重放 SSE 与后续审计。
    id: int
    session_id: str
    request_id: str
    sequence: int
    event_type: str
    payload: dict[str, Any]
    created_at: str


class AgentState(TypedDict, total=False):
    # 请求标识和乐观锁版本：用于解决同一会话的并发状态覆盖问题。
    request_id: str
    session_id: str
    expected_session_version: int
    persisted_session_version: int

    # 业务身份：用于审计和后续接入的权限策略。
    user: str
    role: str

    # 对话上下文：近期消息、历史摘要和必须长期保留的关键事实。
    messages: list[Message]
    conversation_summary: str
    pinned_facts: list[str]

    # 任务理解：多意图、实体、置信度以及还缺少哪些必填字段。
    request: str
    intents: list[str]
    entities: dict[str, str]
    intent_confidence: float
    missing_fields: list[str]
    clarification_required: bool
    clarification_question: str

    # 检索和执行结果：知识版本、召回内容、专业 Agent 结果和工具结果。
    knowledge_version: int
    retrieved: list[dict[str, Any]]
    specialist_results: list[dict[str, Any]]
    tool_results: list[dict[str, Any]]

    # 工作流控制：这些状态无法可靠地从自然语言 messages 中反推出来。
    step_count: int
    action_history: list[str]
    remaining_budget: int
    status: str
    termination_reason: str

    # 审计、可观测性和最终响应。
    audit: dict[str, Any]
    trace: list[dict[str, Any]]
    answer: str


def trace_to_dict(event: TraceEvent) -> dict[str, Any]:
    """将 Trace 领域事件转换为普通字典。"""
    return asdict(event)
