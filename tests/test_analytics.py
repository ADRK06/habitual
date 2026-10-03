from datetime import date, timedelta

from habitual.analytics import (
    completion_series,
    day_state,
    habit_status,
    habit_strength,
    month_ring,
    overview_summary,
    smart_insight,
    thirty_day_grid,
    week_ring,
    weekly_habit_strength,
    weekly_month_ring,
    weekly_smart_insight,
    weekly_week_ring,
)
from habitual.frequency import not_scheduled_dates

D0 = date(2026, 1, 1)  # a Thursday


def days(*offsets):
    return {D0 + timedelta(days=o) for o in offsets}


def habit_info(id, completed, frozen, created_on, title="Habit", emoji="🔥"):
    return {
        "id": id, "title": title, "emoji": emoji,
        "completed": completed, "frozen": frozen, "created_on": created_on,
    }


# --- day_state -----------------------------------------------------------


def test_day_state_before_created():
    assert day_state(D0 - timedelta(days=1), set(), set(), D0, D0 + timedelta(days=5)) == "before_created"


def test_day_state_future():
    assert day_state(D0 + timedelta(days=6), set(), set(), D0, D0 + timedelta(days=5)) == "future"


def test_day_state_done():
    d = D0 + timedelta(days=1)
    assert day_state(d, {d}, set(), D0, D0 + timedelta(days=5)) == "done"


def test_day_state_frozen():
    d = D0 + timedelta(days=2)
    assert day_state(d, set(), {d}, D0, D0 + timedelta(days=5)) == "frozen"


def test_day_state_missed():
    d = D0 + timedelta(days=3)
    assert day_state(d, set(), set(), D0, D0 + timedelta(days=5)) == "missed"


# --- rings -----------------------------------------------------------------


def test_week_ring_established_habit_has_fixed_denominator_of_7():
    created_on = D0 - timedelta(days=30)
    completed = {D0 - timedelta(days=3), D0 - timedelta(days=1)}  # within Mon-Sun containing D0
    assert week_ring(completed, created_on, D0) == (2, 7)


def test_week_ring_brand_new_habit_denominator_is_still_7():
    # D0 (Thursday) created today: days before it existed just can't be
    # done — they count as 0 toward 7, not a shrunk denominator.
    assert week_ring({D0}, D0, D0) == (1, 7)


def test_month_ring_established_habit_has_fixed_denominator_of_days_in_month():
    created_on = date(2025, 12, 1)
    today = date(2026, 1, 15)
    completed = {date(2026, 1, 1), date(2026, 1, 10), date(2026, 1, 15)}
    assert month_ring(completed, created_on, today) == (3, 31)


def test_month_ring_brand_new_habit_denominator_is_still_days_in_month():
    created_on = date(2026, 1, 10)
    today = date(2026, 1, 15)
    completed = {date(2026, 1, 10), date(2026, 1, 12)}
    assert month_ring(completed, created_on, today) == (2, 31)


# --- habit strength ----------------------------------------------------


def test_habit_strength_fully_done_habit_is_100():
    assert habit_strength(days(*range(10)), set(), D0, D0 + timedelta(days=9)) == 100.0


def test_habit_strength_today_not_done_yet_does_not_lower_it():
    completed = days(*range(10))  # D0..D0+9 done, D0+10 not yet checked in
    today = D0 + timedelta(days=10)
    as_if_today_didnt_exist = habit_strength(completed, set(), D0, D0 + timedelta(days=9))
    assert habit_strength(completed, set(), D0, today) == as_if_today_didnt_exist


def test_habit_strength_checking_in_can_only_raise_it():
    completed = days(*range(10))
    today = D0 + timedelta(days=10)
    before = habit_strength(completed, set(), D0, today)
    after = habit_strength(completed | {today}, set(), D0, today)
    assert after >= before


def test_habit_strength_weighs_recent_misses_more_than_old_ones():
    full = days(*range(30))
    today = D0 + timedelta(days=29)
    old_miss = habit_strength(full - {D0 + timedelta(days=1)}, set(), D0, today)
    recent_miss = habit_strength(full - {D0 + timedelta(days=28)}, set(), D0, today)
    assert recent_miss < old_miss


