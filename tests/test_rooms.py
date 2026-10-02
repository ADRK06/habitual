import secrets
from datetime import date, datetime, timedelta, timezone as dt_timezone
from zoneinfo import ZoneInfo

from habitual.habits import EMOJI_CHOICES
from habitual.models import Checkin, Habit, PointTransaction, Room, RoomCrown, RoomMember, User
from habitual.rooms import (
    JOIN_CODE_ALPHABET,
    JOIN_CODE_LENGTH,
    JOIN_CODE_MAX_FAILURES,
    MAX_ROOM_MEMBERS,
    finalize_due_crowns,
    generate_join_code,
    normalize_join_code,
)

VALID_PASSWORD = "Sup3r$ecret"


def _create_user(db, username="aadhira", password=VALID_PASSWORD, timezone="Asia/Kolkata"):
    user = User(name=username.title(), username=username, timezone=timezone)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    return user


def _login(client, db, username="aadhira", timezone="Asia/Kolkata"):
    user = _create_user(db, username=username, timezone=timezone)
    client.post("/login", data={"username": username, "password": VALID_PASSWORD, "next": ""})
    return user


def _create_room(db, creator, title="Morning Run", emoji="🏃", duration_days=14, start_date=None):
    start_date = start_date or date.today()
    room = Room(
        title=title, emoji=emoji, creator_id=creator.id, duration_days=duration_days,
        start_date=start_date, invite_token=secrets.token_urlsafe(16), join_code=generate_join_code(),
    )
    db.session.add(room)
    db.session.flush()
    db.session.add(RoomMember(room_id=room.id, user_id=creator.id, joined_on=start_date))
    db.session.add(Habit(user_id=creator.id, room_id=room.id, title=title, emoji=emoji, created_on=start_date))
    db.session.commit()
    return room


def _join_room_direct(db, room, user, joined_on=None):
    joined_on = joined_on or date.today()
    db.session.add(RoomMember(room_id=room.id, user_id=user.id, joined_on=joined_on))
    db.session.add(Habit(
        user_id=user.id, room_id=room.id, title=room.title, emoji=room.emoji, created_on=joined_on,
    ))
    db.session.commit()


def _local_time_to_utc(d, hour, minute, tz_name):
    return datetime(d.year, d.month, d.day, hour, minute, tzinfo=ZoneInfo(tz_name)).astimezone(dt_timezone.utc)


# -- create room --------------------------------------------------------------


def test_create_room_requires_login(client):
    response = client.post("/rooms", data={"title": "Run Club", "emoji": EMOJI_CHOICES[0], "duration_days": "14"})
    assert response.status_code == 302
    assert "/login" in response.location


def test_create_room_creates_membership_and_habit(client, db):
    user = _login(client, db)
    response = client.post("/rooms", data={"title": "Run Club", "emoji": EMOJI_CHOICES[0], "duration_days": "14"})
    assert response.status_code == 302

    room = Room.query.filter_by(title="Run Club").first()
    assert f"/rooms/{room.id}" in response.location
    assert room is not None
    assert room.creator_id == user.id
    assert room.duration_days == 14
    assert RoomMember.query.filter_by(room_id=room.id, user_id=user.id).count() == 1
    habit = Habit.query.filter_by(room_id=room.id, user_id=user.id).first()
    assert habit is not None
    assert habit.title == "Run Club"
    assert habit.created_on == date.today()


def test_create_room_rejects_duration_outside_7_to_90(client, db):
    _login(client, db)
    response = client.post("/rooms", data={"title": "Run Club", "emoji": EMOJI_CHOICES[0], "duration_days": "5"})
    assert response.status_code == 400
    assert Room.query.count() == 0


def test_create_room_rejects_emoji_outside_picker(client, db):
    _login(client, db)
    response = client.post("/rooms", data={"title": "Run Club", "emoji": "💩", "duration_days": "14"})
    assert response.status_code == 400
    assert Room.query.count() == 0


def test_create_room_rejects_blank_title(client, db):
    _login(client, db)
    response = client.post("/rooms", data={"title": "   ", "emoji": EMOJI_CHOICES[0], "duration_days": "14"})
    assert response.status_code == 400
    assert Room.query.count() == 0


# -- join flow ----------------------------------------------------------------


def test_join_landing_shows_room_info_without_login(client, db):
    creator = _create_user(db, username="creator")
    room = _create_room(db, creator, title="Run Club")

    response = client.get(f"/join/{room.invite_token}")
    assert response.status_code == 200
    assert b"Run Club" in response.data
    assert b"Log in" in response.data


