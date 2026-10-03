"""All points/streak/freeze rules. Pure functions only — no DB access — so the
rules can be tested in isolation and reused for both live check-ins and
retroactive recomputation (e.g. when a freeze is applied after the fact).

Callers pass the full set of completed dates and frozen dates for a habit;
every function here derives its answer from that final state, never from the
order actions happened in. That's what makes "freeze applied after check-in"
and "freeze applied before check-in" converge to the same points.
"""

from datetime import date, timedelta

BASE_POINTS = 5
FREEZE_COST = 50
MAX_UNUSED_FREEZES = 2


def milestone_bonus(streak_day: int) -> int:
    """Bonus points for a day that extends the streak to `streak_day`."""
    if streak_day == 7:
        return 10
    if streak_day == 14:
        return 20
    if streak_day >= 30 and streak_day % 30 == 0:
        return 30
    return 0


def next_milestone(streak_day: int) -> int:
    """Smallest milestone day >= `streak_day` — the target the milestone
    progress ring counts up to. Full on the exact milestone day; rolls to
    the next target the day after (e.g. day 31 -> 60), same restart rule as
    the bonus itself."""
    if streak_day <= 7:
        return 7
    if streak_day <= 14:
        return 14
    if streak_day <= 30:
        return 30
    return ((streak_day + 29) // 30) * 30


def milestone_label(streak_day: int) -> str | None:
    """User-facing name for the milestone hit on `streak_day`, or None."""
    if streak_day == 7:
        return "Week streak bonus!"
    if streak_day == 14:
        return "Two-week streak bonus!"
    if streak_day >= 30 and streak_day % 30 == 0:
        return "Milestone bonus!"
    return None


def points_for_day(streak_day: int) -> int:
    """Total points for completing day `streak_day` of a streak."""
    return BASE_POINTS + milestone_bonus(streak_day)


def _streak_ending_at(
    completed: set[date], frozen: set[date], end_date: date, floor: date | None = None
) -> int:
    """Consecutive completed-day count ending at `end_date`. Frozen days bridge
    a gap without breaking the chain or adding to the count. `floor` (None for
    every habit whose frequency has never been edited - a true no-op, since
    there's never data before `created_on` anyway) stops the walk there,
    treating the day before `floor` as neither completed nor frozen - the
    restart mechanism behind a frequency edit: a streak broken before the
    edit can never bridge across it and resurrect itself."""
    cursor = end_date
    count = 0
    while (floor is None or cursor >= floor) and (cursor in completed or cursor in frozen):
        if cursor in completed:
            count += 1
        cursor -= timedelta(days=1)
    return count


def current_streak(
    completed: set[date], frozen: set[date], today: date, floor: date | None = None
) -> int:
    """Streak as of `today`. If today isn't done yet, this is yesterday's
    streak (so the card doesn't zero out the moment the day rolls over)."""
    end = today if today in completed else today - timedelta(days=1)
    return _streak_ending_at(completed, frozen, end, floor)


def streak_day_on(
    completed: set[date], frozen: set[date], target: date, floor: date | None = None
) -> int:
    """Which streak day `target` was, given the *current* completed/frozen
    state. 0 if `target` isn't a completed date, or if it's before `floor`
    (predates a frequency-edit restart). Used to (re)price a specific
    check-in's points regardless of when a bridging freeze was added."""
    if target not in completed or (floor is not None and target < floor):
        return 0
    return _streak_ending_at(completed, frozen, target, floor)


def points_for_date(completed: set[date], frozen: set[date], target: date) -> int:
    """Points a completed `target` date is worth, given current state."""
    return points_for_day(streak_day_on(completed, frozen, target))


def longest_streak(completed: set[date], frozen: set[date], start_date: date, today: date) -> int:
    """Longest streak ever, same bridging definition as `current_streak`."""
    running = 0
    best = 0
    cursor = start_date
    while cursor <= today:
        if cursor in completed:
            running += 1
            best = max(best, running)
        elif cursor in frozen:
            pass
        else:
            running = 0
        cursor += timedelta(days=1)
    return best


def streak_length_through(completed: set[date], frozen: set[date], target: date) -> int:
    """Length (completed-day count) of the consecutive completed/frozen chain
    that `target` belongs to - used for the "freeze_saver" badge (used a
    freeze that later carried a streak to day 7). 0 if `target` is neither
    completed nor frozen."""
    if target not in completed and target not in frozen:
        return 0
    end = target
    while (end + timedelta(days=1)) in completed or (end + timedelta(days=1)) in frozen:
        end += timedelta(days=1)
    return _streak_ending_at(completed, frozen, end)


def success_rate(
    completed: set[date], start_date: date, today: date, not_scheduled: set[date] = frozenset()
) -> float:
    """Percent of elapsed days completed. Today only counts toward the
    denominator once it's actually completed, so an unfinished "today"
    doesn't drag the rate down. `not_scheduled` (a Specific-Days habit's
    non-due dates in range - empty for every existing caller) is excluded
    from both the numerator and denominator, same convention as
    analytics.py's day_state/habit_strength/week_ring/month_ring - a 3-day/
    week habit isn't penalized for the 4 days nobody asked it to run on."""
    not_scheduled_elapsed = sum(1 for d in not_scheduled if start_date <= d <= today)
    days_elapsed = (today - start_date).days - not_scheduled_elapsed
    if today in completed:
        days_elapsed += 1
    if days_elapsed <= 0:
        return 0.0
    completed_count = sum(1 for d in completed if start_date <= d <= today and d not in not_scheduled)
    return (completed_count / days_elapsed) * 100


def freeze_target_date(
    completed: set[date], frozen: set[date], today: date, schedule: tuple[date, date] | None = None,
    floor: date | None = None,
) -> date | None:
    """The date a freeze bought right now would cover, or None if there's
    nothing to save. `schedule=None` (Daily): yesterday, if it was missed
    (and not already frozen) on a habit with an active streak before it.
    `schedule=(missed_candidate, window_end)` (Specific Days - the pair
    habits.py computes via frequency.prev_scheduled/next_scheduled): same
    idea, but `missed_candidate` is the most recent *scheduled* day instead
    of literally yesterday, and the offer stays open through `window_end`
    (the next scheduled day after it) regardless of whether `window_end`
    itself has since been checked in - same order-independence as Daily.
    `floor` (see `_streak_ending_at`) means a day right before a frequency
    edit can never be "saved" by bridging into a pre-edit streak that's
    meant to have restarted."""
    if schedule is None:
        missed_candidate = today - timedelta(days=1)
    else:
        missed_candidate, window_end = schedule
        if today > window_end:
            return None
    if missed_candidate in completed or missed_candidate in frozen:
        return None
    if floor is not None and missed_candidate < floor:
        return None
    streak_before_miss = current_streak(completed, frozen, missed_candidate - timedelta(days=1), floor)
    return missed_candidate if streak_before_miss >= 1 else None


def freeze_available(
    completed: set[date], frozen: set[date], today: date, schedule: tuple[date, date] | None = None,
    floor: date | None = None,
) -> bool:
    """True if a freeze bought right now would have something to cover -
    i.e. "Save your streak" should show today. See `freeze_target_date`."""
    return freeze_target_date(completed, frozen, today, schedule, floor) is not None


def can_purchase_freeze(balance: int, unused_freeze_count: int) -> bool:
    return balance >= FREEZE_COST and unused_freeze_count < MAX_UNUSED_FREEZES


CROWN_BONUS = 2


def has_valid_proof_for_crown(proof_note: str | None) -> bool:
    """A crown candidate's proof note needs real content - at least 3
    non-whitespace characters - not just a stray character or empty note."""
    if not proof_note:
        return False
    return len("".join(proof_note.split())) >= 3


def crown_winner(candidates):
    """Picks a date's crown winner from `candidates` - an iterable of
    `(local_time_of_day, created_at_utc, ...)` tuples, one per eligible
    check-in for that date (any trailing elements are carried through
    untouched, e.g. the checkin/user/habit ids the caller needs back).
    Ranked by local clock time first, so a member in a timezone that's
    simply "ahead" can't win on that alone, then by the real UTC instant to
    break a same-local-time tie. Returns the winning tuple, or None if
    `candidates` is empty."""
    candidates = list(candidates)
    if not candidates:
        return None
    return min(candidates, key=lambda c: (c[0], c[1]))


def room_streak(member_states: list[dict], today_anchor: date) -> int:
    """Consecutive days (ending at `today_anchor`, or the day before if
    `today_anchor` isn't fully checked in yet) on which every member who'd
    already joined by that day completed it on their own local date -
    `member_states` is `[{"completed": set[date], "joined_on": date}, ...]`.
    Unlike a solo habit's streak, freezes never bridge a room streak.
    `today_anchor` should be the earliest "today" among the room's members
    (the most-behind member's own local date) - a day can't be judged
    "everyone made it" before everyone has actually had the chance to."""

    def all_checked_in(d):
        joined = [m for m in member_states if m["joined_on"] <= d]
        if not joined:
            return False
        return all(d in m["completed"] for m in joined)

    end = today_anchor if all_checked_in(today_anchor) else today_anchor - timedelta(days=1)
    count = 0
    cursor = end
    while all_checked_in(cursor):
        count += 1
        cursor -= timedelta(days=1)
    return count


def weekly_room_streak(member_states: list[dict], target: int, today_anchor: date) -> int:
    """Weekly-room twin of `room_streak`: consecutive weeks (by Monday,
    ending at `today_anchor`'s week, or last week if this week isn't
    decided for everyone yet) on which every member who'd joined by that
    week's Monday hit `target` completions of their own. `member_states` is
    `[{"completed": set[date], "joined_on": date}, ...]`."""

    def all_hit(wk):
        joined = [m for m in member_states if m["joined_on"] <= wk]
        if not joined:
            return False
        return all(weekly_completions(m["completed"]).get(wk, 0) >= target for m in joined)

    this_week = week_start(today_anchor)
    end_week = this_week if all_hit(this_week) else this_week - timedelta(days=7)
    count = 0
    cursor = end_week
    while all_hit(cursor):
        count += 1
        cursor -= timedelta(days=7)
    return count


def missed_days(completed: set[date], frozen: set[date], start_date: date, today: date) -> int:
    """Count of days in [start_date, today) that are neither completed nor
    frozen - used as a leaderboard tiebreaker. `today` itself is excluded
    entirely (same "not a miss until the day is over" convention as
    success_rate), not counted as a miss just because it isn't done yet."""
    missed = 0
    cursor = start_date
    end = today - timedelta(days=1)
    while cursor <= end:
        if cursor not in completed and cursor not in frozen:
            missed += 1
        cursor += timedelta(days=1)
    return missed


def weekly_missed_weeks(completed: set[date], target: int, start_date: date, today: date) -> int:
    """Weeks since `start_date` (excluding the current, still-in-progress
    week) that didn't hit `target` completions - the weekly-room leaderboard
    tiebreaker equivalent of `missed_days`."""
    counts = weekly_completions(completed)
    first_week = week_start(start_date)
    this_week = week_start(today)
    missed = 0
    cursor = first_week
    while cursor < this_week:
        if counts.get(cursor, 0) < target:
            missed += 1
        cursor += timedelta(days=7)
    return missed


def week_start(d: date) -> date:
    """Monday of the week containing `d` - the anchor every weekly function
    below keys its per-week bucket on."""
    return d - timedelta(days=d.weekday())


def weekly_completions(completed: set[date]) -> dict[date, int]:
    """Maps each week's Monday to how many completions fall in it."""
    counts: dict[date, int] = {}
    for d in completed:
        wk = week_start(d)
        counts[wk] = counts.get(wk, 0) + 1
    return counts


def _weekly_streak_ending_at(
    completed: set[date], target: int, end_week: date, frozen_weeks: set[date] = frozenset(),
    floor: date | None = None,
) -> int:
    """Consecutive weeks (by Monday), counting backward from `end_week`, that
    hit >= target completions. A week in `frozen_weeks` counts as hit
    regardless of its actual count - same bridging idea as
    `_streak_ending_at`, one granularity up. `floor` (a week's Monday, see
    `_streak_ending_at`) stops the walk there - the frequency-edit restart
    mechanism, one granularity up. With no `floor`, a week with 0
    completions before the habit existed naturally fails `target` (target
    is always >= 1), so the walk terminates on its own anyway."""
    counts = weekly_completions(completed)
    count = 0
    cursor = end_week
    while (floor is None or cursor >= floor) and (cursor in frozen_weeks or counts.get(cursor, 0) >= target):
        count += 1
        cursor -= timedelta(days=7)
    return count


def weekly_streak(
    completed: set[date], target: int, today: date, frozen_weeks: set[date] = frozenset(),
    floor: date | None = None,
) -> int:
    """Streak in weeks as of `today`. If this week hasn't hit `target` yet,
    this is last week's streak - the same "today not done yet" grace
    `current_streak` gives, one granularity up, so the card doesn't zero out
    mid-week just because there's still time left to hit the target."""
    counts = weekly_completions(completed)
    this_week = week_start(today)

    def hit(wk: date) -> bool:
        return wk in frozen_weeks or counts.get(wk, 0) >= target

    end_week = this_week if hit(this_week) else this_week - timedelta(days=7)
    return _weekly_streak_ending_at(completed, target, end_week, frozen_weeks, floor)


def longest_weekly_streak(
    completed: set[date], target: int, created_on: date, today: date,
    frozen_weeks: set[date] = frozenset(),
) -> int:
    """Longest weekly streak ever, same bridging definition as
    `weekly_streak`. Takes `frozen_weeks` (unlike `weekly_streak`'s plain
    streak-count companion in the daily family, `longest_streak`, which
    does) so a frozen week can never make the *current* streak look longer
    than the *best ever* one."""
    counts = weekly_completions(completed)
    first_week = week_start(created_on)
    last_week = week_start(today)
    running = 0
    best = 0
    cursor = first_week
    while cursor <= last_week:
        if cursor in frozen_weeks or counts.get(cursor, 0) >= target:
            running += 1
            best = max(best, running)
        else:
            running = 0
        cursor += timedelta(days=7)
    return best


def weekly_success_rate(completed: set[date], start: date, today: date, target: int) -> float:
    """Percent of this habit's weekly targets hit, lifetime. Unlike the daily
    `success_rate`, the current week always counts fully in the denominator
    (never prorated by day-of-week) - matching the "fixed denominator"
    convention `week_ring`/`month_ring` already use, so a Monday-morning
    glance at a 3x/week habit doesn't read as "0%" just because the week
    just started."""
    if target <= 0:
        return 0.0
    first_week = week_start(start)
    this_week = week_start(today)
    weeks_elapsed = (this_week - first_week).days // 7 + 1
    if weeks_elapsed <= 0:
        return 0.0
    completed_count = sum(1 for d in completed if first_week <= d <= today)
    return (completed_count / (weeks_elapsed * target)) * 100


def weekly_freeze_target_week(
    completed: set[date], target: int, today: date, frozen_weeks: set[date] = frozenset(),
    floor: date | None = None,
) -> date | None:
    """The week (its Monday) a freeze bought right now would cover, or None.
    Mirrors `freeze_target_date` one granularity up: true if *last* week
    missed target (and isn't already frozen) and the weekly streak was
    active going into it. `floor` (see `_weekly_streak_ending_at`) keeps a
    frequency edit's restart from being undone by freezing a pre-edit week."""
    this_week = week_start(today)
    last_week = this_week - timedelta(days=7)
    if last_week in frozen_weeks:
        return None
    if floor is not None and last_week < floor:
        return None
    counts = weekly_completions(completed)
    if counts.get(last_week, 0) >= target:
        return None
    streak_before_miss = _weekly_streak_ending_at(
        completed, target, last_week - timedelta(days=7), frozen_weeks, floor
    )
    return last_week if streak_before_miss >= 1 else None


def weekly_freeze_available(
    completed: set[date], target: int, today: date, frozen_weeks: set[date] = frozenset(),
    floor: date | None = None,
) -> bool:
    """True if a freeze bought right now would have a week to cover - i.e.
    "Save your streak" should show today. See `weekly_freeze_target_week`."""
    return weekly_freeze_target_week(completed, target, today, frozen_weeks, floor) is not None


def weekly_milestone_bonus_for_checkin(
    completed: set[date], target: int, checkin_date: date, frozen_weeks: set[date] = frozenset(),
    floor: date | None = None,
) -> int:
    """Per-check-in weekly milestone pricing: within `checkin_date`'s week,
    sort that week's completions chronologically - only the one that reaches
    `target` earns a bonus. Every check-in before or after the
    target-reaching one earns base points only. If `checkin_date` IS the
    target-reaching one, the bonus is keyed off that week's streak-number
    (reusing the day-numbered milestone table at week granularity) via
    `milestone_bonus`. `floor` restarts that streak-number the same way a
    frequency edit restarts the daily family."""
    week = week_start(checkin_date)
    week_completions = sorted(d for d in completed if week_start(d) == week)
    if len(week_completions) < target or week_completions[target - 1] != checkin_date:
        return 0
    streak_number = _weekly_streak_ending_at(completed, target, week, frozen_weeks, floor)
    return milestone_bonus(streak_number)


def earned_points(amounts: list[int]) -> int:
    """Sum of positive ledger amounts — never decreases except via habit delete."""
    return sum(a for a in amounts if a > 0)


def balance(amounts: list[int]) -> int:
    """Earned minus spent — what freezes get bought with."""
    return sum(amounts)
