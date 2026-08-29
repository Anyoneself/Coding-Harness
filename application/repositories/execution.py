"""Turn 执行控制面的仓储契约与 SQLite 实现。"""

from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from ..domain.execution import (
    Checkpoint,
    ExecutionBudget,
    Item,
    ItemStatus,
    ItemType,
    PermissionProfile,
    Thread,
    ThreadNotFoundError,
    ThreadStatus,
    Turn,
    TurnEvent,
    TurnNotFoundError,
    TurnStatus,
    Workspace,
    WorkspaceNotFoundError,
)


class ActiveTurnExistsError(RuntimeError):
    """同一 Thread 已经存在尚未结束的 Turn。"""


class TurnLeaseConflictError(RuntimeError):
    """Turn 已被另一个拥有有效租约的 Worker 领取。"""


class TurnExecutionStore(Protocol):
    """定义执行 Service 所需的事务型持久化能力。"""

    def create_workspace(
        self,
        root_path: str,
        permission_profile: PermissionProfile | str,
    ) -> Workspace:
        """创建工作区边界。"""
        ...

    def create_thread(self, workspace_id: str, title: str) -> Thread:
        """在指定工作区中创建任务线程。"""
        ...

    def create_turn(
        self,
        thread_id: str,
        prompt: str,
        budget: ExecutionBudget | None = None,
    ) -> Turn:
        """创建排队中的 Turn 并追加初始事件。"""
        ...

    def get_turn(self, turn_id: str) -> Turn:
        """读取 Turn 快照。"""
        ...

    def claim_turn(self, turn_id: str, *, owner: str, expires_at: datetime) -> Turn:
        """领取 Turn 租约并进入运行状态。"""
        ...

    def transition_turn(
        self,
        turn_id: str,
        target: TurnStatus,
        *,
        reason: str | None = None,
    ) -> Turn:
        """原子更新 Turn 状态并追加事件。"""
        ...

    def append_item_event(
        self,
        turn_id: str,
        *,
        item_type: ItemType,
        item_status: ItemStatus,
        payload: dict[str, Any],
    ) -> tuple[Item, TurnEvent]:
        """原子新增 Item 和对应公开事件。"""
        ...

    def list_events(self, turn_id: str, *, after_sequence: int) -> list[TurnEvent]:
        """读取指定序号之后的事件。"""
        ...

    def save_checkpoint(
        self,
        turn_id: str,
        *,
        phase: str,
        public_state: dict[str, Any],
        model_calls: int,
        tool_calls: int,
    ) -> Checkpoint:
        """保存稳定恢复点。"""
        ...

    def get_latest_checkpoint(self, turn_id: str) -> Checkpoint | None:
        """读取最近的稳定恢复点。"""
        ...

    def request_interrupt(self, turn_id: str) -> Turn:
        """持久化显式中断请求。"""
        ...

    def is_interrupt_requested(self, turn_id: str) -> bool:
        """判断 Turn 是否收到中断请求。"""
        ...

    def recover_expired_turns(self, now: datetime) -> list[str]:
        """把租约过期的运行 Turn 转换为 interrupted。"""
        ...

    def recover_running_turns(self) -> list[str]:
        """在单进程 Runtime 启动时中断旧进程遗留的运行 Turn。"""
        ...

    def close(self) -> None:
        """释放仓储连接。"""
        ...


