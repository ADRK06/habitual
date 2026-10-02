"""Badge catalog and award logic (CLAUDE.md's v1 badge list). Each badge is
awarded once, permanently (badges are never revoked, even if the streak or
room state that earned them later changes) - the UNIQUE(user_id, type)
constraint on `Badge` is what makes `check_and_award` idempotent and safe to
call on every check-in, freeze-use, and page load.

`earned_badge_types` is the pure decision function (no DB access, fully
pytest-able in isolation, same discipline as points.py/analytics.py).
`check_and_award` is the thin DB-wiring layer that gathers the inputs it
needs and persists any newly-earned badges.
"""

from sqlalchemy.exc import IntegrityError

from habitual import db, points
from habitual.models import Badge, Habit, Room, RoomCrown, RoomMember
from habitual.utils.time import local_today

FIRST_CHECKIN = "first_checkin"
FIRST_WEEK = "first_week"
FORTNIGHT = "fortnight"
PERFECT_MONTH = "perfect_month"
FREEZE_SAVER = "freeze_saver"
CROWN_COLLECTOR = "crown_collector"
ROOM_CHAMPION = "room_champion"

CROWN_COLLECTOR_THRESHOLD = 10

BADGE_CATALOG = {
    FIRST_CHECKIN: {"emoji": "🎉", "label": "First Step", "hint": "Complete your first check-in."},
    FIRST_WEEK: {"emoji": "🔥", "label": "Week One", "hint": "Reach a 7-day streak on any habit."},
    FORTNIGHT: {"emoji": "⚡", "label": "Two Weeks Strong", "hint": "Reach a 14-day streak on any habit."},
    PERFECT_MONTH: {"emoji": "🏆", "label": "Perfect Month", "hint": "Reach a 30-day streak on any habit."},
    FREEZE_SAVER: {"emoji": "🧊", "label": "Freeze Saver", "hint": "Use a freeze, then reach a 7-day streak."},
    CROWN_COLLECTOR: {"emoji": "👑", "label": "Crown Collector", "hint": f"Earn {CROWN_COLLECTOR_THRESHOLD} daily crowns in rooms."},
    ROOM_CHAMPION: {"emoji": "🥇", "label": "Room Champion", "hint": "Finish #1 in a room when it ends."},
}

# Display/award-priority order - also what the dashboard's badge row renders.
BADGE_ORDER = [FIRST_CHECKIN, FIRST_WEEK, FORTNIGHT, PERFECT_MONTH, FREEZE_SAVER, CROWN_COLLECTOR, ROOM_CHAMPION]


def earned_badge_types(
    has_any_checkin: bool,
    best_streak_ever: int,
    used_freeze_reached_week: bool,
    crown_count: int,
    is_room_champion: bool,
) -> set[str]:
    """Pure eligibility check - every badge this state qualifies for right
    now (a superset of what may already be awarded; `check_and_award` is
    what diffs this against existing rows)."""
    earned = set()
    if has_any_checkin:
        earned.add(FIRST_CHECKIN)
    if best_streak_ever >= 7:
        earned.add(FIRST_WEEK)
    if best_streak_ever >= 14:
        earned.add(FORTNIGHT)
    if best_streak_ever >= 30:
        earned.add(PERFECT_MONTH)
    if used_freeze_reached_week:
        earned.add(FREEZE_SAVER)
    if crown_count >= CROWN_COLLECTOR_THRESHOLD:
        earned.add(CROWN_COLLECTOR)
    if is_room_champion:
        earned.add(ROOM_CHAMPION)
    return earned


def _is_room_champion(user) -> bool:
    """True if `user` is the top-ranked member of any room that has fully
    ended for every member - checked lazily (no cron, per CLAUDE.md), same
    as crown finalization."""
    from habitual import rooms  # local import avoids a circular import with rooms.py

    for member in RoomMember.query.filter_by(user_id=user.id).all():
        room = db.session.get(Room, member.room_id)
        if room is None:
            continue
        room_members = RoomMember.query.filter_by(room_id=room.id).all()
        if not rooms.room_fully_ended(room, room_members):
            continue
        ranked = rooms.rank_members(room, room_members)
        if ranked and ranked[0]["user"].id == user.id:
            return True
    return False


def check_and_award(user) -> list[dict]:
    """Evaluates every badge for `user` against their current state and
    persists any newly-earned ones. Safe to call as often as needed (e.g. on
    every check-in, freeze-use, and dashboard/room-page load) - already-held
    badges are skipped, and the UNIQUE(user_id, type) constraint makes a
    concurrent double-award a no-op rather than a crash. Returns the
    catalog entries for badges newly earned by this call, for a celebration
    modal - empty if nothing changed."""
    today = local_today(user)
    habit_rows = Habit.query.filter_by(user_id=user.id).all()

    has_any_checkin = False
    best_streak_ever = 0
    used_freeze_reached_week = False
    for habit in habit_rows:
        completed = {c.date for c in habit.checkins}
        if completed:
            has_any_checkin = True
        frozen = {f.used_on for f in habit.freezes if f.used_on is not None}
        best_streak_ever = max(
            best_streak_ever, points.longest_streak(completed, frozen, habit.created_on, today)
        )
        for freeze_date in frozen:
            if points.streak_length_through(completed, frozen, freeze_date) >= 7:
                used_freeze_reached_week = True

    crown_count = RoomCrown.query.filter_by(user_id=user.id).count()

    eligible = earned_badge_types(
        has_any_checkin=has_any_checkin,
        best_streak_ever=best_streak_ever,
        used_freeze_reached_week=used_freeze_reached_week,
        crown_count=crown_count,
        is_room_champion=_is_room_champion(user),
    )

    existing_types = {b.type for b in Badge.query.filter_by(user_id=user.id)}
    newly_earned = sorted(eligible - existing_types, key=BADGE_ORDER.index)

    newly = []
    for badge_type in newly_earned:
        db.session.add(Badge(user_id=user.id, type=badge_type, earned_on=today))
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            continue
        newly.append({"type": badge_type, **BADGE_CATALOG[badge_type]})
    return newly


def badge_rows_for(user) -> list[dict]:
    """Every badge in catalog order, annotated with whether `user` has
    earned it - what the dashboard's badges row renders (locked ones greyed
    with a tooltip)."""
    earned_on_by_type = {b.type: b.earned_on for b in Badge.query.filter_by(user_id=user.id)}
    return [
        {
            "type": badge_type,
            **BADGE_CATALOG[badge_type],
            "earned": badge_type in earned_on_by_type,
            "earned_on": earned_on_by_type.get(badge_type),
        }
        for badge_type in BADGE_ORDER
    ]
