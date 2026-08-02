"""FastAPI web application for the DeepSeek tool-using agent."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from openai import APIConnectionError, AuthenticationError, RateLimitError
from pydantic import BaseModel, Field

from .agent import DeepSeekAgent
from .config import DeepSeekConfigurationError, DeepSeekSettings
from .tools import build_tool_registry

STATIC_DIR = Path(__file__).with_name("static")
load_dotenv()


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=20000)
    session_id: str = Field(min_length=1, max_length=128)
    user: str = Field(default="web-user", min_length=1, max_length=128)
    role: str = Field(default="operations", pattern="^(investment|ir|operations)$")
    model: str | None = None


class ResetRequest(BaseModel):
    session_id: str = Field(min_length=1, max_length=128)


def _sse(event: dict[str, Any]) -> str:
    event_name = str(event.get("type") or "message")
    payload = json.dumps(event, ensure_ascii=False)
    return f"event: {event_name}\ndata: {payload}\n\n"


def _friendly_error(exc: Exception) -> str:
    if isinstance(exc, AuthenticationError):
        return "DeepSeek API Key 无效或没有访问当前模型的权限。"
    if isinstance(exc, RateLimitError):
        return "DeepSeek API 当前触发了限流，请稍后重试。"
    if isinstance(exc, APIConnectionError):
        return "无法连接 DeepSeek API，请检查网络或 DEEPSEEK_BASE_URL。"
    if isinstance(exc, DeepSeekConfigurationError):
        return "尚未配置 DEEPSEEK_API_KEY。"
    return f"Agent 运行失败：{type(exc).__name__}: {str(exc)[:300]}"


def create_app(settings: DeepSeekSettings | None = None) -> FastAPI:
    settings = settings or DeepSeekSettings.from_env()
    app = FastAPI(title="DeepSeek Agent Console", version="1.0.0")
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    app.state.settings = settings
    app.state.agent = DeepSeekAgent(settings) if settings.api_key else None
    app.state.tool_registry = build_tool_registry(settings)

    @app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    @app.get("/api/config")
    def config() -> dict[str, Any]:
        return {
            "ready": app.state.agent is not None,
            "model": settings.model,
            "allowed_models": list(settings.allowed_models),
            "base_url": settings.base_url,
            "thinking_enabled": settings.thinking_enabled,
            "reasoning_effort": settings.reasoning_effort,
            "tools": app.state.tool_registry.names,
            "web_search_enabled": bool(settings.tavily_api_key),
            "workspace_tools_enabled": settings.workspace_tools_enabled,
        }

    @app.post("/api/chat")
    def chat(payload: ChatRequest) -> StreamingResponse:
        def events() -> Iterator[str]:
            agent: DeepSeekAgent | None = app.state.agent
            if agent is None:
                yield _sse(
                    {
                        "type": "error",
                        "message": "尚未配置 DEEPSEEK_API_KEY，请先设置环境变量并重启服务。",
                    }
                )
                return
            try:
                for event in agent.run(
                    payload.message,
                    user=payload.user,
                    role=payload.role,
                    session_id=payload.session_id,
                    model=payload.model,
                ):
                    yield _sse(event)
            except Exception as exc:
                yield _sse({"type": "error", "message": _friendly_error(exc)})

        return StreamingResponse(
            events(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
            },
        )

    @app.post("/api/session/reset")
    def reset(payload: ResetRequest) -> dict[str, bool]:
        agent: DeepSeekAgent | None = app.state.agent
        if agent is not None:
            agent.clear_session(payload.session_id)
        return {"ok": True}

    @app.get("/api/health")
    def health() -> dict[str, Any]:
        if not STATIC_DIR.exists():
            raise HTTPException(status_code=500, detail="static assets are missing")
        return {"ok": True, "model_ready": app.state.agent is not None}

    return app


app = create_app()


def main() -> None:
    import uvicorn

    uvicorn.run(
        "production_agent.web:app",
        host="127.0.0.1",
        port=8000,
        reload=False,
    )


if __name__ == "__main__":
    main()