class SqliteTurnExecutionStore:
    """使用 SQLite 事务实现本地与测试执行控制面。"""

    def __init__(self, database: str = ":memory:") -> None:
        """打开线程安全连接并初始化版本化执行 Schema。"""
        if database != ":memory:" and not database.startswith("file:"):
            Path(database).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)
        self._connection: sqlite3.Connection | None = sqlite3.connect(
            database,
            check_same_thread=False,
            isolation_level=None,
        )
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA foreign_keys=ON")
        self._connection.execute("PRAGMA journal_mode=WAL")
        self._lock = threading.RLock()
        self._migrate()

    def create_workspace(
        self,
        root_path: str,
        permission_profile: PermissionProfile | str,
    ) -> Workspace:
        """创建工作区记录并返回持久化快照。"""
        normalized_root = str(Path(root_path).expanduser().resolve())
        profile = PermissionProfile(permission_profile)
        workspace = Workspace(
            id=str(uuid.uuid4()),
            root_path=normalized_root,
            permission_profile=profile,
            created_at=datetime.now(UTC),
        )
        with self._lock:
            self._execute(
                "INSERT INTO workspaces(id, root_path, permission_profile, created_at) VALUES (?, ?, ?, ?)",
                (workspace.id, workspace.root_path, profile.value, _format_datetime(workspace.created_at)),
            )
        return workspace

    def create_thread(self, workspace_id: str, title: str) -> Thread:
        """校验工作区后创建活动任务线程。"""
        clean_title = title.strip()
        if not clean_title:
            raise ValueError("thread title cannot be empty")
        with self._lock:
            if self._fetchone("SELECT id FROM workspaces WHERE id = ?", (workspace_id,)) is None:
                raise WorkspaceNotFoundError(workspace_id)
            thread = Thread(
                id=str(uuid.uuid4()),
                workspace_id=workspace_id,
                title=clean_title,
                status=ThreadStatus.ACTIVE,
                created_at=datetime.now(UTC),
            )
            self._execute(
                "INSERT INTO threads(id, workspace_id, title, status, created_at) VALUES (?, ?, ?, ?, ?)",
                (
                    thread.id,
                    thread.workspace_id,
                    thread.title,
                    thread.status.value,
                    _format_datetime(thread.created_at),
                ),
            )
        return thread

    def create_turn(
        self,
        thread_id: str,
        prompt: str,
        budget: ExecutionBudget | None = None,
    ) -> Turn:
        """在单个事务中创建 Turn 并记录 queued 事件。"""
        clean_prompt = prompt.strip()
        if not clean_prompt:
            raise ValueError("turn prompt cannot be empty")
        execution_budget = budget or ExecutionBudget()
        now = datetime.now(UTC)
        turn = Turn(
            id=str(uuid.uuid4()),
            thread_id=thread_id,
            prompt=clean_prompt,
            status=TurnStatus.QUEUED,
            version=1,
            next_sequence=2,
            budget=execution_budget,
            created_at=now,
            updated_at=now,
        )
        with self._transaction():
            thread_row = self._fetchone(
                "SELECT workspace_id FROM threads WHERE id = ?",
                (thread_id,),
            )
            if thread_row is None:
                raise ThreadNotFoundError(thread_id)
            try:
                self._execute(
                    """
                    INSERT INTO turns(
                        id, thread_id, prompt, status, version, next_sequence,
                        budget_json, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        turn.id,
                        turn.thread_id,
                        turn.prompt,
                        turn.status.value,
                        turn.version,
                        turn.next_sequence,
                        _budget_json(execution_budget),
                        _format_datetime(now),
                        _format_datetime(now),
                    ),
                )
            except sqlite3.IntegrityError as exc:
                if "active" in str(exc).lower() or "unique" in str(exc).lower():
                    raise ActiveTurnExistsError(thread_id) from exc
                raise
            self._insert_event(
                turn,
                workspace_id=str(thread_row["workspace_id"]),
                sequence=1,
                event_type="turn.queued",
                payload={"prompt": clean_prompt},
                occurred_at=now,
            )
        return turn

    def get_turn(self, turn_id: str) -> Turn:
        """读取 Turn；不存在时抛出语义明确的领域异常。"""
        with self._lock:
            row = self._fetchone("SELECT * FROM turns WHERE id = ?", (turn_id,))
        if row is None:
            raise TurnNotFoundError(turn_id)
        return _row_to_turn(row)

    def claim_turn(self, turn_id: str, *, owner: str, expires_at: datetime) -> Turn:
        """原子领取排队 Turn，并拒绝覆盖仍有效的其他租约。"""
        clean_owner = owner.strip()
        if not clean_owner:
            raise ValueError("lease owner cannot be empty")
        now = datetime.now(UTC)
        with self._transaction():
            turn = self._get_turn_in_transaction(turn_id)
            if (
                turn.lease_owner is not None
                and turn.lease_owner != clean_owner
                and turn.lease_expires_at is not None
                and turn.lease_expires_at > now
            ):
                raise TurnLeaseConflictError(turn_id)
            transitioned = turn.transition_to(TurnStatus.RUNNING)
            self._execute(
                """
                UPDATE turns
                SET status = ?, version = ?, lease_owner = ?, lease_expires_at = ?, updated_at = ?
                WHERE id = ? AND version = ?
                """,
                (
                    transitioned.status.value,
                    transitioned.version,
                    clean_owner,
                    _format_datetime(expires_at),
                    _format_datetime(now),
                    turn_id,
                    turn.version,
                ),
            )
            event = self._append_event_in_transaction(
                turn_id,
                "turn.running",
                {"lease_owner": clean_owner},
            )
        claimed = self.get_turn(turn_id)
        self._assert_event_belongs_to_turn(event, claimed)
        return claimed

    def transition_turn(
        self,
        turn_id: str,
        target: TurnStatus,
        *,
        reason: str | None = None,
    ) -> Turn:
        """校验状态机后原子更新 Turn 与公开事件。"""
        with self._transaction():
            turn = self._get_turn_in_transaction(turn_id)
            transitioned = turn.transition_to(target)
            terminal = target in {
                TurnStatus.COMPLETED,
                TurnStatus.FAILED,
                TurnStatus.INTERRUPTED,
                TurnStatus.CANCELLED,
            }
            self._execute(
                """
                UPDATE turns
                SET status = ?, version = ?, termination_reason = ?,
                    lease_owner = ?, lease_expires_at = ?,
                    interrupt_requested_at = ?, updated_at = ?
                WHERE id = ? AND version = ?
                """,
                (
                    target.value,
                    transitioned.version,
                    reason,
                    None if terminal else turn.lease_owner,
                    None if terminal else _format_optional_datetime(turn.lease_expires_at),
                    None
                    if target is TurnStatus.QUEUED
                    else _format_optional_datetime(turn.interrupt_requested_at),
                    _format_datetime(datetime.now(UTC)),
                    turn_id,
                    turn.version,
                ),
            )
            self._append_event_in_transaction(
                turn_id,
                f"turn.{target.value}",
                {"reason": reason} if reason else {},
            )
        return self.get_turn(turn_id)

    def append_item_event(
        self,
        turn_id: str,
        *,
        item_type: ItemType,
        item_status: ItemStatus,
        payload: dict[str, Any],
    ) -> tuple[Item, TurnEvent]:
        """在同一事务中持久化 Item 和引用该 Item 的事件。"""
        now = datetime.now(UTC)
        item = Item(
            id=str(uuid.uuid4()),
            turn_id=turn_id,
            type=item_type,
            status=item_status,
            payload=dict(payload),
            created_at=now,
        )
        with self._transaction():
            self._get_turn_in_transaction(turn_id)
            self._execute(
                """
                INSERT INTO items(id, turn_id, type, status, payload_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    item.id,
                    item.turn_id,
                    item.type.value,
                    item.status.value,
                    _json(payload),
                    _format_datetime(now),
                ),
            )
            event = self._append_event_in_transaction(
                turn_id,
                f"item.{item_status.value}",
                {
                    "item": {
                        "id": item.id,
                        "type": item.type.value,
                        "status": item.status.value,
                        "payload": item.payload,
                    }
                },
            )
        return item, event

    def list_events(self, turn_id: str, *, after_sequence: int) -> list[TurnEvent]:
        """按序返回游标之后的公开事件，不依赖内存订阅状态。"""
        if after_sequence < 0:
            raise ValueError("after_sequence cannot be negative")
        with self._lock:
            rows = self._fetchall(
                """
                SELECT * FROM turn_events
                WHERE turn_id = ? AND sequence > ?
                ORDER BY sequence
                """,
                (turn_id, after_sequence),
            )
        return [_row_to_event(row) for row in rows]

    def save_checkpoint(
        self,
        turn_id: str,
        *,
        phase: str,
        public_state: dict[str, Any],
        model_calls: int,
        tool_calls: int,
    ) -> Checkpoint:
        """保存不含隐藏推理的稳定恢复点并返回快照。"""
        if _contains_hidden_reasoning(public_state):
            raise ValueError("checkpoint cannot persist hidden reasoning")
        checkpoint = Checkpoint(
            id=str(uuid.uuid4()),
            turn_id=turn_id,
            phase=phase,
            last_sequence=0,
            public_state=dict(public_state),
            model_calls=model_calls,
            tool_calls=tool_calls,
            created_at=datetime.now(UTC),
        )
        with self._transaction():
            turn = self._get_turn_in_transaction(turn_id)
            checkpoint = Checkpoint(
                id=checkpoint.id,
                turn_id=checkpoint.turn_id,
                phase=checkpoint.phase,
                last_sequence=turn.next_sequence - 1,
                public_state=checkpoint.public_state,
                model_calls=checkpoint.model_calls,
                tool_calls=checkpoint.tool_calls,
                created_at=checkpoint.created_at,
            )
            self._execute(
                """
                INSERT INTO checkpoints(
                    id, turn_id, phase, last_sequence, public_state_json,
                    model_calls, tool_calls, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    checkpoint.id,
                    checkpoint.turn_id,
                    checkpoint.phase,
                    checkpoint.last_sequence,
                    _json(checkpoint.public_state),
                    checkpoint.model_calls,
                    checkpoint.tool_calls,
                    _format_datetime(checkpoint.created_at),
                ),
            )
        return checkpoint

    def get_latest_checkpoint(self, turn_id: str) -> Checkpoint | None:
        """读取最新稳定恢复点，不存在时返回 None。"""
        with self._lock:
            row = self._fetchone(
                """
                SELECT * FROM checkpoints
                WHERE turn_id = ?
                ORDER BY created_at DESC, rowid DESC
                LIMIT 1
                """,
                (turn_id,),
            )
        if row is None:
            return None
        return _row_to_checkpoint(row)

    def request_interrupt(self, turn_id: str) -> Turn:
        """记录中断请求时间，使执行器在稳定边界停止。"""
        with self._lock:
            cursor = self._execute(
                "UPDATE turns SET interrupt_requested_at = ?, updated_at = ? WHERE id = ?",
                (
                    _format_datetime(datetime.now(UTC)),
                    _format_datetime(datetime.now(UTC)),
                    turn_id,
                ),
            )
            if cursor.rowcount != 1:
                raise TurnNotFoundError(turn_id)
        return self.get_turn(turn_id)

    def is_interrupt_requested(self, turn_id: str) -> bool:
        """读取持久化中断标记。"""
        return self.get_turn(turn_id).interrupt_requested_at is not None

    def recover_expired_turns(self, now: datetime) -> list[str]:
        """查找租约过期的运行 Turn，并逐个原子转为 interrupted。"""
        with self._lock:
            rows = self._fetchall(
                """
                SELECT id FROM turns
                WHERE status = ? AND lease_expires_at IS NOT NULL AND lease_expires_at <= ?
                ORDER BY created_at
                """,
                (TurnStatus.RUNNING.value, _format_datetime(now)),
            )
        recovered: list[str] = []
        for row in rows:
            turn_id = str(row["id"])
            self.transition_turn(turn_id, TurnStatus.INTERRUPTED, reason="lease_expired")
            recovered.append(turn_id)
        return recovered

    def recover_running_turns(self) -> list[str]:
        """中断单进程 Scheduler 无法继续持有的全部遗留运行 Turn。"""
        with self._lock:
            rows = self._fetchall(
                "SELECT id FROM turns WHERE status = ? ORDER BY created_at",
                (TurnStatus.RUNNING.value,),
            )
        recovered: list[str] = []
        for row in rows:
            turn_id = str(row["id"])
            self.transition_turn(turn_id, TurnStatus.INTERRUPTED, reason="process_restarted")
            recovered.append(turn_id)
        return recovered

    def close(self) -> None:
        """幂等关闭 SQLite 连接并释放资源。"""
        with self._lock:
            if self._connection is not None:
                self._connection.close()
                self._connection = None

    def _migrate(self) -> None:
        """在本地仓储中创建第一阶段所需的版本化 Schema。"""
        script = """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version INTEGER PRIMARY KEY,
            applied_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS workspaces (
            id TEXT PRIMARY KEY,
            root_path TEXT NOT NULL,
            permission_profile TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS threads (
            id TEXT PRIMARY KEY,
            workspace_id TEXT NOT NULL REFERENCES workspaces(id),
            title TEXT NOT NULL,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS turns (
            id TEXT PRIMARY KEY,
            thread_id TEXT NOT NULL REFERENCES threads(id),
            prompt TEXT NOT NULL,
            status TEXT NOT NULL,
            version INTEGER NOT NULL,
            next_sequence INTEGER NOT NULL,
            budget_json TEXT NOT NULL,
            lease_owner TEXT,
            lease_expires_at TEXT,
            interrupt_requested_at TEXT,
            termination_reason TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE UNIQUE INDEX IF NOT EXISTS uq_turns_one_active_per_thread
        ON turns(thread_id)
        WHERE status IN ('queued', 'running', 'waiting_approval');
        CREATE TABLE IF NOT EXISTS items (
            id TEXT PRIMARY KEY,
            turn_id TEXT NOT NULL REFERENCES turns(id),
            type TEXT NOT NULL,
            status TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS turn_events (
            id TEXT PRIMARY KEY,
            workspace_id TEXT NOT NULL REFERENCES workspaces(id),
            thread_id TEXT NOT NULL REFERENCES threads(id),
            turn_id TEXT NOT NULL REFERENCES turns(id),
            sequence INTEGER NOT NULL,
            event_type TEXT NOT NULL,
            schema_version INTEGER NOT NULL,
            payload_json TEXT NOT NULL,
            occurred_at TEXT NOT NULL,
            UNIQUE(turn_id, sequence)
        );
        CREATE TABLE IF NOT EXISTS checkpoints (
            id TEXT PRIMARY KEY,
            turn_id TEXT NOT NULL REFERENCES turns(id),
            phase TEXT NOT NULL,
            last_sequence INTEGER NOT NULL,
            public_state_json TEXT NOT NULL,
            model_calls INTEGER NOT NULL,
            tool_calls INTEGER NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS context_snapshots (
            id TEXT PRIMARY KEY,
            turn_id TEXT NOT NULL REFERENCES turns(id),
            sources_json TEXT NOT NULL,
            builder_version TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS model_calls (
            id TEXT PRIMARY KEY,
            turn_id TEXT NOT NULL REFERENCES turns(id),
            provider TEXT NOT NULL,
            model TEXT NOT NULL,
            public_usage_json TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        INSERT OR IGNORE INTO schema_migrations(version, applied_at)
        VALUES (1, CURRENT_TIMESTAMP);
        """
        with self._lock:
            self._require_connection().executescript(script)

    def _get_turn_in_transaction(self, turn_id: str) -> Turn:
        """在当前事务中读取 Turn，并统一处理不存在语义。"""
        row = self._fetchone("SELECT * FROM turns WHERE id = ?", (turn_id,))
        if row is None:
            raise TurnNotFoundError(turn_id)
        return _row_to_turn(row)

    def _append_event_in_transaction(
        self,
        turn_id: str,
        event_type: str,
        payload: dict[str, Any],
    ) -> TurnEvent:
        """在当前事务中分配序号并插入事件。"""
        turn = self._get_turn_in_transaction(turn_id)
        sequence = turn.next_sequence
        self._execute(
            "UPDATE turns SET next_sequence = next_sequence + 1 WHERE id = ?",
            (turn_id,),
        )
        context = self._fetchone(
            """
            SELECT threads.workspace_id
            FROM turns JOIN threads ON threads.id = turns.thread_id
            WHERE turns.id = ?
            """,
            (turn_id,),
        )
        if context is None:
            raise TurnNotFoundError(turn_id)
        return self._insert_event(
            turn,
            workspace_id=str(context["workspace_id"]),
            sequence=sequence,
            event_type=event_type,
            payload=payload,
            occurred_at=datetime.now(UTC),
        )

    def _insert_event(
        self,
        turn: Turn,
        *,
        workspace_id: str,
        sequence: int,
        event_type: str,
        payload: dict[str, Any],
        occurred_at: datetime,
    ) -> TurnEvent:
        """插入已经分配序号的版本化事件。"""
        event = TurnEvent(
            id=str(uuid.uuid4()),
            workspace_id=workspace_id,
            thread_id=turn.thread_id,
            turn_id=turn.id,
            sequence=sequence,
            event_type=event_type,
            schema_version=1,
            payload=dict(payload),
            occurred_at=occurred_at,
        )
        self._execute(
            """
            INSERT INTO turn_events(
                id, workspace_id, thread_id, turn_id, sequence,
                event_type, schema_version, payload_json, occurred_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event.id,
                event.workspace_id,
                event.thread_id,
                event.turn_id,
                event.sequence,
                event.event_type,
                event.schema_version,
                _json(event.payload),
                _format_datetime(event.occurred_at),
            ),
        )
        return event

    @staticmethod
    def _assert_event_belongs_to_turn(event: TurnEvent, turn: Turn) -> None:
        """保护内部事务结果，确保事件没有关联到错误 Turn。"""
        if event.turn_id != turn.id:
            raise RuntimeError("persisted event does not belong to claimed turn")

    def _transaction(self) -> _SqliteTransaction:
        """创建持有仓储锁的显式 SQLite 事务上下文。"""
        return _SqliteTransaction(self)

    def _execute(self, sql: str, parameters: tuple[Any, ...] = ()) -> sqlite3.Cursor:
        """在已打开连接上执行 SQL，并拒绝关闭后的访问。"""
        return self._require_connection().execute(sql, parameters)

    def _fetchone(self, sql: str, parameters: tuple[Any, ...]) -> sqlite3.Row | None:
        """执行查询并返回单行结果。"""
        return self._execute(sql, parameters).fetchone()

    def _fetchall(self, sql: str, parameters: tuple[Any, ...]) -> list[sqlite3.Row]:
        """执行查询并返回全部行。"""
        return list(self._execute(sql, parameters).fetchall())

    def _require_connection(self) -> sqlite3.Connection:
        """返回活动连接，仓储关闭后拒绝继续访问。"""
        if self._connection is None:
            raise RuntimeError("execution store is closed")
        return self._connection


class _SqliteTransaction:
    """协调 SQLite 显式事务和仓储可重入锁。"""

    def __init__(self, store: SqliteTurnExecutionStore) -> None:
        """保存需要进入事务的仓储。"""
        self._store = store

    def __enter__(self) -> None:
        """获取锁并启动立即事务，序列化写入与事件序号。"""
        self._store._lock.acquire()
        try:
            self._store._execute("BEGIN IMMEDIATE")
        except Exception:
            self._store._lock.release()
            raise

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> bool:
        """根据执行结果提交或回滚，并始终释放锁。"""
        del traceback
        try:
            if exc_type is None:
                self._store._execute("COMMIT")
            else:
                self._store._execute("ROLLBACK")
        finally:
            self._store._lock.release()
        return False


def _row_to_turn(row: sqlite3.Row) -> Turn:
    """把 SQLite 行转换为稳定的 Turn 领域对象。"""
    budget_data = json.loads(str(row["budget_json"]))
    return Turn(
        id=str(row["id"]),
        thread_id=str(row["thread_id"]),
        prompt=str(row["prompt"]),
        status=TurnStatus(str(row["status"])),
        version=int(row["version"]),
        next_sequence=int(row["next_sequence"]),
        budget=ExecutionBudget(**budget_data),
        lease_owner=str(row["lease_owner"]) if row["lease_owner"] is not None else None,
        lease_expires_at=_parse_optional_datetime(row["lease_expires_at"]),
        interrupt_requested_at=_parse_optional_datetime(row["interrupt_requested_at"]),
        termination_reason=(
            str(row["termination_reason"]) if row["termination_reason"] is not None else None
        ),
        created_at=_parse_datetime(str(row["created_at"])),
        updated_at=_parse_datetime(str(row["updated_at"])),
    )


def _row_to_event(row: sqlite3.Row) -> TurnEvent:
    """把 SQLite 行转换为公开 TurnEvent。"""
    return TurnEvent(
        id=str(row["id"]),
        workspace_id=str(row["workspace_id"]),
        thread_id=str(row["thread_id"]),
        turn_id=str(row["turn_id"]),
        sequence=int(row["sequence"]),
        event_type=str(row["event_type"]),
        schema_version=int(row["schema_version"]),
        payload=json.loads(str(row["payload_json"])),
        occurred_at=_parse_datetime(str(row["occurred_at"])),
    )


def _row_to_checkpoint(row: sqlite3.Row) -> Checkpoint:
    """把 SQLite 行转换为不含供应商私有状态的 Checkpoint。"""
    return Checkpoint(
        id=str(row["id"]),
        turn_id=str(row["turn_id"]),
        phase=str(row["phase"]),
        last_sequence=int(row["last_sequence"]),
        public_state=json.loads(str(row["public_state_json"])),
        model_calls=int(row["model_calls"]),
        tool_calls=int(row["tool_calls"]),
        created_at=_parse_datetime(str(row["created_at"])),
    )


def _budget_json(budget: ExecutionBudget) -> str:
    """把执行预算序列化为稳定 JSON。"""
    return _json(
        {
            "max_model_calls": budget.max_model_calls,
            "max_tool_calls": budget.max_tool_calls,
            "max_wall_time_seconds": budget.max_wall_time_seconds,
            "max_tokens": budget.max_tokens,
            "max_cost": budget.max_cost,
        }
    )


def _json(value: dict[str, Any]) -> str:
    """使用稳定键序列化公开结构。"""
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _format_datetime(value: datetime) -> str:
    """把时间统一转换为 UTC ISO-8601 文本。"""
    return value.astimezone(UTC).isoformat()


def _format_optional_datetime(value: datetime | None) -> str | None:
    """将可选时间转换为 SQLite 可持久化文本。"""
    if value is None:
        return None
    return _format_datetime(value)


def _parse_datetime(value: str) -> datetime:
    """解析数据库中的 ISO-8601 时间并统一为 UTC。"""
    return datetime.fromisoformat(value).astimezone(UTC)


def _parse_optional_datetime(value: object) -> datetime | None:
    """解析数据库中的可选时间字段。"""
    if value is None:
        return None
    return _parse_datetime(str(value))


def _contains_hidden_reasoning(value: object) -> bool:
    """递归检测不得进入 Checkpoint 的隐藏推理字段。"""
    if isinstance(value, dict):
        for key, nested in value.items():
            if str(key).lower() in {"reasoning_content", "hidden_reasoning"}:
                return True
            if _contains_hidden_reasoning(nested):
                return True
    if isinstance(value, list):
        return any(_contains_hidden_reasoning(item) for item in value)
    return False
