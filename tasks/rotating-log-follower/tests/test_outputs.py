"""Hidden verifier for rotating-log-follower."""
import json
import os
import sys

import pytest

APP_DIR = os.environ.get("APP_DIR", "/app")
sys.path.insert(0, APP_DIR)

from logfollow import follow  # noqa: E402


@pytest.fixture
def paths(tmp_path):
    return str(tmp_path / "app.log"), str(tmp_path / "state.json")


def append(path, data: bytes):
    with open(path, "ab") as fh:
        fh.write(data)


def rotate(log, keep=5):
    for n in range(keep, 0, -1):
        src = f"{log}.{n}"
        if os.path.exists(src):
            os.rename(src, f"{log}.{n + 1}")
    os.rename(log, f"{log}.1")
    open(log, "wb").close()


def test_missing_file_returns_empty(paths):
    log, state = paths
    assert follow(log, state) == []


def test_basic_incremental(paths):
    log, state = paths
    append(log, b"a\nb\n")
    assert follow(log, state) == ["a", "b"]
    assert follow(log, state) == []
    append(log, b"c\n")
    assert follow(log, state) == ["c"]


def test_partial_line_held_back_then_whole(paths):
    log, state = paths
    append(log, b"one\ntw")
    assert follow(log, state) == ["one"]
    append(log, b"o\nthree")
    assert follow(log, state) == ["two"]
    append(log, b"\n")
    assert follow(log, state) == ["three"]


def test_crlf_and_invalid_utf8(paths):
    log, state = paths
    append(log, "héllo\r\n".encode() + b"bad\xff\n")
    assert follow(log, state) == ["héllo", "bad�"]


def test_multibyte_char_split_across_writes(paths):
    log, state = paths
    data = "naïve\n".encode()
    append(log, data[:3])
    assert follow(log, state) == []
    append(log, data[3:])
    assert follow(log, state) == ["naïve"]


def test_rename_rotation_drains_old_file_first(paths):
    log, state = paths
    append(log, b"1\n2\n")
    assert follow(log, state) == ["1", "2"]
    append(log, b"3\n4\n")          # written after our last read
    rotate(log)
    append(log, b"5\n")
    assert follow(log, state) == ["3", "4", "5"]
    assert follow(log, state) == []


def test_rotation_when_new_file_is_already_bigger(paths):
    log, state = paths
    append(log, b"x\n")
    assert follow(log, state) == ["x"]
    append(log, b"y\n")
    rotate(log)
    big = [f"new-{i:04d}" for i in range(200)]
    append(log, ("\n".join(big) + "\n").encode())
    assert follow(log, state) == ["y"] + big


def test_double_rotation_between_calls(paths):
    log, state = paths
    append(log, b"a\n")
    assert follow(log, state) == ["a"]
    append(log, b"b\n")
    rotate(log)
    append(log, b"c\n")
    rotate(log)
    append(log, b"d\n")
    assert follow(log, state) == ["b", "c", "d"]


def test_partial_line_completed_in_rotated_file(paths):
    log, state = paths
    append(log, b"keep\nhal")
    assert follow(log, state) == ["keep"]
    append(log, b"f done\n")
    rotate(log)
    append(log, b"fresh\n")
    assert follow(log, state) == ["half done", "fresh"]


def test_copytruncate(paths):
    log, state = paths
    append(log, b"old1\nold2\n")
    assert follow(log, state) == ["old1", "old2"]
    with open(log, "r+b") as fh:
        fh.truncate(0)
    append(log, b"n\n")
    assert follow(log, state) == ["n"]


def test_rotated_file_already_gone(paths):
    log, state = paths
    append(log, b"a\n")
    assert follow(log, state) == ["a"]
    append(log, b"lost\n")
    rotate(log)
    os.remove(log + ".1")
    append(log, b"b\n")
    assert follow(log, state) == ["b"]


def test_legacy_state_file_accepted(paths):
    log, state = paths
    append(log, b"seen\nnew\n")
    with open(state, "w") as fh:
        json.dump({"offset": 5}, fh)
    assert follow(log, state) == ["new"]


def test_state_is_saved_atomically(paths, monkeypatch):
    log, state = paths
    append(log, b"a\n")
    follow(log, state)
    before = open(state).read()
    append(log, b"b\n")

    import builtins
    real_open = builtins.open

    class Boom(Exception):
        pass

    def exploding_open(file, mode="r", *a, **k):
        fh = real_open(file, mode, *a, **k)
        if "w" in mode and os.path.abspath(str(file)) == os.path.abspath(state):
            fh.close()
            raise Boom("crash while saving")
        return fh

    monkeypatch.setattr(builtins, "open", exploding_open)
    import json as _json

    def exploding_dump(obj, fh, *a, **k):
        fh.write('{"ident": [1, ')
        fh.flush()
        raise Boom("crash mid-write")

    monkeypatch.setattr(_json, "dump", exploding_dump)
    with pytest.raises(Exception):
        follow(log, state)
    monkeypatch.undo()
    assert open(state).read() == before
    assert follow(log, state) == ["b"]
