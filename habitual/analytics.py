"""Stats/insights for the habit analytics page and (later) the dashboard
overview. Pure functions only, same discipline as points.py — no DB access,
so every rule here is unit-testable and safe to reuse from multiple routes.
"""

import calendar
from datetime import date, timedelta

from habitual import points

STRENGTH_HALF_LIFE_DAYS = 10
WEEKDAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def day_state(
    d: date, completed: set[date], frozen: set[date], start_date: date, today: date,
    not_scheduled: set[date] = frozenset(),
) -> str:
    """Which of the 6 visual states a single day is in, for the 7-day row,
    the 5-week heatmap, the month calendar, and the dashboard's 30-day grid —
    one function so every grid agrees on the same vocabulary. `not_scheduled`
    (a Specific-Days habit's non-scheduled dates - always empty for Daily/
    Weekly) reads as "wasn't asked for", not "missed" - but an actual
    completion still wins and shows as "done" even on a day that wouldn't
    otherwise have been scheduled (e.g. history from before a frequency
    change), since the user genuinely did it."""
    if d > today:
        return "future"
    if d < start_date:
        return "before_created"
    if d in completed:
        return "done"
    if d in not_scheduled:
        return "not_scheduled"
    if d in frozen:
        return "frozen"
    return "missed"


def _monday_of(d: date) -> date:
    return d - timedelta(days=d.weekday())


def _month_bounds(d: date) -> tuple[date, date]:
    start = d.replace(day=1)
    last_day = calendar.monthrange(d.year, d.month)[1]
    return start, d.replace(day=last_day)


def week_ring(
    completed: set[date], created_on: date, today: date, not_scheduled: set[date] = frozenset()
) -> tuple[int, int]:
    """(done, scheduled days in the week) — Apple-activity-ring style, fills
    up as the week progresses. The denominator is always the full week's
    scheduled-day count (7 for Daily, fewer with `not_scheduled` set for
    Specific Days), even for a habit younger than the week: days before it
    existed (or not scheduled) just can't be done, same as any other missed
    day, so they're not "not applicable", they count toward the denominator
    as 0."""
    week_start = _monday_of(today)
    week_end = week_start + timedelta(days=6)
    range_start = max(week_start, created_on)
    numer = sum(1 for d in completed if range_start <= d <= today)
    not_scheduled_this_week = sum(1 for d in not_scheduled if week_start <= d <= week_end)
    return numer, 7 - not_scheduled_this_week


def month_ring(
    completed: set[date], created_on: date, today: date, not_scheduled: set[date] = frozenset()
) -> tuple[int, int]:
    """Same idea as week_ring, scoped to the calendar month — denominator is
    the number of days in the month, minus any that aren't scheduled."""
    month_start, month_end = _month_bounds(today)
    range_start = max(month_start, created_on)
    numer = sum(1 for d in completed if range_start <= d <= today)
    not_scheduled_this_month = sum(1 for d in not_scheduled if month_start <= d <= month_end)
    return numer, month_end.day - not_scheduled_this_month


def habit_strength(
    completed: set[date], frozen: set[date], start_date: date, today: date,
    not_scheduled: set[date] = frozenset(),
) -> float:
    """Exponentially-weighted completion score (0-100) — recent days count
    more than old ones, unlike points.success_rate's flat lifetime average.
    Today only counts once it's actually completed (same rule as
    success_rate), so the score never drops just because a new day started
    with nothing checked in yet. `not_scheduled` days are skipped entirely,
    same as `frozen` days - no score contribution, no decay step consumed."""
    decay = 0.5 ** (1 / STRENGTH_HALF_LIFE_DAYS)
    end = today if today in completed else today - timedelta(days=1)
    if end < start_date:
        return 0.0

    score = None
    cursor = start_date
    while cursor <= end:
        if cursor in frozen or cursor in not_scheduled:
            cursor += timedelta(days=1)
            continue
        value = 100.0 if cursor in completed else 0.0
        score = value if score is None else decay * score + (1 - decay) * value
        cursor += timedelta(days=1)
    return score if score is not None else 0.0


