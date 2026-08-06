"""会话状态与幂等执行记录的持久化实现。"""

from __future__ import annotations

import json
import sqlite3
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol

from ..domain.models import SessionEvent, ToolResult


class ConcurrentUpdateError(RuntimeError):
    """保存会话时发现版本已过期，说明存在并发更新。"""


class SessionRepository(Protocol):
    """定义真实模型服务依赖的会话与事件持久化契约。"""

    def load(self, session_id: str) -> tuple[int, dict[str, Any]]:
        """读取会话版本和状态。"""
        ...

    def save(self, session_id: str, expected_version: int, state: dict[str, Any]) -> int:
        """使用乐观锁保存会话状态。"""
        ...

    def delete_session(self, session_id: str) -> None:
        """删除会话上下文但保留审计事件。"""
        ...

    def append_event(
        self,
        *,
        session_id: str,
        request_id: str,
        sequence: int,
        event: dict[str, Any],
    ) -> int:
        """追加一个结构化执行事件。"""
        ...

    def list_events(
        self,
        session_id: str,
        *,
        request_id: str | None = None,
    ) -> list[SessionEvent]:
        """按写入顺序读取结构化执行事件。"""
        ...

    def close(self) -> None:
        """关闭仓储持有的数据库连接资源。"""
        ...


class SessionStore:
    """使用 compare-and-swap 乐观锁维护 SQLite 会话状态。"""

    def __init__(self, database: str = ":memory:") -> None:
        """初始化会话表，并创建线程安全的数据库访问锁。"""
        if database != ":memory:" and not database.startswith("file:"):
            Path(database).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(database, check_same_thread=False, isolation_level=None)
        self._connection.execute("PRAGMA journal_mode=WAL")
        self._connection.execute(
            """
            CREATE TABLE IF NOT EXISTS agent_sessions (
                session_id TEXT PRIMARY KEY,
                version INTEGER NOT NULL,
                state_json TEXT NOT NULL
            )
            """
        )
        self._connection.execute(
            """
            CREATE TABLE IF NOT EXISTS agent_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                request_id TEXT NOT NULL,
                sequence INTEGER NOT NULL,
                event_type TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(request_id, sequence)
            )
            """
        )
        self._connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_agent_events_session_id
            ON agent_events(session_id, id)
            """
        )
        self._lock = threading.RLock()

    def load(self, session_id: str) -> tuple[int, dict[str, Any]]:
        """读取会话版本和持久化状态，新会话返回版本零。"""
        with self._lock:
            row = self._connection.execute(
                "SELECT version, state_json FROM agent_sessions WHERE session_id = ?",
                (session_id,),
            ).fetchone()
        if row is None:
            return 0, {}
        return int(row[0]), json.loads(row[1])

    def save(self, session_id: str, expected_version: int, state: dict[str, Any]) -> int:
        """仅在版本匹配时保存状态，并返回递增后的会话版本。"""
        payload = json.dumps(state, ensure_ascii=False, sort_keys=True)
        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                next_version = self._save_in_transaction(
                    session_id,
                    expected_version,
                    payload,
                )
                self._connection.execute("COMMIT")
                return next_version
            except Exception:
                self._connection.execute("ROLLBACK")
                raise

    def delete_session(self, session_id: str) -> None:
        """删除指定会话上下文，同时保留事件用于审计和问题追踪。"""
        with self._lock:
            self._connection.execute(
                "DELETE FROM agent_sessions WHERE session_id = ?",
                (session_id,),
            )

    def append_event(
        self,
        *,
        session_id: str,
        request_id: str,
        sequence: int,
        event: dict[str, Any],
    ) -> int:
        """按请求内序号持久化一个结构化 Agent 事件，并返回事件主键。"""
        event_type = str(event.get("type") or "message")
        payload = json.dumps(event, ensure_ascii=False, sort_keys=True)
        with self._lock:
            cursor = self._connection.execute(
                """
                INSERT INTO agent_events(
                    session_id, request_id, sequence, event_type, payload_json
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (session_id, request_id, sequence, event_type, payload),
            )
            return int(cursor.lastrowid)

    def list_events(
        self,
        session_id: str,
        *,
        request_id: str | None = None,
    ) -> list[SessionEvent]:
        """按写入顺序读取指定会话或单次请求的结构化事件。"""
        query = (
            "SELECT id, session_id, request_id, sequence, event_type, payload_json, created_at "
            "FROM agent_events WHERE session_id = ?"
        )
        parameters: tuple[str, ...] = (session_id,)
        if request_id is not None:
            query += " AND request_id = ?"
            parameters = (session_id, request_id)
        query += " ORDER BY id"
        with self._lock:
            rows = self._connection.execute(query, parameters).fetchall()
        return [
            SessionEvent(
                id=int(row[0]),
                session_id=str(row[1]),
                request_id=str(row[2]),
                sequence=int(row[3]),
                event_type=str(row[4]),
                payload=json.loads(row[5]),
                created_at=str(row[6]),
            )
            for row in rows
        ]

    def close(self) -> None:
        """幂等关闭 SQLite 数据库连接。"""
        with self._lock:
            if self._connection is not None:
                self._connection.close()
                self._connection = None

    def _save_in_transaction(
        self,
        session_id: str,
        expected_version: int,
        payload: str,
    ) -> int:
        """在当前事务中执行会话新增或带版本条件的更新。"""
        if expected_version == 0:
            cursor = self._connection.execute(
                """
                INSERT OR IGNORE INTO agent_sessions(session_id, version, state_json)
                VALUES (?, 1, ?)
                """,
                (session_id, payload),
            )
            if cursor.rowcount != 1:
                raise ConcurrentUpdateError(f"session {session_id} was created concurrently")
            return 1

        cursor = self._connection.execute(
            """
            UPDATE agent_sessions
            SET version = version + 1, state_json = ?
            WHERE session_id = ? AND version = ?
            """,
            (payload, session_id, expected_version),
        )
        if cursor.rowcount != 1:
            raise ConcurrentUpdateError(
                f"session {session_id} expected version {expected_version}"
            )
        return expected_version + 1


class IdempotencyStore:
    """保证同一幂等键对应的写操作只执行一次。"""

    def __init__(self) -> None:
        """初始化进程内幂等记录和并发锁。"""
        self._records: dict[str, ToolResult] = {}
        self._lock = threading.RLock()

    def execute(
        self,
        tool_name: str,
        key: str,
        operation: Callable[[], dict[str, Any]],
    ) -> ToolResult:
        """执行首次写操作，后续相同幂等键直接重放已有结果。"""
        with self._lock:
            existing = self._records.get(key)
            if existing is not None:
                return ToolResult(
                    tool_name=existing.tool_name,
                    idempotency_key=existing.idempotency_key,
                    status=existing.status,
                    output=existing.output,
                    replayed=True,
                )
            try:
                result = ToolResult(tool_name, key, "succeeded", operation())
            except Exception as exc:
                result = ToolResult(
                    tool_name,
                    key,
                    "failed",
                    {"error_type": type(exc).__name__, "message": str(exc)},
                )
            self._records[key] = result
            return result
