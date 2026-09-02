"""根据运行配置装配 Harness 执行存储。"""

from __future__ import annotations

from ..config import DeepSeekSettings
from ..repositories.execution import SqliteTurnExecutionStore, TurnExecutionStore
from ..repositories.postgres_turn_execution import PostgresTurnExecutionStore


def build_turn_execution_store(settings: DeepSeekSettings) -> TurnExecutionStore:
    """按数据库 URL 装配第一阶段 PostgreSQL 或 SQLite 执行仓储。"""
    if settings.database_url.startswith(("postgresql://", "postgres://")):
        return PostgresTurnExecutionStore(settings.database_url)
    if settings.database_url == "sqlite:///:memory:":
        return SqliteTurnExecutionStore()
    if settings.database_url.startswith("sqlite:///"):
        return SqliteTurnExecutionStore(settings.database_url.removeprefix("sqlite:///"))
    raise ValueError("DATABASE_URL 仅支持 postgresql:// 或 sqlite:/// 协议")