def test_join_landing_404_for_unknown_token(client, db):
    response = client.get("/join/not-a-real-token")
    assert response.status_code == 404


def test_join_room_requires_login(client, db):
    creator = _create_user(db, username="creator")
    room = _create_room(db, creator)

    response = client.post(f"/join/{room.invite_token}")
    assert response.status_code == 302
    assert "/login" in response.location


def test_join_room_creates_membership_and_habit(client, db):
    creator = _create_user(db, username="creator")
    room = _create_room(db, creator, title="Run Club")
    _login(client, db, username="joiner")

    response = client.post(f"/join/{room.invite_token}")
    assert response.status_code == 302
    assert f"/rooms/{room.id}" in response.location
    assert RoomMember.query.filter_by(room_id=room.id).count() == 2
    assert Habit.query.filter_by(room_id=room.id).count() == 2


def test_join_room_twice_is_a_no_op(client, db):
    creator = _create_user(db, username="creator")
    room = _create_room(db, creator)
    _login(client, db, username="joiner")

    client.post(f"/join/{room.invite_token}")
    client.post(f"/join/{room.invite_token}")

    assert RoomMember.query.filter_by(room_id=room.id).count() == 2


def test_join_room_blocked_after_final_day_for_joiner(client, db):
    creator = _create_user(db, username="creator")
    today = date.today()
    room = _create_room(db, creator, duration_days=7, start_date=today - timedelta(days=10))
    _login(client, db, username="latecomer")

    response = client.post(f"/join/{room.invite_token}")
    assert response.status_code == 400
    assert RoomMember.query.filter_by(room_id=room.id).count() == 1


def test_join_landing_reflects_ended_state_for_a_logged_in_viewer(client, db):
    creator = _create_user(db, username="creator")
    today = date.today()
    room = _create_room(db, creator, duration_days=7, start_date=today - timedelta(days=10))
    _login(client, db, username="latecomer")

    response = client.get(f"/join/{room.invite_token}")
    assert response.status_code == 200
    assert b"already ended" in response.data


# -- leave + ownership transfer -----------------------------------------------


def test_leave_room_deletes_habit_and_membership(client, db):
    user = _login(client, db)
    room = _create_room(db, user)
    habit = Habit.query.filter_by(room_id=room.id, user_id=user.id).first()

    response = client.post(f"/rooms/{room.id}/leave")
    assert response.status_code == 302
    assert db.session.get(Habit, habit.id) is None
    assert RoomMember.query.filter_by(room_id=room.id, user_id=user.id).count() == 0


def test_leave_room_requires_membership(client, db):
    creator = _create_user(db, username="creator")
    room = _create_room(db, creator)
    _login(client, db, username="outsider")

    response = client.post(f"/rooms/{room.id}/leave")
    assert response.status_code == 404


def test_last_member_leaving_deletes_the_room(client, db):
    user = _login(client, db)
    room = _create_room(db, user)
    room_id = room.id

    client.post(f"/rooms/{room_id}/leave")
    assert db.session.get(Room, room_id) is None


def test_one_of_several_members_leaving_keeps_the_room(client, db):
    user = _login(client, db)
    room = _create_room(db, user)
    other = _create_user(db, username="other")
    _join_room_direct(db, room, other)

    client.post(f"/rooms/{room.id}/leave")
    assert db.session.get(Room, room.id) is not None
    assert RoomMember.query.filter_by(room_id=room.id).count() == 1


def test_creator_leaving_transfers_ownership_to_top_ranked_member(client, db):
    creator = _login(client, db, username="creator")
    room = _create_room(db, creator)
    other = _create_user(db, username="other")
    _join_room_direct(db, room, other)

    other_habit = Habit.query.filter_by(room_id=room.id, user_id=other.id).first()
    db.session.add(PointTransaction(
        user_id=other.id, habit_id=other_habit.id, amount=50, reason="daily", date=date.today(),
    ))
    db.session.commit()

    client.post(f"/rooms/{room.id}/leave")

    room_after = db.session.get(Room, room.id)
    assert room_after is not None
    assert room_after.creator_id == other.id


