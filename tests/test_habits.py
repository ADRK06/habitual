import json
from datetime import date, timedelta

from habitual.habits import EMOJI_CHOICES
from habitual.models import Checkin, Freeze, Habit, PointTransaction, User

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
    assert b"Done today" in response.data


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


def test_checkin_response_includes_header_oob_with_correct_totals(client, db):
    user = _login(client, db)
    habit = _create_habit(db, user, created_on=date.today())

    response = client.post(f"/habits/{habit.id}/checkin")
    assert b'id="header-stats"' in response.data
    assert b'hx-swap-oob="true"' in response.data
    assert b'data-counter="5"' in response.data


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


def test_delete_habit_removes_a_freeze_used_on_it_but_not_unused_freezes(client, db):
    user = _login(client, db)
    today = date.today()
    yesterday = today - timedelta(days=1)
    habit = _create_habit(db, user, created_on=today - timedelta(days=3))
    for i in (3, 2):
        d = today - timedelta(days=i)
        db.session.add(Checkin(habit_id=habit.id, date=d))
        db.session.add(PointTransaction(user_id=user.id, habit_id=habit.id, amount=5, reason="daily", date=d))
    db.session.add(Freeze(user_id=user.id, habit_id=habit.id, used_on=yesterday))  # used on this habit
    db.session.add(Freeze(user_id=user.id))  # unused, not tied to any habit
    db.session.commit()

    client.delete(f"/habits/{habit.id}")

    assert Freeze.query.filter_by(habit_id=habit.id).count() == 0  # the used one went with the habit
    assert Freeze.query.filter_by(user_id=user.id, used_on=None).count() == 1  # the unused one survives


def test_delete_response_includes_header_oob_with_correct_totals(client, db):
    user = _login(client, db)
    habit1 = _create_habit(db, user, title="Read")
    habit2 = _create_habit(db, user, title="Run")
    client.post(f"/habits/{habit1.id}/checkin")  # +5, will be deleted
    client.post(f"/habits/{habit2.id}/checkin")  # +5, stays

    response = client.delete(f"/habits/{habit1.id}")
    assert b'id="header-stats"' in response.data
    assert b'hx-swap-oob="true"' in response.data
    assert b'data-counter="5"' in response.data  # only habit2's points remain


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


# -- undo check-in --------------------------------------------------------


def test_undo_checkin_removes_checkin_and_its_points(client, db):
    user = _login(client, db)
    habit = _create_habit(db, user, created_on=date.today())
    client.post(f"/habits/{habit.id}/checkin")

    response = client.delete(f"/habits/{habit.id}/checkin")
    assert response.status_code == 200
    assert Checkin.query.filter_by(habit_id=habit.id).count() == 0
    assert PointTransaction.query.filter_by(habit_id=habit.id).count() == 0
    assert b"Check in" in response.data
    assert b"Done today" not in response.data


def test_checkin_undo_then_checkin_again_gives_identical_totals(client, db):
    user = _login(client, db)
    habit = _create_habit(db, user, created_on=date.today())

    client.post(f"/habits/{habit.id}/checkin")
    first_amounts = sorted(pt.amount for pt in PointTransaction.query.filter_by(habit_id=habit.id))

    client.delete(f"/habits/{habit.id}/checkin")
    client.post(f"/habits/{habit.id}/checkin")
    second_amounts = sorted(pt.amount for pt in PointTransaction.query.filter_by(habit_id=habit.id))

    assert first_amounts == second_amounts == [5]
    assert Checkin.query.filter_by(habit_id=habit.id).count() == 1


def test_undo_on_a_milestone_day_removes_the_bonus_too(client, db):
    user = _login(client, db)
    today = date.today()
    habit = _create_habit(db, user, created_on=today - timedelta(days=6))

    for i in range(6):
        d = today - timedelta(days=6 - i)
        db.session.add(Checkin(habit_id=habit.id, date=d))
        db.session.add(PointTransaction(user_id=user.id, habit_id=habit.id, amount=5, reason="daily", date=d))
    db.session.commit()

    client.post(f"/habits/{habit.id}/checkin")
    assert sum(pt.amount for pt in PointTransaction.query.filter_by(habit_id=habit.id, date=today)) == 15

    client.delete(f"/habits/{habit.id}/checkin")
    assert Checkin.query.filter_by(habit_id=habit.id, date=today).count() == 0
    assert PointTransaction.query.filter_by(habit_id=habit.id, date=today).count() == 0


