"""Tiny SQL migration runner used by the `migrate` CLI.

Migrations are plain ``.sql`` files named ``<version>_<name>.sql``. Applied migrations
are recorded in the ``schema_migrations`` table of the target SQLite database.
"""

from __future__ import annotations

import hashlib
import os
import sqlite3
from dataclasses import dataclass

TABLE = "schema_migrations"


class MigrationError(Exception):
    """Raised when migrations cannot be applied safely."""


@dataclass(frozen=True)
class Migration:
    version: str
    name: str
    path: str

    def read(self) -> str:
        with open(self.path, encoding="utf-8") as fh:
            return fh.read()

    def checksum(self) -> str:
        return hashlib.sha256(self.read().encode("utf-8")).hexdigest()


def discover(directory: str) -> list[Migration]:
    found = []
    for entry in os.listdir(directory):
        version, _, rest = entry.partition("_")
        name = rest[: -len(".sql")] if rest.endswith(".sql") else rest
        found.append(Migration(version, name, os.path.join(directory, entry)))
    return sorted(found, key=lambda m: m.version)


def _connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.execute(
        f"CREATE TABLE IF NOT EXISTS {TABLE} (version TEXT PRIMARY KEY, name TEXT NOT NULL,"
        " checksum TEXT NOT NULL, applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)"
    )
    conn.commit()
    return conn


def _applied(conn) -> dict[str, str]:
    return dict(conn.execute(f"SELECT version, checksum FROM {TABLE}").fetchall())


def up(db_path, directory, target=None, allow_out_of_order=False):
    conn = _connect(db_path)
    done = _applied(conn)
    applied_now = []
    for m in discover(directory):
        if m.version in done:
            continue
        if target is not None and int(m.version) > target:
            break
        try:
            conn.executescript(m.read())
        finally:
            conn.execute(f"INSERT INTO {TABLE} (version, name, checksum) VALUES (?, ?, ?)",
                         (m.version, m.name, m.checksum()))
            conn.commit()
        applied_now.append(m.version)
    conn.close()
    return applied_now


def status(db_path, directory):
    conn = _connect(db_path)
    done = _applied(conn)
    conn.close()
    return [(m.version, m.name, "applied" if m.version in done else "pending")
            for m in discover(directory)]
