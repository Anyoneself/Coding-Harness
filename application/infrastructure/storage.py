"""根据运行配置装配会话与知识存储适配器。"""

from __future__ import annotations

from pathlib import Path

from ..config import DeepSeekSettings
from ..repositories.knowledge import DEFAULT_DOCUMENTS, KnowledgeRepository, VersionedKnowledgeBase
from ..repositories.milvus_knowledge import MilvusKnowledgeBase
from ..repositories.postgres_session import PostgresSessionStore
from ..repositories.session import SessionRepository, SessionStore


def build_session_repository(settings: DeepSeekSettings) -> SessionRepository:
    """按数据库 URL 装配 PostgreSQL 生产仓储或 SQLite 测试仓储。"""
    if settings.database_url.startswith(("postgresql://", "postgres://")):
        return PostgresSessionStore(settings.database_url)
    if settings.database_url == "sqlite:///:memory:":
        return SessionStore()
    if settings.database_url.startswith("sqlite:///"):
        database_path = Path(settings.database_url.removeprefix("sqlite:///"))
        return SessionStore(str(database_path))
    raise ValueError("DATABASE_URL 仅支持 postgresql:// 或 sqlite:/// 协议")


def build_knowledge_repository(settings: DeepSeekSettings) -> KnowledgeRepository:
    """按配置装配 Milvus 生产知识仓储或确定性本地测试仓储。"""
    if settings.milvus_enabled:
        return MilvusKnowledgeBase(
            uri=settings.milvus_uri,
            token=settings.milvus_token,
            collection_name=settings.milvus_collection,
            dimension=settings.embedding_dimension,
            documents=DEFAULT_DOCUMENTS,
        )
    return VersionedKnowledgeBase(DEFAULT_DOCUMENTS)
