"""PostgreSQL 会话与结构化事件仓储。"""

from __future__ import annotations

import threading
from typing import Any

from ..domain.models import SessionEvent
from .session import ConcurrentUpdateError


class PostgresSessionStore:
    """使用连接池和乐观锁持久化真实模型会话与执行事件。"""

    def __init__(self, database_url: str, *, min_pool_size: int = 1, max_pool_size: int = 10) -> None:
        """保存连接配置；实际连接和建表延迟到首次数据访问。"""
        self.database_url = database_url
        self.min_pool_size = min_pool_size
        self.max_pool_size = max_pool_size
        self._pool: Any | None = None
        self._lock = threading.RLock()

    def load(self, session_id: str) -> tuple[int, dict[str, Any]]:
        """从 PostgreSQL 读取会话版本和 JSON 状态。"""
        pool = self._get_pool()
        with pool.connection() as connection:
            row = connection.execute(
                "SELECT version, state_json FROM agent_sessions WHERE session_id = %s",
                (session_id,),
            ).fetchone()
        if row is None:
            return 0, {}
        return int(row[0]), dict(row[1])

    def save(self, session_id: str, expected_version: int, state: dict[str, Any]) -> int:
        """在单个事务中执行 PostgreSQL compare-and-swap 保存。"""
        from psycopg.types.json import Jsonb

        pool = self._get_pool()
        with pool.connection() as connection:
            if expected_version == 0:
                row = connection.execute(
                    """
                    INSERT INTO agent_sessions(session_id, version, state_json)
                    VALUES (%s, 1, %s)
                    ON CONFLICT (session_id) DO NOTHING
                    RETURNING version
                    """,
                    (session_id, Jsonb(state)),
                ).fetchone()
            else:
                row = connection.execute(
                    """
                    UPDATE agent_sessions
                    SET version = version + 1, state_json = %s, updated_at = NOW()
                    WHERE session_id = %s AND version = %s
                    RETURNING version
                    """,
                    (Jsonb(state), session_id, expected_version),
                ).fetchone()
            if row is None:
                raise ConcurrentUpdateError(
                    f"session {session_id} expected version {expected_version}"
                )
            return int(row[0])

    def delete_session(self, session_id: str) -> None:
        """删除 PostgreSQL 中的会话上下文，同时保留审计事件。"""
        pool = self._get_pool()
        with pool.connection() as connection:
            connection.execute(
                "DELETE FROM agent_sessions WHERE session_id = %s",
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
        """向 PostgreSQL 追加一个带请求内序号的 JSONB 事件。"""
        from psycopg.types.json import Jsonb

        pool = self._get_pool()
        with pool.connection() as connection:
            row = connection.execute(
                """
                INSERT INTO agent_events(
                    session_id, request_id, sequence, event_type, payload_json
                ) VALUES (%s, %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    session_id,
                    request_id,
                    sequence,
                    str(event.get("type") or "message"),
                    Jsonb(event),
                ),
            ).fetchone()
        if row is None:
            raise RuntimeError("PostgreSQL did not return an event id")
        return int(row[0])

    def list_events(
        self,
        session_id: str,
        *,
        request_id: str | None = None,
    ) -> list[SessionEvent]:
        """按事件主键顺序读取 PostgreSQL 中的会话或请求事件。"""
        query = """
            SELECT id, session_id, request_id, sequence, event_type, payload_json, created_at
            FROM agent_events
            WHERE session_id = %s
        """
        parameters: tuple[str, ...] = (session_id,)
        if request_id is not None:
            query += " AND request_id = %s"
            parameters = (session_id, request_id)
        query += " ORDER BY id"
        pool = self._get_pool()
        with pool.connection() as connection:
            rows = connection.execute(query, parameters).fetchall()
        return [
            SessionEvent(
                id=int(row[0]),
                session_id=str(row[1]),
                request_id=str(row[2]),
                sequence=int(row[3]),
                event_type=str(row[4]),
                payload=dict(row[5]),
                created_at=row[6].isoformat(),
            )
            for row in rows
        ]

    def close(self) -> None:
        """关闭已经创建的 PostgreSQL 连接池。"""
        with self._lock:
            if self._pool is not None:
                self._pool.close()
                self._pool = None

    def _get_pool(self) -> Any:
        """延迟创建连接池和数据库表，并返回可用连接池。"""
        with self._lock:
            if self._pool is not None:
                return self._pool
            from psycopg_pool import ConnectionPool

            pool = ConnectionPool(
                conninfo=self.database_url,
                min_size=self.min_pool_size,
                max_size=self.max_pool_size,
                open=False,
                timeout=10.0,
            )
            pool.open(wait=True, timeout=30.0)
            with pool.connection() as connection:
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS agent_sessions (
                        session_id TEXT PRIMARY KEY,
                        version BIGINT NOT NULL,
                        state_json JSONB NOT NULL,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                    """
                )
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS agent_events (
                        id BIGSERIAL PRIMARY KEY,
                        session_id TEXT NOT NULL,
                        request_id TEXT NOT NULL,
                        sequence INTEGER NOT NULL,
                        event_type TEXT NOT NULL,
                        payload_json JSONB NOT NULL,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        UNIQUE(request_id, sequence)
                    )
                    """
                )
                connection.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_agent_events_session_id
                    ON agent_events(session_id, id)
                    """
                )
            self._pool = pool
            return pool