def test_habit_strength_frozen_day_is_neutral_not_a_penalty():
    today = D0 + timedelta(days=4)
    with_freeze = habit_strength(days(0, 1, 3, 4), days(2), D0, today)
    without_freeze = habit_strength(days(0, 1, 3, 4), set(), D0, today)
    assert with_freeze > without_freeze


# --- habit status --------------------------------------------------------


def test_habit_status_streak_saved_overrides_everything():
    label, variant = habit_status(set(), set(), True, D0, D0, now_hour=9)
    assert (label, variant) == ("Streak saved", "saved")


def test_habit_status_on_track_when_checked_in_today():
    today = D0 + timedelta(days=3)
    label, variant = habit_status(days(0, 1, 2, 3), set(), False, D0, today, now_hour=9)
    assert (label, variant) == ("On track", "ontrack")


def test_habit_status_due_today_when_streak_small_and_recent_rate_healthy():
    today = D0 + timedelta(days=6)
    completed = days(0, 2, 4, 5)  # today (day 6) not done; recent rate 4/7 = 57%
    label, variant = habit_status(completed, set(), False, D0, today, now_hour=20)
    assert (label, variant) == ("Due today", "due")


def test_habit_status_at_risk_when_streak_at_stake_after_6pm():
    today = D0 + timedelta(days=3)
    completed = days(0, 1, 2)  # 3-day streak, today not done
    before_6pm = habit_status(completed, set(), False, D0, today, now_hour=17)
    at_6pm = habit_status(completed, set(), False, D0, today, now_hour=18)
    assert before_6pm == ("Due today", "due")
    assert at_6pm == ("At risk", "risk")


def test_habit_status_brand_new_habit_is_due_today_not_at_risk():
    # Created today, nothing checked in yet — too little history for the
    # 7-day consistency check to mean anything.
    label, variant = habit_status(set(), set(), False, D0, D0, now_hour=9)
    assert (label, variant) == ("Due today", "due")


def test_habit_status_at_risk_from_low_recent_rate_any_time_of_day():
    today = D0 + timedelta(days=6)
    completed = days(0)  # 1/7 done this week, streak is 0 (no streak at stake)
    label, variant = habit_status(completed, set(), False, D0, today, now_hour=9)
    assert (label, variant) == ("At risk", "risk")


# --- smart insight --------------------------------------------------------


def test_smart_insight_locked_before_14_days():
    assert smart_insight(set(), D0, D0 + timedelta(days=13)) is None


def test_smart_insight_flags_worst_weekday_when_deficit_is_large():
    # Every day done except both Mondays in a 15-day window (D0 is a Thursday).
    monday_offsets = {4, 11}
    completed = {D0 + timedelta(days=o) for o in range(15) if o not in monday_offsets}
    today = D0 + timedelta(days=14)
    assert smart_insight(completed, D0, today) == "You miss most often on Mondays."


def test_smart_insight_falls_back_to_month_over_month_when_no_weekday_stands_out():
    created_on = date(2025, 12, 15)  # a Monday
    today = date(2026, 1, 10)
    completed = {created_on + timedelta(days=o) for o in range(17)}  # Dec 15-31 all done
    # Jan 1-10 all missed. No single weekday is far below the ~63% overall
    # rate (worst is 50%, a 13-point gap — under the 20-point bar) because
    # misses land on every weekday roughly evenly across the two months.
    assert smart_insight(completed, created_on, today) == "Down 100% vs last month."


def test_smart_insight_falls_back_to_best_weekday_otherwise():
    # All 15 days done: no weekday deficit, and created this month so the
    # month-over-month gate can't pass (no prior-month overlap).
    completed = days(*range(15))
    today = D0 + timedelta(days=14)
    assert smart_insight(completed, D0, today) == "You're most consistent on Mondays."


# --- dashboard overview (Part B) -------------------------------------------


