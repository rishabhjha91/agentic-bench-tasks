"""Hidden verifier for sqlite-migration-runner.

Each test pins one requirement from instruction.md. Several target assumptions a
shortcut implementation tends to make (lexical ordering, executescript being
transactional, splitting SQL on ';', hashing raw bytes).
"""
import os
import sqlite3
import subprocess
import sys

import pytest

APP_DIR = os.environ.get("APP_DIR", "/app")
sys.path.insert(0, APP_DIR)

from migrate import MigrationError, discover, status, up  # noqa: E402


def write(d, name, sql, crlf=False):
    data = sql.replace("\n", "\r\n") if crlf else sql
    with open(os.path.join(d, name), "w", encoding="utf-8", newline="") as fh:
        fh.write(data)


def tables(db):
    conn = sqlite3.connect(db)
    try:
        return {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    finally:
        conn.close()


def recorded(db):
    conn = sqlite3.connect(db)
    try:
        return sorted(int(r[0]) for r in conn.execute("SELECT version FROM schema_migrations"))
    finally:
        conn.close()


@pytest.fixture
def env(tmp_path):
    d = tmp_path / "migrations"
    d.mkdir()
    return str(tmp_path / "app.db"), str(d)


def test_numeric_order_and_zero_padding(env):
    db, d = env
    write(d, "10_c.sql", "CREATE TABLE c (id INTEGER, b_id INTEGER REFERENCES b(id));\nINSERT INTO c SELECT id, id FROM b;")
    write(d, "2_b.sql", "CREATE TABLE b (id INTEGER);\nINSERT INTO b SELECT id FROM a;")
    write(d, "0001_a.sql", "CREATE TABLE a (id INTEGER);\nINSERT INTO a VALUES (1);")
    assert [m.version for m in discover(d)] == [1, 2, 10] or [int(m.version) for m in discover(d)] == [1, 2, 10]
    up(db, d)
    assert recorded(db) == [1, 2, 10]


def test_non_migration_files_ignored(env):
    db, d = env
    write(d, "0001_a.sql", "CREATE TABLE a (id INTEGER);")
    write(d, "README.md", "not sql")
    write(d, ".DS_Store", "junk")
    write(d, "0002_b.sql~", "CREATE TABLE junk (x);")
    write(d, "notes.sql", "CREATE TABLE junk2 (x);")
    up(db, d)
    assert recorded(db) == [1]
    assert "junk" not in tables(db) and "junk2" not in tables(db)


def test_duplicate_version_is_error(env):
    db, d = env
    write(d, "0002_a.sql", "CREATE TABLE a (id INTEGER);")
    write(d, "2_b.sql", "CREATE TABLE b (id INTEGER);")
    with pytest.raises(MigrationError):
        up(db, d)


def test_failed_migration_rolls_back_completely(env):
    db, d = env
    write(d, "0001_ok.sql", "CREATE TABLE ok (id INTEGER);")
    write(d, "0002_half.sql", "CREATE TABLE half (id INTEGER);\nINSERT INTO half VALUES (1);\nINSERT INTO no_such_table VALUES (1);")
    write(d, "0003_later.sql", "CREATE TABLE later (id INTEGER);")
    with pytest.raises(MigrationError) as info:
        up(db, d)
    assert "2" in str(info.value)
    assert "ok" in tables(db)
    assert "half" not in tables(db), "first half of a failed migration was left behind"
    assert "later" not in tables(db)
    assert recorded(db) == [1]


def test_failed_migration_can_be_fixed_and_rerun(env):
    db, d = env
    write(d, "0001_t.sql", "CREATE TABLE t (id INTEGER);\nINSERT INTO missing VALUES (1);")
    with pytest.raises(MigrationError):
        up(db, d)
    write(d, "0001_t.sql", "CREATE TABLE t (id INTEGER);")
    assert [int(v) for v in up(db, d)] == [1]
    assert "t" in tables(db)


def test_trigger_with_inner_semicolons(env):
    db, d = env
    write(d, "0001_audit.sql", """
CREATE TABLE item (id INTEGER PRIMARY KEY, qty INTEGER);
CREATE TABLE audit (item_id INTEGER, note TEXT);
CREATE TRIGGER item_audit AFTER UPDATE ON item
BEGIN
    INSERT INTO audit VALUES (NEW.id, 'qty changed');
    INSERT INTO audit VALUES (NEW.id, 'second row');
END;
INSERT INTO item VALUES (1, 5);
UPDATE item SET qty = 6 WHERE id = 1;
""")
    up(db, d)
    conn = sqlite3.connect(db)
    assert conn.execute("SELECT COUNT(*) FROM audit").fetchone()[0] == 2
    conn.close()


def test_semicolon_inside_string_literal(env):
    db, d = env
    write(d, "0001_s.sql", "CREATE TABLE s (v TEXT);\nINSERT INTO s VALUES ('a;b; c');\n-- trailing comment; with semicolon\n")
    up(db, d)
    conn = sqlite3.connect(db)
    assert conn.execute("SELECT v FROM s").fetchone()[0] == "a;b; c"
    conn.close()


def test_edited_applied_migration_blocks_up(env):
    db, d = env
    write(d, "0001_a.sql", "CREATE TABLE a (id INTEGER);")
    up(db, d)
    write(d, "0001_a.sql", "CREATE TABLE a (id INTEGER, extra TEXT);")
    write(d, "0002_b.sql", "CREATE TABLE b (id INTEGER);")
    with pytest.raises(MigrationError):
        up(db, d)
    assert "b" not in tables(db)
    states = {v if isinstance(v, int) else int(v): s for v, _, s in status(db, d)}
    assert states == {1: "drifted", 2: "pending"}


def test_line_ending_change_is_not_drift(env):
    db, d = env
    write(d, "0001_a.sql", "CREATE TABLE a (id INTEGER);\nINSERT INTO a VALUES (1);\n")
    up(db, d)
    write(d, "0001_a.sql", "CREATE TABLE a (id INTEGER);\nINSERT INTO a VALUES (1);\n", crlf=True)
    write(d, "0002_b.sql", "CREATE TABLE b (id INTEGER);")
    up(db, d)
    assert recorded(db) == [1, 2]
    assert [s for _, _, s in status(db, d)] == ["applied", "applied"]


def test_deleted_applied_migration(env):
    db, d = env
    write(d, "0001_a.sql", "CREATE TABLE a (id INTEGER);")
    write(d, "0002_b.sql", "CREATE TABLE b (id INTEGER);")
    up(db, d)
    os.remove(os.path.join(d, "0001_a.sql"))
    write(d, "0003_c.sql", "CREATE TABLE c (id INTEGER);")
    with pytest.raises(MigrationError):
        up(db, d)
    assert "c" not in tables(db)
    rows = [(int(v), s) for v, _, s in status(db, d)]
    assert rows == [(1, "missing"), (2, "applied"), (3, "pending")]


def test_out_of_order_requires_flag(env):
    db, d = env
    write(d, "0001_a.sql", "CREATE TABLE a (id INTEGER);")
    write(d, "0003_c.sql", "CREATE TABLE c (id INTEGER);")
    up(db, d)
    write(d, "0002_b.sql", "CREATE TABLE b (id INTEGER);")
    with pytest.raises(MigrationError):
        up(db, d)
    assert "b" not in tables(db)
    up(db, d, allow_out_of_order=True)
    assert recorded(db) == [1, 2, 3]


def test_target_stops_inclusive(env):
    db, d = env
    for v in (1, 2, 3, 4):
        write(d, f"{v:04d}_t{v}.sql", f"CREATE TABLE t{v} (id INTEGER);")
    up(db, d, target=2)
    assert recorded(db) == [1, 2]
    up(db, d)
    assert recorded(db) == [1, 2, 3, 4]


def test_second_run_is_noop(env):
    db, d = env
    write(d, "0001_a.sql", "CREATE TABLE a (id INTEGER);")
    assert len(up(db, d)) == 1
    assert list(up(db, d)) == []


def test_cli_failure_exit_code(env):
    db, d = env
    write(d, "0001_bad.sql", "CREATE TABLE x (;")
    proc = subprocess.run([sys.executable, "-m", "migrate", "up", "--db", db, "--dir", d],
                          cwd=APP_DIR, capture_output=True, text=True)
    assert proc.returncode != 0
    assert proc.stderr.strip()