def test_leave_after_winning_a_crown_keeps_history_but_removes_points(client, db):
    today = date.today()
    d0 = today - timedelta(days=5)
    winner = _login(client, db, username="winner")
    other = _create_user(db, username="other")
    room = _create_room(db, winner, duration_days=30, start_date=d0)
    _join_room_direct(db, room, other, joined_on=d0)

    winner_habit = Habit.query.filter_by(room_id=room.id, user_id=winner.id).first()
    other_habit = Habit.query.filter_by(room_id=room.id, user_id=other.id).first()

    winner_checkin = Checkin(
        habit_id=winner_habit.id, date=d0, proof_note="early bird",
        created_at=datetime(d0.year, d0.month, d0.day, 6, 0, tzinfo=dt_timezone.utc),
    )
    other_checkin = Checkin(
        habit_id=other_habit.id, date=d0, proof_note="late riser",
        created_at=datetime(d0.year, d0.month, d0.day, 10, 0, tzinfo=dt_timezone.utc),
    )
    db.session.add_all([winner_checkin, other_checkin])
    db.session.commit()

    finalize_due_crowns(room)

    crown = RoomCrown.query.filter_by(room_id=room.id, date=d0).first()
    assert crown is not None
    assert crown.user_id == winner.id
    assert crown.checkin_id == winner_checkin.id
    assert PointTransaction.query.filter_by(habit_id=winner_habit.id, reason="crown").count() == 1

    response = client.post(f"/rooms/{room.id}/leave")
    assert response.status_code == 302

    # The habit (and its whole ledger, including the crown's +2) is gone -
    # earned points never survive a deleted habit, crown or otherwise.
    assert db.session.get(Habit, winner_habit.id) is None
    assert PointTransaction.query.filter_by(habit_id=winner_habit.id).count() == 0

    # The crown itself survives as history: the row isn't deleted, but the
    # now-dangling check-in reference is cleared rather than left pointing
    # at a deleted row.
    crown_after = db.session.get(RoomCrown, crown.id)
    assert crown_after is not None
    assert crown_after.user_id == winner.id
    assert crown_after.checkin_id is None


# -- regenerate invite ---------------------------------------------------------


def test_regenerate_invite_changes_the_token(client, db):
    user = _login(client, db)
    room = _create_room(db, user)
    old_token = room.invite_token

    client.post(f"/rooms/{room.id}/regenerate-invite")

    room_after = db.session.get(Room, room.id)
    assert room_after.invite_token != old_token


def test_regenerate_invite_requires_creator(client, db):
    creator = _create_user(db, username="creator")
    room = _create_room(db, creator)
    old_token = room.invite_token
    member = _login(client, db, username="member")
    _join_room_direct(db, room, member)

    response = client.post(f"/rooms/{room.id}/regenerate-invite")
    assert response.status_code == 404
    assert db.session.get(Room, room.id).invite_token == old_token


# -- crown finalization: lazy, idempotent, per-member local dates -----------


def test_crown_is_fair_across_timezones(client, db):
    # IST checks in at 9am IST (their local morning) - EST checks in at
    # 7am EST (earlier in their own day). IST's UTC instant is actually
    # earlier (IST is UTC+5:30 vs EST's UTC-5), so a naive UTC-timestamp
    # comparison would wrongly crown the IST member - the crown must go to
    # EST, the one who was genuinely earlier in their own day.
    ist_user = _create_user(db, username="ist_user", timezone="Asia/Kolkata")
    est_user = _create_user(db, username="est_user", timezone="America/New_York")
    d0 = date.today() - timedelta(days=5)
    room = _create_room(db, ist_user, duration_days=30, start_date=d0)
    _join_room_direct(db, room, est_user, joined_on=d0)

    ist_habit = Habit.query.filter_by(room_id=room.id, user_id=ist_user.id).first()
    est_habit = Habit.query.filter_by(room_id=room.id, user_id=est_user.id).first()

    db.session.add(Checkin(
        habit_id=ist_habit.id, date=d0, proof_note="ran 5k",
        created_at=_local_time_to_utc(d0, 9, 0, "Asia/Kolkata"),
    ))
    db.session.add(Checkin(
        habit_id=est_habit.id, date=d0, proof_note="morning run",
        created_at=_local_time_to_utc(d0, 7, 0, "America/New_York"),
    ))
    db.session.commit()

    finalize_due_crowns(room)

    crown = RoomCrown.query.filter_by(room_id=room.id, date=d0).first()
    assert crown is not None
    assert crown.user_id == est_user.id


