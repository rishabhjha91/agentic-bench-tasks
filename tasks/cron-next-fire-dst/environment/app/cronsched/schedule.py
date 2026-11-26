"""Compute the next fire time for a cron expression."""
from datetime import timedelta
from zoneinfo import ZoneInfo


def _field(spec, lo, hi):
    if spec == "*":
        return set(range(lo, hi + 1))
    out = set()
    for part in spec.split(","):
        if "/" in part:
            base, step = part.split("/")
            start = lo if base == "*" else int(base)
            out.update(range(start, hi + 1, int(step)))
        elif "-" in part:
            a, b = part.split("-")
            out.update(range(int(a), int(b) + 1))
        else:
            out.add(int(part))
    return out


def next_fire(expr, after, tz):
    minute, hour, dom, month, dow = expr.split()
    mins, hours = _field(minute, 0, 59), _field(hour, 0, 23)
    doms, months, dows = _field(dom, 1, 31), _field(month, 1, 12), _field(dow, 0, 6)
    zone = ZoneInfo(tz)
    t = after.astimezone(zone).replace(second=0, microsecond=0) + timedelta(minutes=1)
    while True:
        if (t.minute in mins and t.hour in hours and t.day in doms
                and t.month in months and (t.weekday() + 1) % 7 in dows):
            return t
        t += timedelta(minutes=1)
