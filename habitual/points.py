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


def _streak_ending_at(completed: set[date], frozen: set[date], end_date: date) -> int:
    """Consecutive completed-day count ending at `end_date`. Frozen days bridge
    a gap without breaking the chain or adding to the count."""
    cursor = end_date
    count = 0
    while cursor in completed or cursor in frozen:
        if cursor in completed:
            count += 1
        cursor -= timedelta(days=1)
    return count


def current_streak(completed: set[date], frozen: set[date], today: date) -> int:
    """Streak as of `today`. If today isn't done yet, this is yesterday's
    streak (so the card doesn't zero out the moment the day rolls over)."""
    end = today if today in completed else today - timedelta(days=1)
    return _streak_ending_at(completed, frozen, end)


def streak_day_on(completed: set[date], frozen: set[date], target: date) -> int:
    """Which streak day `target` was, given the *current* completed/frozen
    state. 0 if `target` isn't a completed date. Used to (re)price a specific
    check-in's points regardless of when a bridging freeze was added."""
    if target not in completed:
        return 0
    return _streak_ending_at(completed, frozen, target)


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


def success_rate(completed: set[date], start_date: date, today: date) -> float:
    """Percent of elapsed days completed. Today only counts toward the
    denominator once it's actually completed, so an unfinished "today"
    doesn't drag the rate down."""
    days_elapsed = (today - start_date).days
    if today in completed:
        days_elapsed += 1
    if days_elapsed <= 0:
        return 0.0
    completed_count = sum(1 for d in completed if start_date <= d <= today)
    return (completed_count / days_elapsed) * 100


def freeze_available(completed: set[date], frozen: set[date], today: date) -> bool:
    """True if yesterday was missed (and not already frozen) on a habit that
    had an active streak — i.e. "Save your streak" should show today."""
    yesterday = today - timedelta(days=1)
    if yesterday in completed or yesterday in frozen:
        return False
    streak_before_miss = current_streak(completed, frozen, yesterday - timedelta(days=1))
    return streak_before_miss >= 1


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


def earned_points(amounts: list[int]) -> int:
    """Sum of positive ledger amounts — never decreases except via habit delete."""
    return sum(a for a in amounts if a > 0)


def balance(amounts: list[int]) -> int:
    """Earned minus spent — what freezes get bought with."""
    return sum(amounts)