def test_cannot_undo_a_past_days_checkin(client, db):
    user = _login(client, db)
    today = date.today()
    yesterday = today - timedelta(days=1)
    habit = _create_habit(db, user, created_on=yesterday)
    db.session.add(Checkin(habit_id=habit.id, date=yesterday))
    db.session.add(PointTransaction(user_id=user.id, habit_id=habit.id, amount=5, reason="daily", date=yesterday))
    db.session.commit()

    # No checkin exists for *today*, so there's nothing this route can touch,
    # regardless of what happened yesterday.
    response = client.delete(f"/habits/{habit.id}/checkin")
    assert response.status_code == 404
    assert Checkin.query.filter_by(habit_id=habit.id, date=yesterday).count() == 1
    assert PointTransaction.query.filter_by(habit_id=habit.id, date=yesterday).count() == 1


def test_undo_checkin_does_not_break_a_freeze_used_for_yesterday(client, db):
    user = _login(client, db)
    today = date.today()
    yesterday = today - timedelta(days=1)
    habit = _create_habit(db, user, created_on=today - timedelta(days=2))

    older = today - timedelta(days=2)
    db.session.add(Checkin(habit_id=habit.id, date=older))
    db.session.add(PointTransaction(user_id=user.id, habit_id=habit.id, amount=5, reason="daily", date=older))
    db.session.add(Freeze(user_id=user.id, habit_id=habit.id, used_on=yesterday))
    db.session.commit()

    client.post(f"/habits/{habit.id}/checkin")
    client.delete(f"/habits/{habit.id}/checkin")

    freeze = Freeze.query.filter_by(habit_id=habit.id).first()
    assert freeze is not None
    assert freeze.used_on == yesterday


def test_undo_checkin_requires_ownership(client, db):
    owner = _create_user(db, username="owner")
    today = date.today()
    habit = _create_habit(db, owner, created_on=today)
    db.session.add(Checkin(habit_id=habit.id, date=today))
    db.session.add(PointTransaction(user_id=owner.id, habit_id=habit.id, amount=5, reason="daily", date=today))
    db.session.commit()

    _login(client, db, username="intruder")
    response = client.delete(f"/habits/{habit.id}/checkin")
    assert response.status_code == 404
    assert Checkin.query.filter_by(habit_id=habit.id).count() == 1


# -- proof note -----------------------------------------------------------


def test_checkin_stores_proof_note(client, db):
    user = _login(client, db)
    habit = _create_habit(db, user, created_on=date.today())

    client.post(f"/habits/{habit.id}/checkin", data={"proof_note": "Ran 5k this morning"})
    checkin = Checkin.query.filter_by(habit_id=habit.id).first()
    assert checkin.proof_note == "Ran 5k this morning"


def test_checkin_truncates_proof_note_over_280_chars(client, db):
    user = _login(client, db)
    habit = _create_habit(db, user, created_on=date.today())

    client.post(f"/habits/{habit.id}/checkin", data={"proof_note": "x" * 300})
    checkin = Checkin.query.filter_by(habit_id=habit.id).first()
    assert len(checkin.proof_note) == 280


# -- milestone toast --------------------------------------------------------


def test_checkin_toast_names_the_milestone_on_day_seven(client, db):
    user = _login(client, db)
    today = date.today()
    habit = _create_habit(db, user, created_on=today - timedelta(days=6))
    for i in range(6):
        d = today - timedelta(days=6 - i)
        db.session.add(Checkin(habit_id=habit.id, date=d))
        db.session.add(PointTransaction(user_id=user.id, habit_id=habit.id, amount=5, reason="daily", date=d))
    db.session.commit()

    response = client.post(f"/habits/{habit.id}/checkin")
    trigger = json.loads(response.headers["HX-Trigger"])
    assert "Week streak bonus" in trigger["toast"]["message"]
    assert trigger["checkinCelebration"]["milestone"] is True


def test_checkin_toast_is_generic_on_a_normal_day(client, db):
    user = _login(client, db)
    habit = _create_habit(db, user, created_on=date.today())

    response = client.post(f"/habits/{habit.id}/checkin")
    assert "+5 points!" in response.headers["HX-Trigger"]


# -- create habit templates --------------------------------------------------


