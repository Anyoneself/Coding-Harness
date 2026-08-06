"""My-Agent Web 应用的依赖装配入口。"""

from __future__ import annotations

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


def create_app(settings: DeepSeekSettings | None = None) -> FastAPI:
    """装配配置、应用服务、API 路由和静态资源。"""
    runtime_settings = settings or DeepSeekSettings.from_env()
    chat_service = AgentChatService(runtime_settings)
    application = FastAPI(title="My-Agent", version="1.0.0")
    application.state.settings = runtime_settings
    application.state.chat_service = chat_service
    application.include_router(create_api_router(chat_service))
    application.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @application.get("/", include_in_schema=False)
    def index() -> FileResponse:
        """返回 My-Agent Web 控制台首页。"""
        return FileResponse(STATIC_DIR / "index.html")

    return application


app = create_app()