def test_thirty_day_grid_is_most_recent_first_and_excludes_before_created():
    today = D0 + timedelta(days=29)
    habit_a = habit_info(1, days(*range(30)), set(), D0)
    habit_b = habit_info(2, {D0 + timedelta(days=o) for o in range(15, 30)}, set(), D0 + timedelta(days=15))
    rows = thirty_day_grid([habit_a, habit_b], today)

    assert len(rows) == 30
    assert rows[0]["date"] == today
    assert rows[-1]["date"] == D0
    assert rows[0]["done_count"] == 2 and rows[0]["total_count"] == 2

    # The day before habit B existed: only habit A is applicable.
    row_before_b = next(r for r in rows if r["date"] == D0 + timedelta(days=14))
    assert row_before_b == {"date": D0 + timedelta(days=14), "states": ["done", "before_created"], "done_count": 1, "total_count": 1}

    row_at_b_creation = next(r for r in rows if r["date"] == D0 + timedelta(days=15))
    assert row_at_b_creation["total_count"] == 2
    assert row_at_b_creation["done_count"] == 2


def test_completion_series_is_chronological_and_computes_percent():
    today = D0 + timedelta(days=1)
    habit_a = habit_info(1, {D0}, set(), D0)  # day D0 done, today (D0+1) missed
    rows = thirty_day_grid([habit_a], today)
    series = completion_series(rows)

    assert len(series) == 30
    assert series[0] == 0.0  # oldest day in the window: before this habit existed
    assert series[-2] == 100.0  # D0: done
    assert series[-1] == 0.0  # today: missed


def test_overview_summary_today_progress():
    habit_a = habit_info(1, {D0}, set(), D0)
    habit_b = habit_info(2, set(), set(), D0)
    summary = overview_summary([habit_a, habit_b], D0)
    assert (summary["today_done"], summary["today_total"]) == (1, 2)


def test_overview_summary_habits_remaining_counts_undone_habits():
    habit_a = habit_info(1, {D0}, set(), D0)
    habit_b = habit_info(2, set(), set(), D0)
    habit_c = habit_info(3, set(), set(), D0)
    summary = overview_summary([habit_a, habit_b, habit_c], D0)
    assert summary["habits_remaining"] == 2


def test_overview_summary_habits_remaining_zero_when_all_done():
    habit_a = habit_info(1, {D0}, set(), D0)
    summary = overview_summary([habit_a], D0)
    assert summary["habits_remaining"] == 0


def test_overview_summary_habits_remaining_none_with_no_habits():
    summary = overview_summary([], D0)
    assert summary["habits_remaining"] is None


def test_overview_summary_month_success_aggregates_across_habits():
    today = date(2026, 1, 10)
    habit_a = habit_info(1, {date(2026, 1, d) for d in range(1, 11)}, set(), date(2025, 12, 1))  # 10/10
    habit_b = habit_info(2, set(), set(), date(2026, 1, 6))  # 0/5 (Jan 6-10)
    summary = overview_summary([habit_a, habit_b], today)
    assert summary["month_success"] == 67  # 10/15 = 66.67%


def test_overview_summary_best_streak_picks_the_max():
    today = D0 + timedelta(days=5)
    habit_a = habit_info(1, days(0, 1, 2, 3, 4, 5), set(), D0, title="Good")
    habit_b = habit_info(2, days(5), set(), D0, title="Newer")
    summary = overview_summary([habit_a, habit_b], today)
    assert summary["best_streak"]["id"] == 1
    assert summary["best_streak"]["current_streak"] == 6


def test_overview_summary_needs_attention_flags_worst_under_threshold():
    today = D0 + timedelta(days=6)
    habit_a = habit_info(1, days(0, 1, 2, 3, 4, 5, 6), set(), D0, title="Good")  # 100%
    habit_b = habit_info(2, days(0), set(), D0, title="Bad")  # 1/7
    summary = overview_summary([habit_a, habit_b], today)
    assert summary["needs_attention"]["id"] == 2


def test_overview_summary_needs_attention_none_when_all_above_threshold():
    today = D0 + timedelta(days=6)
    habit_a = habit_info(1, days(0, 1, 2, 3, 4, 5, 6), set(), D0)
    habit_b = habit_info(2, days(0, 1, 2, 3, 4, 5, 6), set(), D0)
    summary = overview_summary([habit_a, habit_b], today)
    assert summary["needs_attention"] is None


def test_overview_summary_needs_attention_excludes_brand_new_habit():
    # Created today — too little history for a 7-day rate to mean anything,
    # same guard as habit_status's "At risk" check.
    habit_a = habit_info(1, set(), set(), D0)
    summary = overview_summary([habit_a], D0)
    assert summary["needs_attention"] is None


