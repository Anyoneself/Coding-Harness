"""运行时存储配置和装配行为测试。"""

from __future__ import annotations

import os
import unittest
from unittest.mock import Mock, patch

from application.config import DeepSeekSettings
from application.infrastructure.storage import (
    build_knowledge_repository,
    build_session_repository,
    build_turn_execution_store,
)
from application.repositories import SessionStore
from application.repositories.execution import SqliteTurnExecutionStore
from application.repositories.knowledge import DEFAULT_DOCUMENTS
from application.repositories.milvus_knowledge import MilvusKnowledgeBase
from application.repositories.postgres_session import PostgresSessionStore
from application.repositories.postgres_turn_execution import PostgresTurnExecutionStore


class StorageConfigurationTests(unittest.TestCase):
    """验证生产配置选择 PostgreSQL 和 Milvus，测试配置仍可使用内存适配器。"""

    def test_environment_defaults_to_postgres_and_milvus(self) -> None:
        """验证环境配置默认指向 Docker 暴露的 PostgreSQL 与 Milvus 服务。"""
        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": ""}, clear=True):
            settings = DeepSeekSettings.from_env()

        self.assertTrue(settings.database_url.startswith("postgresql://"))
        self.assertEqual("http://127.0.0.1:19530", settings.milvus_uri)
        self.assertTrue(settings.milvus_enabled)

    def test_in_memory_settings_keep_external_services_out_of_unit_tests(self) -> None:
        """验证显式测试配置装配 SQLite 和本地知识库，不连接外部服务。"""
        settings = DeepSeekSettings(api_key="", database_url="sqlite:///:memory:")

        sessions = build_session_repository(settings)
        knowledge = build_knowledge_repository(settings)

        self.assertIsInstance(sessions, SessionStore)
        self.assertNotIsInstance(sessions, PostgresSessionStore)
        self.assertNotIsInstance(knowledge, MilvusKnowledgeBase)

    def test_production_settings_build_lazy_external_adapters(self) -> None:
        """验证生产配置装配外部适配器时不会在应用启动阶段立即联网。"""
        settings = DeepSeekSettings(
            api_key="",
            database_url="postgresql://agent:agent@127.0.0.1:5433/my_agent",
            milvus_enabled=True,
        )

        sessions = build_session_repository(settings)
        knowledge = build_knowledge_repository(settings)

        self.assertIsInstance(sessions, PostgresSessionStore)
        self.assertIsInstance(knowledge, MilvusKnowledgeBase)

    def test_execution_store_follows_database_url_without_connecting_eagerly(self) -> None:
        """验证执行控制面按数据库 URL 选择 SQLite 或懒连接 PostgreSQL。"""
        sqlite_store = build_turn_execution_store(
            DeepSeekSettings(api_key="", database_url="sqlite:///:memory:")
        )
        postgres_store = build_turn_execution_store(
            DeepSeekSettings(
                api_key="",
                database_url="postgresql://agent:agent@127.0.0.1:5433/my_agent",
            )
        )
        try:
            self.assertIsInstance(sqlite_store, SqliteTurnExecutionStore)
            self.assertIsInstance(postgres_store, PostgresTurnExecutionStore)
            self.assertIsNone(postgres_store._pool)
        finally:
            sqlite_store.close()
            postgres_store.close()

    def test_milvus_adapter_indexes_and_returns_safe_document_data(self) -> None:
        """验证 Milvus 适配器写入默认文档并转换向量检索结果。"""
        client = Mock()
        client.has_collection.return_value = False
        client.query.return_value = []
        client.get_collection_stats.return_value = {"row_count": 2}
        client.search.return_value = [
            [
                {
                    "id": "doc-1",
                    "distance": 0.91,
                    "entity": {
                        "document_id": "doc-1",
                        "source_type": "guide",
                        "domain": "通用资料",
                        "title": "可信来源",
                        "content": "保留来源链接",
                        "source": "guide.md",
                        "knowledge_version": 1,
                    },
                }
            ]
        ]
        knowledge = MilvusKnowledgeBase(
            uri="http://milvus:19530",
            collection_name="test_knowledge",
            documents=DEFAULT_DOCUMENTS,
            client=client,
        )

        hits, diagnostics = knowledge.search("来源", top_k=1)

        client.create_collection.assert_called_once()
        client.upsert.assert_called_once()
        self.assertEqual("可信来源", hits[0].title)
        self.assertEqual(2, diagnostics.total_documents)


if __name__ == "__main__":
    unittest.main()
