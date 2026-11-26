#!/bin/bash
# Shortcut baseline: tracks inode + partial lines, but on rename rotation it jumps
# straight to the new file and loses the tail of the rotated one.
set -euo pipefail
APP_DIR="${APP_DIR:-/app}"
cat > "$APP_DIR/logfollow/follower.py" <<'PYEOF'
"""Incrementally read new lines from a log file between calls.

State is tracked by file identity (st_dev, st_ino) plus byte offset, so rename-style
rotation and copytruncate rotation can be told apart and nothing is lost or repeated.
"""
from __future__ import annotations

import json
import os
import tempfile

MAX_ROTATED = 50


def _load(state_path: str) -> dict:
    try:
        with open(state_path, encoding="utf-8") as fh:
            state = json.load(fh)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}
    return state if isinstance(state, dict) else {}


def _save(state_path: str, state: dict) -> None:
    directory = os.path.dirname(os.path.abspath(state_path))
    fd, tmp = tempfile.mkstemp(prefix=".logfollow-", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(state, fh)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, state_path)
    except BaseException:
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass
        raise


def _ident(st: os.stat_result) -> list[int]:
    return [st.st_dev, st.st_ino]


def _read_complete(path: str, offset: int) -> tuple[list[str], int]:
    """Read complete lines from ``offset``; return lines and the new offset."""
    with open(path, "rb") as fh:
        fh.seek(offset)
        data = fh.read()
    end = data.rfind(b"\n")
    if end == -1:
        return [], offset
    chunk = data[: end + 1]
    lines = []
    for raw in chunk.split(b"\n")[:-1]:
        if raw.endswith(b"\r"):
            raw = raw[:-1]
        lines.append(raw.decode("utf-8", errors="replace"))
    return lines, offset + len(chunk)


def _rotated_chain(log_path: str, ident: list[int] | None) -> list[str]:
    """Return rotated files newer than (and including) the one with ``ident``, oldest first."""
    if ident is None:
        return []
    for n in range(1, MAX_ROTATED + 1):
        candidate = f"{log_path}.{n}"
        try:
            st = os.stat(candidate)
        except FileNotFoundError:
            continue
        if _ident(st) == ident:
            return [f"{log_path}.{k}" for k in range(n, 0, -1)]
    return []


def follow(log_path: str, state_path: str) -> list[str]:
    state = _load(state_path)
    offset = int(state.get("offset", 0))
    ident = state.get("ident")
    try:
        st = os.stat(log_path)
    except FileNotFoundError:
        return []

    lines: list[str] = []
    if ident is None and "offset" in state and offset <= st.st_size:
        ident = _ident(st)  # legacy state from the old version: assume same file
    if ident is not None and ident != _ident(st):
        offset = 0
    elif offset > st.st_size:
        offset = 0  # copytruncate

    got, offset = _read_complete(log_path, offset)
    lines.extend(got)
    _save(state_path, {"ident": _ident(st), "offset": offset})
    return lines
PYEOF
