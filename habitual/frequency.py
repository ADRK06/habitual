"""Habit scheduling (Daily / specific weekdays / X times a week). Pure,
DB-free functions - same discipline as points.py/analytics.py - so every
rule here is unit-testable and reusable from habits.py and rooms.py alike.

`frequency_days` is a 7-bit mask, one bit per weekday, matching Python's
`date.weekday()` convention (Monday=0 .. Sunday=6) - bit i set means weekday
i is scheduled. Only meaningful when frequency_type == "days".
"""

from datetime import date, timedelta

DAILY = "daily"
DAYS = "days"
WEEKLY = "weekly"

WEEKDAY_BIT = {0: 1, 1: 2, 2: 4, 3: 8, 4: 16, 5: 32, 6: 64}
ALL_DAYS_MASK = 127


def is_scheduled(d: date, frequency_type: str, frequency_days: int | None) -> bool:
    """True if `d` is a day this habit is due. Always True for "daily" and
    "weekly" - weekly has no single-day due/not-due concept, any day can
    contribute toward the week's target."""
    if frequency_type != DAYS:
        return True
    return bool((frequency_days or 0) & WEEKDAY_BIT[d.weekday()])


def not_scheduled_dates(frequency_type: str, frequency_days: int | None, start: date, end: date) -> set[date]:
    """Every date in [start, end] that is NOT scheduled - empty for "daily"
    and "weekly". This is the integration point with points.py: callers union
    this into a habit's `frozen` set before calling the streak/missed-day
    functions there, since "bridges the chain without counting" is already
    exactly what `frozen` means - a non-scheduled day needs nothing more."""
    if frequency_type != DAYS or start > end:
        return set()
    out = set()
    cursor = start
    while cursor <= end:
        if not is_scheduled(cursor, frequency_type, frequency_days):
            out.add(cursor)
        cursor += timedelta(days=1)
    return out


def scheduled_days_per_week(frequency_days: int | None) -> int:
    return bin(frequency_days or 0).count("1")


def week_bounds(d: date) -> tuple[date, date]:
    monday = d - timedelta(days=d.weekday())
    return monday, monday + timedelta(days=6)


def prev_scheduled(d: date, frequency_type: str, frequency_days: int | None) -> date:
    """Nearest scheduled day strictly before `d`. For "daily" (and as a
    degenerate case, "weekly"), that's just `d - 1`. Bounded to 7 steps for
    "days" - form validation guarantees at least one bit is set, so this
    always terminates within a week."""
    cursor = d - timedelta(days=1)
    if frequency_type != DAYS:
        return cursor
    for _ in range(7):
        if is_scheduled(cursor, frequency_type, frequency_days):
            return cursor
        cursor -= timedelta(days=1)
    return cursor  # unreachable when frequency_days has >=1 bit set


def next_scheduled(d: date, frequency_type: str, frequency_days: int | None) -> date:
    """Nearest scheduled day strictly after `d` - the forward-looking twin of
    `prev_scheduled`, same bounding rationale."""
    cursor = d + timedelta(days=1)
    if frequency_type != DAYS:
        return cursor
    for _ in range(7):
        if is_scheduled(cursor, frequency_type, frequency_days):
            return cursor
        cursor += timedelta(days=1)
    return cursor  # unreachable when frequency_days has >=1 bit set
