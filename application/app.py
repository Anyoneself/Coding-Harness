"""My-Agent Web 应用的依赖装配入口。"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .config import DeepSeekSettings
from .controllers.http import create_api_router
from .services.chat import AgentChatService

STATIC_DIR = Path(__file__).with_name("static")
load_dotenv()


def create_app(
    settings: DeepSeekSettings | None = None,
    *,
    chat_service: AgentChatService | None = None,
) -> FastAPI:
    """装配配置、应用服务、API 路由和静态资源。"""
    runtime_settings = settings or DeepSeekSettings.from_env()
    runtime_chat_service = chat_service or AgentChatService(runtime_settings)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        """在应用退出时显式释放模型客户端和外部存储连接。"""
        try:
            yield
        finally:
            runtime_chat_service.close()

    application = FastAPI(title="My-Agent", version="1.0.0", lifespan=lifespan)
    application.state.settings = runtime_settings
    application.state.chat_service = runtime_chat_service
    application.include_router(create_api_router(runtime_chat_service))
    application.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @application.get("/", include_in_schema=False)
    def index() -> FileResponse:
        """返回 My-Agent Web 控制台首页。"""
        return FileResponse(STATIC_DIR / "index.html")

    @application.get("/favicon.ico", include_in_schema=False)
    def favicon() -> FileResponse:
        """返回站点图标，避免浏览器默认请求产生无意义的 404 日志。"""
        return FileResponse(STATIC_DIR / "favicon.svg", media_type="image/svg+xml")

    return application


app = create_app()
