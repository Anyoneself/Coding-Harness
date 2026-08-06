"""会话状态与幂等执行记录的持久化实现。"""

from __future__ import annotations

import json
import sqlite3
import threading
from collections.abc import Callable
from typing import Any

from ..domain.models import ToolResult


class ConcurrentUpdateError(RuntimeError):
    """保存会话时发现版本已过期，说明存在并发更新。"""


class SessionStore:
    """使用 compare-and-swap 乐观锁维护 SQLite 会话状态。"""

    def __init__(self, database: str = ":memory:") -> None:
        """初始化会话表，并创建线程安全的数据库访问锁。"""
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
