import secrets
from datetime import date, timedelta

from habitual.badges import (
    CROWN_COLLECTOR,
    CROWN_COLLECTOR_THRESHOLD,
    FIRST_CHECKIN,
    FIRST_WEEK,
    FORTNIGHT,
    FREEZE_SAVER,
    PERFECT_MONTH,
    ROOM_CHAMPION,
    badge_rows_for,
    check_and_award,
    earned_badge_types,
)
from habitual.models import Badge, Checkin, Freeze, Habit, PointTransaction, Room, RoomCrown, RoomMember, User
from habitual.rooms import generate_join_code

VALID_PASSWORD = "Sup3r$ecret"


def _create_user(db, username="aadhira"):
    user = User(name=username.title(), username=username, timezone="Asia/Kolkata")
    user.set_password(VALID_PASSWORD)
    db.session.add(user)
    db.session.commit()
    return user


def _login(client, db, username="aadhira"):
    user = _create_user(db, username=username)
    client.post("/login", data={"username": username, "password": VALID_PASSWORD, "next": ""})
    return user


def _create_habit(db, user, title="Read", emoji="📚", created_on=None):
    habit = Habit(user_id=user.id, title=title, emoji=emoji, created_on=created_on or date.today())
    db.session.add(habit)
    db.session.commit()
    return habit


def _checkin(db, habit, d, amount_days_into_streak):
    """Writes a check-in + correctly priced ledger rows for day `d`, same
    shape habits.checkin() produces - good enough for badge tests that only
    care about streak length, not exact milestone amounts."""
    db.session.add(Checkin(habit_id=habit.id, date=d))
    db.session.add(PointTransaction(
        user_id=habit.user_id, habit_id=habit.id, amount=5, reason="daily", date=d,
    ))
    db.session.commit()


def _checkin_run(db, habit, start, count):
    for i in range(count):
        _checkin(db, habit, start + timedelta(days=i), i + 1)


# --- earned_badge_types (pure) ----------------------------------------------


def test_no_badges_from_a_blank_slate():
    assert earned_badge_types(False, 0, False, 0, False) == set()


def test_first_checkin_only_needs_one_checkin_ever():
    assert earned_badge_types(True, 0, False, 0, False) == {FIRST_CHECKIN}


def test_streak_milestones_stack():
    earned = earned_badge_types(True, 30, False, 0, False)
    assert earned == {FIRST_CHECKIN, FIRST_WEEK, FORTNIGHT, PERFECT_MONTH}


def test_streak_of_six_earns_nothing_streak_related():
    earned = earned_badge_types(True, 6, False, 0, False)
    assert FIRST_WEEK not in earned
    assert FORTNIGHT not in earned
    assert PERFECT_MONTH not in earned


def test_freeze_saver_requires_the_explicit_flag():
    assert FREEZE_SAVER in earned_badge_types(True, 0, True, 0, False)
    assert FREEZE_SAVER not in earned_badge_types(True, 0, False, 0, False)


def test_crown_collector_threshold():
    assert CROWN_COLLECTOR not in earned_badge_types(True, 0, False, CROWN_COLLECTOR_THRESHOLD - 1, False)
    assert CROWN_COLLECTOR in earned_badge_types(True, 0, False, CROWN_COLLECTOR_THRESHOLD, False)


def test_room_champion_flag():
    assert ROOM_CHAMPION in earned_badge_types(True, 0, False, 0, True)


# --- check_and_award (DB-wired) ----------------------------------------------


def test_check_and_award_grants_first_checkin(db):
    user = _create_user(db)
    habit = _create_habit(db, user)
    _checkin(db, habit, date.today(), 1)

    newly = check_and_award(user)

    assert [b["type"] for b in newly] == [FIRST_CHECKIN]
    assert Badge.query.filter_by(user_id=user.id, type=FIRST_CHECKIN).count() == 1


def test_check_and_award_is_idempotent(db):
    user = _create_user(db)
    habit = _create_habit(db, user)
    _checkin(db, habit, date.today(), 1)

    check_and_award(user)
    second_call = check_and_award(user)

    assert second_call == []
    assert Badge.query.filter_by(user_id=user.id).count() == 1


def test_check_and_award_grants_streak_milestones_together(db):
    user = _create_user(db)
    start = date.today() - timedelta(days=29)
    habit = _create_habit(db, user, created_on=start)
    _checkin_run(db, habit, start, 30)

    newly_types = {b["type"] for b in check_and_award(user)}

    assert {FIRST_CHECKIN, FIRST_WEEK, FORTNIGHT, PERFECT_MONTH}.issubset(newly_types)


