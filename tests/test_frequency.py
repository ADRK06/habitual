from datetime import date, timedelta

from habitual.frequency import (
    DAILY,
    DAYS,
    WEEKLY,
    is_scheduled,
    next_scheduled,
    not_scheduled_dates,
    prev_scheduled,
    scheduled_days_per_week,
    week_bounds,
)

MON = date(2026, 1, 5)  # a Monday
TUE = MON + timedelta(days=1)
WED = MON + timedelta(days=2)
THU = MON + timedelta(days=3)
FRI = MON + timedelta(days=4)
SAT = MON + timedelta(days=5)
SUN = MON + timedelta(days=6)

MON_WED_FRI = 1 | 4 | 16  # bits 0, 2, 4


# --- is_scheduled ------------------------------------------------------


def test_daily_is_always_scheduled():
    for d in (MON, TUE, WED, SAT, SUN):
        assert is_scheduled(d, DAILY, None) is True


def test_weekly_is_always_scheduled():
    for d in (MON, TUE, WED, SAT, SUN):
        assert is_scheduled(d, WEEKLY, None) is True


def test_days_only_scheduled_on_set_bits():
    assert is_scheduled(MON, DAYS, MON_WED_FRI) is True
    assert is_scheduled(WED, DAYS, MON_WED_FRI) is True
    assert is_scheduled(FRI, DAYS, MON_WED_FRI) is True
    assert is_scheduled(TUE, DAYS, MON_WED_FRI) is False
    assert is_scheduled(THU, DAYS, MON_WED_FRI) is False
    assert is_scheduled(SAT, DAYS, MON_WED_FRI) is False
    assert is_scheduled(SUN, DAYS, MON_WED_FRI) is False


def test_days_with_none_mask_schedules_nothing():
    assert is_scheduled(MON, DAYS, None) is False


# --- not_scheduled_dates -------------------------------------------------


def test_not_scheduled_dates_empty_for_daily():
    assert not_scheduled_dates(DAILY, None, MON, SUN) == set()


def test_not_scheduled_dates_empty_for_weekly():
    assert not_scheduled_dates(WEEKLY, None, MON, SUN) == set()


def test_not_scheduled_dates_for_specific_days():
    assert not_scheduled_dates(DAYS, MON_WED_FRI, MON, SUN) == {TUE, THU, SAT, SUN}


def test_not_scheduled_dates_empty_range_when_start_after_end():
    assert not_scheduled_dates(DAYS, MON_WED_FRI, SUN, MON) == set()


# --- scheduled_days_per_week ----------------------------------------------


def test_scheduled_days_per_week_counts_bits():
    assert scheduled_days_per_week(MON_WED_FRI) == 3
    assert scheduled_days_per_week(0) == 0
    assert scheduled_days_per_week(None) == 0
    assert scheduled_days_per_week(127) == 7


# --- week_bounds -----------------------------------------------------------


def test_week_bounds_returns_monday_through_sunday():
    assert week_bounds(WED) == (MON, SUN)
    assert week_bounds(MON) == (MON, SUN)
    assert week_bounds(SUN) == (MON, SUN)


# --- prev_scheduled / next_scheduled ----------------------------------------


def test_prev_next_scheduled_for_daily_is_just_adjacent_day():
    assert prev_scheduled(WED, DAILY, None) == TUE
    assert next_scheduled(WED, DAILY, None) == THU


def test_prev_scheduled_for_specific_days_skips_non_scheduled():
    # Thursday's previous scheduled day (Mon/Wed/Fri) is Wednesday.
    assert prev_scheduled(THU, DAYS, MON_WED_FRI) == WED
    # Tuesday's previous scheduled day is Monday.
    assert prev_scheduled(TUE, DAYS, MON_WED_FRI) == MON
    # Monday's previous scheduled day wraps back to last week's Friday.
    assert prev_scheduled(MON, DAYS, MON_WED_FRI) == FRI - timedelta(days=7)


def test_next_scheduled_for_specific_days_skips_non_scheduled():
    # Wednesday's next scheduled day (Mon/Wed/Fri) is Friday.
    assert next_scheduled(WED, DAYS, MON_WED_FRI) == FRI
    # Saturday's next scheduled day wraps to next week's Monday.
    assert next_scheduled(SAT, DAYS, MON_WED_FRI) == MON + timedelta(days=7)
