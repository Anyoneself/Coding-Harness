"""面向 Controller 的 DeepSeek 对话应用服务。"""

from __future__ import annotations

import threading
import uuid
from collections.abc import Iterator
from typing import Any

from ..agent import DeepSeekAgent
from ..config import DeepSeekSettings
from ..domain.models import SessionEvent
from ..infrastructure.storage import build_knowledge_repository, build_session_repository
from ..repositories import ConcurrentUpdateError, SessionRepository
from ..tools import ToolRegistry, build_tool_registry


class AgentChatService:
    """封装模型 Agent 生命周期和 Web 层需要的对话用例。"""

    def __init__(
        self,
        settings: DeepSeekSettings,
        *,
        agent: DeepSeekAgent | None = None,
        tool_registry: ToolRegistry | None = None,
        session_store: SessionRepository | None = None,
    ) -> None:
        """装配模型、工具和持久化会话仓储，并初始化会话级执行锁。"""
        self.settings = settings
        self._knowledge_base = None
        if tool_registry is None:
            self._knowledge_base = build_knowledge_repository(settings)
            tool_registry = build_tool_registry(
                settings,
                knowledge_base=self._knowledge_base,
            )
        self.tool_registry = tool_registry
        self.session_store = session_store or build_session_repository(settings)
        self.agent = agent
        if self.agent is None and settings.api_key:
            self.agent = DeepSeekAgent(settings, tools=self.tool_registry)
        self._session_locks: dict[str, threading.RLock] = {}
        self._lock = threading.RLock()

    def close(self) -> None:
        """幂等关闭模型客户端、会话仓储和知识仓储持有的外部资源。"""
        with self._lock:
            self._close_resource(self.agent)
            self._close_resource(self.session_store)
            self._close_resource(self._knowledge_base)

    @staticmethod
    def _close_resource(resource: object | None) -> None:
        """仅在资源声明关闭能力时调用其关闭方法。"""
        close = getattr(resource, "close", None)
        if callable(close):
            close()

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
        thinking_enabled: bool | None = None,
        reasoning_effort: str | None = None,
    ) -> Iterator[dict[str, Any]]:
        """读取持久化历史并执行对话，同时保存全部结构化事件。"""
        request_id = str(uuid.uuid4())
        if self.agent is None:
            event = {
                "type": "error",
                "request_id": request_id,
                "message": "尚未配置 DEEPSEEK_API_KEY，请先设置环境变量并重启服务。",
            }
            self.session_store.append_event(
                session_id=session_id,
                request_id=request_id,
                sequence=1,
                event=event,
            )
            yield event
            return

        with self._get_session_lock(session_id):
            version, state = self.session_store.load(session_id)
            history = self._load_history(state)
            events = self.agent.run(
                message,
                user=user,
                role=role,
                session_id=session_id,
                model=model,
                thinking_enabled=thinking_enabled,
                reasoning_effort=reasoning_effort,
                history=history,
                request_id=request_id,
            )
            for sequence, raw_event in enumerate(events, start=1):
                event = {"request_id": request_id, **raw_event}
                if event.get("type") == "final":
                    answer = str(event.get("answer") or "")
                    version = self._save_completed_turn(
                        session_id=session_id,
                        expected_version=version,
                        history=history,
                        user_message=message,
                        answer=answer,
                    )
                    history = self._compact_history(
                        [
                            *history,
                            {"role": "user", "content": message.strip()},
                            {"role": "assistant", "content": answer},
                        ]
                    )
                self.session_store.append_event(
                    session_id=session_id,
                    request_id=request_id,
                    sequence=sequence,
                    event=self._event_for_audit(event),
                )
                yield event

    def reset_session(self, session_id: str) -> None:
        """清理指定会话上下文，并保留既有事件作为审计记录。"""
        with self._get_session_lock(session_id):
            self.session_store.clear_session_context(session_id)
            request_id = str(uuid.uuid4())
            self.session_store.append_event(
                session_id=session_id,
                request_id=request_id,
                sequence=1,
                event={"type": "session_reset", "request_id": request_id},
            )

    def delete_session(self, session_id: str) -> None:
        """永久删除指定会话的模型上下文和全部审计事件。"""
        with self._get_session_lock(session_id):
            self.session_store.delete_session(session_id)

    def get_session_events(
        self,
        session_id: str,
        *,
        request_id: str | None = None,
    ) -> list[SessionEvent]:
        """返回指定会话或请求的持久化事件，供 CLI 和审计入口复用。"""
        return self.session_store.list_events(session_id, request_id=request_id)

    def get_public_config(self) -> dict[str, Any]:
        """返回允许公开给前端的运行配置。"""
        return {
            "ready": self.is_ready,
            "model": self.settings.model,
            "allowed_models": list(self.settings.allowed_models),
            "base_url": self.settings.base_url,
            "thinking_enabled": self.settings.thinking_enabled,
            "reasoning_effort": self.settings.reasoning_effort,
            "reasoning_efforts": ["low", "high", "max"],
            "tools": self.tool_registry.names,
            "web_search_enabled": bool(self.settings.tavily_api_key),
            "workspace_tools_enabled": self.settings.workspace_tools_enabled,
        }

    def _save_completed_turn(
        self,
        *,
        session_id: str,
        expected_version: int,
        history: list[dict[str, Any]],
        user_message: str,
        answer: str,
    ) -> int:
        """保存完成的用户与助手消息，并在跨实例并发冲突时合并最新历史。"""
        current_version = expected_version
        current_history = history
        for attempt in range(2):
            messages = self._compact_history(
                [
                    *current_history,
                    {"role": "user", "content": user_message.strip()},
                    {"role": "assistant", "content": answer},
                ]
            )
            try:
                return self.session_store.save(
                    session_id,
                    current_version,
                    {"messages": messages},
                )
            except ConcurrentUpdateError:
                if attempt == 1:
                    raise
                current_version, state = self.session_store.load(session_id)
                current_history = self._load_history(state)
        raise ConcurrentUpdateError(f"session {session_id} could not be updated")

    @staticmethod
    def _load_history(state: dict[str, Any]) -> list[dict[str, Any]]:
        """从持久化状态中读取格式有效的用户与助手消息。"""
        messages = state.get("messages")
        if not isinstance(messages, list):
            return []
        return [
            {"role": str(item["role"]), "content": str(item["content"])}
            for item in messages
            if isinstance(item, dict)
            and item.get("role") in {"user", "assistant"}
            and isinstance(item.get("content"), str)
        ]

    @staticmethod
    def _compact_history(history: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """仅保留最近二十条消息，限制模型上下文和数据库状态增长。"""
        return history[-20:]

    @staticmethod
    def _event_for_audit(event: dict[str, Any]) -> dict[str, Any]:
        """移除思考原文后生成可持久化的审计事件。"""
        if event.get("type") != "thinking_delta":
            return event
        return {
            key: value
            for key, value in event.items()
            if key != "delta"
        } | {"content_redacted": True}

    def _get_session_lock(self, session_id: str) -> threading.RLock:
        """获取或创建指定会话的进程内串行执行锁。"""
        with self._lock:
            return self._session_locks.setdefault(session_id, threading.RLock())
