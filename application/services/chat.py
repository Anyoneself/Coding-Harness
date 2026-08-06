"""面向 Controller 的 DeepSeek 对话应用服务。"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from ..agent import DeepSeekAgent
from ..config import DeepSeekSettings
from ..tools import ToolRegistry, build_tool_registry


class AgentChatService:
    """封装模型 Agent 生命周期和 Web 层需要的对话用例。"""

    def __init__(
        self,
        settings: DeepSeekSettings,
        *,
        agent: DeepSeekAgent | None = None,
        tool_registry: ToolRegistry | None = None,
    ) -> None:
        """根据配置装配工具注册表，并在密钥可用时创建模型 Agent。"""
        self.settings = settings
        self.tool_registry = tool_registry or build_tool_registry(settings)
        self.agent = agent
        if self.agent is None and settings.api_key:
            self.agent = DeepSeekAgent(settings, tools=self.tool_registry)

    @property
    def is_ready(self) -> bool:
        """返回外部模型是否已完成配置。"""
        return self.agent is not None

    def stream_chat(
        self,
        message: str,
        *,
        user: str,
        role: str,
        session_id: str,
        model: str | None,
    ) -> Iterator[dict[str, Any]]:
        """流式执行一次对话，并在未配置模型时返回结构化错误事件。"""
        if self.agent is None:
            yield {
                "type": "error",
                "message": "尚未配置 DEEPSEEK_API_KEY，请先设置环境变量并重启服务。",
            }
            return
        yield from self.agent.run(
            message,
            user=user,
            role=role,
            session_id=session_id,
            model=model,
        )

    def reset_session(self, session_id: str) -> None:
        """清理指定模型会话的历史上下文。"""
        if self.agent is not None:
            self.agent.clear_session(session_id)

    def get_public_config(self) -> dict[str, Any]:
        """返回允许公开给前端的运行配置。"""
        return {
            "ready": self.is_ready,
            "model": self.settings.model,
            "allowed_models": list(self.settings.allowed_models),
            "base_url": self.settings.base_url,
            "thinking_enabled": self.settings.thinking_enabled,
            "reasoning_effort": self.settings.reasoning_effort,
            "tools": self.tool_registry.names,
            "web_search_enabled": bool(self.settings.tavily_api_key),
            "workspace_tools_enabled": self.settings.workspace_tools_enabled,
        }
