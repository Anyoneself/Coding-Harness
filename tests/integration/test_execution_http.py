"""第一阶段 Harness HTTP 资源契约的集成测试。"""

from __future__ import annotations

import tempfile
import time
import unittest
from collections.abc import Iterator

from fastapi.testclient import TestClient

from application.agent.provider import ModelCompleted, ModelDelta, ModelRequest
from application.app import create_app
from application.config import DeepSeekSettings
from application.repositories.execution import SqliteTurnExecutionStore
from application.services.execution import HarnessRuntime


class HttpFakeProvider:
    """为 HTTP 集成测试提供确定性的公开模型事件。"""

    def stream(self, request: ModelRequest) -> Iterator[ModelDelta | ModelCompleted]:
        """根据请求返回一个增量和最终回答。"""
        yield ModelDelta(f"正在处理：{request.prompt}")
        yield ModelCompleted("HTTP Turn 已完成")

    def close(self) -> None:
        """保持与真实 Provider 相同的关闭契约。"""


class ExecutionHttpTests(unittest.TestCase):
    """验证 Controller 只通过执行 Service 暴露稳定资源契约。"""

    def test_create_turn_returns_202_and_events_can_be_replayed(self) -> None:
        """验证创建资源、后台执行和按序重放组成完整 HTTP 闭环。"""
        with tempfile.TemporaryDirectory() as directory:
            runtime = HarnessRuntime(
                SqliteTurnExecutionStore(),
                HttpFakeProvider(),
            )
            application = create_app(
                DeepSeekSettings(
                    api_key="",
                    database_url="sqlite:///:memory:",
                    milvus_enabled=False,
                ),
                harness_runtime=runtime,
            )
            with TestClient(application) as client:
                workspace_response = client.post(
                    "/api/workspaces",
                    json={"root_path": directory, "permission_profile": "read_only"},
                )
                self.assertEqual(201, workspace_response.status_code)
                workspace_id = workspace_response.json()["id"]

                thread_response = client.post(
                    f"/api/workspaces/{workspace_id}/threads",
                    json={"title": "HTTP 后台任务"},
                )
                self.assertEqual(201, thread_response.status_code)
                thread_id = thread_response.json()["id"]

                turn_response = client.post(
                    f"/api/threads/{thread_id}/turns",
                    json={"prompt": "检查项目架构"},
                )
                self.assertEqual(202, turn_response.status_code)
                turn_id = turn_response.json()["id"]

                turn = self._wait_for_completion(client, turn_id)
                events_response = client.get(
                    f"/api/turns/{turn_id}/events",
                    params={"after_sequence": 1},
                )
                self.assertEqual(200, events_response.status_code)
                sequences = [event["sequence"] for event in events_response.json()]
                self.assertEqual(sorted(sequences), sequences)
                self.assertTrue(all(sequence > 1 for sequence in sequences))
                self.assertEqual("completed", turn["status"])

                legacy_health = client.get("/api/health")
                self.assertEqual(200, legacy_health.status_code)

    def test_invalid_turn_cursor_is_rejected_by_schema(self) -> None:
        """验证负数事件游标在进入 Service 前被 HTTP Schema 拒绝。"""
        runtime = HarnessRuntime(SqliteTurnExecutionStore(), HttpFakeProvider())
        application = create_app(
            DeepSeekSettings(api_key="", database_url="sqlite:///:memory:"),
            harness_runtime=runtime,
        )
        with TestClient(application) as client:
            response = client.get("/api/turns/missing/events?after_sequence=-1")
            self.assertEqual(422, response.status_code)

    def _wait_for_completion(self, client: TestClient, turn_id: str) -> dict[str, object]:
        """轮询资源接口直到后台 Turn 完成或测试超时。"""
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            response = client.get(f"/api/turns/{turn_id}")
            self.assertEqual(200, response.status_code)
            turn = response.json()
            if turn["status"] == "completed":
                return turn
            time.sleep(0.01)
        self.fail(f"Turn {turn_id} did not complete")


if __name__ == "__main__":
    unittest.main()
