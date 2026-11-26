"""Incrementally read new lines from a log file between calls."""
import json
import os


def _load(state_path):
    try:
        with open(state_path) as fh:
            return json.load(fh)
    except FileNotFoundError:
        return {"offset": 0}


def follow(log_path, state_path):
    state = _load(state_path)
    if not os.path.exists(log_path):
        return []
    offset = state.get("offset", 0)
    if os.path.getsize(log_path) < offset:
        offset = 0
    with open(log_path, "rb") as fh:
        fh.seek(offset)
        data = fh.read()
    lines = data.decode("utf-8").splitlines()
    with open(state_path, "w") as fh:
        json.dump({"offset": offset + len(data)}, fh)
    return lines
