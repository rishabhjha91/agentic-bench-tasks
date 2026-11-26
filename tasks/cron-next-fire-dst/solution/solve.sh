#!/bin/bash
set -euo pipefail
APP_DIR="${APP_DIR:-/app}"
cat > "$APP_DIR/cronsched/schedule.py" <<'PYEOF'
"""Compute the next fire time for a 5-field cron expression (Vixie semantics, DST aware)."""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

MONTHS = {n: i for i, n in enumerate(
    "JAN FEB MAR APR MAY JUN JUL AUG SEP OCT NOV DEC".split(), start=1)}
DAYS = {n: i for i, n in enumerate("SUN MON TUE WED THU FRI SAT".split())}
SEARCH_DAYS = 366 * 8 + 2  # a full leap cycle, enough for "29 Feb on a Monday"


def _value(token: str, lo: int, hi: int, names: dict[str, int] | None) -> int:
    tok = token.strip().upper()
    if names and tok in names:
        return names[tok]
    if not tok.isdigit():
        raise ValueError(f"bad cron value {token!r}")
    v = int(tok)
    if not lo <= v <= hi:
        raise ValueError(f"value {v} out of range {lo}-{hi}")
    return v


def _field(spec: str, lo: int, hi: int, names=None) -> set[int]:
    if not spec:
        raise ValueError("empty cron field")
    out: set[int] = set()
    for part in spec.split(","):
        step = 1
        if "/" in part:
            part, step_s = part.split("/", 1)
            if not step_s.isdigit() or int(step_s) == 0:
                raise ValueError(f"bad step {step_s!r}")
            step = int(step_s)
        if part == "*":
            a, b = lo, hi
        elif "-" in part:
            a_s, b_s = part.split("-", 1)
            a, b = _value(a_s, lo, hi, names), _value(b_s, lo, hi, names)
            if a > b:
                raise ValueError(f"descending range {part!r}")
        else:
            a = _value(part, lo, hi, names)
            b = hi if step != 1 else a
        out.update(range(a, b + 1, step))
    return out


class _Cron:
    def __init__(self, expr: str):
        parts = expr.split()
        if len(parts) != 5:
            raise ValueError(f"expected 5 fields, got {len(parts)}: {expr!r}")
        m, h, dom, mon, dow = parts
        self.minutes = sorted(_field(m, 0, 59))
        self.hours = sorted(_field(h, 0, 23))
        self.doms = _field(dom, 1, 31)
        self.months = _field(mon, 1, 12, MONTHS)
        self.dows = {d % 7 for d in _field(dow, 0, 7, DAYS)}
        self.dom_star = dom.startswith("*")
        self.dow_star = dow.startswith("*")
        self.hourly = h == "*"

    def day_matches(self, d: date) -> bool:
        if d.month not in self.months:
            return False
        dom_ok = d.day in self.doms
        dow_ok = (d.weekday() + 1) % 7 in self.dows
        if self.dom_star and self.dow_star:
            return True
        if self.dom_star:
            return dow_ok
        if self.dow_star:
            return dom_ok
        return dom_ok or dow_ok


def _instants(naive: datetime, zone: ZoneInfo, hourly: bool) -> list[datetime]:
    """UTC instants at which a wall-clock time ``naive`` should fire in ``zone``."""
    u0 = naive.replace(tzinfo=zone, fold=0).astimezone(timezone.utc)
    u1 = naive.replace(tzinfo=zone, fold=1).astimezone(timezone.utc)
    if u0 == u1:
        return [u0]
    back0 = u0.astimezone(zone).replace(tzinfo=None)
    if back0 == naive:  # ambiguous: wall time occurs twice (fall back)
        first, second = sorted((u0, u1))
        return [first, second] if hourly else [first]
    # nonexistent (spring forward): fire at the transition instant
    lo, hi = sorted((u0, u1))
    off = lo.astimezone(zone).utcoffset()
    t = lo
    while t < hi and t.astimezone(zone).utcoffset() == off:
        t += timedelta(minutes=1)
    return [t]


def next_fire(expr: str, after: datetime, tz: str) -> datetime:
    if after.tzinfo is None:
        raise ValueError("'after' must be timezone-aware")
    cron = _Cron(expr)
    zone = ZoneInfo(tz)
    after_utc = after.astimezone(timezone.utc)
    day = after.astimezone(zone).date() - timedelta(days=1)
    for _ in range(SEARCH_DAYS):
        if cron.day_matches(day):
            found = set()
            for h in cron.hours:
                for m in cron.minutes:
                    for inst in _instants(datetime.combine(day, time(h, m)), zone, cron.hourly):
                        if inst > after_utc:
                            found.add(inst)
            if found:
                return min(found).astimezone(zone)
        day += timedelta(days=1)
    raise ValueError(f"cron expression never matches: {expr!r}")
PYEOF
