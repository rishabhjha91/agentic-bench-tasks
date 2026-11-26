"""Hidden verifier for cron-next-fire-dst."""
import os
import signal
import sys
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

APP_DIR = os.environ.get("APP_DIR", "/app")
sys.path.insert(0, APP_DIR)

from cronsched import next_fire  # noqa: E402

LON = "Europe/London"
UTC = timezone.utc


@pytest.fixture(autouse=True)
def _per_test_deadline():
    """An implementation that loops forever must fail that test, not hang the run."""
    def _expired(signum, frame):
        raise TimeoutError("next_fire took longer than 5s")
    old = signal.signal(signal.SIGALRM, _expired)
    signal.alarm(5)
    yield
    signal.alarm(0)
    signal.signal(signal.SIGALRM, old)


def L(*a, fold=0):
    return datetime(*a, tzinfo=ZoneInfo(LON), fold=fold)


def same_instant(a, b):
    assert a.astimezone(UTC) == b.astimezone(UTC), f"{a.isoformat()} != {b.isoformat()}"


def test_simple_daily():
    got = next_fire("15 9 * * *", L(2026, 6, 1, 9, 15), LON)
    same_instant(got, L(2026, 6, 2, 9, 15))
    assert got.utcoffset() == timedelta(hours=1)


def test_steps_and_ranges():
    got = next_fire("10-50/20 * * * *", L(2026, 6, 1, 9, 31), LON)
    same_instant(got, L(2026, 6, 1, 9, 50))
    got = next_fire("*/15 * * * *", L(2026, 6, 1, 9, 59), LON)
    same_instant(got, L(2026, 6, 1, 10, 0))


def test_names_any_case_and_sunday_7():
    # 2026-06-06 is a Saturday
    got = next_fire("0 8 * * mon-Fri", L(2026, 6, 6, 12, 0), LON)
    same_instant(got, L(2026, 6, 8, 8, 0))
    got = next_fire("0 8 * * 7", L(2026, 6, 6, 12, 0), LON)
    same_instant(got, L(2026, 6, 7, 8, 0))
    got = next_fire("0 0 1 feb,Jul *", L(2026, 6, 6, 12, 0), LON)
    same_instant(got, L(2026, 7, 1, 0, 0))


def test_dom_and_dow_are_ored():
    # 13th of the month OR any Friday. 2026-06-05 is a Friday, the 13th is a Saturday.
    got = next_fire("0 12 13 * 5", L(2026, 6, 1, 0, 0), LON)
    same_instant(got, L(2026, 6, 5, 12, 0))
    got = next_fire("0 12 13 * 5", L(2026, 6, 12, 13, 0), LON)
    same_instant(got, L(2026, 6, 13, 12, 0))


def test_only_dom_restricted_ignores_dow():
    got = next_fire("0 12 13 * *", L(2026, 6, 1, 0, 0), LON)
    same_instant(got, L(2026, 6, 13, 12, 0))


def test_after_in_other_timezone():
    after = datetime(2026, 6, 1, 23, 30, tzinfo=ZoneInfo("America/New_York"))  # 04:30 London next day
    got = next_fire("0 5 * * *", after, LON)
    same_instant(got, L(2026, 6, 2, 5, 0))
    assert got.tzinfo is not None and got.utcoffset() == timedelta(hours=1)


def test_spring_forward_runs_once_at_transition():
    # 2026-03-29: London clocks go 01:00 GMT -> 02:00 BST
    got = next_fire("30 1 * * *", L(2026, 3, 28, 12, 0), LON)
    same_instant(got, datetime(2026, 3, 29, 1, 0, tzinfo=UTC))
    nxt = next_fire("30 1 * * *", got, LON)
    same_instant(nxt, L(2026, 3, 30, 1, 30))


def test_spring_forward_several_gap_times_fire_once():
    got = next_fire("*/20 1 * * *", L(2026, 3, 29, 0, 50), LON)
    same_instant(got, datetime(2026, 3, 29, 1, 0, tzinfo=UTC))
    nxt = next_fire("*/20 1 * * *", got, LON)
    same_instant(nxt, L(2026, 3, 30, 1, 0))


def test_fall_back_daily_runs_once():
    # 2026-10-25: London 02:00 BST -> 01:00 GMT, so 01:30 happens twice
    first = next_fire("30 1 * * *", L(2026, 10, 24, 12, 0), LON)
    same_instant(first, datetime(2026, 10, 25, 0, 30, tzinfo=UTC))
    second = next_fire("30 1 * * *", first, LON)
    same_instant(second, L(2026, 10, 26, 1, 30))


def test_fall_back_hourly_runs_in_both_hours():
    first = next_fire("30 * * * *", L(2026, 10, 25, 1, 0), LON)
    same_instant(first, datetime(2026, 10, 25, 0, 30, tzinfo=UTC))
    second = next_fire("30 * * * *", first, LON)
    same_instant(second, datetime(2026, 10, 25, 1, 30, tzinfo=UTC))
    third = next_fire("30 * * * *", second, LON)
    same_instant(third, datetime(2026, 10, 25, 2, 30, tzinfo=UTC))


def test_leap_day_on_weekday_only_dow_star():
    got = next_fire("0 0 29 2 *", L(2026, 3, 1, 0, 0), LON)
    same_instant(got, datetime(2028, 2, 29, 0, 0, tzinfo=UTC))


@pytest.mark.parametrize("expr", [
    "60 * * * *", "* 24 * * *", "* * 0 * *", "* * * 13 *", "* * * * 8",
    "*/0 * * * *", "5-1 * * * *", "* * * * FOO", "* * * *", "1 2 3 4 5 6", "a * * * *",
])
def test_invalid_expressions(expr):
    with pytest.raises(ValueError):
        next_fire(expr, L(2026, 6, 1, 0, 0), LON)


def test_never_matching_expression_raises():
    with pytest.raises(ValueError):
        next_fire("0 0 30 2 *", L(2026, 6, 1, 0, 0), LON)
