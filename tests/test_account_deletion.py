import secrets
from datetime import date, datetime, timedelta, timezone as dt_timezone

from habitual.models import (
    Badge, Checkin, EmailToken, Freeze, Habit, PointTransaction, RateLimit, Room, RoomCrown, RoomMember,
    User, Vouch,
)
from habitual.rooms import generate_join_code

VALID_PASSWORD = "Tangerine7!Comet"


def _create_user(db, username="aadhira", email=None, password=VALID_PASSWORD):
    user = User(name=username.title(), username=username, timezone="Asia/Kolkata", email=email)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    return user


def _login(client, db, username="aadhira", email=None, password=VALID_PASSWORD):
    user = _create_user(db, username=username, email=email, password=password)
    client.post("/login", data={"username": username, "password": password, "next": ""})
    return user


def _create_habit(db, user, title="Read", created_on=None, room_id=None):
    habit = Habit(
        user_id=user.id, room_id=room_id, title=title, emoji="📚",
        created_on=created_on or date.today(),
    )
    db.session.add(habit)
    db.session.commit()
    return habit


def _create_room(db, creator, title="Run Club"):
    today = date.today()
    room = Room(
        title=title, emoji="🏃", creator_id=creator.id, duration_days=14, start_date=today,
        invite_token=secrets.token_urlsafe(16), join_code=generate_join_code(),
    )
    db.session.add(room)
    db.session.flush()
    db.session.add(RoomMember(room_id=room.id, user_id=creator.id, joined_on=today))
    db.session.add(Habit(user_id=creator.id, room_id=room.id, title=title, emoji="🏃", created_on=today))
    db.session.commit()
    return room


def _join_room(db, room, user, joined_on=None):
    joined_on = joined_on or date.today()
    db.session.add(RoomMember(room_id=room.id, user_id=user.id, joined_on=joined_on))
    db.session.add(Habit(user_id=user.id, room_id=room.id, title=room.title, emoji=room.emoji, created_on=joined_on))
    db.session.commit()


def _delete_payload(username=None, password=VALID_PASSWORD):
    return {"confirm_username": username or "aadhira", "password": password}


# -- happy path: full deletion, no orphans ------------------------------------


def test_delete_account_removes_everything_and_the_user_row(client, db):
    user = _login(client, db, email="aadhira@example.com")
    habit = _create_habit(db, user)
    db.session.add(Checkin(habit_id=habit.id, date=date.today()))
    db.session.add(Freeze(user_id=user.id))  # unused freeze, no habit_id
    db.session.add(PointTransaction(user_id=user.id, habit_id=habit.id, amount=5, reason="daily", date=date.today()))
    db.session.add(PointTransaction(user_id=user.id, habit_id=None, amount=-50, reason="freeze_purchase", date=date.today()))
    db.session.add(Badge(user_id=user.id, type="first_checkin", earned_on=date.today()))
    db.session.add(EmailToken(
        user_id=user.id, token_hash="x" * 64, purpose="verify_email", target_email="aadhira@example.com",
        expires_at=datetime.now(dt_timezone.utc) + timedelta(hours=1),
    ))
    db.session.commit()
    user_id = user.id

    response = client.post("/account/security/delete", data=_delete_payload())
    assert response.status_code == 302
    assert response.location == "/"

    assert User.query.filter_by(id=user_id).first() is None
    assert Habit.query.filter_by(user_id=user_id).count() == 0
    assert Checkin.query.join(Habit, isouter=True).filter(Habit.id.is_(None)).count() == 0
    assert Freeze.query.filter_by(user_id=user_id).count() == 0
    assert PointTransaction.query.filter_by(user_id=user_id).count() == 0
    assert Badge.query.filter_by(user_id=user_id).count() == 0
    assert EmailToken.query.filter_by(user_id=user_id).count() == 0