# --- frequency-aware (Specific Days) ----------------------------------------
#
# D0 (2026-01-01) is a Thursday. MON/WED/FRI below are the first full
# Mon/Wed/Fri after it, used as a realistic Specific-Days schedule.

MON = D0 + timedelta(days=4)
TUE = MON + timedelta(days=1)
WED = MON + timedelta(days=2)
THU = MON + timedelta(days=3)
FRI = MON + timedelta(days=4)


def test_day_state_not_scheduled():
    not_scheduled = not_scheduled_dates("days", 1 | 4 | 16, MON, FRI)  # Mon/Wed/Fri mask
    assert day_state(TUE, set(), set(), MON, FRI, not_scheduled) == "not_scheduled"
    assert day_state(WED, set(), set(), MON, FRI, not_scheduled) == "missed"


def test_day_state_done_wins_over_not_scheduled():
    # A completion on a date that isn't scheduled (e.g. leftover from before
    # a frequency change) still shows as done, not not_scheduled.
    not_scheduled = {TUE}
    assert day_state(TUE, {TUE}, set(), MON, FRI, not_scheduled) == "done"


def test_week_ring_denominator_shrinks_for_specific_days():
    not_scheduled = not_scheduled_dates("days", 1 | 4 | 16, MON, MON + timedelta(days=6))
    completed = {MON, WED}
    assert week_ring(completed, MON, FRI, not_scheduled) == (2, 3)


def test_month_ring_denominator_shrinks_for_specific_days():
    month_end = date(2026, 1, 31)
    not_scheduled = not_scheduled_dates("days", 1 | 4 | 16, date(2026, 1, 1), month_end)
    numer, denom = month_ring({MON, WED}, date(2026, 1, 1), FRI, not_scheduled)
    assert numer == 2
    assert denom < 31


def test_habit_strength_skips_not_scheduled_days():
    # Tuesday (not scheduled) sitting between two completed scheduled days
    # shouldn't cost any decay - strength stays at the max.
    not_scheduled = {TUE}
    completed = {MON, WED}
    assert habit_strength(completed, set(), MON, WED, not_scheduled) == 100.0


def test_habit_status_not_due_today_is_resting():
    assert habit_status(set(), set(), False, MON, TUE, 10, not_due_today=True) == ("Not due today", "resting")


def test_habit_status_completed_today_wins_over_not_due():
    # Bonus/edge case: if today is somehow completed, that still wins.
    assert habit_status({TUE}, set(), False, MON, TUE, 10, not_due_today=True) == ("On track", "ontrack")


def test_smart_insight_weekday_gate_not_blocked_by_never_scheduled_weekdays():
    # Mon/Wed/Fri habit, 3 weeks of perfect attendance on all 3 scheduled
    # days, one single miss on a Wednesday - the never-scheduled weekdays
    # (Tue/Thu/Sat/Sun) must not block the weekday-breakdown insight.
    mask = 1 | 4 | 16
    scheduled_days = [MON + timedelta(days=7 * w + o) for w in range(3) for o in (0, 2, 4)]
    completed = set(scheduled_days) - {WED}
    today = scheduled_days[-1]
    not_scheduled = not_scheduled_dates("days", mask, MON, today)
    insight = smart_insight(completed, MON, today, not_scheduled)
    assert insight == "You miss most often on Wednesdays."


def test_thirty_day_grid_excludes_not_scheduled_from_total_count():
    not_scheduled = not_scheduled_dates("days", 1 | 4 | 16, MON, FRI)
    habit = {**habit_info(1, {MON, WED}, set(), MON), "not_scheduled": not_scheduled}
    grid = thirty_day_grid([habit], FRI)
    tue_row = next(r for r in grid if r["date"] == TUE)
    assert tue_row["total_count"] == 0
    assert tue_row["states"] == ["not_scheduled"]


def test_overview_summary_excludes_habits_not_due_today():
    not_scheduled = not_scheduled_dates("days", 1 | 4 | 16, MON, TUE)
    habit = {**habit_info(1, set(), set(), MON), "not_scheduled": not_scheduled}
    summary = overview_summary([habit], TUE)  # Tuesday isn't scheduled
    assert summary["today_total"] == 0
    assert summary["today_done"] == 0
    assert summary["habits_remaining"] == 0  # tracked, but nothing due - "All done today"