def test_crown_not_finalized_for_a_date_until_every_members_day_has_ended(client, db):
    today = date.today()
    user_a = _login(client, db, username="a")
    user_b = _create_user(db, username="b")
    room = _create_room(db, user_a, duration_days=30, start_date=today)
    _join_room_direct(db, room, user_b, joined_on=today)

    habit_a = Habit.query.filter_by(room_id=room.id, user_id=user_a.id).first()
    db.session.add(Checkin(
        habit_id=habit_a.id, date=today, proof_note="done", created_at=datetime.now(dt_timezone.utc),
    ))
    db.session.commit()

    finalize_due_crowns(room)

    # Today is never closed - neither member's local day has ended yet.
    assert RoomCrown.query.filter_by(room_id=room.id, date=today).count() == 0


def test_finalize_due_crowns_twice_awards_only_once(client, db):
    today = date.today()
    d0 = today - timedelta(days=3)
    user = _login(client, db, username="solo_winner")
    room = _create_room(db, user, duration_days=30, start_date=d0)
    habit = Habit.query.filter_by(room_id=room.id, user_id=user.id).first()

    db.session.add(Checkin(
        habit_id=habit.id, date=d0, proof_note="valid note",
        created_at=datetime(d0.year, d0.month, d0.day, 8, 0, tzinfo=dt_timezone.utc),
    ))
    db.session.commit()

    finalize_due_crowns(room)
    finalize_due_crowns(room)

    assert RoomCrown.query.filter_by(room_id=room.id, date=d0).count() == 1
    assert PointTransaction.query.filter_by(habit_id=habit.id, reason="crown").count() == 1


def test_crown_skips_checkins_without_a_valid_proof_note(client, db):
    today = date.today()
    d0 = today - timedelta(days=3)
    short_note_user = _login(client, db, username="short_note")
    good_note_user = _create_user(db, username="good_note")
    room = _create_room(db, short_note_user, duration_days=30, start_date=d0)
    _join_room_direct(db, room, good_note_user, joined_on=d0)

    short_habit = Habit.query.filter_by(room_id=room.id, user_id=short_note_user.id).first()
    good_habit = Habit.query.filter_by(room_id=room.id, user_id=good_note_user.id).first()

    # Checks in first (earliest local time) but the note is too short to
    # count - the crown must skip it even though it'd otherwise win.
    db.session.add(Checkin(
        habit_id=short_habit.id, date=d0, proof_note="ok",
        created_at=datetime(d0.year, d0.month, d0.day, 5, 0, tzinfo=dt_timezone.utc),
    ))
    db.session.add(Checkin(
        habit_id=good_habit.id, date=d0, proof_note="ran a full 5k today",
        created_at=datetime(d0.year, d0.month, d0.day, 9, 0, tzinfo=dt_timezone.utc),
    ))
    db.session.commit()

    finalize_due_crowns(room)

    crown = RoomCrown.query.filter_by(room_id=room.id, date=d0).first()
    assert crown is not None
    assert crown.user_id == good_note_user.id


def test_crown_finalization_ignores_members_who_joined_after_the_date(client, db):
    d0 = date.today() - timedelta(days=5)
    early_user = _login(client, db, username="early")
    room = _create_room(db, early_user, duration_days=30, start_date=d0)
    early_habit = Habit.query.filter_by(room_id=room.id, user_id=early_user.id).first()

    db.session.add(Checkin(
        habit_id=early_habit.id, date=d0, proof_note="first day done",
        created_at=datetime(d0.year, d0.month, d0.day, 8, 0, tzinfo=dt_timezone.utc),
    ))
    db.session.commit()

    # Joins the room two days later - must not be considered for, or block
    # finalizing, a crown on a date before they existed in the room.
    latecomer = _create_user(db, username="latecomer")
    _join_room_direct(db, room, latecomer, joined_on=d0 + timedelta(days=2))

    finalize_due_crowns(room)

    crown = RoomCrown.query.filter_by(room_id=room.id, date=d0).first()
    assert crown is not None
    assert crown.user_id == early_user.id


# -- room page -----------------------------------------------------------------


def test_room_detail_requires_membership(client, db):
    creator = _create_user(db, username="creator")
    room = _create_room(db, creator)
    _login(client, db, username="outsider")

    response = client.get(f"/rooms/{room.id}")
    assert response.status_code == 404


def test_room_detail_renders_for_a_member(client, db):
    user = _login(client, db)
    room = _create_room(db, user, title="Run Club")

    response = client.get(f"/rooms/{room.id}")
    assert response.status_code == 200
    assert b"Run Club" in response.data
    assert b"Leaderboard" in response.data
    assert b'id="my-room-panel"' in response.data


