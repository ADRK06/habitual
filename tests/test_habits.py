from datetime import date, timedelta

from habitual.habits import EMOJI_CHOICES
from habitual.models import Checkin, Habit, PointTransaction, User

VALID_PASSWORD = "Sup3r$ecret"


def _create_user(db, username="aadhira", password=VALID_PASSWORD):
    user = User(name="Aadhira", username=username, timezone="Asia/Kolkata")
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    return user


def _login(client, db, username="aadhira"):
    user = _create_user(db, username=username)
    client.post("/login", data={"username": username, "password": VALID_PASSWORD, "next": ""})
    return user


def _create_habit(db, user, title="Read", emoji="📚", created_on=None):
    habit = Habit(
        user_id=user.id,
        title=title,
        emoji=emoji,
        created_on=created_on or date.today(),
    )
    db.session.add(habit)
    db.session.commit()
    return habit


# -- dashboard ---------------------------------------------------------------


def test_dashboard_requires_login(client):
    response = client.get("/dashboard")
    assert response.status_code == 302
    assert "/login" in response.location


def test_dashboard_shows_empty_state_with_no_habits(client, db):
    _login(client, db)
    response = client.get("/dashboard")
    assert response.status_code == 200
    assert b"No habits yet" in response.data


def test_dashboard_shows_habit_card(client, db):
    user = _login(client, db)
    _create_habit(db, user, title="Morning Run", emoji="🏃")
    response = client.get("/dashboard")
    assert b"Morning Run" in response.data
    assert b"No habits yet" not in response.data


# -- create habit -------------------------------------------------------------


def test_create_habit_redirects_with_new_param(client, db):
    _login(client, db)
    response = client.post("/habits", data={"title": "Drink water", "emoji": EMOJI_CHOICES[1], "tiny_version": ""})
    assert response.status_code == 302
    assert "/dashboard?new=" in response.location

    habit = Habit.query.filter_by(title="Drink water").first()
    assert habit is not None
    assert habit.emoji == EMOJI_CHOICES[1]


def test_dashboard_renders_exactly_one_emoji_field(client, db):
    # Regression: form.hidden_tag() auto-renders every HiddenField (including
    # our custom "emoji" one), which previously duplicated the Alpine-bound
    # emoji input and caused the first (empty) one to win on submit.
    _login(client, db)
    response = client.get("/dashboard")
    assert response.data.count(b'name="emoji"') == 1


def test_create_habit_rejects_blank_title(client, db):
    _login(client, db)
    response = client.post("/habits", data={"title": "   ", "emoji": EMOJI_CHOICES[0]})
    assert response.status_code == 400
    assert Habit.query.count() == 0


def test_create_habit_rejects_title_over_60_chars(client, db):
    _login(client, db)
    response = client.post("/habits", data={"title": "x" * 61, "emoji": EMOJI_CHOICES[0]})
    assert response.status_code == 400
    assert Habit.query.count() == 0


def test_create_habit_rejects_emoji_outside_picker(client, db):
    _login(client, db)
    response = client.post("/habits", data={"title": "Read", "emoji": "💩"})
    assert response.status_code == 400
    assert Habit.query.count() == 0


def test_create_habit_rejects_tiny_version_over_120_chars(client, db):
    _login(client, db)
    response = client.post(
        "/habits", data={"title": "Read", "emoji": EMOJI_CHOICES[0], "tiny_version": "x" * 121}
    )
    assert response.status_code == 400
    assert Habit.query.count() == 0


def test_create_habit_trims_title(client, db):
    _login(client, db)
    client.post("/habits", data={"title": "  Read  ", "emoji": EMOJI_CHOICES[0]})
    habit = Habit.query.first()
    assert habit.title == "Read"


# -- habit detail placeholder --------------------------------------------------


def test_habit_detail_requires_ownership(client, db):
    owner = _create_user(db, username="owner")
    habit = _create_habit(db, owner)

    _login(client, db, username="intruder")
    response = client.get(f"/habits/{habit.id}")
    assert response.status_code == 404