def test_check_and_award_grants_freeze_saver_after_a_bridged_week(db):
    user = _create_user(db)
    start = date.today() - timedelta(days=9)
    habit = _create_habit(db, user, created_on=start)
    # days 0-2 completed, day 3 frozen, days 4-9 completed -> a 9-long chain
    # through the freeze, well past the 7-day threshold.
    _checkin_run(db, habit, start, 3)
    frozen_date = start + timedelta(days=3)
    db.session.add(Freeze(user_id=user.id, habit_id=habit.id, used_on=frozen_date))
    db.session.commit()
    _checkin_run(db, habit, start + timedelta(days=4), 6)

    newly_types = {b["type"] for b in check_and_award(user)}

    assert FREEZE_SAVER in newly_types


def test_check_and_award_does_not_grant_freeze_saver_for_a_short_bridge(db):
    user = _create_user(db)
    start = date.today() - timedelta(days=4)
    habit = _create_habit(db, user, created_on=start)
    # days 0,1 completed, day 2 frozen, days 3,4 completed -> chain of 4, short of 7
    _checkin_run(db, habit, start, 2)
    frozen_date = start + timedelta(days=2)
    db.session.add(Freeze(user_id=user.id, habit_id=habit.id, used_on=frozen_date))
    db.session.commit()
    _checkin_run(db, habit, start + timedelta(days=3), 2)

    newly_types = {b["type"] for b in check_and_award(user)}

    assert FREEZE_SAVER not in newly_types


def test_check_and_award_grants_crown_collector(db):
    user = _create_user(db)
    habit = _create_habit(db, user)
    room = Room(
        title="Race", emoji="🏃", creator_id=user.id, duration_days=30,
        start_date=date.today() - timedelta(days=10), invite_token=secrets.token_urlsafe(16),
        join_code=generate_join_code(),
    )
    db.session.add(room)
    db.session.commit()
    for i in range(CROWN_COLLECTOR_THRESHOLD):
        db.session.add(RoomCrown(room_id=room.id, date=date.today() - timedelta(days=i), user_id=user.id))
    db.session.commit()

    newly_types = {b["type"] for b in check_and_award(user)}

    assert CROWN_COLLECTOR in newly_types


def test_check_and_award_grants_room_champion_to_the_ended_rooms_top_member(db):
    winner = _create_user(db, username="winner")
    loser = _create_user(db, username="loser")
    # A 7-day room that started 10 days ago has fully ended for both members.
    start = date.today() - timedelta(days=10)
    room = Room(
        title="Race", emoji="🏃", creator_id=winner.id, duration_days=7,
        start_date=start, invite_token=secrets.token_urlsafe(16), join_code=generate_join_code(),
    )
    db.session.add(room)
    db.session.flush()
    db.session.add(RoomMember(room_id=room.id, user_id=winner.id, joined_on=start))
    db.session.add(RoomMember(room_id=room.id, user_id=loser.id, joined_on=start))
    winner_habit = Habit(user_id=winner.id, room_id=room.id, title="Race", emoji="🏃", created_on=start)
    loser_habit = Habit(user_id=loser.id, room_id=room.id, title="Race", emoji="🏃", created_on=start)
    db.session.add_all([winner_habit, loser_habit])
    db.session.commit()
    _checkin_run(db, winner_habit, start, 7)
    _checkin_run(db, loser_habit, start, 2)

    winner_newly = {b["type"] for b in check_and_award(winner)}
    loser_newly = {b["type"] for b in check_and_award(loser)}

    assert ROOM_CHAMPION in winner_newly
    assert ROOM_CHAMPION not in loser_newly


# --- badge_rows_for -----------------------------------------------------


def test_badge_rows_for_marks_locked_vs_earned(db):
    user = _create_user(db)
    habit = _create_habit(db, user)
    _checkin(db, habit, date.today(), 1)
    check_and_award(user)

    rows = badge_rows_for(user)
    by_type = {r["type"]: r for r in rows}

    assert by_type[FIRST_CHECKIN]["earned"] is True
    assert by_type[FIRST_CHECKIN]["earned_on"] == date.today()
    assert by_type[FIRST_WEEK]["earned"] is False
    assert by_type[FIRST_WEEK]["earned_on"] is None


# --- dashboard integration ------------------------------------------------


def test_dashboard_shows_badges_row(client, db):
    user = _login(client, db)
    habit = _create_habit(db, user)
    _checkin(db, habit, date.today(), 1)

    response = client.get("/dashboard")

    assert b'id="badges-row"' in response.data


def test_checkin_response_triggers_badges_earned_event(client, db):
    user = _login(client, db)
    habit = _create_habit(db, user, created_on=date.today())

    response = client.post(f"/habits/{habit.id}/checkin")

    trigger = response.headers.get("HX-Trigger", "")
    assert "badgesEarned" in trigger
    assert "first_checkin" in trigger
