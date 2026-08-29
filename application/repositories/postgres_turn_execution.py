"""PostgreSQL 的 Turn 执行控制面实现。"""

from __future__ import annotations

import threading
import uuid
from datetime import UTC, datetime
from typing import Any

from ..db.migrations import SchemaMigrationService
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
from .execution import ActiveTurnExistsError, TurnLeaseConflictError


class PostgresTurnExecutionStore:
    """使用 PostgreSQL 事务、行锁和部分唯一索引维护执行状态。"""

    def __init__(self, database_url: str, *, min_pool_size: int = 1, max_pool_size: int = 10) -> None:
        """保存连接配置，并把连接与迁移延迟到首次访问。"""
        self.database_url = database_url
        self.min_pool_size = min_pool_size
        self.max_pool_size = max_pool_size
        self._pool: Any | None = None
        self._lock = threading.RLock()
        self._migration_service = SchemaMigrationService()

    def create_workspace(
        self,
        root_path: str,
        permission_profile: PermissionProfile | str,
    ) -> Workspace:
        """创建工作区并返回领域快照。"""
        from pathlib import Path

        workspace = Workspace(
            id=str(uuid.uuid4()),
            root_path=str(Path(root_path).expanduser().resolve()),
            permission_profile=PermissionProfile(permission_profile),
            created_at=datetime.now(UTC),
        )
        with self._get_pool().connection() as connection:
            connection.execute(
                """
                INSERT INTO workspaces(id, root_path, permission_profile, created_at)
                VALUES (%s, %s, %s, %s)
                """,
                (
                    workspace.id,
                    workspace.root_path,
                    workspace.permission_profile.value,
                    workspace.created_at,
                ),
            )
        return workspace

    def create_thread(self, workspace_id: str, title: str) -> Thread:
        """校验 Workspace 后创建任务线程。"""
        clean_title = title.strip()
        if not clean_title:
            raise ValueError("thread title cannot be empty")
        with self._get_pool().connection() as connection:
            exists = connection.execute(
                "SELECT id FROM workspaces WHERE id = %s",
                (workspace_id,),
            ).fetchone()
            if exists is None:
                raise WorkspaceNotFoundError(workspace_id)
            thread = Thread(
                id=str(uuid.uuid4()),
                workspace_id=workspace_id,
                title=clean_title,
                status=ThreadStatus.ACTIVE,
                created_at=datetime.now(UTC),
            )
            connection.execute(
                """
                INSERT INTO threads(id, workspace_id, title, status, created_at)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (thread.id, workspace_id, thread.title, thread.status.value, thread.created_at),
            )
        return thread

    def create_turn(
        self,
        thread_id: str,
        prompt: str,
        budget: ExecutionBudget | None = None,
    ) -> Turn:
        """原子创建排队 Turn 和首个版本化事件。"""
        from psycopg.errors import UniqueViolation
        from psycopg.types.json import Jsonb

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
        with self._get_pool().connection() as connection:
            thread_row = connection.execute(
                "SELECT workspace_id FROM threads WHERE id = %s",
                (thread_id,),
            ).fetchone()
            if thread_row is None:
                raise ThreadNotFoundError(thread_id)
            try:
                connection.execute(
                    """
                    INSERT INTO turns(
                        id, thread_id, prompt, status, version, next_sequence,
                        budget_json, created_at, updated_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        turn.id,
                        turn.thread_id,
                        turn.prompt,
                        turn.status.value,
                        turn.version,
                        turn.next_sequence,
                        Jsonb(_budget_dict(execution_budget)),
                        now,
                        now,
                    ),
                )
            except UniqueViolation as exc:
                raise ActiveTurnExistsError(thread_id) from exc
            self._insert_event(
                connection,
                turn,
                workspace_id=str(thread_row["workspace_id"]),
                sequence=1,
                event_type="turn.queued",
                payload={"prompt": clean_prompt},
            )
        return turn

    def get_turn(self, turn_id: str) -> Turn:
        """从 PostgreSQL 读取 Turn，不存在时返回领域异常。"""
        with self._get_pool().connection() as connection:
            row = connection.execute("SELECT * FROM turns WHERE id = %s", (turn_id,)).fetchone()
        if row is None:
            raise TurnNotFoundError(turn_id)
        return _mapping_to_turn(row)

    def claim_turn(self, turn_id: str, *, owner: str, expires_at: datetime) -> Turn:
        """使用行锁领取 Turn，并拒绝覆盖有效租约。"""
        clean_owner = owner.strip()
        if not clean_owner:
            raise ValueError("lease owner cannot be empty")
        now = datetime.now(UTC)
        with self._get_pool().connection() as connection:
            turn = self._locked_turn(connection, turn_id)
            if (
                turn.lease_owner is not None
                and turn.lease_owner != clean_owner
                and turn.lease_expires_at is not None
                and turn.lease_expires_at > now
            ):
                raise TurnLeaseConflictError(turn_id)
            transitioned = turn.transition_to(TurnStatus.RUNNING)
            connection.execute(
                """
                UPDATE turns
                SET status = %s, version = %s, lease_owner = %s,
                    lease_expires_at = %s, updated_at = %s
                WHERE id = %s AND version = %s
                """,
                (
                    transitioned.status.value,
                    transitioned.version,
                    clean_owner,
                    expires_at,
                    now,
                    turn_id,
                    turn.version,
                ),
            )
            self._append_event(connection, turn_id, "turn.running", {"lease_owner": clean_owner})
        return self.get_turn(turn_id)

    def transition_turn(
        self,
        turn_id: str,
        target: TurnStatus,
        *,
        reason: str | None = None,
    ) -> Turn:
        """在行锁事务中校验状态机、更新聚合并追加事件。"""
        with self._get_pool().connection() as connection:
            turn = self._locked_turn(connection, turn_id)
            transitioned = turn.transition_to(target)
            terminal = target in {
                TurnStatus.COMPLETED,
                TurnStatus.FAILED,
                TurnStatus.INTERRUPTED,
                TurnStatus.CANCELLED,
            }
            connection.execute(
                """
                UPDATE turns
                SET status = %s, version = %s, termination_reason = %s,
                    lease_owner = %s, lease_expires_at = %s,
                    interrupt_requested_at = %s, updated_at = %s
                WHERE id = %s AND version = %s
                """,
                (
                    target.value,
                    transitioned.version,
                    reason,
                    None if terminal else turn.lease_owner,
                    None if terminal else turn.lease_expires_at,
                    None if target is TurnStatus.QUEUED else turn.interrupt_requested_at,
                    datetime.now(UTC),
                    turn_id,
                    turn.version,
                ),
            )
            self._append_event(
                connection,
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
        """在同一 PostgreSQL 事务中写入 Item 与事件。"""
        from psycopg.types.json import Jsonb

        item = Item(
            id=str(uuid.uuid4()),
            turn_id=turn_id,
            type=item_type,
            status=item_status,
            payload=dict(payload),
            created_at=datetime.now(UTC),
        )
        with self._get_pool().connection() as connection:
            self._locked_turn(connection, turn_id)
            connection.execute(
                """
                INSERT INTO items(id, turn_id, type, status, payload_json, created_at)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (
                    item.id,
                    item.turn_id,
                    item.type.value,
                    item.status.value,
                    Jsonb(item.payload),
                    item.created_at,
                ),
            )
            event = self._append_event(
                connection,
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
        """按序读取游标之后的 PostgreSQL 事件。"""
        if after_sequence < 0:
            raise ValueError("after_sequence cannot be negative")
        with self._get_pool().connection() as connection:
            rows = connection.execute(
                """
                SELECT * FROM turn_events
                WHERE turn_id = %s AND sequence > %s
                ORDER BY sequence
                """,
                (turn_id, after_sequence),
            ).fetchall()
        return [_mapping_to_event(row) for row in rows]

    def save_checkpoint(
        self,
        turn_id: str,
        *,
        phase: str,
        public_state: dict[str, Any],
        model_calls: int,
        tool_calls: int,
    ) -> Checkpoint:
        """保存公开稳定状态，明确拒绝隐藏推理字段。"""
        from psycopg.types.json import Jsonb

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
        with self._get_pool().connection() as connection:
            turn = self._locked_turn(connection, turn_id)
            checkpoint = Checkpoint(
                id=checkpoint.id,
                turn_id=checkpoint.turn_id,
                phase=checkpoint.phase,
                last_sequence=turn.next_sequence - 1,
                public_state=checkpoint.public_state,
                model_calls=model_calls,
                tool_calls=tool_calls,
                created_at=checkpoint.created_at,
            )
            connection.execute(
                """
                INSERT INTO checkpoints(
                    id, turn_id, phase, last_sequence, public_state_json,
                    model_calls, tool_calls, created_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    checkpoint.id,
                    checkpoint.turn_id,
                    checkpoint.phase,
                    checkpoint.last_sequence,
                    Jsonb(checkpoint.public_state),
                    checkpoint.model_calls,
                    checkpoint.tool_calls,
                    checkpoint.created_at,
                ),
            )
        return checkpoint

    def get_latest_checkpoint(self, turn_id: str) -> Checkpoint | None:
        """读取 PostgreSQL 中最近的稳定恢复点。"""
        with self._get_pool().connection() as connection:
            row = connection.execute(
                """
                SELECT * FROM checkpoints
                WHERE turn_id = %s
                ORDER BY created_at DESC, id DESC
                LIMIT 1
                """,
                (turn_id,),
            ).fetchone()
        if row is None:
            return None
        return _mapping_to_checkpoint(row)

    def request_interrupt(self, turn_id: str) -> Turn:
        """持久化显式中断请求。"""
        with self._get_pool().connection() as connection:
            row = connection.execute(
                """
                UPDATE turns
                SET interrupt_requested_at = NOW(), updated_at = NOW()
                WHERE id = %s
                RETURNING id
                """,
                (turn_id,),
            ).fetchone()
            if row is None:
                raise TurnNotFoundError(turn_id)
        return self.get_turn(turn_id)

    def is_interrupt_requested(self, turn_id: str) -> bool:
        """判断 Turn 是否存在持久化中断标记。"""
        return self.get_turn(turn_id).interrupt_requested_at is not None

    def recover_expired_turns(self, now: datetime) -> list[str]:
        """把租约过期的运行 Turn 转为 interrupted 并记录事件。"""
        with self._get_pool().connection() as connection:
            rows = connection.execute(
                """
                SELECT id FROM turns
                WHERE status = %s AND lease_expires_at IS NOT NULL AND lease_expires_at <= %s
                ORDER BY created_at
                """,
                (TurnStatus.RUNNING.value, now),
            ).fetchall()
        recovered: list[str] = []
        for row in rows:
            turn_id = str(row["id"])
            self.transition_turn(turn_id, TurnStatus.INTERRUPTED, reason="lease_expired")
            recovered.append(turn_id)
        return recovered

    def recover_running_turns(self) -> list[str]:
        """在 P0 单进程启动时中断所有旧进程遗留的运行 Turn。"""
        with self._get_pool().connection() as connection:
            rows = connection.execute(
                "SELECT id FROM turns WHERE status = %s ORDER BY created_at",
                (TurnStatus.RUNNING.value,),
            ).fetchall()
        recovered: list[str] = []
        for row in rows:
            turn_id = str(row["id"])
            self.transition_turn(turn_id, TurnStatus.INTERRUPTED, reason="process_restarted")
            recovered.append(turn_id)
        return recovered

    def close(self) -> None:
        """关闭已经创建的连接池，未连接时保持幂等。"""
        with self._lock:
            if self._pool is not None:
                self._pool.close()
                self._pool = None

    def _get_pool(self) -> Any:
        """延迟创建连接池，并在 advisory lock 下执行编号迁移。"""
        with self._lock:
            if self._pool is not None:
                return self._pool
            from psycopg.rows import dict_row
            from psycopg_pool import ConnectionPool

            pool = ConnectionPool(
                conninfo=self.database_url,
                min_size=self.min_pool_size,
                max_size=self.max_pool_size,
                open=False,
                timeout=10.0,
                kwargs={"row_factory": dict_row},
            )
            pool.open(wait=True, timeout=30.0)
            try:
                with pool.connection() as connection:
                    self._migration_service.migrate(connection)
            except Exception:
                pool.close()
                raise
            self._pool = pool
            return pool

    def _locked_turn(self, connection: Any, turn_id: str) -> Turn:
        """使用 `FOR UPDATE` 读取 Turn 并统一不存在语义。"""
        row = connection.execute(
            "SELECT * FROM turns WHERE id = %s FOR UPDATE",
            (turn_id,),
        ).fetchone()
        if row is None:
            raise TurnNotFoundError(turn_id)
        return _mapping_to_turn(row)

    def _append_event(
        self,
        connection: Any,
        turn_id: str,
        event_type: str,
        payload: dict[str, Any],
    ) -> TurnEvent:
        """在已持有行锁的事务中分配序号并插入事件。"""
        row = connection.execute(
            """
            UPDATE turns
            SET next_sequence = next_sequence + 1
            WHERE id = %s
            RETURNING thread_id, next_sequence - 1 AS sequence
            """,
            (turn_id,),
        ).fetchone()
        if row is None:
            raise TurnNotFoundError(turn_id)
        workspace = connection.execute(
            "SELECT workspace_id FROM threads WHERE id = %s",
            (row["thread_id"],),
        ).fetchone()
        if workspace is None:
            raise ThreadNotFoundError(str(row["thread_id"]))
        turn = self._locked_turn(connection, turn_id)
        return self._insert_event(
            connection,
            turn,
            workspace_id=str(workspace["workspace_id"]),
            sequence=int(row["sequence"]),
            event_type=event_type,
            payload=payload,
        )

    def _insert_event(
        self,
        connection: Any,
        turn: Turn,
        *,
        workspace_id: str,
        sequence: int,
        event_type: str,
        payload: dict[str, Any],
    ) -> TurnEvent:
        """插入已经分配序号的 PostgreSQL 事件。"""
        from psycopg.types.json import Jsonb

        event = TurnEvent(
            id=str(uuid.uuid4()),
            workspace_id=workspace_id,
            thread_id=turn.thread_id,
            turn_id=turn.id,
            sequence=sequence,
            event_type=event_type,
            schema_version=1,
            payload=dict(payload),
            occurred_at=datetime.now(UTC),
        )
        connection.execute(
            """
            INSERT INTO turn_events(
                id, workspace_id, thread_id, turn_id, sequence,
                event_type, schema_version, payload_json, occurred_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                event.id,
                event.workspace_id,
                event.thread_id,
                event.turn_id,
                event.sequence,
                event.event_type,
                event.schema_version,
                Jsonb(event.payload),
                event.occurred_at,
            ),
        )
        return event


def _mapping_to_turn(row: dict[str, Any]) -> Turn:
    """把 PostgreSQL 字典行转换为 Turn。"""
    return Turn(
        id=str(row["id"]),
        thread_id=str(row["thread_id"]),
        prompt=str(row["prompt"]),
        status=TurnStatus(str(row["status"])),
        version=int(row["version"]),
        next_sequence=int(row["next_sequence"]),
        budget=ExecutionBudget(**dict(row["budget_json"])),
        lease_owner=str(row["lease_owner"]) if row["lease_owner"] is not None else None,
        lease_expires_at=row["lease_expires_at"],
        interrupt_requested_at=row["interrupt_requested_at"],
        termination_reason=(
            str(row["termination_reason"]) if row["termination_reason"] is not None else None
        ),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _mapping_to_event(row: dict[str, Any]) -> TurnEvent:
    """把 PostgreSQL 字典行转换为 TurnEvent。"""
    return TurnEvent(
        id=str(row["id"]),
        workspace_id=str(row["workspace_id"]),
        thread_id=str(row["thread_id"]),
        turn_id=str(row["turn_id"]),
        sequence=int(row["sequence"]),
        event_type=str(row["event_type"]),
        schema_version=int(row["schema_version"]),
        payload=dict(row["payload_json"]),
        occurred_at=row["occurred_at"],
    )


def _mapping_to_checkpoint(row: dict[str, Any]) -> Checkpoint:
    """把 PostgreSQL 字典行转换为 Checkpoint。"""
    return Checkpoint(
        id=str(row["id"]),
        turn_id=str(row["turn_id"]),
        phase=str(row["phase"]),
        last_sequence=int(row["last_sequence"]),
        public_state=dict(row["public_state_json"]),
        model_calls=int(row["model_calls"]),
        tool_calls=int(row["tool_calls"]),
        created_at=row["created_at"],
    )


def _budget_dict(budget: ExecutionBudget) -> dict[str, int | float]:
    """把 ExecutionBudget 转换为 PostgreSQL JSONB 结构。"""
    return {
        "max_model_calls": budget.max_model_calls,
        "max_tool_calls": budget.max_tool_calls,
        "max_wall_time_seconds": budget.max_wall_time_seconds,
        "max_tokens": budget.max_tokens,
        "max_cost": budget.max_cost,
    }


def _contains_hidden_reasoning(value: object) -> bool:
    """递归阻止隐藏推理字段进入 Checkpoint。"""
    if isinstance(value, dict):
        for key, nested in value.items():
            if str(key).lower() in {"reasoning_content", "hidden_reasoning"}:
                return True
            if _contains_hidden_reasoning(nested):
                return True
    if isinstance(value, list):
        return any(_contains_hidden_reasoning(item) for item in value)
    return False