def test_dashboard_shows_habit_templates(client, db):
    _login(client, db)
    response = client.get("/dashboard")
    assert b"Quick start" in response.data
    assert b"Drink water" in response.data


def test_create_habit_form_xdata_attribute_is_well_formed(client, db):
    # Regression: Flask's |tojson marks its output as pre-escaped for <script>
    # context. Used directly inside an HTML attribute (x-data="...") its raw
    # quotes terminate the attribute early and corrupt the whole form -
    # Alpine never saw title/tinyVersion as declared properties. |forceescape
    # re-applies HTML-entity escaping so the browser decodes it correctly.
    _login(client, db)
    response = client.get("/dashboard")
    assert b'x-data="{ emoji: ""' not in response.data
    assert b"&#34;&#34;" in response.data


# -- buy freeze -------------------------------------------------------------


def test_buy_freeze_succeeds_with_enough_balance(client, db):
    user = _login(client, db)
    db.session.add(PointTransaction(user_id=user.id, habit_id=None, amount=50, reason="daily", date=date.today()))
    db.session.commit()

    response = client.post("/freezes/buy")
    assert response.status_code == 200
    assert Freeze.query.filter_by(user_id=user.id, used_on=None).count() == 1
    spend = [pt.amount for pt in PointTransaction.query.filter_by(user_id=user.id, reason="freeze_purchase")]
    assert spend == [-50]
    assert sum(pt.amount for pt in PointTransaction.query.filter_by(user_id=user.id)) == 0


def test_buy_freeze_response_is_header_stats_without_oob_wrapper(client, db):
    user = _login(client, db)
    db.session.add(PointTransaction(user_id=user.id, habit_id=None, amount=50, reason="daily", date=date.today()))
    db.session.commit()

    response = client.post("/freezes/buy")
    assert b'id="header-stats"' in response.data
    assert b'hx-swap-oob="true"' not in response.data


def test_buy_freeze_rejected_without_enough_balance(client, db):
    user = _login(client, db)
    response = client.post("/freezes/buy")
    assert response.status_code == 400
    assert Freeze.query.filter_by(user_id=user.id).count() == 0


def test_buy_freeze_rejected_at_max_held(client, db):
    user = _login(client, db)
    db.session.add(PointTransaction(user_id=user.id, habit_id=None, amount=150, reason="daily", date=date.today()))
    db.session.add(Freeze(user_id=user.id))
    db.session.add(Freeze(user_id=user.id))
    db.session.commit()

    response = client.post("/freezes/buy")
    assert response.status_code == 400
    assert Freeze.query.filter_by(user_id=user.id, used_on=None).count() == 2


# -- use freeze -------------------------------------------------------------


def _give_freeze(db, user):
    freeze = Freeze(user_id=user.id)
    db.session.add(freeze)
    db.session.commit()
    return freeze


def test_dashboard_grid_shows_save_your_streak_for_an_eligible_habit(client, db):
    # Regression: dashboard.html's {% with %} block for the card grid lists
    # each field it forwards into habit_card.html by name. can_save_streak
    # and has_freeze_to_use were added to _habit_view()'s return dict but
    # not to that list, so they were silently Undefined (falsy) only on
    # this route - the checkin/freeze HTMX partials pass context straight
    # through and never showed the bug.
    user = _login(client, db)
    today = date.today()
    habit = _create_habit(db, user, created_on=today - timedelta(days=3))
    for i in (3, 2):
        d = today - timedelta(days=i)
        db.session.add(Checkin(habit_id=habit.id, date=d))
        db.session.add(PointTransaction(user_id=user.id, habit_id=habit.id, amount=5, reason="daily", date=d))
    db.session.commit()
    _give_freeze(db, user)

    response = client.get("/dashboard")
    assert b"Save your streak" in response.data


def test_save_your_streak_is_disabled_without_a_freeze_held(client, db):
    user = _login(client, db)
    today = date.today()
    habit = _create_habit(db, user, created_on=today - timedelta(days=3))
    for i in (3, 2):
        d = today - timedelta(days=i)
        db.session.add(Checkin(habit_id=habit.id, date=d))
        db.session.add(PointTransaction(user_id=user.id, habit_id=habit.id, amount=5, reason="daily", date=d))
    db.session.commit()

    response = client.get("/dashboard")
    assert b"Save your streak" in response.data
    assert b"disabled" in response.data
    assert b"Buy a freeze" in response.data