def test_delete_account_removes_vouches_given_and_received_but_not_others_habits(client, db):
    other = _create_user(db, username="other")
    other_habit = _create_habit(db, other, title="Other's habit")
    other_checkin = Checkin(habit_id=other_habit.id, date=date.today())
    db.session.add(other_checkin)
    db.session.commit()

    bystander = _create_user(db, username="bystander")
    bystander_habit = _create_habit(db, bystander, title="Bystander's habit")
    bystander_checkin = Checkin(habit_id=bystander_habit.id, date=date.today())
    db.session.add(bystander_checkin)
    db.session.commit()

    user = _login(client, db, username="aadhira")
    habit = _create_habit(db, user, title="Mine")
    my_checkin = Checkin(habit_id=habit.id, date=date.today())
    db.session.add(my_checkin)
    db.session.commit()

    # I vouch on the other person's check-in (vouch GIVEN, dies via user_id);
    # they vouch on mine (vouch RECEIVED, dies when my checkin's habit goes);
    # and - uninvolved with me at all - other vouches on bystander's checkin,
    # which must survive completely untouched.
    db.session.add(Vouch(checkin_id=other_checkin.id, user_id=user.id, emoji="✅"))
    db.session.add(Vouch(checkin_id=my_checkin.id, user_id=other.id, emoji="🔥"))
    db.session.add(Vouch(checkin_id=bystander_checkin.id, user_id=other.id, emoji="✅"))
    db.session.commit()

    client.post("/account/security/delete", data=_delete_payload())

    assert Vouch.query.filter_by(user_id=user.id).count() == 0  # given, by user_id
    assert Vouch.query.filter_by(checkin_id=other_checkin.id).count() == 0  # the vouch I gave is gone
    assert Habit.query.filter_by(user_id=user.id).count() == 0
    # Nobody else's data is touched, including a vouch that never involved
    # the deleted account at all.
    assert Habit.query.filter_by(id=other_habit.id).count() == 1
    assert Checkin.query.filter_by(id=other_checkin.id).count() == 1
    assert Vouch.query.filter_by(checkin_id=bystander_checkin.id, user_id=other.id).count() == 1


def test_delete_account_removes_its_rate_limit_rows_but_not_ip_keyed_ones(client, db):
    user = _login(client, db, email="aadhira@example.com")
    db.session.add(RateLimit(key=f"user:{user.id}", scope="verify_resend", attempts=1))
    db.session.add(RateLimit(key="aadhira@example.com", scope="forgot_email", attempts=1))
    db.session.add(RateLimit(key="1.2.3.4", scope="forgot_ip", attempts=3))
    db.session.commit()

    client.post("/account/security/delete", data=_delete_payload())

    assert RateLimit.query.filter_by(key=f"user:{user.id}", scope="verify_resend").count() == 0
    assert RateLimit.query.filter_by(key="aadhira@example.com", scope="forgot_email").count() == 0
    assert RateLimit.query.filter_by(key="1.2.3.4", scope="forgot_ip").count() == 1  # not theirs - untouched


def test_delete_account_leaves_another_users_data_completely_untouched(client, db):
    other = _create_user(db, username="other")
    other_habit = _create_habit(db, other, title="Keep me")
    db.session.add(Checkin(habit_id=other_habit.id, date=date.today()))
    db.session.add(PointTransaction(user_id=other.id, habit_id=other_habit.id, amount=5, reason="daily", date=date.today()))
    db.session.commit()

    _login(client, db, username="aadhira")
    client.post("/account/security/delete", data=_delete_payload())

    assert User.query.filter_by(username="other").count() == 1
    assert Habit.query.filter_by(id=other_habit.id).count() == 1
    assert Checkin.query.filter_by(habit_id=other_habit.id).count() == 1
    assert PointTransaction.query.filter_by(habit_id=other_habit.id).count() == 1


# -- rooms: ownership transfer / room deletion / crown history ---------------


