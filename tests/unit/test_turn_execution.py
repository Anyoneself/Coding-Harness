"""第一阶段后台 Turn 执行闭环的行为测试。"""

from __future__ import annotations

import threading
import time
import unittest
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

from application.agent.provider import ModelCompleted, ModelDelta, ModelRequest
from application.domain.execution import ExecutionBudget, TurnStatus
from application.infrastructure.sandbox import CommandExecutionDeniedError, DenyCommandSandbox
from application.repositories.execution import SqliteTurnExecutionStore
from application.services.execution import (
    EventCoalescer,
    InProcessTurnScheduler,
    LocalConditionNotifier,
    ThreadService,
    TurnCommandService,
    TurnExecutionService,
    TurnQueryService,
)


class FakeModelProvider:
    """以确定性事件模拟一个不访问网络的模型供应商。"""

    def __init__(self, events: list[ModelDelta | ModelCompleted]) -> None:
        """保存每次调用需要返回的公开模型事件。"""
        self.events = events
        self.requests: list[ModelRequest] = []

    def stream(self, request: ModelRequest) -> Iterator[ModelDelta | ModelCompleted]:
        """记录请求并按顺序返回预设事件。"""
        self.requests.append(request)
        yield from self.events

    def close(self) -> None:
        """保持与真实 Provider 一致的资源关闭接口。"""


class BlockingModelProvider:
    """在首个分片后等待测试释放，用于验证主动中断。"""

    def __init__(self) -> None:
        """初始化用于协调测试线程的同步事件。"""
        self.started = threading.Event()
        self.release = threading.Event()

    def stream(self, request: ModelRequest) -> Iterator[ModelDelta | ModelCompleted]:
        """返回首个分片并等待中断请求已经写入。"""
        del request
        self.started.set()
        yield ModelDelta("处理中")
        self.release.wait(timeout=2)
        yield ModelCompleted("不应成为最终回答")

    def close(self) -> None:
        """释放可能仍在等待的测试线程。"""
        self.release.set()


