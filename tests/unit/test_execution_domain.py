"""第一阶段执行领域与 SQLite 仓储的行为测试。"""

from __future__ import annotations

import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path

from application.domain.execution import (
    InvalidTurnTransitionError,
    ItemStatus,
    ItemType,
    TurnStatus,
)
from application.repositories.execution import (
    ActiveTurnExistsError,
    SqliteTurnExecutionStore,
    TurnLeaseConflictError,
)


class ExecutionDomainTests(unittest.TestCase):
    """验证 Turn 状态规则和持久化执行契约。"""

    def setUp(self) -> None:
        """为每个测试创建隔离的 SQLite 执行仓储。"""
        self.store = SqliteTurnExecutionStore()
        self.workspace = self.store.create_workspace("/workspace", "workspace")
        self.thread = self.store.create_thread(self.workspace.id, "实现执行底座")

    def tearDown(self) -> None:
        """关闭测试仓储，避免泄漏 SQLite 连接。"""
        self.store.close()

    def test_completed_turn_rejects_transition_without_new_event(self) -> None:
        """验证完成后的非法迁移不会改变状态或追加事件。"""
        turn = self.store.create_turn(self.thread.id, "只读分析代码")
        claimed = self.store.claim_turn(
            turn.id,
            owner="worker-1",
            expires_at=datetime.now(UTC) + timedelta(minutes=1),
        )
        self.store.transition_turn(claimed.id, TurnStatus.COMPLETED, reason="done")
        before_events = self.store.list_events(turn.id, after_sequence=0)

        with self.assertRaises(InvalidTurnTransitionError):
            self.store.transition_turn(turn.id, TurnStatus.RUNNING, reason="invalid")

        persisted = self.store.get_turn(turn.id)
        after_events = self.store.list_events(turn.id, after_sequence=0)
        self.assertEqual(TurnStatus.COMPLETED, persisted.status)
        self.assertEqual(len(before_events), len(after_events))

    def test_only_one_active_turn_is_allowed_per_thread(self) -> None:
        """验证同一 Thread 的第二个活动 Turn 会被拒绝。"""
        first = self.store.create_turn(self.thread.id, "第一个任务")

        with self.assertRaises(ActiveTurnExistsError):
            self.store.create_turn(self.thread.id, "第二个任务")

        self.assertEqual(TurnStatus.QUEUED, self.store.get_turn(first.id).status)

    def test_claim_rejects_a_second_live_lease(self) -> None:
        """验证有效租约存在时另一个 Worker 不能领取 Turn。"""
        turn = self.store.create_turn(self.thread.id, "分析")
        expires_at = datetime.now(UTC) + timedelta(minutes=1)
        self.store.claim_turn(turn.id, owner="worker-1", expires_at=expires_at)

        with self.assertRaises(TurnLeaseConflictError):
            self.store.claim_turn(turn.id, owner="worker-2", expires_at=expires_at)

    def test_events_survive_store_recreation_and_resume_after_sequence(self) -> None:
        """验证关闭并重建仓储后可从指定序号继续重放事件。"""
        with tempfile.TemporaryDirectory() as directory:
            database = str(Path(directory) / "execution.sqlite")
            first_store = SqliteTurnExecutionStore(database)
            workspace = first_store.create_workspace("/workspace", "workspace")
            thread = first_store.create_thread(workspace.id, "持久化")
            turn = first_store.create_turn(thread.id, "分析")
            first_store.append_item_event(
                turn.id,
                item_type=ItemType.AGENT_MESSAGE,
                item_status=ItemStatus.IN_PROGRESS,
                payload={"delta": "第一段"},
            )
            first_store.close()

            second_store = SqliteTurnExecutionStore(database)
            try:
                events = second_store.list_events(turn.id, after_sequence=1)
                self.assertEqual([2], [event.sequence for event in events])
                self.assertEqual("第一段", events[0].payload["item"]["payload"]["delta"])
            finally:
                second_store.close()

    def test_expired_running_turn_is_recovered_as_interrupted(self) -> None:
        """验证启动恢复把租约过期的运行 Turn 转换为 interrupted。"""
        turn = self.store.create_turn(self.thread.id, "分析")
        claimed = self.store.claim_turn(
            turn.id,
            owner="dead-worker",
            expires_at=datetime.now(UTC) - timedelta(seconds=1),
        )

        recovered = self.store.recover_expired_turns(datetime.now(UTC))

        self.assertEqual([claimed.id], recovered)
        self.assertEqual(TurnStatus.INTERRUPTED, self.store.get_turn(claimed.id).status)

    def test_process_restart_interrupts_running_turn_even_with_live_lease(self) -> None:
        """验证单进程 Runtime 重启不会让旧 Worker 的有效租约永久卡住 Turn。"""
        turn = self.store.create_turn(self.thread.id, "分析")
        claimed = self.store.claim_turn(
            turn.id,
            owner="old-process-worker",
            expires_at=datetime.now(UTC) + timedelta(minutes=10),
        )

        recovered = self.store.recover_running_turns()

        self.assertEqual([claimed.id], recovered)
        persisted = self.store.get_turn(claimed.id)
        self.assertEqual(TurnStatus.INTERRUPTED, persisted.status)
        self.assertEqual("process_restarted", persisted.termination_reason)


if __name__ == "__main__":
    unittest.main()
