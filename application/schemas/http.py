"""My-Agent HTTP 接口使用的请求与响应模型。"""

from __future__ import annotations

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    """描述一次需要流式处理的 Agent 对话请求。"""

    message: str = Field(min_length=1, max_length=20000)
    session_id: str = Field(min_length=1, max_length=128)
    user: str = Field(default="web-user", min_length=1, max_length=128)
    role: str = Field(default="standard", min_length=1, max_length=64)
    model: str | None = None


class ResetSessionRequest(BaseModel):
    """描述需要清理上下文的会话。"""

    session_id: str = Field(min_length=1, max_length=128)
