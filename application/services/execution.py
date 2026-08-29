"""Coding Harness 的 Thread、Turn、调度和后台执行用例。"""

from __future__ import annotations

import threading
import time
import uuid
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol

from ..agent.provider import ModelCompleted, ModelDelta, ModelProvider, ModelRequest
from ..domain.execution import (
    ExecutionBudget,
    ItemStatus,
    ItemType,
    PermissionProfile,
    Thread,
    Turn,
    TurnEvent,
    TurnStatus,
    Workspace,
)
from ..repositories.execution import TurnExecutionStore


class TurnScheduler(Protocol):
    """定义提交后台 Turn 的最小调度能力。"""

    def schedule(self, turn_id: str) -> None:
        """安排指定 Turn 在请求生命周期之外执行。"""
        ...

    def close(self) -> None:
        """停止接收新任务并释放调度资源。"""
        ...


class EventNotifier(Protocol):
    """定义事件持久化后的进程内低延迟通知能力。"""

    def notify(self, turn_id: str, sequence: int) -> None:
        """通知观察者指定 Turn 已持久化新序号。"""
        ...


class LocalConditionNotifier:
    """使用 Condition 提供可丢失但不承担事实存储的本地通知。"""

    def __init__(self) -> None:
        """初始化每个 Turn 的最新序号和条件变量。"""
        self._condition = threading.Condition()
        self._latest_sequences: dict[str, int] = {}

    def notify(self, turn_id: str, sequence: int) -> None:
        """记录最新序号并唤醒当前进程中的等待者。"""
        with self._condition:
            current = self._latest_sequences.get(turn_id, 0)
            self._latest_sequences[turn_id] = max(current, sequence)
            self._condition.notify_all()

    def wait_for_event(self, turn_id: str, after_sequence: int, timeout: float) -> bool:
        """在有限时间内等待比游标更新的事件通知。"""
        with self._condition:
            if self._latest_sequences.get(turn_id, 0) > after_sequence:
                return True
            self._condition.wait_for(
                lambda: self._latest_sequences.get(turn_id, 0) > after_sequence,
                timeout=timeout,
            )
            return self._latest_sequences.get(turn_id, 0) > after_sequence


class EventCoalescer:
    """按字符数或时间窗口合并公开模型文本，降低事件写入频率。"""

    def __init__(
        self,
        *,
        max_chars: int = 2048,
        max_interval_seconds: float = 0.1,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        """配置刷新阈值，并注入单调时钟以支持确定性测试。"""
        if max_chars < 1:
            raise ValueError("max_chars must be at least 1")
        if max_interval_seconds <= 0:
            raise ValueError("max_interval_seconds must be positive")
        self._max_chars = max_chars
        self._max_interval_seconds = max_interval_seconds
        self._clock = clock
        self._parts: list[str] = []
        self._char_count = 0
        self._last_flush_at = clock()

    def add(self, content: str) -> str | None:
        """添加非空文本，并在达到大小或时间阈值时返回合并结果。"""
        if not content:
            return None
        self._parts.append(content)
        self._char_count += len(content)
        elapsed = self._clock() - self._last_flush_at
        if self._char_count >= self._max_chars or elapsed >= self._max_interval_seconds:
            return self.flush()
        return None

    def flush(self) -> str | None:
        """返回当前累计文本并重置窗口，没有内容时返回 None。"""
        if not self._parts:
            return None
        content = "".join(self._parts)
        self._parts.clear()
        self._char_count = 0
        self._last_flush_at = self._clock()
        return content


class InProcessTurnScheduler:
    """使用有界线程池串行执行 P0 Turn。"""

    def __init__(
        self,
        execute_turn: Callable[[str], None],
        *,
        max_workers: int = 1,
    ) -> None:
        """装配执行回调并限制进程内并发数。"""
        if max_workers < 1:
            raise ValueError("max_workers must be at least 1")
        self._execute_turn = execute_turn
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix="turn-worker",
        )
        self._futures: dict[str, Future[None]] = {}
        self._lock = threading.RLock()
        self._closed = False

    def schedule(self, turn_id: str) -> None:
        """幂等提交 Turn，避免同一进程重复调度相同 ID。"""
        with self._lock:
            if self._closed:
                raise RuntimeError("turn scheduler is closed")
            existing = self._futures.get(turn_id)
            if existing is not None and not existing.done():
                return
            future = self._executor.submit(self._execute_turn, turn_id)
            self._futures[turn_id] = future

    def close(self) -> None:
        """等待已提交 Turn 到达稳定终态后关闭线程池。"""
        with self._lock:
            if self._closed:
                return
            self._closed = True
        self._executor.shutdown(wait=True, cancel_futures=False)


