"""Stats/insights for the habit analytics page and (later) the dashboard
overview. Pure functions only, same discipline as points.py — no DB access,
so every rule here is unit-testable and safe to reuse from multiple routes.
"""

import calendar
from datetime import date, timedelta

from habitual import points

STRENGTH_HALF_LIFE_DAYS = 10
WEEKDAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def day_state(d: date, completed: set[date], frozen: set[date], start_date: date, today: date) -> str:
    """Which of the 5 visual states a single day is in, for the 7-day row,
    the 5-week heatmap, and (later) the dashboard's 30-day grid — one
    function so every grid agrees on the same vocabulary."""
    if d > today:
        return "future"
    if d < start_date:
        return "before_created"
    if d in completed:
        return "done"
    if d in frozen:
        return "frozen"
    return "missed"


def _monday_of(d: date) -> date:
    return d - timedelta(days=d.weekday())


def _month_bounds(d: date) -> tuple[date, date]:
    start = d.replace(day=1)
    last_day = calendar.monthrange(d.year, d.month)[1]
    return start, d.replace(day=last_day)


def week_ring(completed: set[date], created_on: date, today: date) -> tuple[int, int]:
    """(done, 7) — Apple-activity-ring style, fills up as the week
    progresses. The denominator is always 7, even for a habit younger than
    the week: days before it existed just can't be done, same as any other
    missed day, so they're not "not applicable", they're 0 toward 7."""
    week_start = _monday_of(today)
    range_start = max(week_start, created_on)
    numer = sum(1 for d in completed if range_start <= d <= today)
    return numer, 7


def month_ring(completed: set[date], created_on: date, today: date) -> tuple[int, int]:
    """Same idea as week_ring, scoped to the calendar month — denominator is
    always the number of days in the month."""
    month_start, month_end = _month_bounds(today)
    range_start = max(month_start, created_on)
    numer = sum(1 for d in completed if range_start <= d <= today)
    return numer, month_end.day


def habit_strength(completed: set[date], frozen: set[date], start_date: date, today: date) -> float:
    """Exponentially-weighted completion score (0-100) — recent days count
    more than old ones, unlike points.success_rate's flat lifetime average.
    Today only counts once it's actually completed (same rule as
    success_rate), so the score never drops just because a new day started
    with nothing checked in yet."""
    decay = 0.5 ** (1 / STRENGTH_HALF_LIFE_DAYS)
    end = today if today in completed else today - timedelta(days=1)
    if end < start_date:
        return 0.0

    score = None
    cursor = start_date
    while cursor <= end:
        if cursor in frozen:
            cursor += timedelta(days=1)
            continue
        value = 100.0 if cursor in completed else 0.0
        score = value if score is None else decay * score + (1 - decay) * value
        cursor += timedelta(days=1)
    return score if score is not None else 0.0


def _plain_rate(completed: set[date], start: date, end: date) -> float:
    """Flat completion rate over an already-closed [start, end] range — no
    "today doesn't count yet" nuance, since both callers here only ever pass
    fully-elapsed ranges."""
    total_days = (end - start).days + 1
    if total_days <= 0:
        return 0.0
    done = sum(1 for d in completed if start <= d <= end)
    return (done / total_days) * 100


def habit_status(
    completed: set[date],
    frozen: set[date],
    froze_used_yesterday: bool,
    created_on: date,
    today: date,
    now_hour: int,
) -> tuple[str, str]:
    """(label, variant) for the status pill. variant is one of
    "saved" | "risk" | "due" | "ontrack". now_hour is passed in (rather than
    read from the clock) so this stays pure and testable — the route supplies
    it from utils.time.local_now(user).hour."""
    if froze_used_yesterday:
        return "Streak saved", "saved"

    if today in completed:
        return "On track", "ontrack"

    streak_at_stake = points.current_streak(completed, frozen, today)
    week_start = max(today - timedelta(days=6), created_on)
    window_days = (today - week_start).days + 1
    rate7 = _plain_rate(completed, week_start, today)

    if streak_at_stake >= 3 and now_hour >= 18:
        return "At risk", "risk"
    # A brand-new habit's first day or two is too little history for a
    # "consistency dropping" signal to mean anything — it would otherwise
    # flag every just-created habit as "At risk" before it's even had a
    # chance to be checked in once.
    if window_days >= 3 and rate7 < 50:
        return "At risk", "risk"
    return "Due today", "due"


def _weekday_counts(completed: set[date], created_on: date, today: date) -> dict[int, tuple[int, int]]:
    done = [0] * 7
    total = [0] * 7
    cursor = created_on
    while cursor <= today:
        wd = cursor.weekday()
        total[wd] += 1
        if cursor in completed:
            done[wd] += 1
        cursor += timedelta(days=1)
    return {wd: (done[wd], total[wd]) for wd in range(7)}