def test_delete_account_as_creator_transfers_ownership_to_top_ranked_member(client, db):
    creator = _login(client, db, username="aadhira")
    room = _create_room(db, creator)
    other = _create_user(db, username="other")
    _join_room(db, room, other)

    # Give the other member more points so they're unambiguously top-ranked.
    other_habit = Habit.query.filter_by(room_id=room.id, user_id=other.id).first()
    db.session.add(PointTransaction(user_id=other.id, habit_id=other_habit.id, amount=100, reason="daily", date=date.today()))
    db.session.commit()

    room_id, creator_id = room.id, creator.id
    client.post("/account/security/delete", data=_delete_payload())

    room = Room.query.filter_by(id=room_id).first()
    assert room is not None
    assert room.creator_id == other.id
    assert RoomMember.query.filter_by(room_id=room_id, user_id=creator_id).count() == 0
    assert Habit.query.filter_by(room_id=room_id, user_id=creator_id).count() == 0
    # The other member's own room habit survives untouched.
    assert Habit.query.filter_by(room_id=room_id, user_id=other.id).count() == 1


def test_delete_account_as_last_member_deletes_the_room(client, db):
    creator = _login(client, db, username="aadhira")
    room = _create_room(db, creator)
    room_id = room.id

    client.post("/account/security/delete", data=_delete_payload())

    assert Room.query.filter_by(id=room_id).first() is None
    assert RoomMember.query.filter_by(room_id=room_id).count() == 0


def test_delete_account_keeps_room_crown_history_with_user_reference_cleared(client, db):
    winner = _login(client, db, username="aadhira")
    room = _create_room(db, winner)
    other = _create_user(db, username="other")
    _join_room(db, room, other)

    db.session.add(RoomCrown(room_id=room.id, date=date.today() - timedelta(days=1), user_id=winner.id, checkin_id=None))
    db.session.commit()
    room_id = room.id

    client.post("/account/security/delete", data=_delete_payload())

    crown = RoomCrown.query.filter_by(room_id=room_id).first()
    assert crown is not None  # history survives
    assert crown.user_id is None  # reference cleared
    assert Room.query.filter_by(id=room_id).first() is not None  # other member keeps the room


# -- validation / lockout -----------------------------------------------------


def test_delete_account_rejects_wrong_password(client, db):
    user = _login(client, db)
    response = client.post("/account/security/delete", data=_delete_payload(password="wrongwrong"))
    assert response.status_code == 400
    assert b"Incorrect password" in response.data
    assert User.query.filter_by(username=user.username).count() == 1


def test_delete_account_rejects_wrong_username_text(client, db):
    user = _login(client, db)
    response = client.post("/account/security/delete", data=_delete_payload(username="notmyusername"))
    assert response.status_code == 400
    assert b"not your username" in response.data
    assert User.query.filter_by(username=user.username).count() == 1


def test_delete_account_locks_after_five_failed_attempts(client, db):
    user = _login(client, db)
    for _ in range(5):
        client.post("/account/security/delete", data=_delete_payload(password="wrongwrong"))

    user = User.query.filter_by(username=user.username).first()
    assert user.failed_delete_attempts == 5
    assert user.delete_locked_until is not None

    # Even the CORRECT password is now refused until the lock expires.
    response = client.post("/account/security/delete", data=_delete_payload(), follow_redirects=True)
    assert b"Too many failed attempts" in response.data
    assert User.query.filter_by(username=user.username).count() == 1


def test_delete_account_requires_login(client):
    response = client.post("/account/security/delete", data=_delete_payload())
    assert response.status_code == 302
    assert "/login" in response.location


# -- logout / session invalidation --------------------------------------------


def test_delete_account_logs_out_the_current_session(client, db):
    _login(client, db)
    client.post("/account/security/delete", data=_delete_payload())

    response = client.get("/dashboard")
    assert response.status_code == 302
    assert "/login" in response.location


def test_delete_account_flashes_confirmation(client, db):
    _login(client, db)
    client.post("/account/security/delete", data=_delete_payload())
    home = client.get("/")
    assert b"account has been deleted" in home.data
