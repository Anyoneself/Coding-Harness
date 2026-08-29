"""首次运行敏感配置的应用服务。"""

from __future__ import annotations

import os
import re
import tempfile
import threading
from dataclasses import replace
from pathlib import Path

from ..agent import DeepSeekAgent
from ..agent.provider import DeepSeekModelProvider, ModelProvider
from ..config import DeepSeekSettings
from .chat import AgentChatService
from .execution import HarnessRuntime

API_KEY_LINE = re.compile(r"^\s*(?:export\s+)?DEEPSEEK_API_KEY\s*=")


class ApiKeyAlreadyConfiguredError(RuntimeError):
    """当前进程已经启用 API Key，禁止通过首次配置入口覆盖。"""


class ApiKeyConfigurationService:
    """协调 API Key 校验、安全持久化和运行时模型激活。"""

    def __init__(
        self,
        settings: DeepSeekSettings,
        chat_service: AgentChatService,
        harness_runtime: HarnessRuntime,
        env_path: Path,
    ) -> None:
        """注入配置快照、两个运行时目标和本地环境文件路径。"""
        self._settings = settings
        self._chat_service = chat_service
        self._harness_runtime = harness_runtime
        self._env_path = env_path
        self._lock = threading.Lock()

    def configure_api_key(self, api_key: str) -> bool:
        """首次写入 API Key 并立即启用聊天与 Harness 模型能力。"""
        secret = self._validate_api_key(api_key)
        with self._lock:
            if self._chat_service.is_ready:
                raise ApiKeyAlreadyConfiguredError("DeepSeek API Key is already configured")

            configured_settings = replace(self._settings, api_key=secret)
            agent = DeepSeekAgent(
                configured_settings,
                tools=self._chat_service.tool_registry,
            )
            provider: ModelProvider | None = None
            try:
                provider = DeepSeekModelProvider(configured_settings)
                self._persist_api_key(secret)
                os.environ["DEEPSEEK_API_KEY"] = secret
                self._chat_service.activate_agent(configured_settings, agent)
                self._harness_runtime.activate_provider(provider)
            except Exception:
                if not self._chat_service.is_ready:
                    agent.close()
                if provider is not None and self._harness_runtime.provider is not provider:
                    provider.close()
                raise
            self._settings = configured_settings
            return self._chat_service.is_ready

    @staticmethod
    def _validate_api_key(api_key: str) -> str:
        """在应用服务边界再次验证密钥，防止非 HTTP 调用绕过 Schema。"""
        secret = api_key.strip()
        if not 16 <= len(secret) <= 256:
            raise ValueError("API Key length is invalid")
        if re.fullmatch(r"sk-[A-Za-z0-9._-]+", secret) is None:
            raise ValueError("API Key format is invalid")
        return secret

    def _persist_api_key(self, api_key: str) -> None:
        """原子更新环境文件中的唯一密钥行，并把权限限制为当前用户读写。"""
        self._env_path.parent.mkdir(parents=True, exist_ok=True)
        current = self._env_path.read_text(encoding="utf-8") if self._env_path.exists() else ""
        rendered = self._replace_api_key_line(current, api_key)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{self._env_path.name}.",
            dir=self._env_path.parent,
            text=True,
        )
        temporary_path = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as temporary_file:
                temporary_file.write(rendered)
                temporary_file.flush()
                os.fsync(temporary_file.fileno())
            os.chmod(temporary_path, 0o600)
            os.replace(temporary_path, self._env_path)
            os.chmod(self._env_path, 0o600)
        finally:
            if temporary_path.exists():
                temporary_path.unlink()

    @staticmethod
    def _replace_api_key_line(content: str, api_key: str) -> str:
        """保留无关环境配置，同时替换或追加唯一的 API Key 行。"""
        lines = content.splitlines(keepends=True)
        result: list[str] = []
        replaced = False
        for line in lines:
            if API_KEY_LINE.match(line):
                if not replaced:
                    result.append(f"DEEPSEEK_API_KEY={api_key}\n")
                    replaced = True
                continue
            result.append(line)
        if result and not result[-1].endswith(("\n", "\r")):
            result[-1] = f"{result[-1]}\n"
        if not replaced:
            result.append(f"DEEPSEEK_API_KEY={api_key}\n")
        return "".join(result)