class ThreadService:
    """编排 Workspace 和 Thread 的创建用例。"""

    def __init__(self, store: TurnExecutionStore) -> None:
        """注入执行控制面仓储。"""
        self._store = store

    def create_workspace(
        self,
        root_path: str,
        permission_profile: PermissionProfile | str,
    ) -> Workspace:
        """创建带明确权限档的工作区。"""
        return self._store.create_workspace(root_path, permission_profile)

    def create_thread(self, workspace_id: str, title: str) -> Thread:
        """在工作区中创建持续任务线程。"""
        return self._store.create_thread(workspace_id, title)


class TurnCommandService:
    """处理创建、中断和主动恢复 Turn 的命令。"""

    def __init__(self, store: TurnExecutionStore, scheduler: TurnScheduler) -> None:
        """注入执行仓储与后台调度器。"""
        self._store = store
        self._scheduler = scheduler

    def create_turn(
        self,
        thread_id: str,
        prompt: str,
        *,
        budget: ExecutionBudget | None = None,
    ) -> Turn:
        """先持久化排队 Turn，再安排后台执行。"""
        turn = self._store.create_turn(thread_id, prompt, budget)
        self._scheduler.schedule(turn.id)
        return turn

    def interrupt_turn(self, turn_id: str) -> Turn:
        """记录显式中断请求，由执行器在稳定边界处理。"""
        return self._store.request_interrupt(turn_id)

    def resume_turn(self, turn_id: str) -> Turn:
        """把 interrupted Turn 重新排队并安排后台执行。"""
        turn = self._store.transition_turn(turn_id, TurnStatus.QUEUED, reason="user_resumed")
        self._scheduler.schedule(turn.id)
        return turn


class TurnQueryService:
    """提供不触发副作用的 Turn 与事件查询。"""

    def __init__(self, store: TurnExecutionStore) -> None:
        """注入执行控制面仓储。"""
        self._store = store

    def get_turn(self, turn_id: str) -> Turn:
        """返回当前 Turn 快照。"""
        return self._store.get_turn(turn_id)

    def list_events(self, turn_id: str, *, after_sequence: int) -> list[TurnEvent]:
        """从数据库事实源读取游标之后的事件。"""
        return self._store.list_events(turn_id, after_sequence=after_sequence)


@dataclass(frozen=True)
class ExecutionContext:
    """保存从稳定 Checkpoint 重建的模型请求与累计预算计数。"""

    request: ModelRequest
    model_calls: int
    tool_calls: int


class ContextBuilder:
    """只使用公开持久化状态为 Turn 构建供应商无关上下文。"""

    def __init__(self, store: TurnExecutionStore) -> None:
        """注入能够读取稳定 Checkpoint 的执行仓储。"""
        self._store = store

    def build(self, turn: Turn) -> ExecutionContext:
        """从最近 Checkpoint 提取有效公开消息和累计预算。"""
        checkpoint = self._store.get_latest_checkpoint(turn.id)
        if checkpoint is None:
            return ExecutionContext(
                request=ModelRequest(turn_id=turn.id, prompt=turn.prompt),
                model_calls=0,
                tool_calls=0,
            )
        messages = checkpoint.public_state.get("messages", [])
        history: list[dict[str, object]] = []
        if isinstance(messages, list):
            for message in messages:
                if not isinstance(message, dict):
                    continue
                role = message.get("role")
                content = message.get("content")
                if role not in {"user", "assistant"} or not isinstance(content, str):
                    continue
                history.append({"role": str(role), "content": content})
        return ExecutionContext(
            request=ModelRequest(
                turn_id=turn.id,
                prompt=turn.prompt,
                history=tuple(history),
            ),
            model_calls=checkpoint.model_calls,
            tool_calls=checkpoint.tool_calls,
        )