class TurnExecutionTests(unittest.TestCase):
    """验证 Scheduler、Provider、Service 和 Store 的完整协作。"""

    def setUp(self) -> None:
        """为每个测试创建独立执行域与通知器。"""
        self.store = SqliteTurnExecutionStore()
        self.notifier = LocalConditionNotifier()
        self.thread_service = ThreadService(self.store)
        workspace = self.thread_service.create_workspace("/workspace", "workspace")
        self.thread = self.thread_service.create_thread(workspace.id, "后台执行")

    def tearDown(self) -> None:
        """关闭测试使用的仓储。"""
        self.store.close()

    def test_background_turn_completes_without_event_subscriber(self) -> None:
        """验证没有 SSE 订阅者时后台 Turn 仍能完成并支持事件重放。"""
        provider = FakeModelProvider([ModelDelta("完成"), ModelCompleted("完成分析")])
        execution = TurnExecutionService(self.store, provider, self.notifier)
        scheduler = InProcessTurnScheduler(execution.execute, max_workers=1)
        commands = TurnCommandService(self.store, scheduler)
        queries = TurnQueryService(self.store)
        try:
            turn = commands.create_turn(self.thread.id, "分析当前架构")
            completed = self._wait_for_status(queries, turn.id, TurnStatus.COMPLETED)
            replayed = queries.list_events(turn.id, after_sequence=1)

            self.assertEqual(TurnStatus.COMPLETED, completed.status)
            self.assertTrue(replayed)
            self.assertEqual("分析当前架构", provider.requests[0].prompt)
            self.assertEqual("turn.completed", replayed[-1].event_type)
        finally:
            scheduler.close()

    def test_interrupt_request_stops_turn_at_model_event_boundary(self) -> None:
        """验证显式中断请求使 Turn 在模型分片边界进入 interrupted。"""
        provider = BlockingModelProvider()
        execution = TurnExecutionService(self.store, provider, self.notifier)
        scheduler = InProcessTurnScheduler(execution.execute, max_workers=1)
        commands = TurnCommandService(self.store, scheduler)
        queries = TurnQueryService(self.store)
        try:
            turn = commands.create_turn(self.thread.id, "持续分析")
            self.assertTrue(provider.started.wait(timeout=2))
            commands.interrupt_turn(turn.id)
            provider.release.set()
            interrupted = self._wait_for_status(queries, turn.id, TurnStatus.INTERRUPTED)
            self.assertEqual(TurnStatus.INTERRUPTED, interrupted.status)
        finally:
            scheduler.close()
            provider.close()

    def test_model_call_budget_exhaustion_produces_failed_turn(self) -> None:
        """验证模型调用预算为零时 Turn 失败且不调用 Provider。"""
        provider = FakeModelProvider([ModelCompleted("不应执行")])
        execution = TurnExecutionService(self.store, provider, self.notifier)
        scheduler = InProcessTurnScheduler(execution.execute, max_workers=1)
        commands = TurnCommandService(self.store, scheduler)
        queries = TurnQueryService(self.store)
        try:
            turn = commands.create_turn(
                self.thread.id,
                "预算测试",
                budget=ExecutionBudget(max_model_calls=0),
            )
            failed = self._wait_for_status(queries, turn.id, TurnStatus.FAILED)
            self.assertEqual([], provider.requests)
            self.assertEqual("model_calls", failed.termination_reason)
        finally:
            scheduler.close()

    def test_token_budget_uses_public_provider_usage(self) -> None:
        """验证公开 Token 用量超限时 Turn 失败且不保存成功终态。"""
        provider = FakeModelProvider(
            [ModelCompleted("回答", usage={"total_tokens": 101})]
        )
        execution = TurnExecutionService(self.store, provider, self.notifier)
        scheduler = InProcessTurnScheduler(execution.execute, max_workers=1)
        commands = TurnCommandService(self.store, scheduler)
        queries = TurnQueryService(self.store)
        try:
            turn = commands.create_turn(
                self.thread.id,
                "Token 预算",
                budget=ExecutionBudget(max_tokens=100),
            )
            failed = self._wait_for_status(queries, turn.id, TurnStatus.FAILED)
            self.assertEqual("tokens", failed.termination_reason)
        finally:
            scheduler.close()

    def test_checkpoint_rejects_hidden_reasoning(self) -> None:
        """验证隐藏推理字段不能进入稳定恢复点。"""
        turn = self.store.create_turn(self.thread.id, "检查持久化边界")

        with self.assertRaises(ValueError):
            self.store.save_checkpoint(
                turn.id,
                phase="before_model",
                public_state={"reasoning_content": "不可持久化"},
                model_calls=0,
                tool_calls=0,
            )

    def test_resume_rebuilds_public_history_from_latest_checkpoint(self) -> None:
        """验证主动恢复从最近稳定点重建公开上下文且清除旧中断标记。"""
        turn = self.store.create_turn(self.thread.id, "继续分析")
        claimed = self.store.claim_turn(
            turn.id,
            owner="crashed-worker",
            expires_at=datetime.now(UTC) + timedelta(minutes=1),
        )
        self.store.save_checkpoint(
            claimed.id,
            phase="after_model",
            public_state={
                "messages": [{"role": "assistant", "content": "已完成第一步"}]
            },
            model_calls=1,
            tool_calls=0,
        )
        self.store.request_interrupt(claimed.id)
        self.store.transition_turn(
            claimed.id,
            TurnStatus.INTERRUPTED,
            reason="worker_crashed",
        )
        provider = FakeModelProvider([ModelCompleted("恢复完成")])
        execution = TurnExecutionService(self.store, provider, self.notifier)
        scheduler = InProcessTurnScheduler(execution.execute, max_workers=1)
        commands = TurnCommandService(self.store, scheduler)
        queries = TurnQueryService(self.store)
        try:
            commands.resume_turn(claimed.id)
            completed = self._wait_for_status(queries, claimed.id, TurnStatus.COMPLETED)
            self.assertEqual(
                ({"role": "assistant", "content": "已完成第一步"},),
                provider.requests[0].history,
            )
            self.assertIsNone(completed.interrupt_requested_at)
        finally:
            scheduler.close()

    def test_deny_command_sandbox_fails_closed(self) -> None:
        """验证未配置可信沙箱时所有命令都被明确拒绝。"""
        sandbox = DenyCommandSandbox()

        with self.assertRaises(CommandExecutionDeniedError):
            sandbox.execute(["python", "-V"], cwd="/workspace", timeout_seconds=5)

    def _wait_for_status(
        self,
        queries: TurnQueryService,
        turn_id: str,
        expected: TurnStatus,
    ):
        """在有限时间内等待后台执行达到预期状态。"""
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            turn = queries.get_turn(turn_id)
            if turn.status is expected:
                return turn
            time.sleep(0.01)
        self.fail(f"Turn {turn_id} did not reach {expected.value}")


class EventCoalescerTests(unittest.TestCase):
    """验证模型文本增量的限频、限量与最终刷新行为。"""

    def test_size_threshold_flushes_accumulated_content(self) -> None:
        """验证累计字符达到阈值时一次返回完整文本。"""
        coalescer = EventCoalescer(max_chars=4, max_interval_seconds=10)

        self.assertIsNone(coalescer.add("ab"))
        self.assertEqual("abcd", coalescer.add("cd"))
        self.assertIsNone(coalescer.flush())

    def test_final_flush_returns_remaining_content(self) -> None:
        """验证未达到阈值的剩余文本可在 final 前强制刷新。"""
        coalescer = EventCoalescer(max_chars=100, max_interval_seconds=10)
        coalescer.add("未满阈值")

        self.assertEqual("未满阈值", coalescer.flush())
        self.assertIsNone(coalescer.flush())


if __name__ == "__main__":
    unittest.main()