def test_room_detail_shows_health_and_streak(client, db):
    user = _login(client, db)
    room = _create_room(db, user)
    habit = Habit.query.filter_by(room_id=room.id, user_id=user.id).first()
    client.post(f"/habits/{habit.id}/checkin", data={"room_view": "1"})

    response = client.get(f"/rooms/{room.id}")
    assert b'id="room-health"' in response.data
    assert b"100%" in response.data  # the only member, checked in today


def test_room_leaderboard_orders_by_points_desc(client, db):
    leader = _login(client, db, username="leader")
    room = _create_room(db, leader)
    trailing = _create_user(db, username="trailing")
    _join_room_direct(db, room, trailing)

    leader_habit = Habit.query.filter_by(room_id=room.id, user_id=leader.id).first()
    db.session.add(PointTransaction(user_id=leader.id, habit_id=leader_habit.id, amount=50, reason="daily", date=date.today()))
    db.session.commit()

    response = client.get(f"/rooms/{room.id}").get_data(as_text=True)
    assert response.index("Leader") < response.index("Trailing")


def test_room_leaderboard_rows_have_stable_flip_ids(client, db):
    user = _login(client, db)
    room = _create_room(db, user)

    response = client.get(f"/rooms/{room.id}")
    assert f'data-flip-id="leaderboard-row-{user.id}"'.encode() in response.data


def test_room_feed_shows_provisional_crown_badge(client, db):
    user = _login(client, db)
    room = _create_room(db, user)
    habit = Habit.query.filter_by(room_id=room.id, user_id=user.id).first()
    client.post(f"/habits/{habit.id}/checkin", data={"proof_note": "ran 5k", "room_view": "1"})

    response = client.get(f"/rooms/{room.id}")
    assert "👑".encode() in response.data


def test_room_page_check_in_returns_live_update_partial(client, db):
    user = _login(client, db)
    room = _create_room(db, user)
    habit = Habit.query.filter_by(room_id=room.id, user_id=user.id).first()

    response = client.post(f"/habits/{habit.id}/checkin", data={"room_view": "1"})
    assert response.status_code == 200
    html = response.data.decode()
    assert 'id="my-room-panel"' in html
    assert 'id="leaderboard-list" hx-swap-oob="true"' in html
    assert 'id="room-health" hx-swap-oob="true"' in html
    assert "habit-card-" not in html  # the dashboard-shaped fragment never leaks into the room-page response


def test_dashboard_check_in_still_returns_dashboard_shaped_partial_for_a_room_habit(client, db):
    # The SAME habit's dashboard room-card checks in through the same route
    # without the room_view flag - it must get the normal dashboard partial,
    # not the room page's.
    user = _login(client, db)
    room = _create_room(db, user)
    habit = Habit.query.filter_by(room_id=room.id, user_id=user.id).first()

    response = client.post(f"/habits/{habit.id}/checkin")
    assert response.status_code == 200
    html = response.data.decode()
    assert f'id="habit-card-{habit.id}"' in html
    assert 'id="my-room-panel"' not in html


def test_dashboard_shows_room_badge_and_leader(client, db):
    user = _login(client, db)
    _create_room(db, user, title="Run Club")

    response = client.get("/dashboard")
    assert b"Run Club" in response.data
    assert b"Room" in response.data
    assert b"You lead" in response.data


def test_dashboard_room_card_has_leave_button_not_delete(client, db):
    user = _login(client, db)
    room = _create_room(db, user, title="Run Club")

    response = client.get("/dashboard").get_data(as_text=True)
    assert f'/rooms/{room.id}/leave' in response
    assert 'Leave "Run Club"?' in response


def test_delete_habit_route_rejects_a_room_habit(client, db):
    user = _login(client, db)
    room = _create_room(db, user)
    habit = Habit.query.filter_by(room_id=room.id, user_id=user.id).first()

    response = client.delete(f"/habits/{habit.id}")
    assert response.status_code == 400
    assert db.session.get(Habit, habit.id) is not None


def test_habit_detail_back_link_points_to_room_for_a_room_habit(client, db):
    user = _login(client, db)
    room = _create_room(db, user)
    habit = Habit.query.filter_by(room_id=room.id, user_id=user.id).first()

    response = client.get(f"/habits/{habit.id}")
    assert f'/rooms/{room.id}'.encode() in response.data


