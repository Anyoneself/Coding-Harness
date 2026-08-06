"""PostgreSQL 与 Milvus 外部存储适配器的可选集成测试。"""

from __future__ import annotations

import os
import unittest
import uuid

from application.repositories.knowledge import DEFAULT_DOCUMENTS
from application.repositories.milvus_knowledge import MilvusKnowledgeBase
from application.repositories.postgres_session import PostgresSessionStore


@unittest.skipUnless(os.environ.get("POSTGRES_TEST_DSN"), "未配置 PostgreSQL 集成测试")
class PostgresSessionStoreTests(unittest.TestCase):
    """验证 PostgreSQL 会话和事件仓储的真实数据库行为。"""

    def test_session_and_events_survive_repository_recreation(self) -> None:
        """验证仓储实例重建后仍可读取会话版本、状态和审计事件。"""
        database_url = os.environ["POSTGRES_TEST_DSN"]
        session_id = f"test-{uuid.uuid4()}"
        request_id = f"request-{uuid.uuid4()}"
        first_store = PostgresSessionStore(database_url)
        self.assertEqual(1, first_store.save(session_id, 0, {"messages": []}))
        first_store.append_event(
            session_id=session_id,
            request_id=request_id,
            sequence=1,
            event={"type": "started", "request_id": request_id},
        )
        first_store.close()

        second_store = PostgresSessionStore(database_url)
        version, state = second_store.load(session_id)
        events = second_store.list_events(session_id)
        second_store.delete_session(session_id)
        second_store.close()

        self.assertEqual(1, version)
        self.assertEqual([], state["messages"])
        self.assertEqual("started", events[0].event_type)


@unittest.skipUnless(os.environ.get("MILVUS_TEST_URI"), "未配置 Milvus 集成测试")
class MilvusKnowledgeBaseTests(unittest.TestCase):
    """验证 Milvus 知识仓储的真实向量写入与检索行为。"""

    def test_default_documents_are_indexed_and_searchable(self) -> None:
        """验证默认知识文档写入独立集合后可以返回带来源的检索结果。"""
        collection_name = f"test_knowledge_{uuid.uuid4().hex}"
        knowledge = MilvusKnowledgeBase(
            uri=os.environ["MILVUS_TEST_URI"],
            collection_name=collection_name,
            documents=DEFAULT_DOCUMENTS,
        )
        try:
            hits, diagnostics = knowledge.search("可信来源核验", top_k=3)
        finally:
            knowledge.drop_collection()

        self.assertGreaterEqual(diagnostics.total_documents, 1)
        self.assertTrue(hits)
        self.assertTrue(hits[0].source)


if __name__ == "__main__":
    unittest.main()