def _plain_rate(
    completed: set[date], start: date, end: date, not_scheduled: set[date] = frozenset()
) -> float:
    """Flat completion rate over an already-closed [start, end] range — no
    "today doesn't count yet" nuance, since both callers here only ever pass
    fully-elapsed ranges. `not_scheduled` dates are excluded from both the
    numerator and denominator, same as success_rate's `scheduled` param."""
    total_days = (end - start).days + 1 - sum(1 for d in not_scheduled if start <= d <= end)
    if total_days <= 0:
        return 0.0
    done = sum(1 for d in completed if start <= d <= end and d not in not_scheduled)
    return (done / total_days) * 100


def habit_status(
    completed: set[date],
    frozen: set[date],
    froze_used_yesterday: bool,
    created_on: date,
    today: date,
    now_hour: int,
    not_due_today: bool = False,
    not_scheduled: set[date] = frozenset(),
) -> tuple[str, str]:
    """(label, variant) for the status pill. variant is one of
    "saved" | "risk" | "due" | "ontrack" | "resting". now_hour is passed in
    (rather than read from the clock) so this stays pure and testable — the
    route supplies it from utils.time.local_now(user).hour. `not_due_today`
    (today isn't scheduled for a Specific-Days habit, or this week's target
    is already met for a Weekly one) is false for every existing caller."""
    if froze_used_yesterday:
        return "Streak saved", "saved"

    if today in completed:
        return "On track", "ontrack"

    if not_due_today:
        return "Not due today", "resting"

    streak_at_stake = points.current_streak(completed, frozen, today)
    week_start = max(today - timedelta(days=6), created_on)
    window_days = (today - week_start).days + 1
    rate7 = _plain_rate(completed, week_start, today, not_scheduled)

    if streak_at_stake >= 3 and now_hour >= 18:
        return "At risk", "risk"
    # A brand-new habit's first day or two is too little history for a
    # "consistency dropping" signal to mean anything — it would otherwise
    # flag every just-created habit as "At risk" before it's even had a
    # chance to be checked in once.
    if window_days >= 3 and rate7 < 50:
        return "At risk", "risk"
    return "Due today", "due"


STRENGTH_HALF_LIFE_WEEKS = 4


def weekly_week_ring(completed: set[date], today: date, target: int) -> tuple[int, int]:
    """(done this week, target) - a Weekly habit's week ring is literal
    progress toward its target, not a fraction of 7 (there's no single
    "due" day to count against)."""
    start = points.week_start(today)
    done = sum(1 for d in completed if start <= d <= today)
    return done, target


def weekly_month_ring(completed: set[date], created_on: date, today: date, target: int) -> tuple[int, int]:
    """Same idea scoped to the calendar month - the denominator is `target`
    times however many of the habit's weeks have at least one day inside
    the month (bounded below by `created_on`, so a habit born mid-month
    isn't charged for weeks it didn't exist in)."""
    month_start, month_end = _month_bounds(today)
    range_start = max(month_start, created_on)
    numer = sum(1 for d in completed if range_start <= d <= today)
    weeks = set()
    cursor = range_start
    while cursor <= month_end:
        weeks.add(points.week_start(cursor))
        cursor += timedelta(days=1)
    return numer, len(weeks) * target


def weekly_habit_strength(completed: set[date], target: int, created_on: date, today: date) -> float:
    """Exponentially-weighted weekly completion score (0-100), one decay
    step per week instead of per day - each week scored
    min(completions, target) / target * 100. The current week is only
    scored once it's already hit target (same "today only counts once it's
    done" grace `habit_strength` gives, one granularity up), so the score
    never drops just because a week is still in progress."""
    decay = 0.5 ** (1 / STRENGTH_HALF_LIFE_WEEKS)
    counts = points.weekly_completions(completed)
    first_week = points.week_start(created_on)
    this_week = points.week_start(today)
    end_week = this_week if counts.get(this_week, 0) >= target else this_week - timedelta(days=7)
    if end_week < first_week or target <= 0:
        return 0.0

    score = None
    cursor = first_week
    while cursor <= end_week:
        value = min(counts.get(cursor, 0), target) / target * 100
        score = value if score is None else decay * score + (1 - decay) * value
        cursor += timedelta(days=7)
    return score if score is not None else 0.0