def _month_over_month(completed: set[date], created_on: date, today: date) -> tuple[bool, float, float]:
    """(gate_passes, this_month_rate, last_month_rate). Gate requires being
    at least 7 days into the current month AND the habit having existed for
    at least 7 days of last month too, so the comparison has enough data on
    both sides to mean something."""
    month_start, _ = _month_bounds(today)
    last_month_end = month_start - timedelta(days=1)
    last_month_start, _ = _month_bounds(last_month_end)

    overlap_start = max(last_month_start, created_on)
    overlap_days = (last_month_end - overlap_start).days + 1

    gate = today.day >= 7 and overlap_days >= 7
    if not gate:
        return False, 0.0, 0.0

    this_month_start = max(month_start, created_on)
    this_rate = points.success_rate(completed, this_month_start, today)
    last_rate = _plain_rate(completed, overlap_start, last_month_end)
    return True, this_rate, last_rate


def smart_insight(completed: set[date], created_on: date, today: date) -> str | None:
    """One line, prioritized toward the most actionable signal. None means
    "show the unlocks-after-14-days message" (always the case before day 14;
    past day 14 only in the degenerate case where no gate clears)."""
    if (today - created_on).days < 14:
        return None

    overall_rate = points.success_rate(completed, created_on, today)
    counts = _weekday_counts(completed, created_on, today)
    weekday_gate = all(total >= 2 for _done, total in counts.values())

    if weekday_gate:
        rates = {wd: (done / total * 100) for wd, (done, total) in counts.items()}
        worst_wd = min(rates, key=rates.get)
        if overall_rate - rates[worst_wd] >= 20:
            return f"You miss most often on {WEEKDAY_NAMES[worst_wd]}s."

    mom_gate, this_rate, last_rate = _month_over_month(completed, created_on, today)
    if mom_gate and abs(this_rate - last_rate) >= 15:
        direction = "Up" if this_rate >= last_rate else "Down"
        return f"{direction} {round(abs(this_rate - last_rate))}% vs last month."

    if weekday_gate:
        best_wd = max(rates, key=rates.get)
        return f"You're most consistent on {WEEKDAY_NAMES[best_wd]}s."

    return None


# --- dashboard overview (Part B) -------------------------------------------
#
# Every function below takes `habit_infos`: a list of dicts, one per active
# habit, each shaped {"id", "title", "emoji", "completed", "frozen",
# "created_on"} — the same per-habit state the rest of this module works
# with, just bundled so these can aggregate across habits in one pass.

NEEDS_ATTENTION_THRESHOLD = 70
MIN_WINDOW_DAYS_FOR_ATTENTION = 3


def thirty_day_grid(habit_infos: list[dict], today: date) -> list[dict]:
    """30 rows, most-recent-first (matches the dashboard's reading order).
    Each row: {"date", "states" (one day_state per habit, same order as
    habit_infos), "done_count", "total_count"}. `total_count` excludes
    habits that didn't exist yet that day, same as success_rate's
    treatment — a habit created yesterday doesn't drag older days down."""
    rows = []
    for offset in range(30):
        d = today - timedelta(days=offset)
        states = [
            day_state(d, h["completed"], h["frozen"], h["created_on"], today) for h in habit_infos
        ]
        rows.append({
            "date": d,
            "states": states,
            "done_count": sum(1 for s in states if s == "done"),
            "total_count": sum(1 for s in states if s != "before_created"),
        })
    return rows


def completion_series(grid_rows: list[dict]) -> list[float]:
    """Daily completion % for the line chart, oldest first (chronological
    reading order) — the opposite order from thirty_day_grid's rows."""
    chronological = list(reversed(grid_rows))
    return [
        (row["done_count"] / row["total_count"] * 100) if row["total_count"] else 0.0
        for row in chronological
    ]


def overview_summary(habit_infos: list[dict], today: date) -> dict:
    """Today's progress, this month's aggregate success rate, the habit
    with the best current streak, and the one most needing attention."""
    today_done = sum(1 for h in habit_infos if today in h["completed"])

    month_start, _ = _month_bounds(today)
    month_done = 0
    month_applicable = 0
    for h in habit_infos:
        start = max(month_start, h["created_on"])
        if start > today:
            continue
        month_applicable += (today - start).days + 1
        month_done += sum(1 for d in h["completed"] if start <= d <= today)
    month_success = round((month_done / month_applicable) * 100) if month_applicable else 0

    best_streak = None
    for h in habit_infos:
        streak = points.current_streak(h["completed"], h["frozen"], today)
        if best_streak is None or streak > best_streak["current_streak"]:
            best_streak = {"id": h["id"], "title": h["title"], "emoji": h["emoji"], "current_streak": streak}

    # Same reasoning as habit_status's window guard: a habit only a day or
    # two old doesn't have enough history for a 7-day rate to mean anything,
    # so it can't be flagged as "needs attention" yet.
    needs_attention = None
    worst_rate = None
    for h in habit_infos:
        window_start = max(today - timedelta(days=6), h["created_on"])
        window_days = (today - window_start).days + 1
        if window_days < MIN_WINDOW_DAYS_FOR_ATTENTION:
            continue
        rate7 = _plain_rate(h["completed"], window_start, today)
        if rate7 < NEEDS_ATTENTION_THRESHOLD and (worst_rate is None or rate7 < worst_rate):
            worst_rate = rate7
            needs_attention = {"id": h["id"], "title": h["title"], "emoji": h["emoji"], "rate7": round(rate7)}

    return {
        "today_done": today_done,
        "today_total": len(habit_infos),
        "month_success": month_success,
        "best_streak": best_streak,
        "needs_attention": needs_attention,
    }
