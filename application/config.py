"""Environment-backed configuration for the DeepSeek agent."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


class DeepSeekConfigurationError(RuntimeError):
    """外部模型运行配置不完整。"""


@dataclass(frozen=True)
class DeepSeekSettings:
    api_key: str
    base_url: str = "https://api.deepseek.com"
    model: str = "deepseek-v4-flash"
    allowed_models: tuple[str, ...] = ("deepseek-v4-flash", "deepseek-v4-pro")
    max_output_tokens: int = 8192
    workspace_root: str = "."
    database_url: str = "sqlite:///:memory:"

    @classmethod
    def from_env(cls) -> DeepSeekSettings:
        """从环境变量读取并规范化 Coding-Harness 运行配置。"""
        workspace_root = Path(os.environ.get("AGENT_WORKSPACE", Path.cwd())).resolve()
        model = os.environ.get("DEEPSEEK_MODEL", "deepseek-v4-flash").strip()
        configured_models = os.environ.get(
            "DEEPSEEK_ALLOWED_MODELS",
            "deepseek-v4-flash,deepseek-v4-pro",
        )
        allowed_models = tuple(
            dict.fromkeys(item.strip() for item in configured_models.split(",") if item.strip())
        )
        if model not in allowed_models:
            allowed_models = (model, *allowed_models)

        return cls(
            api_key=(os.environ.get("DEEPSEEK_API_KEY") or os.environ.get("DS_API") or "").strip(),
            base_url=os.environ.get(
                "DEEPSEEK_BASE_URL",
                "https://api.deepseek.com",
            ).rstrip("/"),
            model=model,
            allowed_models=allowed_models,
            max_output_tokens=max(
                512,
                int(os.environ.get("AGENT_MAX_OUTPUT_TOKENS", "8192")),
            ),
            workspace_root=str(workspace_root),
            database_url=os.environ.get(
                "DATABASE_URL",
                "postgresql://my_agent:my_agent@127.0.0.1:5433/my_agent",
            ).strip(),
        )
