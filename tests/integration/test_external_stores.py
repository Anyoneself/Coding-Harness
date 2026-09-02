"""PostgreSQL Harness 执行存储的可选集成测试。"""

from __future__ import annotations

import os
import unittest
import uuid

from application.repositories.postgres_turn_execution import PostgresTurnExecutionStore


@unittest.skipUnless(os.environ.get("POSTGRES_TEST_DSN"), "未配置 PostgreSQL 集成测试")
class PostgresTurnExecutionStoreTests(unittest.TestCase):
    """验证 PostgreSQL 新执行 Schema 的持久化行为。"""

    def test_turn_state_and_events_survive_repository_recreation(self) -> None:
        """验证仓储重建后仍能读取 Turn 与版本化事件。"""
        database_url = os.environ["POSTGRES_TEST_DSN"]
        first_store = PostgresTurnExecutionStore(database_url)
        workspace = first_store.create_workspace("/tmp", "read_only")
        thread = first_store.create_thread(workspace.id, f"postgres-{uuid.uuid4()}")
        turn = first_store.create_turn(thread.id, "验证 PostgreSQL Store")
        first_store.close()

        second_store = PostgresTurnExecutionStore(database_url)
        try:
            persisted = second_store.get_turn(turn.id)
            events = second_store.list_events(turn.id, after_sequence=0)
            self.assertEqual("queued", persisted.status.value)
            self.assertEqual([1], [event.sequence for event in events])
        finally:
            second_store.close()


if __name__ == "__main__":
    unittest.main()