def weekly_smart_insight(completed: set[date], target: int, created_on: date, today: date) -> str | None:
    """Weekly's smart-insight line skips the weekday-breakdown signal
    entirely (which day of the week varies habit to habit - not meaningful
    for a "hit it 3x, any days" habit) and only ever surfaces month-over-
    month, driven by `weekly_success_rate` instead of the daily one. None
    means "show the unlocks-after-14-days message", same convention as
    `smart_insight`."""
    if (today - created_on).days < 14:
        return None

    month_start, _ = _month_bounds(today)
    last_month_end = month_start - timedelta(days=1)
    last_month_start, _ = _month_bounds(last_month_end)
    overlap_start = max(last_month_start, created_on)
    overlap_days = (last_month_end - overlap_start).days + 1

    if not (today.day >= 7 and overlap_days >= 7):
        return None

    this_month_start = max(month_start, created_on)
    this_rate = points.weekly_success_rate(completed, this_month_start, today, target)
    last_rate = points.weekly_success_rate(completed, overlap_start, last_month_end, target)
    if abs(this_rate - last_rate) >= 15:
        direction = "Up" if this_rate >= last_rate else "Down"
        return f"{direction} {round(abs(this_rate - last_rate))}% vs last month."
    return None


def _weekday_counts(
    completed: set[date], created_on: date, today: date, not_scheduled: set[date] = frozenset()
) -> dict[int, tuple[int, int]]:
    """Only weekdays that actually occur as scheduled dates in range appear
    in the result - a Specific-Days habit's never-scheduled weekdays are
    simply absent (rather than stuck at total=0 forever), so the
    `weekday_gate` below isn't permanently blocked by days nobody runs on."""
    done = [0] * 7
    total = [0] * 7
    cursor = created_on
    while cursor <= today:
        if cursor not in not_scheduled:
            wd = cursor.weekday()
            total[wd] += 1
            if cursor in completed:
                done[wd] += 1
        cursor += timedelta(days=1)
    return {wd: (done[wd], total[wd]) for wd in range(7) if total[wd] > 0}


def _month_over_month(
    completed: set[date], created_on: date, today: date, not_scheduled: set[date] = frozenset()
) -> tuple[bool, float, float]:
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
    this_rate = points.success_rate(completed, this_month_start, today, not_scheduled)
    last_rate = _plain_rate(completed, overlap_start, last_month_end, not_scheduled)
    return True, this_rate, last_rate