def test_use_freeze_saves_a_missed_yesterday(client, db):
    user = _login(client, db)
    today = date.today()
    yesterday = today - timedelta(days=1)
    habit = _create_habit(db, user, created_on=today - timedelta(days=3))
    for i in (3, 2):
        d = today - timedelta(days=i)
        db.session.add(Checkin(habit_id=habit.id, date=d))
        db.session.add(PointTransaction(user_id=user.id, habit_id=habit.id, amount=5, reason="daily", date=d))
    db.session.commit()
    _give_freeze(db, user)

    response = client.post(f"/habits/{habit.id}/freeze")
    assert response.status_code == 200
    freeze = Freeze.query.filter_by(habit_id=habit.id).first()
    assert freeze is not None
    assert freeze.used_on == yesterday
    assert Freeze.query.filter_by(user_id=user.id, used_on=None).count() == 0
    assert b"Save your streak" not in response.data


def test_use_freeze_response_includes_header_oob(client, db):
    user = _login(client, db)
    today = date.today()
    habit = _create_habit(db, user, created_on=today - timedelta(days=3))
    for i in (3, 2):
        d = today - timedelta(days=i)
        db.session.add(Checkin(habit_id=habit.id, date=d))
        db.session.add(PointTransaction(user_id=user.id, habit_id=habit.id, amount=5, reason="daily", date=d))
    db.session.commit()
    _give_freeze(db, user)

    response = client.post(f"/habits/{habit.id}/freeze")
    assert b'id="header-stats"' in response.data
    assert b'hx-swap-oob="true"' in response.data
    assert b"\xf0\x9f\xa7\x8a 0/2" in response.data  # the one freeze we had just got consumed


def test_use_freeze_requires_an_eligible_gap(client, db):
    user = _login(client, db)
    habit = _create_habit(db, user, created_on=date.today())
    _give_freeze(db, user)

    response = client.post(f"/habits/{habit.id}/freeze")
    assert response.status_code == 400
    assert Freeze.query.filter_by(user_id=user.id, used_on=None).count() == 1


def test_use_freeze_requires_an_unused_freeze(client, db):
    user = _login(client, db)
    today = date.today()
    habit = _create_habit(db, user, created_on=today - timedelta(days=3))
    for i in (3, 2):
        d = today - timedelta(days=i)
        db.session.add(Checkin(habit_id=habit.id, date=d))
        db.session.add(PointTransaction(user_id=user.id, habit_id=habit.id, amount=5, reason="daily", date=d))
    db.session.commit()

    response = client.post(f"/habits/{habit.id}/freeze")
    assert response.status_code == 400


def test_use_freeze_requires_ownership(client, db):
    owner = _create_user(db, username="owner")
    today = date.today()
    habit = _create_habit(db, owner, created_on=today - timedelta(days=3))
    for i in (3, 2):
        d = today - timedelta(days=i)
        db.session.add(Checkin(habit_id=habit.id, date=d))
        db.session.add(PointTransaction(user_id=owner.id, habit_id=habit.id, amount=5, reason="daily", date=d))
    db.session.add(Freeze(user_id=owner.id))
    db.session.commit()

    _login(client, db, username="intruder")
    response = client.post(f"/habits/{habit.id}/freeze")
    assert response.status_code == 404


# -- freeze quota invariants under rapid repeated requests -------------------
#
# These exercise the sequential "double-click" case: a second request that
# arrives right after the first one already committed must see the updated
# state and get rejected. buy_freeze/use_freeze also take a row lock
# (SELECT ... FOR UPDATE on the user) so two genuinely *concurrent* requests
# on Postgres serialize instead of both reading stale state - that specific
# race can't be exercised here since the test suite runs on SQLite, which
# doesn't support row-level locking and these calls run sequentially anyway.


def test_buy_freeze_repeated_clicks_cannot_overspend_balance(client, db):
    user = _login(client, db)
    db.session.add(PointTransaction(user_id=user.id, habit_id=None, amount=50, reason="daily", date=date.today()))
    db.session.commit()

    responses = [client.post("/freezes/buy") for _ in range(3)]

    assert [r.status_code for r in responses] == [200, 400, 400]
    assert Freeze.query.filter_by(user_id=user.id).count() == 1
    balance = sum(pt.amount for pt in PointTransaction.query.filter_by(user_id=user.id))
    assert balance == 0  # never negative


