#!/bin/bash
# Oracle solution: replaces the runner with a transactional implementation.
set -euo pipefail
APP_DIR="${APP_DIR:-/app}"
cat > "$APP_DIR/migrate/runner.py" <<'PYEOF'
"""Tiny SQL migration runner used by the `migrate` CLI.

Migrations are plain ``.sql`` files named ``<version>_<name>.sql``. Applied migrations
are recorded in the ``schema_migrations`` table of the target SQLite database.
"""

from __future__ import annotations

import hashlib
import os
import re
import sqlite3
from dataclasses import dataclass

TABLE = "schema_migrations"
_NAME_RE = re.compile(r"^(\d+)_([A-Za-z0-9_\-]+)\.sql$")


class MigrationError(Exception):
    """Raised when migrations cannot be applied safely."""


@dataclass(frozen=True)
class Migration:
    version: int
    name: str
    path: str

    def read(self) -> str:
        with open(self.path, encoding="utf-8", newline="") as fh:
            return fh.read()

    def checksum(self) -> str:
        normalized = self.read().replace("\r\n", "\n")
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def discover(directory: str) -> list[Migration]:
    by_version: dict[int, Migration] = {}
    for entry in os.listdir(directory):
        match = _NAME_RE.match(entry)
        path = os.path.join(directory, entry)
        if not match or not os.path.isfile(path):
            continue
        version = int(match.group(1))
        if version in by_version:
            raise MigrationError(
                f"duplicate migration version {version}: "
                f"{os.path.basename(by_version[version].path)} and {entry}"
            )
        by_version[version] = Migration(version, match.group(2), path)
    return [by_version[v] for v in sorted(by_version)]


def split_statements(sql: str) -> list[str]:
    """Split a script into complete statements, respecting triggers and literals."""
    statements, buf = [], ""
    for line in sql.splitlines(keepends=True):
        buf += line
        while True:
            idx = _first_complete(buf)
            if idx is None:
                break
            stmt, buf = buf[:idx].strip(), buf[idx:]
            if stmt and stmt != ";":
                statements.append(stmt)
    if buf.strip():
        if _strip_comments(buf).strip():
            raise MigrationError(f"incomplete SQL statement at end of file: {buf.strip()[:60]!r}")
    return statements


def _first_complete(buf: str):
    pos = 0
    while True:
        pos = buf.find(";", pos)
        if pos == -1:
            return None
        if sqlite3.complete_statement(buf[: pos + 1]):
            return pos + 1
        pos += 1


def _strip_comments(sql: str) -> str:
    sql = re.sub(r"/\*.*?\*/", "", sql, flags=re.S)
    return re.sub(r"--[^\n]*", "", sql)


def _connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, isolation_level=None)
    conn.execute(
        f"CREATE TABLE IF NOT EXISTS {TABLE} (version TEXT PRIMARY KEY, name TEXT NOT NULL,"
        " checksum TEXT NOT NULL, applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)"
    )
    return conn


def _applied(conn) -> dict[int, tuple[str, str]]:
    rows = conn.execute(f"SELECT version, name, checksum FROM {TABLE}").fetchall()
    return {int(v): (name, checksum) for v, name, checksum in rows}


def _check_drift(done, migrations):
    on_disk = {m.version: m for m in migrations}
    for version, (name, checksum) in sorted(done.items()):
        m = on_disk.get(version)
        if m is None:
            raise MigrationError(f"applied migration {version} ({name}) is missing from disk")
        if m.checksum() != checksum:
            raise MigrationError(f"applied migration {version} ({m.name}) was edited after it ran")


def _apply(conn, m: Migration) -> None:
    statements = split_statements(m.read())
    conn.execute("BEGIN IMMEDIATE")
    try:
        for stmt in statements:
            conn.execute(stmt)
        conn.execute(
            f"INSERT INTO {TABLE} (version, name, checksum) VALUES (?, ?, ?)",
            (str(m.version), m.name, m.checksum()),
        )
    except sqlite3.Error as exc:
        conn.execute("ROLLBACK")
        raise MigrationError(f"migration {m.version} ({m.name}) failed: {exc}") from exc
    conn.execute("COMMIT")


def up(db_path, directory, target=None, allow_out_of_order=False) -> list[int]:
    migrations = discover(directory)
    conn = _connect(db_path)
    try:
        done = _applied(conn)
        _check_drift(done, migrations)
        todo = [m for m in migrations if m.version not in done]
        if target is not None:
            todo = [m for m in todo if m.version <= target]
        if done and not allow_out_of_order:
            highest = max(done)
            late = [m.version for m in todo if m.version < highest]
            if late:
                raise MigrationError(
                    f"pending migration(s) {late} are older than applied version {highest}"
                )
        applied_now = []
        for m in todo:
            _apply(conn, m)
            applied_now.append(m.version)
        return applied_now
    finally:
        conn.close()


def status(db_path, directory) -> list[tuple[int, str, str]]:
    migrations = discover(directory)
    conn = _connect(db_path)
    try:
        done = _applied(conn)
    finally:
        conn.close()
    rows = []
    for m in migrations:
        if m.version not in done:
            rows.append((m.version, m.name, "pending"))
        elif done[m.version][1] != m.checksum():
            rows.append((m.version, m.name, "drifted"))
        else:
            rows.append((m.version, m.name, "applied"))
    on_disk = {m.version for m in migrations}
    for version, (name, _) in done.items():
        if version not in on_disk:
            rows.append((version, name, "missing"))
    return sorted(rows)
PYEOF