def smart_insight(
    completed: set[date], created_on: date, today: date, not_scheduled: set[date] = frozenset()
) -> str | None:
    """One line, prioritized toward the most actionable signal. None means
    "show the unlocks-after-14-days message" (always the case before day 14;
    past day 14 only in the degenerate case where no gate clears)."""
    if (today - created_on).days < 14:
        return None

    overall_rate = points.success_rate(completed, created_on, today, not_scheduled)
    counts = _weekday_counts(completed, created_on, today, not_scheduled)
    weekday_gate = bool(counts) and all(total >= 2 for _done, total in counts.values())

    if weekday_gate:
        rates = {wd: (done / total * 100) for wd, (done, total) in counts.items()}
        worst_wd = min(rates, key=rates.get)
        if overall_rate - rates[worst_wd] >= 20:
            return f"You miss most often on {WEEKDAY_NAMES[worst_wd]}s."

    mom_gate, this_rate, last_rate = _month_over_month(completed, created_on, today, not_scheduled)
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
    habits that didn't exist yet that day, or weren't scheduled on it
    (`habit_infos[i].get("not_scheduled")`, empty for Daily/Weekly) - same
    "not applicable" treatment either way, so a Specific-Days habit's rest
    days don't drag the ratio down."""
    rows = []
    for offset in range(30):
        d = today - timedelta(days=offset)
        states = [
            day_state(d, h["completed"], h["frozen"], h["created_on"], today, h.get("not_scheduled", set()))
            for h in habit_infos
        ]
        rows.append({
            "date": d,
            "states": states,
            "done_count": sum(1 for s in states if s == "done"),
            "total_count": sum(1 for s in states if s not in ("before_created", "not_scheduled")),
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
    # A Specific-Days habit not scheduled today isn't "pending" - it's just
    # resting, so it's excluded from both today_total and today_done (not
    # counted as "0 done out of 1 still-counted"). A Weekly habit has no
    # single "due today" day at all, so it's excluded entirely - it shows
    # up only in the header's separate weekly-progress chips.
    due_today = [
        h for h in habit_infos
        if h.get("frequency_type") != "weekly" and today not in h.get("not_scheduled", set())
    ]
    today_done = sum(1 for h in due_today if today in h["completed"])

    month_start, _ = _month_bounds(today)
    month_done = 0
    month_applicable = 0
    for h in habit_infos:
        effective_start = h.get("effective_start", h["created_on"])
        start = max(month_start, effective_start)
        if start > today:
            continue
        if h.get("frequency_type") == "weekly":
            target = h.get("frequency_target") or 1
            weeks = set()
            cursor = start
            while cursor <= today:
                weeks.add(points.week_start(cursor))
                cursor += timedelta(days=1)
            month_applicable += len(weeks) * target
            month_done += sum(1 for d in h["completed"] if start <= d <= today)
            continue
        not_scheduled = h.get("not_scheduled", set())
        not_scheduled_in_range = sum(1 for d in not_scheduled if start <= d <= today)
        month_applicable += (today - start).days + 1 - not_scheduled_in_range
        month_done += sum(1 for d in h["completed"] if start <= d <= today and d not in not_scheduled)
    month_success = round((month_done / month_applicable) * 100) if month_applicable else 0

    # A Weekly habit's streak is counted in weeks, not days - comparing the
    # two raw counts with a plain max() is still the simplest honest way to
    # pick "the best one", as long as the copy names the right unit, so the
    # winning habit also carries `streak_unit` for the template to read.
    # `floor` (effective_start, see habits.py) keeps a frequency edit's
    # restart from resurrecting a pre-edit streak on the dashboard too.
    best_streak = None
    for h in habit_infos:
        effective_start = h.get("effective_start", h["created_on"])
        if h.get("frequency_type") == "weekly":
            floor = points.week_start(effective_start)
            streak = points.weekly_streak(h["completed"], h.get("frequency_target") or 1, today, floor=floor)
            unit = "week"
        else:
            bridge = h["frozen"] | h.get("not_scheduled", set())
            streak = points.current_streak(h["completed"], bridge, today, effective_start)
            unit = "day"
        if best_streak is None or streak > best_streak["current_streak"]:
            best_streak = {
                "id": h["id"], "title": h["title"], "emoji": h["emoji"],
                "current_streak": streak, "streak_unit": unit,
            }

    # Same reasoning as habit_status's window guard: a habit only a day or
    # two old doesn't have enough history for a 7-day rate to mean anything,
    # so it can't be flagged as "needs attention" yet. A 7-day lookback
    # doesn't map onto a weekly target either, so Weekly habits are skipped
    # here entirely - omitting the signal beats showing a misleading one.
    needs_attention = None
    worst_rate = None
    for h in habit_infos:
        if h.get("frequency_type") == "weekly":
            continue
        window_start = max(today - timedelta(days=6), h.get("effective_start", h["created_on"]))
        window_days = (today - window_start).days + 1
        if window_days < MIN_WINDOW_DAYS_FOR_ATTENTION:
            continue
        rate7 = _plain_rate(h["completed"], window_start, today, h.get("not_scheduled", set()))
        if rate7 < NEEDS_ATTENTION_THRESHOLD and (worst_rate is None or rate7 < worst_rate):
            worst_rate = rate7
            needs_attention = {"id": h["id"], "title": h["title"], "emoji": h["emoji"], "rate7": round(rate7)}

    return {
        "today_done": today_done,
        "today_total": len(due_today),
        # None (not 0) when there's nothing to track at all, so the header
        # countdown can tell "no habits yet" apart from "all done today"
        # (which also covers "nothing due today" - due_today can be empty
        # while habit_infos isn't, on an all-resting day).
        "habits_remaining": (len(due_today) - today_done) if habit_infos else None,
        "month_success": month_success,
        "best_streak": best_streak,
        "needs_attention": needs_attention,
    }