def test_dashboard_finalizes_due_crowns_without_opening_the_room_page(client, db):
    # Fix #1: crown points must reach the dashboard's header total even if
    # nobody ever opens the room page itself.
    today = date.today()
    d0 = today - timedelta(days=3)
    user = _login(client, db, username="solo_winner")
    room = _create_room(db, user, duration_days=30, start_date=d0)
    habit = Habit.query.filter_by(room_id=room.id, user_id=user.id).first()

    db.session.add(Checkin(
        habit_id=habit.id, date=d0, proof_note="valid note",
        created_at=datetime(d0.year, d0.month, d0.day, 8, 0, tzinfo=dt_timezone.utc),
    ))
    db.session.commit()
    assert PointTransaction.query.filter_by(habit_id=habit.id, reason="crown").count() == 0

    response = client.get("/dashboard")
    assert response.status_code == 200
    assert PointTransaction.query.filter_by(habit_id=habit.id, reason="crown").count() == 1


# -- final-day gate (fix #3): check-in, undo, freeze-use, vouch -------------


def _ended_room_habit(db, user):
    today = date.today()
    room = _create_room(db, user, duration_days=7, start_date=today - timedelta(days=10))
    habit = Habit.query.filter_by(room_id=room.id, user_id=user.id).first()
    return room, habit


def test_checkin_blocked_after_viewers_final_day(client, db):
    user = _login(client, db)
    _room, habit = _ended_room_habit(db, user)

    response = client.post(f"/habits/{habit.id}/checkin")
    assert response.status_code == 400
    assert Checkin.query.filter_by(habit_id=habit.id).count() == 0


def test_undo_checkin_blocked_after_viewers_final_day(client, db):
    user = _login(client, db)
    room, habit = _ended_room_habit(db, user)
    # Backdate a checkin directly (bypassing the now-gated route) so there's
    # something a working undo route would otherwise remove.
    db.session.add(Checkin(habit_id=habit.id, date=date.today()))
    db.session.commit()

    response = client.delete(f"/habits/{habit.id}/checkin")
    assert response.status_code == 400
    assert Checkin.query.filter_by(habit_id=habit.id).count() == 1


def test_use_freeze_blocked_after_viewers_final_day(client, db):
    user = _login(client, db)
    room, habit = _ended_room_habit(db, user)
    db.session.add(PointTransaction(user_id=user.id, habit_id=None, amount=50, reason="daily", date=date.today()))
    db.session.commit()
    client.post("/freezes/buy")

    response = client.post(f"/habits/{habit.id}/freeze")
    assert response.status_code == 400


def test_vouch_blocked_after_viewers_final_day(client, db):
    today = date.today()
    d0 = today - timedelta(days=10)
    owner = _create_user(db, username="owner")
    room = _create_room(db, owner, duration_days=7, start_date=d0)
    owner_habit = Habit.query.filter_by(room_id=room.id, user_id=owner.id).first()
    checkin = Checkin(habit_id=owner_habit.id, date=d0, proof_note="early bird")
    db.session.add(checkin)
    db.session.commit()

    voucher = _login(client, db, username="voucher")
    _join_room_direct(db, room, voucher, joined_on=d0)

    response = client.post(f"/checkins/{checkin.id}/vouch", data={"emoji": "✅"})
    assert response.status_code == 400
    assert checkin.vouches == []


# -- vouch ----------------------------------------------------------------


def test_vouch_requires_membership(client, db):
    owner = _create_user(db, username="owner")
    room = _create_room(db, owner)
    owner_habit = Habit.query.filter_by(room_id=room.id, user_id=owner.id).first()
    checkin = Checkin(habit_id=owner_habit.id, date=date.today(), proof_note="note")
    db.session.add(checkin)
    db.session.commit()

    _login(client, db, username="outsider")
    response = client.post(f"/checkins/{checkin.id}/vouch", data={"emoji": "✅"})
    assert response.status_code == 404


def test_vouch_rejects_self_vouch(client, db):
    user = _login(client, db)
    room = _create_room(db, user)
    habit = Habit.query.filter_by(room_id=room.id, user_id=user.id).first()
    checkin = Checkin(habit_id=habit.id, date=date.today(), proof_note="note")
    db.session.add(checkin)
    db.session.commit()

    response = client.post(f"/checkins/{checkin.id}/vouch", data={"emoji": "✅"})
    assert response.status_code == 400


