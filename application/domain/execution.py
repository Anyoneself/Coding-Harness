"""Coding Harness 执行域的实体、状态机与业务异常。"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any


class InvalidTurnTransitionError(RuntimeError):
    """Turn 状态迁移不符合执行域状态机。"""


class WorkspaceNotFoundError(LookupError):
    """指定 Workspace 不存在。"""


class ThreadNotFoundError(LookupError):
    """指定 Thread 不存在。"""


class TurnNotFoundError(LookupError):
    """指定 Turn 不存在。"""


class PermissionProfile(StrEnum):
    """定义工作区在 Harness 中允许使用的权限档。"""

    READ_ONLY = "read_only"
    WORKSPACE = "workspace"


class ThreadStatus(StrEnum):
    """定义代码任务线程的生命周期状态。"""

    ACTIVE = "active"
    ARCHIVED = "archived"


class TurnStatus(StrEnum):
    """定义一次代码任务执行的稳定状态。"""

    QUEUED = "queued"
    RUNNING = "running"
    WAITING_APPROVAL = "waiting_approval"
    COMPLETED = "completed"
    FAILED = "failed"
    INTERRUPTED = "interrupted"
    CANCELLED = "cancelled"


class ItemType(StrEnum):
    """定义可持久化并展示给用户的执行单元类型。"""

    USER_MESSAGE = "user_message"
    AGENT_MESSAGE = "agent_message"
    ERROR = "error"
    CHECKPOINT = "checkpoint"


class ItemStatus(StrEnum):
    """定义执行单元的处理状态。"""

    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


_ALLOWED_TURN_TRANSITIONS: dict[TurnStatus, frozenset[TurnStatus]] = {
    TurnStatus.QUEUED: frozenset(
        {TurnStatus.RUNNING, TurnStatus.CANCELLED, TurnStatus.FAILED}
    ),
    TurnStatus.RUNNING: frozenset(
        {
            TurnStatus.WAITING_APPROVAL,
            TurnStatus.COMPLETED,
            TurnStatus.FAILED,
            TurnStatus.INTERRUPTED,
            TurnStatus.CANCELLED,
        }
    ),
    TurnStatus.WAITING_APPROVAL: frozenset(
        {TurnStatus.RUNNING, TurnStatus.INTERRUPTED, TurnStatus.CANCELLED}
    ),
    TurnStatus.INTERRUPTED: frozenset({TurnStatus.QUEUED, TurnStatus.CANCELLED}),
    TurnStatus.COMPLETED: frozenset(),
    TurnStatus.FAILED: frozenset(),
    TurnStatus.CANCELLED: frozenset(),
}


@dataclass(frozen=True)
class ExecutionBudget:
    """限制一次 Turn 可消费的模型、工具、时间、Token 和成本。"""

    max_model_calls: int = 8
    max_tool_calls: int = 0
    max_wall_time_seconds: int = 900
    max_tokens: int = 100_000
    max_cost: float = 10.0

    def __post_init__(self) -> None:
        """拒绝任何负数预算，避免将配置错误解释为无限额度。"""
        values = (
            self.max_model_calls,
            self.max_tool_calls,
            self.max_wall_time_seconds,
            self.max_tokens,
            self.max_cost,
        )
        if any(value < 0 for value in values):
            raise ValueError("execution budget values cannot be negative")


@dataclass(frozen=True)
class Workspace:
    """描述 Harness 可以访问的本地工作区及权限边界。"""

    id: str
    root_path: str
    permission_profile: PermissionProfile
    created_at: datetime

@dataclass(frozen=True)
class Thread:
    """描述围绕一个持续代码目标形成的任务线程。"""

    id: str
    workspace_id: str
    title: str
    status: ThreadStatus
    created_at: datetime


@dataclass(frozen=True)
class Turn:
    """描述一次用户输入触发的完整 Harness 执行。"""

    id: str
    thread_id: str
    prompt: str
    status: TurnStatus
    version: int
    next_sequence: int
    budget: ExecutionBudget
    lease_owner: str | None = None
    lease_expires_at: datetime | None = None
    interrupt_requested_at: datetime | None = None
    termination_reason: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def transition_to(self, target: TurnStatus) -> Turn:
        """校验目标状态，并返回版本递增的新 Turn 快照。"""
        allowed_targets = _ALLOWED_TURN_TRANSITIONS[self.status]
        if target not in allowed_targets:
            raise InvalidTurnTransitionError(
                f"turn {self.id} cannot transition from {self.status.value} to {target.value}"
            )
        return Turn(
            id=self.id,
            thread_id=self.thread_id,
            prompt=self.prompt,
            status=target,
            version=self.version + 1,
            next_sequence=self.next_sequence,
            budget=self.budget,
            lease_owner=self.lease_owner,
            lease_expires_at=self.lease_expires_at,
            interrupt_requested_at=self.interrupt_requested_at,
            termination_reason=self.termination_reason,
            created_at=self.created_at,
            updated_at=datetime.now(UTC),
        )


@dataclass(frozen=True)
class Item:
    """描述事件流中可独立展示和持久化的执行内容。"""

    id: str
    turn_id: str
    type: ItemType
    status: ItemStatus
    payload: dict[str, Any]
    created_at: datetime


@dataclass(frozen=True)
class TurnEvent:
    """描述带单调序号和版本的公开 Turn 事件。"""

    id: str
    workspace_id: str
    thread_id: str
    turn_id: str
    sequence: int
    event_type: str
    schema_version: int
    payload: dict[str, Any]
    occurred_at: datetime


@dataclass(frozen=True)
class Checkpoint:
    """保存能够安全恢复 Turn 的公开稳定状态。"""

    id: str
    turn_id: str
    phase: str
    last_sequence: int
    public_state: dict[str, Any]
    model_calls: int
    tool_calls: int
    created_at: datetime
