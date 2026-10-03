"""Regression tripwire for the habit-frequency feature (see
.claude/plans/spicy-stargazing-valley.md). Every value here is the CURRENT,
pre-frequency behavior of points.py/analytics.py, captured for a realistic
Daily habit history. Frequency work will add new optional parameters
(`floor`, `not_scheduled`, `scheduled`, ...) to several of these functions -
every one of them must default to exactly this behavior when omitted, since
every existing Daily habit (and every call site that hasn't been touched yet)
omits them. If any assertion here ever changes, a "no behavior change for
Daily habits" guarantee from the plan has been broken.
"""

import pytest

from datetime import date, timedelta

from habitual import analytics, points

D0 = date(2026, 1, 1)


def day(offset):
    return D0 + timedelta(days=offset)


# --- scenario 1: a clean streak with one genuine (unfrozen) miss -----------

SIMPLE_COMPLETED = {day(o) for o in (0, 1, 2, 4, 5, 6)}  # day 3 missed
SIMPLE_TODAY = day(6)


def test_current_streak_unchanged():
    assert points.current_streak(SIMPLE_COMPLETED, set(), SIMPLE_TODAY) == 3


def test_longest_streak_unchanged():
    assert points.longest_streak(SIMPLE_COMPLETED, set(), D0, SIMPLE_TODAY) == 3


def test_success_rate_unchanged():
    assert points.success_rate(SIMPLE_COMPLETED, D0, SIMPLE_TODAY) == pytest.approx(85.71428571428571)


def test_habit_strength_unchanged():
    assert analytics.habit_strength(SIMPLE_COMPLETED, set(), D0, SIMPLE_TODAY) == pytest.approx(94.56058868989635)


def test_week_ring_unchanged():
    assert analytics.week_ring(SIMPLE_COMPLETED, D0, SIMPLE_TODAY) == (3, 7)


def test_month_ring_unchanged():
    assert analytics.month_ring(SIMPLE_COMPLETED, D0, SIMPLE_TODAY) == (6, 31)


def test_day_state_unchanged():
    assert analytics.day_state(day(3), SIMPLE_COMPLETED, set(), D0, SIMPLE_TODAY) == "missed"
    assert analytics.day_state(day(6), SIMPLE_COMPLETED, set(), D0, SIMPLE_TODAY) == "done"
    assert analytics.day_state(day(7), SIMPLE_COMPLETED, set(), D0, SIMPLE_TODAY) == "future"


def test_habit_status_unchanged():
    assert analytics.habit_status(SIMPLE_COMPLETED, set(), False, D0, SIMPLE_TODAY, 10) == ("On track", "ontrack")


# --- scenario 2: a freeze bridging a missed day -----------------------------

FROZEN_COMPLETED = {day(o) for o in (0, 1, 2, 3, 4, 6, 7, 8, 9)}
FROZEN_DATES = {day(5)}
FROZEN_TODAY = day(9)


def test_current_streak_with_freeze_unchanged():
    assert points.current_streak(FROZEN_COMPLETED, FROZEN_DATES, FROZEN_TODAY) == 9


def test_longest_streak_with_freeze_unchanged():
    assert points.longest_streak(FROZEN_COMPLETED, FROZEN_DATES, D0, FROZEN_TODAY) == 9


def test_success_rate_with_freeze_unchanged():
    assert points.success_rate(FROZEN_COMPLETED, D0, FROZEN_TODAY) == 90.0


def test_habit_strength_with_freeze_unchanged():
    assert analytics.habit_strength(FROZEN_COMPLETED, FROZEN_DATES, D0, FROZEN_TODAY) == 100.0


def test_day_state_frozen_day_unchanged():
    assert analytics.day_state(day(5), FROZEN_COMPLETED, FROZEN_DATES, D0, FROZEN_TODAY) == "frozen"


def test_freeze_available_unchanged():
    assert points.freeze_available(FROZEN_COMPLETED, FROZEN_DATES, FROZEN_TODAY + timedelta(days=1)) is False


# --- scenario 3: a 20-day history (insights + dashboard overview) ----------

PATTERNED_COMPLETED = {day(o) for o in range(20) if o % 4 != 0}  # every 4th day missed
PATTERNED_TODAY = day(19)
HABIT_INFOS = [{
    "id": 1, "title": "Read", "emoji": "📚",
    "completed": PATTERNED_COMPLETED, "frozen": set(), "created_on": D0,
}]


def test_smart_insight_unchanged():
    assert analytics.smart_insight(PATTERNED_COMPLETED, D0, PATTERNED_TODAY) == "You're most consistent on Wednesdays."


def test_thirty_day_grid_unchanged():
    grid = analytics.thirty_day_grid(HABIT_INFOS, PATTERNED_TODAY)
    assert grid[0] == {"date": day(19), "states": ["done"], "done_count": 1, "total_count": 1}
    assert grid[19] == {"date": day(0), "states": ["missed"], "done_count": 0, "total_count": 1}


def test_overview_summary_unchanged():
    summary = analytics.overview_summary(HABIT_INFOS, PATTERNED_TODAY)
    assert summary == {
        "today_done": 1,
        "today_total": 1,
        "habits_remaining": 0,
        "month_success": 75,
        "best_streak": {"id": 1, "title": "Read", "emoji": "📚", "current_streak": 3, "streak_unit": "day"},
        "needs_attention": None,
    }