def test_vouch_rejects_invalid_emoji(client, db):
    owner = _create_user(db, username="owner")
    room = _create_room(db, owner)
    owner_habit = Habit.query.filter_by(room_id=room.id, user_id=owner.id).first()
    checkin = Checkin(habit_id=owner_habit.id, date=date.today(), proof_note="note")
    db.session.add(checkin)
    db.session.commit()

    voucher = _login(client, db, username="voucher")
    _join_room_direct(db, room, voucher)

    response = client.post(f"/checkins/{checkin.id}/vouch", data={"emoji": "😀"})
    assert response.status_code == 400


def test_vouch_toggle_adds_switches_and_removes(client, db):
    owner = _create_user(db, username="owner")
    room = _create_room(db, owner)
    owner_habit = Habit.query.filter_by(room_id=room.id, user_id=owner.id).first()
    checkin = Checkin(habit_id=owner_habit.id, date=date.today(), proof_note="note")
    db.session.add(checkin)
    db.session.commit()

    voucher = _login(client, db, username="voucher")
    _join_room_direct(db, room, voucher)

    client.post(f"/checkins/{checkin.id}/vouch", data={"emoji": "✅"})
    from habitual.models import Vouch
    assert Vouch.query.filter_by(checkin_id=checkin.id, user_id=voucher.id).first().emoji == "✅"

    client.post(f"/checkins/{checkin.id}/vouch", data={"emoji": "🔥"})
    assert Vouch.query.filter_by(checkin_id=checkin.id, user_id=voucher.id).first().emoji == "🔥"

    client.post(f"/checkins/{checkin.id}/vouch", data={"emoji": "🔥"})
    assert Vouch.query.filter_by(checkin_id=checkin.id, user_id=voucher.id).first() is None


# -- join codes -----------------------------------------------------------


def test_generate_join_code_format(db):
    for _ in range(50):
        code = generate_join_code()
        assert len(code) == JOIN_CODE_LENGTH
        assert all(c in JOIN_CODE_ALPHABET for c in code)
    assert not set("0O1IL") & set(JOIN_CODE_ALPHABET)


def test_generate_join_code_is_unique(db):
    creator = _create_user(db, username="creator")
    existing = {_create_room(db, creator, title=f"Room {i}").join_code for i in range(20)}
    assert len(existing) == 20  # no collisions among 20 real rows

    new_code = generate_join_code()
    assert new_code not in existing


def test_normalize_join_code_strips_dashes_spaces_and_case():
    assert normalize_join_code("k7m4-qx") == "K7M4QX"
    assert normalize_join_code("K7M4 QX") == "K7M4QX"
    assert normalize_join_code(" k7m4qx ") == "K7M4QX"
    assert normalize_join_code("K7M4QX") == "K7M4QX"


def test_find_by_code_redirects_to_join_landing_case_and_format_insensitive(client, db):
    creator = _create_user(db, username="creator")
    room = _create_room(db, creator)
    _login(client, db, username="finder")

    variants = [room.join_code.lower(), f"{room.join_code[:3]}-{room.join_code[3:]}", f" {room.join_code} "]
    for variant in variants:
        response = client.post("/rooms/find-by-code", data={"code": variant})
        assert response.status_code == 302
        assert f"/join/{room.invite_token}" in response.location


def test_find_by_code_never_auto_joins(client, db):
    creator = _create_user(db, username="creator")
    room = _create_room(db, creator)
    finder = _login(client, db, username="finder")

    client.post("/rooms/find-by-code", data={"code": room.join_code})
    assert RoomMember.query.filter_by(room_id=room.id, user_id=finder.id).count() == 0


def test_find_by_code_wrong_code_shows_friendly_error(client, db):
    _login(client, db)
    response = client.post("/rooms/find-by-code", data={"code": "ZZZZZZ"})
    assert response.status_code == 400
    assert b"No room found with that code" in response.data


def test_find_by_code_rate_limits_after_max_failures(client, db):
    user = _login(client, db)
    for _ in range(JOIN_CODE_MAX_FAILURES):
        client.post("/rooms/find-by-code", data={"code": "ZZZZZZ"})

    assert db.session.get(User, user.id).join_locked_until is not None

    response = client.post("/rooms/find-by-code", data={"code": "ZZZZZZ"})
    assert response.status_code == 400
    assert b"Too many attempts" in response.data


def test_find_by_code_success_clears_failed_attempts(client, db):
    creator = _create_user(db, username="creator")
    room = _create_room(db, creator)
    user = _login(client, db, username="finder")

    client.post("/rooms/find-by-code", data={"code": "ZZZZZZ"})
    client.post("/rooms/find-by-code", data={"code": "ZZZZZZ"})
    assert db.session.get(User, user.id).failed_join_attempts == 2

    client.post("/rooms/find-by-code", data={"code": room.join_code})
    assert db.session.get(User, user.id).failed_join_attempts == 0