def test_habit_detail_renders_for_owner(client, db):
    user = _login(client, db)
    habit = _create_habit(db, user, title="Morning Run", emoji="🏃")
    response = client.get(f"/habits/{habit.id}")
    assert response.status_code == 200
    assert b"Morning Run" in response.data
    assert b"Phase 3" in response.data


# -- check-in ------------------------------------------------------------------


def test_checkin_awards_base_points_and_marks_done(client, db):
    user = _login(client, db)
    habit = _create_habit(db, user, created_on=date.today())

    response = client.post(f"/habits/{habit.id}/checkin")
    assert response.status_code == 200
    assert Checkin.query.filter_by(habit_id=habit.id).count() == 1

    amounts = [pt.amount for pt in PointTransaction.query.filter_by(habit_id=habit.id)]
    assert sum(amounts) == 5
    assert b"Checked in today" in response.data


def test_checkin_awards_milestone_bonus_on_day_seven(client, db):
    user = _login(client, db)
    today = date.today()
    habit = _create_habit(db, user, created_on=today - timedelta(days=6))

    for i in range(6):
        db.session.add(Checkin(habit_id=habit.id, date=today - timedelta(days=6 - i)))
        db.session.add(PointTransaction(
            user_id=user.id, habit_id=habit.id, amount=5, reason="daily", date=today - timedelta(days=6 - i)
        ))
    db.session.commit()

    client.post(f"/habits/{habit.id}/checkin")

    amounts = sorted(pt.amount for pt in PointTransaction.query.filter_by(habit_id=habit.id, date=today))
    assert amounts == [5, 10]  # base + day-7 milestone


def test_double_checkin_same_day_is_safe(client, db):
    user = _login(client, db)
    habit = _create_habit(db, user, created_on=date.today())

    first = client.post(f"/habits/{habit.id}/checkin")
    second = client.post(f"/habits/{habit.id}/checkin")

    assert first.status_code == 200
    assert second.status_code == 200
    assert Checkin.query.filter_by(habit_id=habit.id).count() == 1

    amounts = [pt.amount for pt in PointTransaction.query.filter_by(habit_id=habit.id)]
    assert sum(amounts) == 5  # no duplicate points from the second submit


def test_checkin_requires_ownership(client, db):
    owner = _create_user(db, username="owner")
    habit = _create_habit(db, owner)

    _login(client, db, username="intruder")
    response = client.post(f"/habits/{habit.id}/checkin")
    assert response.status_code == 404
    assert Checkin.query.filter_by(habit_id=habit.id).count() == 0


# -- delete ---------------------------------------------------------------


def test_delete_habit_removes_habit_and_its_points(client, db):
    user = _login(client, db)
    habit = _create_habit(db, user)
    client.post(f"/habits/{habit.id}/checkin")
    assert PointTransaction.query.filter_by(habit_id=habit.id).count() > 0

    response = client.delete(f"/habits/{habit.id}")
    assert response.status_code == 200
    assert db.session.get(Habit, habit.id) is None
    assert PointTransaction.query.filter_by(habit_id=habit.id).count() == 0
    assert Checkin.query.filter_by(habit_id=habit.id).count() == 0


def test_delete_last_habit_shows_empty_state_via_oob(client, db):
    user = _login(client, db)
    habit = _create_habit(db, user)

    response = client.delete(f"/habits/{habit.id}")
    assert b'id="habit-grid" hx-swap-oob="true"' in response.data
    assert b"No habits yet" in response.data


def test_delete_one_of_several_habits_keeps_grid(client, db):
    user = _login(client, db)
    habit1 = _create_habit(db, user, title="Read")
    _create_habit(db, user, title="Run")

    response = client.delete(f"/habits/{habit1.id}")
    assert b"No habits yet" not in response.data


def test_delete_habit_requires_ownership(client, db):
    owner = _create_user(db, username="owner")
    habit = _create_habit(db, owner)

    _login(client, db, username="intruder")
    response = client.delete(f"/habits/{habit.id}")
    assert response.status_code == 404
    assert db.session.get(Habit, habit.id) is not None
