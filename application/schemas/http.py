"""My-Agent HTTP 接口使用的请求与响应模型。"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from ..domain.execution import ExecutionBudget, PermissionProfile


class ChatRequest(BaseModel):
    """描述一次需要流式处理的 Agent 对话请求。"""

    message: str = Field(min_length=1, max_length=20000)
    session_id: str = Field(min_length=1, max_length=128)
    user: str = Field(default="web-user", min_length=1, max_length=128)
    role: str = Field(default="standard", min_length=1, max_length=64)
    model: str | None = None
    thinking_enabled: bool | None = None
    reasoning_effort: Literal["low", "high", "max"] | None = None


class ResetSessionRequest(BaseModel):
    """描述需要清理上下文的会话。"""

    session_id: str = Field(min_length=1, max_length=128)


class WorkspaceCreateRequest(BaseModel):
    """描述创建 Harness 工作区所需的路径和权限档。"""

    root_path: str = Field(min_length=1, max_length=4096)
    permission_profile: PermissionProfile = PermissionProfile.READ_ONLY


class ThreadCreateRequest(BaseModel):
    """描述在工作区中创建持续任务线程的输入。"""

    title: str = Field(min_length=1, max_length=256)


class ExecutionBudgetRequest(BaseModel):
    """描述客户端可以显式收紧的 Turn 资源预算。"""

    max_model_calls: int = Field(default=8, ge=0, le=100)
    max_tool_calls: int = Field(default=0, ge=0, le=1000)
    max_wall_time_seconds: int = Field(default=900, ge=0, le=86400)
    max_tokens: int = Field(default=100_000, ge=0)
    max_cost: float = Field(default=10.0, ge=0)

    def to_domain(self) -> ExecutionBudget:
        """把经过 HTTP 校验的预算转换为执行领域值对象。"""
        return ExecutionBudget(**self.model_dump())


class TurnCreateRequest(BaseModel):
    """描述一次需要后台执行的代码任务。"""

    prompt: str = Field(min_length=1, max_length=20000)
    budget: ExecutionBudgetRequest | None = None


class WorkspaceResponse(BaseModel):
    """返回工作区稳定标识、规范化路径和权限档。"""

    model_config = ConfigDict(from_attributes=True)

    id: str
    root_path: str
    permission_profile: PermissionProfile
    created_at: datetime


class ThreadResponse(BaseModel):
    """返回任务线程的稳定资源表示。"""

    model_config = ConfigDict(from_attributes=True)

    id: str
    workspace_id: str
    title: str
    status: str
    created_at: datetime


class TurnResponse(BaseModel):
    """返回 Turn 的当前持久化状态与终止原因。"""

    model_config = ConfigDict(from_attributes=True)

    id: str
    thread_id: str
    prompt: str
    status: str
    version: int
    next_sequence: int
    termination_reason: str | None
    created_at: datetime
    updated_at: datetime


class TurnEventResponse(BaseModel):
    """返回可通过游标重放的版本化公开事件。"""

    model_config = ConfigDict(from_attributes=True)

    id: str
    workspace_id: str
    thread_id: str
    turn_id: str
    sequence: int
    event_type: str
    schema_version: int
    payload: dict[str, Any]
    occurred_at: datetime
