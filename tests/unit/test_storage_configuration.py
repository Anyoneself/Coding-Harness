"""Harness 执行存储配置测试。"""

from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from application.config import DeepSeekSettings
from application.infrastructure.storage import build_turn_execution_store
from application.repositories.execution import SqliteTurnExecutionStore
from application.repositories.postgres_turn_execution import PostgresTurnExecutionStore


class StorageConfigurationTests(unittest.TestCase):
    """验证新链只装配 TurnExecutionStore。"""

    def test_environment_defaults_to_postgres(self) -> None:
        """验证生产默认配置指向 PostgreSQL 执行存储。"""
        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": ""}, clear=True):
            settings = DeepSeekSettings.from_env()
        self.assertTrue(settings.database_url.startswith("postgresql://"))

    def test_execution_store_follows_database_url_without_eager_connection(self) -> None:
        """验证 SQLite 与 PostgreSQL 实现按 URL 选择且 PostgreSQL 懒连接。"""
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


if __name__ == "__main__":
    unittest.main()