def test_overview_summary_habits_remaining_none_only_with_zero_habits_total():
    summary = overview_summary([], TUE)
    assert summary["habits_remaining"] is None


# --- frequency-aware (Weekly) ------------------------------------------------
#
# MON (2026-01-05) is a Monday - reused as the first week's anchor, same as
# tests/test_points.py's WEEK0.

WEEK0 = MON
WEEK1 = WEEK0 + timedelta(days=7)


def test_weekly_week_ring_is_literal_progress_toward_target():
    completed = {WEEK0, WEEK0 + timedelta(days=1)}
    today = WEEK0 + timedelta(days=2)
    assert weekly_week_ring(completed, today, 3) == (2, 3)


def test_weekly_month_ring_denominator_scales_with_overlapping_weeks():
    created_on = date(2026, 1, 1)
    today = date(2026, 1, 31)
    completed = {WEEK0, WEEK0 + timedelta(days=1), WEEK1}
    numer, denom = weekly_month_ring(completed, created_on, today, 2)
    assert numer == 3
    assert denom > 2 * 2  # more than 2 weeks overlap January


def test_weekly_habit_strength_full_when_every_week_hits_target():
    created_on = WEEK0
    today = WEEK1 + timedelta(days=1)
    completed = {WEEK0, WEEK0 + timedelta(days=1), WEEK1, WEEK1 + timedelta(days=1)}
    assert weekly_habit_strength(completed, 2, created_on, today) == 100.0


def test_weekly_habit_strength_in_progress_week_does_not_drag_score_down():
    created_on = WEEK0
    completed = {WEEK0, WEEK0 + timedelta(days=1)}  # week0 fully hit target
    today = WEEK1  # week1 just started, hasn't hit target yet
    assert weekly_habit_strength(completed, 2, created_on, today) == 100.0


def test_weekly_smart_insight_none_before_14_days():
    assert weekly_smart_insight(set(), 3, WEEK0, WEEK0 + timedelta(days=5)) is None


def test_weekly_smart_insight_reports_month_over_month_change():
    created_on = date(2025, 11, 1)
    today = date(2026, 1, 10)
    # Perfect hits every week in December, nothing in January so far.
    completed = set()
    cursor = date(2025, 12, 1)
    while cursor <= date(2025, 12, 31):
        completed.add(cursor)
        cursor += timedelta(days=7)
    insight = weekly_smart_insight(completed, 1, created_on, today)
    assert insight is not None
    assert "vs last month" in insight


def _weekly_habit_info(id, completed, created_on, target, title="Gym", emoji="💪"):
    return {
        "id": id, "title": title, "emoji": emoji,
        "completed": completed, "frozen": set(), "created_on": created_on,
        "frequency_type": "weekly", "frequency_target": target,
    }


def test_overview_summary_excludes_weekly_habits_from_today_total():
    weekly_habit = _weekly_habit_info(1, set(), WEEK0, 3)
    daily_habit = habit_info(2, set(), set(), WEEK0)
    summary = overview_summary([weekly_habit, daily_habit], WEEK0)
    assert summary["today_total"] == 1  # only the daily habit counts


def test_overview_summary_month_success_counts_weekly_habits_by_week():
    weekly_habit = _weekly_habit_info(1, {WEEK0, WEEK0 + timedelta(days=1)}, WEEK0, 2)
    today = WEEK0 + timedelta(days=1)
    summary = overview_summary([weekly_habit], today)
    assert summary["month_success"] == 100  # 2/2 in the one week so far


def test_overview_summary_best_streak_is_unit_aware_for_weekly():
    weekly_habit = _weekly_habit_info(1, {WEEK0, WEEK0 + timedelta(days=1)}, WEEK0, 2)
    today = WEEK0 + timedelta(days=1)
    summary = overview_summary([weekly_habit], today)
    assert summary["best_streak"] == {
        "id": 1, "title": "Gym", "emoji": "💪", "current_streak": 1, "streak_unit": "week",
    }


def test_overview_summary_needs_attention_skips_weekly_habits():
    weekly_habit = _weekly_habit_info(1, set(), WEEK0, 3)
    today = WEEK0 + timedelta(days=10)
    summary = overview_summary([weekly_habit], today)
    assert summary["needs_attention"] is None
