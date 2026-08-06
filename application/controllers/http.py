"""My-Agent 的 HTTP 与 SSE 接入层。"""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from openai import APIConnectionError, AuthenticationError, RateLimitError

from ..config import DeepSeekConfigurationError
from ..schemas.http import ChatRequest, ResetSessionRequest
from ..services.chat import AgentChatService


def encode_sse(event: dict[str, Any]) -> str:
    """把结构化 Agent 事件编码为标准 SSE 文本。"""
    event_name = str(event.get("type") or "message")
    payload = json.dumps(event, ensure_ascii=False)
    return f"event: {event_name}\ndata: {payload}\n\n"


def friendly_error(exc: Exception) -> str:
    """将外部依赖异常转换为不泄漏内部信息的用户提示。"""
    if isinstance(exc, AuthenticationError):
        return "DeepSeek API Key 无效或没有访问当前模型的权限。"
    if isinstance(exc, RateLimitError):
        return "DeepSeek API 当前触发了限流，请稍后重试。"
    if isinstance(exc, APIConnectionError):
        return "无法连接 DeepSeek API，请检查网络或 DEEPSEEK_BASE_URL。"
    if isinstance(exc, DeepSeekConfigurationError):
        return "尚未配置 DEEPSEEK_API_KEY。"
    return f"Agent 运行失败：{type(exc).__name__}: {str(exc)[:300]}"


def create_api_router(chat_service: AgentChatService) -> APIRouter:
    """创建仅负责协议转换的 API 路由集合。"""
    router = APIRouter(prefix="/api")

    @router.get("/config")
    def get_config() -> dict[str, Any]:
        """返回前端可以读取的 Agent 配置。"""
        return chat_service.get_public_config()

    @router.post("/chat")
    def chat(payload: ChatRequest) -> StreamingResponse:
        """接收对话请求并以 SSE 形式返回执行事件。"""

        def generate_events() -> Iterator[str]:
            """迭代应用服务事件，并统一转换未处理异常。"""
            try:
                for event in chat_service.stream_chat(
                    payload.message,
                    user=payload.user,
                    role=payload.role,
                    session_id=payload.session_id,
                    model=payload.model,
                ):
                    yield encode_sse(event)
            except Exception as exc:
                yield encode_sse({"type": "error", "message": friendly_error(exc)})

        return StreamingResponse(
            generate_events(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @router.post("/session/reset")
    def reset_session(payload: ResetSessionRequest) -> dict[str, bool]:
        """清理指定会话并返回稳定的成功响应。"""
        chat_service.reset_session(payload.session_id)
        return {"ok": True}

    @router.get("/health")
    def health() -> dict[str, bool]:
        """返回进程健康状态和模型配置状态。"""
        return {"ok": True, "model_ready": chat_service.is_ready}

    return router
