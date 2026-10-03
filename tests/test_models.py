from datetime import date

from habitual.models import Habit, Room, User


def test_password_hash_roundtrip(db):
    user = User(name="Aadhira", username="aadhira")
    user.set_password("Sup3r$ecret")
    db.session.add(user)
    db.session.commit()

    assert user.check_password("Sup3r$ecret") is True
    assert user.check_password("wrong-password") is False


def test_defaults(db):
    user = User(name="Aadhira", username="aadhira2")
    user.set_password("Sup3r$ecret")
    db.session.add(user)
    db.session.commit()

    assert user.timezone == "Asia/Kolkata"
    assert user.theme == "dark"
    assert user.failed_login_attempts == 0
    assert user.locked_until is None


def test_habit_frequency_defaults_to_daily_with_no_other_fields_set(db):
    user = User(name="Aadhira", username="aadhira3")
    user.set_password("Sup3r$ecret")
    db.session.add(user)
    db.session.commit()

    habit = Habit(user_id=user.id, title="Read", emoji="📚", created_on=date.today())
    db.session.add(habit)
    db.session.commit()

    assert habit.frequency_type == "daily"
    assert habit.frequency_days is None
    assert habit.frequency_target is None
    assert habit.frequency_changed_on is None


def test_room_frequency_defaults_to_daily(db):
    user = User(name="Aadhira", username="aadhira4")
    user.set_password("Sup3r$ecret")
    db.session.add(user)
    db.session.commit()

    room = Room(
        title="Run Club", emoji="🏃", creator_id=user.id, duration_days=14,
        start_date=date.today(), invite_token="tok", join_code="ABCDEF",
    )
    db.session.add(room)
    db.session.commit()

    assert room.frequency_type == "daily"
    assert room.frequency_days is None
    assert room.frequency_target is None
