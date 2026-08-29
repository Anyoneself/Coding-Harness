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
    reasoning_effort: str = "high"
    thinking_enabled: bool = True
    max_rounds: int = 8
    max_output_tokens: int = 8192
    tavily_api_key: str = ""
    workspace_root: str = "."
    workspace_tools_enabled: bool = True
    max_tool_output_chars: int = 20000
    max_workspace_file_bytes: int = 1_000_000
    command_timeout_seconds: int = 30
    database_url: str = "sqlite:///:memory:"
    milvus_enabled: bool = False
    milvus_uri: str = "http://127.0.0.1:19530"
    milvus_token: str = ""
    milvus_collection: str = "my_agent_knowledge"
    embedding_dimension: int = 256

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
            reasoning_effort=os.environ.get("DEEPSEEK_REASONING_EFFORT", "high"),
            thinking_enabled=_env_flag("DEEPSEEK_THINKING", default=True),
            max_rounds=max(1, int(os.environ.get("AGENT_MAX_ROUNDS", "8"))),
            max_output_tokens=max(
                512,
                int(os.environ.get("AGENT_MAX_OUTPUT_TOKENS", "8192")),
            ),
            tavily_api_key=os.environ.get("TAVILY_API_KEY", "").strip(),
            workspace_root=str(workspace_root),
            workspace_tools_enabled=_env_flag(
                "AGENT_ENABLE_WORKSPACE_TOOLS",
                default=True,
            ),
            max_tool_output_chars=max(
                1000,
                int(os.environ.get("AGENT_MAX_TOOL_OUTPUT_CHARS", "20000")),
            ),
            max_workspace_file_bytes=max(
                1000,
                int(os.environ.get("AGENT_MAX_WORKSPACE_FILE_BYTES", "1000000")),
            ),
            command_timeout_seconds=max(
                1,
                int(os.environ.get("AGENT_COMMAND_TIMEOUT_SECONDS", "30")),
            ),
            database_url=os.environ.get(
                "DATABASE_URL",
                "postgresql://my_agent:my_agent@127.0.0.1:5433/my_agent",
            ).strip(),
            milvus_enabled=_env_flag("MILVUS_ENABLED", default=True),
            milvus_uri=os.environ.get("MILVUS_URI", "http://127.0.0.1:19530").strip(),
            milvus_token=os.environ.get("MILVUS_TOKEN", "").strip(),
            milvus_collection=os.environ.get(
                "MILVUS_COLLECTION",
                "my_agent_knowledge",
            ).strip(),
            embedding_dimension=max(
                32,
                int(os.environ.get("AGENT_EMBEDDING_DIMENSION", "256")),
            ),
        )


def _env_flag(name: str, *, default: bool) -> bool:
    """读取兼容常见真假文本的布尔环境变量。"""
    fallback = "true" if default else "false"
    return os.environ.get(name, fallback).lower() not in {
        "0",
        "false",
        "no",
        "off",
    }