def test_buy_freeze_repeated_clicks_cannot_exceed_max_held(client, db):
    user = _login(client, db)
    db.session.add(PointTransaction(user_id=user.id, habit_id=None, amount=500, reason="daily", date=date.today()))
    db.session.add(Freeze(user_id=user.id))  # already holding 1
    db.session.commit()

    responses = [client.post("/freezes/buy") for _ in range(3)]

    assert [r.status_code for r in responses] == [200, 400, 400]
    assert Freeze.query.filter_by(user_id=user.id, used_on=None).count() == 2


def test_use_freeze_repeated_clicks_consume_only_one_freeze(client, db):
    user = _login(client, db)
    today = date.today()
    habit_a = _create_habit(db, user, title="A", created_on=today - timedelta(days=3))
    habit_b = _create_habit(db, user, title="B", created_on=today - timedelta(days=3))
    for habit in (habit_a, habit_b):
        for i in (3, 2):
            d = today - timedelta(days=i)
            db.session.add(Checkin(habit_id=habit.id, date=d))
            db.session.add(PointTransaction(user_id=user.id, habit_id=habit.id, amount=5, reason="daily", date=d))
    db.session.add(Freeze(user_id=user.id))  # only one freeze held
    db.session.commit()

    response_a = client.post(f"/habits/{habit_a.id}/freeze")
    response_b = client.post(f"/habits/{habit_b.id}/freeze")

    assert response_a.status_code == 200
    assert response_b.status_code == 400  # no freeze left for B
    assert Freeze.query.filter_by(user_id=user.id).count() == 1
    freeze = Freeze.query.filter_by(user_id=user.id).first()
    assert freeze.habit_id == habit_a.id  # went to A, not silently stolen by B


def test_use_freeze_after_todays_checkin_reprices_today(client, db):
    # 6-day streak ending the day before yesterday, yesterday missed, today
    # checked in *before* the freeze is bought - so today prices as day 1
    # (5 pts) at checkin time. Buying the freeze afterwards bridges
    # yesterday, making today actually the 7th day of the streak - its
    # ledger entries must be corrected up to the milestone total, exactly
    # matching what checking in *after* the freeze would have paid.
    user = _login(client, db)
    today = date.today()
    habit = _create_habit(db, user, created_on=today - timedelta(days=7))

    for i in range(7, 1, -1):  # today-7 .. today-2: 6 consecutive days
        d = today - timedelta(days=i)
        db.session.add(Checkin(habit_id=habit.id, date=d))
        db.session.add(PointTransaction(user_id=user.id, habit_id=habit.id, amount=5, reason="daily", date=d))
    db.session.commit()

    client.post(f"/habits/{habit.id}/checkin")
    before = sorted(pt.amount for pt in PointTransaction.query.filter_by(habit_id=habit.id, date=today))
    assert before == [5]

    _give_freeze(db, user)
    response = client.post(f"/habits/{habit.id}/freeze")
    assert response.status_code == 200

    after = sorted(pt.amount for pt in PointTransaction.query.filter_by(habit_id=habit.id, date=today))
    assert after == [5, 10]  # repriced up to the day-7 milestone


def test_undo_after_freeze_reprice_removes_both_entries_and_keeps_freeze(client, db):
    user = _login(client, db)
    today = date.today()
    yesterday = today - timedelta(days=1)
    habit = _create_habit(db, user, created_on=today - timedelta(days=7))
    for i in range(7, 1, -1):
        d = today - timedelta(days=i)
        db.session.add(Checkin(habit_id=habit.id, date=d))
        db.session.add(PointTransaction(user_id=user.id, habit_id=habit.id, amount=5, reason="daily", date=d))
    db.session.commit()

    client.post(f"/habits/{habit.id}/checkin")
    _give_freeze(db, user)
    client.post(f"/habits/{habit.id}/freeze")
    assert sum(pt.amount for pt in PointTransaction.query.filter_by(habit_id=habit.id, date=today)) == 15

    client.delete(f"/habits/{habit.id}/checkin")
    assert PointTransaction.query.filter_by(habit_id=habit.id, date=today).count() == 0
    assert Checkin.query.filter_by(habit_id=habit.id, date=today).count() == 0

    freeze = Freeze.query.filter_by(habit_id=habit.id).first()
    assert freeze is not None
    assert freeze.used_on == yesterday