class TurnExecutionService:
    """在租约、预算和 Checkpoint 约束下执行只读模型 Turn。"""

    def __init__(
        self,
        store: TurnExecutionStore,
        provider: ModelProvider,
        notifier: EventNotifier,
        *,
        lease_seconds: int = 60,
        context_builder: ContextBuilder | None = None,
    ) -> None:
        """注入执行边界，并配置单次租约有效期。"""
        self._store = store
        self._provider = provider
        self._notifier = notifier
        self._lease_seconds = lease_seconds
        self._context_builder = context_builder or ContextBuilder(store)
        self._worker_id = f"worker-{uuid.uuid4()}"

    def replace_provider(self, provider: ModelProvider) -> None:
        """替换后续 Turn 使用的模型 Provider。"""
        self._provider = provider

    def execute(self, turn_id: str) -> None:
        """领取并执行一个 Turn，将所有可观察结果持久化后通知订阅者。"""
        turn = self._store.claim_turn(
            turn_id,
            owner=self._worker_id,
            expires_at=datetime.now(UTC) + timedelta(seconds=self._lease_seconds),
        )
        started_at = time.monotonic()
        context = self._context_builder.build(turn)
        model_calls = context.model_calls
        tool_calls = context.tool_calls
        coalescer = EventCoalescer()
        try:
            self._store.save_checkpoint(
                turn.id,
                phase="before_model",
                public_state={"prompt": turn.prompt},
                model_calls=model_calls,
                tool_calls=tool_calls,
            )
            exhausted = self._budget_exhaustion_reason(turn, started_at, model_calls)
            if exhausted is not None:
                self._fail_for_budget(turn.id, exhausted)
                return

            model_calls += 1
            completed: ModelCompleted | None = None
            for event in self._provider.stream(context.request):
                if self._store.is_interrupt_requested(turn.id):
                    self._transition_and_notify(
                        turn.id,
                        TurnStatus.INTERRUPTED,
                        reason="user_requested",
                    )
                    return
                wall_time_reason = self._budget_exhaustion_reason(
                    turn,
                    started_at,
                    model_calls,
                )
                if wall_time_reason == "wall_time":
                    self._fail_for_budget(turn.id, wall_time_reason)
                    return
                if isinstance(event, ModelDelta):
                    merged_delta = coalescer.add(event.content)
                    if merged_delta is not None:
                        self._append_and_notify(
                            turn.id,
                            ItemType.AGENT_MESSAGE,
                            ItemStatus.IN_PROGRESS,
                            {"delta": merged_delta},
                        )
                    continue
                remaining_delta = coalescer.flush()
                if remaining_delta is not None:
                    self._append_and_notify(
                        turn.id,
                        ItemType.AGENT_MESSAGE,
                        ItemStatus.IN_PROGRESS,
                        {"delta": remaining_delta},
                    )
                completed = event

            if completed is None:
                raise RuntimeError("model provider ended without a completion event")
            usage_exhaustion = self._usage_budget_exhaustion_reason(turn, completed)
            if usage_exhaustion is not None:
                self._fail_for_budget(turn.id, usage_exhaustion)
                return
            self._append_and_notify(
                turn.id,
                ItemType.AGENT_MESSAGE,
                ItemStatus.COMPLETED,
                {
                    "answer": completed.answer,
                    "finish_reason": completed.finish_reason,
                    "usage": completed.usage,
                },
            )
            self._store.save_checkpoint(
                turn.id,
                phase="final",
                public_state={"answer": completed.answer},
                model_calls=model_calls,
                tool_calls=tool_calls,
            )
            self._transition_and_notify(turn.id, TurnStatus.COMPLETED, reason="model_completed")
        except Exception as exc:
            current = self._store.get_turn(turn.id)
            if current.status is TurnStatus.RUNNING:
                self._append_and_notify(
                    turn.id,
                    ItemType.ERROR,
                    ItemStatus.FAILED,
                    {"error_type": type(exc).__name__, "message": str(exc)[:300]},
                )
                self._transition_and_notify(
                    turn.id,
                    TurnStatus.FAILED,
                    reason=type(exc).__name__,
                )

    def _budget_exhaustion_reason(
        self,
        turn: Turn,
        started_at: float,
        model_calls: int,
    ) -> str | None:
        """返回当前首先耗尽的预算维度。"""
        if model_calls >= turn.budget.max_model_calls:
            return "model_calls"
        if time.monotonic() - started_at >= turn.budget.max_wall_time_seconds:
            return "wall_time"
        return None

    def _fail_for_budget(self, turn_id: str, dimension: str) -> None:
        """记录结构化预算耗尽 Item，并把 Turn 安全结束为 failed。"""
        self._append_and_notify(
            turn_id,
            ItemType.ERROR,
            ItemStatus.FAILED,
            {"code": "budget_exhausted", "dimension": dimension},
        )
        self._transition_and_notify(turn_id, TurnStatus.FAILED, reason=dimension)

    @staticmethod
    def _usage_budget_exhaustion_reason(
        turn: Turn,
        completed: ModelCompleted,
    ) -> str | None:
        """根据 Provider 公开用量判断 Token 或成本预算是否耗尽。"""
        total_tokens = completed.usage.get("total_tokens", 0)
        if isinstance(total_tokens, (int, float)) and total_tokens > turn.budget.max_tokens:
            return "tokens"
        total_cost = completed.usage.get("total_cost", completed.usage.get("cost", 0))
        if isinstance(total_cost, (int, float)) and total_cost > turn.budget.max_cost:
            return "cost"
        return None

    def _append_and_notify(
        self,
        turn_id: str,
        item_type: ItemType,
        item_status: ItemStatus,
        payload: dict[str, object],
    ) -> None:
        """提交 Item 事件后发送非权威本地通知。"""
        _, event = self._store.append_item_event(
            turn_id,
            item_type=item_type,
            item_status=item_status,
            payload=payload,
        )
        self._notifier.notify(turn_id, event.sequence)

    def _transition_and_notify(
        self,
        turn_id: str,
        target: TurnStatus,
        *,
        reason: str,
    ) -> None:
        """提交 Turn 状态事件后通知当前进程观察者。"""
        turn = self._store.transition_turn(turn_id, target, reason=reason)
        self._notifier.notify(turn_id, turn.next_sequence - 1)