def test_regenerate_invite_invalidates_old_token_and_code(client, db):
    user = _login(client, db)
    room = _create_room(db, user)
    old_token, old_code = room.invite_token, room.join_code

    client.post(f"/rooms/{room.id}/regenerate-invite")

    room_after = db.session.get(Room, room.id)
    assert room_after.invite_token != old_token
    assert room_after.join_code != old_code

    assert client.get(f"/join/{old_token}").status_code == 404
    found = client.post("/rooms/find-by-code", data={"code": old_code})
    assert found.status_code == 400
    assert b"No room found with that code" in found.data


# -- room member cap --------------------------------------------------------


def test_join_landing_shows_full_message_at_cap(client, db):
    creator = _create_user(db, username="creator")
    room = _create_room(db, creator)
    for i in range(MAX_ROOM_MEMBERS - 1):
        _join_room_direct(db, room, _create_user(db, username=f"member{i}"))

    _login(client, db, username="latecomer")
    response = client.get(f"/join/{room.invite_token}")
    assert response.status_code == 200
    assert f"{MAX_ROOM_MEMBERS}/{MAX_ROOM_MEMBERS}".encode() in response.data
    assert b"full" in response.data.lower()


def test_join_room_rejected_at_cap(client, db):
    creator = _create_user(db, username="creator")
    room = _create_room(db, creator)
    for i in range(MAX_ROOM_MEMBERS - 1):
        _join_room_direct(db, room, _create_user(db, username=f"member{i}"))
    assert RoomMember.query.filter_by(room_id=room.id).count() == MAX_ROOM_MEMBERS

    _login(client, db, username="latecomer")
    response = client.post(f"/join/{room.invite_token}")
    assert response.status_code == 400
    assert RoomMember.query.filter_by(room_id=room.id).count() == MAX_ROOM_MEMBERS


# -- security review ---------------------------------------------------------
#
# Same "sequential double-click" caveat as habits.py's freeze-quota tests:
# this exercises the double-submit case (second request sees the first's
# already-committed state), not genuine concurrency, which SQLite can't
# simulate. The route's own try/except IntegrityError around the insert
# guards the real race on Postgres.


def test_vouch_repeated_clicks_cannot_create_duplicate_vouches(client, db):
    owner = _create_user(db, username="owner")
    room = _create_room(db, owner)
    owner_habit = Habit.query.filter_by(room_id=room.id, user_id=owner.id).first()
    checkin = Checkin(habit_id=owner_habit.id, date=date.today(), proof_note="note")
    db.session.add(checkin)
    db.session.commit()

    voucher = _login(client, db, username="voucher")
    _join_room_direct(db, room, voucher)

    responses = [client.post(f"/checkins/{checkin.id}/vouch", data={"emoji": "✅"}) for _ in range(3)]

    # First click adds it, second toggles it off, third adds it back - never
    # an error, and never more than one row for this (checkin, user) pair.
    assert [r.status_code for r in responses] == [200, 200, 200]
    from habitual.models import Vouch
    assert Vouch.query.filter_by(checkin_id=checkin.id, user_id=voucher.id).count() <= 1


def test_room_fully_ended_blocks_checkin_and_vouch_for_every_member(client, db):
    today = date.today()
    start = today - timedelta(days=20)
    user_a = _login(client, db, username="a")
    user_b = _create_user(db, username="b")
    room = _create_room(db, user_a, duration_days=7, start_date=start)  # final_day long past
    _join_room_direct(db, room, user_b, joined_on=start)

    habit_a = Habit.query.filter_by(room_id=room.id, user_id=user_a.id).first()
    habit_b = Habit.query.filter_by(room_id=room.id, user_id=user_b.id).first()
    checkin_b = Checkin(habit_id=habit_b.id, date=start, proof_note="old note")
    db.session.add(checkin_b)
    db.session.commit()

    members = RoomMember.query.filter_by(room_id=room.id).all()
    from habitual.rooms import room_fully_ended
    assert room_fully_ended(room, members) is True

    # The still-logged-in member (a) can't check in or vouch on b's old entry.
    assert client.post(f"/habits/{habit_a.id}/checkin").status_code == 400
    assert client.post(f"/checkins/{checkin_b.id}/vouch", data={"emoji": "✅"}).status_code == 400
