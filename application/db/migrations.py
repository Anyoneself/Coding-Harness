"""按编号串行执行 PostgreSQL Schema 迁移。"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

MIGRATIONS_DIR = Path(__file__).with_name("migrations")
MIGRATION_NAME_PATTERN = re.compile(r"^(?P<version>\d+)_.*\.sql$")
MIGRATION_LOCK_ID = 604_291_337


class SchemaMigrationService:
    """使用事务级 advisory lock 管理编号 SQL 迁移。"""

    def __init__(self, migrations_dir: Path = MIGRATIONS_DIR) -> None:
        """保存迁移目录，实际数据库访问由调用方连接提供。"""
        self._migrations_dir = migrations_dir

    def migrate(self, connection: Any) -> list[int]:
        """在同一连接中按版本执行未应用迁移，并返回本次版本列表。"""
        connection.execute("SELECT pg_advisory_xact_lock(%s)", (MIGRATION_LOCK_ID,))
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version BIGINT PRIMARY KEY,
                name TEXT NOT NULL,
                applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
        rows = connection.execute("SELECT version FROM schema_migrations").fetchall()
        applied_versions = {int(row["version"]) for row in rows}
        applied_now: list[int] = []
        for version, path in self._migration_files():
            if version in applied_versions:
                continue
            connection.execute(path.read_text(encoding="utf-8"))
            connection.execute(
                "INSERT INTO schema_migrations(version, name) VALUES (%s, %s)",
                (version, path.name),
            )
            applied_now.append(version)
        return applied_now

    def _migration_files(self) -> list[tuple[int, Path]]:
        """读取并校验迁移文件名，拒绝重复版本。"""
        migrations: list[tuple[int, Path]] = []
        seen_versions: set[int] = set()
        for path in sorted(self._migrations_dir.glob("*.sql")):
            match = MIGRATION_NAME_PATTERN.match(path.name)
            if match is None:
                raise ValueError(f"invalid migration filename: {path.name}")
            version = int(match.group("version"))
            if version in seen_versions:
                raise ValueError(f"duplicate migration version: {version}")
            seen_versions.add(version)
            migrations.append((version, path))
        return migrations