class HarnessRuntime:
    """拥有第一阶段执行 Store、Provider、Scheduler 和 Service 的生命周期。"""

    def __init__(
        self,
        store: TurnExecutionStore,
        provider: ModelProvider,
        *,
        max_workers: int = 1,
    ) -> None:
        """装配可运行的后台 Turn 纵向闭环。"""
        self.store = store
        self.provider = provider
        self.notifier = LocalConditionNotifier()
        self.execution_service = TurnExecutionService(store, provider, self.notifier)
        self.scheduler = InProcessTurnScheduler(
            self.execution_service.execute,
            max_workers=max_workers,
        )
        self.thread_service = ThreadService(store)
        self.command_service = TurnCommandService(store, self.scheduler)
        self.query_service = TurnQueryService(store)
        self._closed = False
        self._lock = threading.RLock()

    def activate_provider(self, provider: ModelProvider) -> None:
        """启用已构造的 Provider，并释放启动时的不可用占位实现。"""
        with self._lock:
            if self._closed:
                raise RuntimeError("Harness Runtime is closed")
            previous_provider = self.provider
            self.provider = provider
            self.execution_service.replace_provider(provider)
        previous_provider.close()

    def recover_interrupted_turns(self) -> list[str]:
        """在 P0 单进程启动时把旧 Worker 遗留 Turn 标记为 interrupted。"""
        return self.store.recover_running_turns()

    def close(self) -> None:
        """先等待 Worker 稳定退出，再关闭 Provider 与数据连接。"""
        with self._lock:
            if self._closed:
                return
            self._closed = True
        self.scheduler.close()
        self.provider.close()
        self.store.close()
