from datetime import date, datetime, timedelta, timezone as dt_timezone

from habitual import game
from habitual.models import Building, Checkin, Colony, Habit, PointTransaction, User

VALID_PASSWORD = "Sup3r$ecret"


def _create_user(db, username="aadhira", password=VALID_PASSWORD, timezone="Asia/Kolkata"):
    user = User(name="Aadhira", username=username, timezone=timezone)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    return user


def _login(client, db, username="aadhira", timezone="Asia/Kolkata"):
    user = _create_user(db, username=username, timezone=timezone)
    client.post("/login", data={"username": username, "password": VALID_PASSWORD, "next": ""})
    return user


def _create_habit(db, user, title="Run", category="fitness", created_on=None):
    habit = Habit(
        user_id=user.id, title=title, emoji="🏃", category=category, created_on=created_on or date.today(),
    )
    db.session.add(habit)
    db.session.commit()
    return habit


def _give_checkins(db, habit, count, start=None):
    start = start or (date.today() - timedelta(days=count))
    for i in range(count):
        db.session.add(Checkin(habit_id=habit.id, date=start + timedelta(days=i)))
    db.session.commit()


def _give_energy(db, user, amount, date_on=None):
    db.session.add(PointTransaction(
        user_id=user.id, habit_id=None, amount=amount, reason="daily", date=date_on or date.today(),
    ))
    db.session.commit()


# -- auto-create --------------------------------------------------------------


def test_colony_requires_login(client):
    response = client.get("/colony")
    assert response.status_code == 302
    assert "/login" in response.location


def test_colony_auto_creates_on_first_visit(client, db):
    user = _login(client, db)
    assert Colony.query.filter_by(user_id=user.id).count() == 0

    response = client.get("/colony")

    assert response.status_code == 200
    colony = Colony.query.filter_by(user_id=user.id).first()
    assert colony is not None
    assert colony.planet_type == "rust"


def test_colony_get_is_idempotent_no_duplicate_colony(client, db):
    user = _login(client, db)
    client.get("/colony")
    client.get("/colony")
    assert Colony.query.filter_by(user_id=user.id).count() == 1


# -- build --------------------------------------------------------------------


def test_build_blocked_below_unlock_threshold(client, db):
    user = _login(client, db)
    habit = _create_habit(db, user, category="fitness")
    _give_checkins(db, habit, 9)
    _give_energy(db, user, 500)

    response = client.post("/colony/build", data={"type": game.DEFENSE_TOWER})

    assert response.status_code == 400
    assert Building.query.count() == 0


def test_build_allowed_at_unlock_threshold_charges_cost_and_sets_pending_level_zero(client, db):
    user = _login(client, db)
    habit = _create_habit(db, user, category="fitness")
    _give_checkins(db, habit, 10)
    _give_energy(db, user, 500)

    response = client.post("/colony/build", data={"type": game.DEFENSE_TOWER})
    assert response.status_code == 302

    colony = Colony.query.filter_by(user_id=user.id).first()
    building = Building.query.filter_by(colony_id=colony.id, type=game.DEFENSE_TOWER).first()
    assert building is not None
    assert building.level == 0  # first build pending, not yet level 1
    assert building.finishes_at is not None
    assert building.slot == game.default_slot(game.DEFENSE_TOWER)

    balance = sum(pt.amount for pt in PointTransaction.query.filter_by(user_id=user.id))
    assert balance == 500 - game.next_level_cost(game.DEFENSE_TOWER, 1)
    spend = PointTransaction.query.filter_by(user_id=user.id, reason="build").first()
    assert spend.amount == -game.next_level_cost(game.DEFENSE_TOWER, 1)


def test_build_blocked_with_insufficient_balance(client, db):
    user = _login(client, db)
    habit = _create_habit(db, user, category="fitness")
    _give_checkins(db, habit, 10)
    _give_energy(db, user, 10)  # tower costs 120

    response = client.post("/colony/build", data={"type": game.DEFENSE_TOWER})

    assert response.status_code == 400
    assert Building.query.count() == 0


def test_build_blocked_if_already_started(client, db):
    user = _login(client, db)
    habit = _create_habit(db, user, category="fitness")
    _give_checkins(db, habit, 10)
    _give_energy(db, user, 1000)

    first = client.post("/colony/build", data={"type": game.DEFENSE_TOWER})
    second = client.post("/colony/build", data={"type": game.DEFENSE_TOWER})

    assert first.status_code == 302
    assert second.status_code == 400
    assert Building.query.filter_by(type=game.DEFENSE_TOWER).count() == 1


def test_build_rejects_an_unknown_type(client, db):
    user = _login(client, db)
    _give_energy(db, user, 1000)
    response = client.post("/colony/build", data={"type": "not_a_real_building"})
    assert response.status_code == 400


def test_custom_module_unlocks_from_any_ten_checkins_regardless_of_category(client, db):
    user = _login(client, db)
    habit = _create_habit(db, user, category="fitness")  # NOT "other"
    _give_checkins(db, habit, 10)
    _give_energy(db, user, 500)

    response = client.post("/colony/build", data={"type": game.CUSTOM_MODULE})

    assert response.status_code == 302
    assert Building.query.filter_by(type=game.CUSTOM_MODULE).count() == 1


def test_category_building_still_locked_with_only_other_category_checkins(client, db):
    user = _login(client, db)
    habit = _create_habit(db, user, category="other")
    _give_checkins(db, habit, 10)
    _give_energy(db, user, 500)

    response = client.post("/colony/build", data={"type": game.DEFENSE_TOWER})  # needs "fitness" specifically

    assert response.status_code == 400


def test_repeated_build_clicks_cannot_overspend_balance(client, db):
    # Same sequential "double-click" case as habits.buy_freeze's own tests -
    # true concurrent-row-lock behavior can't be exercised on SQLite, see
    # _spend_or_400's docstring; this proves the second click, arriving
    # right after the first already committed, is rejected correctly.
    user = _login(client, db)
    habit = _create_habit(db, user, category="fitness")
    _give_checkins(db, habit, 10)
    cost = game.next_level_cost(game.DEFENSE_TOWER, 1)
    _give_energy(db, user, cost)  # exactly enough for one

    responses = [client.post("/colony/build", data={"type": game.DEFENSE_TOWER}) for _ in range(3)]

    assert [r.status_code for r in responses] == [302, 400, 400]
    balance = sum(pt.amount for pt in PointTransaction.query.filter_by(user_id=user.id))
    assert balance == 0  # never negative


# -- settlement (lazy, on read) ------------------------------------------------


def test_first_build_settles_to_level_one_once_finishes_at_has_passed(client, db):
    user = _login(client, db)
    habit = _create_habit(db, user, category="fitness")
    _give_checkins(db, habit, 10)
    _give_energy(db, user, 500)
    client.post("/colony/build", data={"type": game.DEFENSE_TOWER})

    building = Building.query.filter_by(type=game.DEFENSE_TOWER).first()
    building.finishes_at = datetime.now(dt_timezone.utc) - timedelta(minutes=1)
    db.session.commit()

    client.get("/colony")

    db.session.refresh(building)
    assert building.level == 1
    assert building.finishes_at is None
    assert building.started_at is None


def test_settlement_is_idempotent(client, db):
    user = _login(client, db)
    habit = _create_habit(db, user, category="fitness")
    _give_checkins(db, habit, 10)
    _give_energy(db, user, 500)
    client.post("/colony/build", data={"type": game.DEFENSE_TOWER})

    building = Building.query.filter_by(type=game.DEFENSE_TOWER).first()
    building.finishes_at = datetime.now(dt_timezone.utc) - timedelta(minutes=1)
    db.session.commit()

    client.get("/colony")
    client.get("/colony")  # a second load after settlement must not bump it again

    db.session.refresh(building)
    assert building.level == 1


def test_upgrade_in_progress_still_shows_old_level_until_settled(client, db):
    user = _login(client, db)
    habit = _create_habit(db, user, category="fitness")
    _give_checkins(db, habit, 10)
    _give_energy(db, user, 2000)
    client.post("/colony/build", data={"type": game.DEFENSE_TOWER})
    building = Building.query.filter_by(type=game.DEFENSE_TOWER).first()
    building.finishes_at = datetime.now(dt_timezone.utc) - timedelta(minutes=1)
    db.session.commit()
    client.get("/colony")  # settle the first build to level 1

    response = client.post(f"/colony/upgrade/{building.id}")
    assert response.status_code == 302

    db.session.refresh(building)
    assert building.level == 1  # still the OLD level - not bumped yet
    assert building.finishes_at is not None

    building.finishes_at = datetime.now(dt_timezone.utc) - timedelta(minutes=1)
    db.session.commit()
    client.get("/colony")

    db.session.refresh(building)
    assert building.level == 2


def test_upgrade_blocked_while_already_in_progress(client, db):
    user = _login(client, db)
    habit = _create_habit(db, user, category="fitness")
    _give_checkins(db, habit, 10)
    _give_energy(db, user, 2000)
    client.post("/colony/build", data={"type": game.DEFENSE_TOWER})
    building = Building.query.filter_by(type=game.DEFENSE_TOWER).first()
    building.finishes_at = datetime.now(dt_timezone.utc) - timedelta(minutes=1)
    db.session.commit()
    client.get("/colony")  # settle to level 1

    first = client.post(f"/colony/upgrade/{building.id}")
    second = client.post(f"/colony/upgrade/{building.id}")

    assert first.status_code == 302
    assert second.status_code == 400
    db.session.refresh(building)
    assert building.level == 1


def test_upgrade_blocked_at_max_level(client, db):
    user = _login(client, db)
    habit = _create_habit(db, user, category="fitness")
    _give_checkins(db, habit, 10)
    _give_energy(db, user, 5000)
    client.post("/colony/build", data={"type": game.DEFENSE_TOWER})
    building = Building.query.filter_by(type=game.DEFENSE_TOWER).first()
    building.level = game.MAX_LEVEL
    building.finishes_at = None
    db.session.commit()

    response = client.post(f"/colony/upgrade/{building.id}")

    assert response.status_code == 400
    db.session.refresh(building)
    assert building.level == game.MAX_LEVEL


def test_upgrade_blocked_with_insufficient_balance(client, db):
    user = _login(client, db)
    habit = _create_habit(db, user, category="fitness")
    _give_checkins(db, habit, 10)
    _give_energy(db, user, game.next_level_cost(game.DEFENSE_TOWER, 1))
    client.post("/colony/build", data={"type": game.DEFENSE_TOWER})
    building = Building.query.filter_by(type=game.DEFENSE_TOWER).first()
    building.level = 1
    building.finishes_at = None
    db.session.commit()
    # Balance is now 0 - not enough for the LV2 upgrade.

    response = client.post(f"/colony/upgrade/{building.id}")

    assert response.status_code == 400
    db.session.refresh(building)
    assert building.level == 1


def test_upgrade_rejects_a_building_belonging_to_someone_else(client, db):
    other = _create_user(db, username="other")
    colony = Colony(user_id=other.id, name="Other's Colony", planet_type="rust", created_on=date.today())
    db.session.add(colony)
    db.session.flush()
    building = Building(colony_id=colony.id, type=game.DEFENSE_TOWER, level=1, slot=0)
    db.session.add(building)
    db.session.commit()
    other_building_id = building.id

    _login(client, db, username="user")

    response = client.post(f"/colony/upgrade/{other_building_id}")

    assert response.status_code == 404


# -- account deletion / habit archiving never touch buildings -----------------


def test_account_deletion_removes_colony_and_buildings(client, db):
    user = _login(client, db)
    habit = _create_habit(db, user, category="fitness")
    _give_checkins(db, habit, 10)
    _give_energy(db, user, 500)
    client.post("/colony/build", data={"type": game.DEFENSE_TOWER})
    user_id = user.id

    db.session.delete(db.session.get(User, user_id))
    db.session.commit()

    assert Colony.query.filter_by(user_id=user_id).count() == 0
    assert Building.query.count() == 0


def test_archiving_the_powering_habit_does_not_touch_the_building(client, db):
    user = _login(client, db)
    habit = _create_habit(db, user, category="fitness")
    _give_checkins(db, habit, 10)
    _give_energy(db, user, 500)
    client.post("/colony/build", data={"type": game.DEFENSE_TOWER})
    building = Building.query.filter_by(type=game.DEFENSE_TOWER).first()
    building.finishes_at = datetime.now(dt_timezone.utc) - timedelta(minutes=1)
    db.session.commit()
    client.get("/colony")  # settle to level 1

    client.delete(f"/habits/{habit.id}")

    stored_habit = db.session.get(Habit, habit.id)
    assert stored_habit.archived_at is not None  # confirms it actually archived
    db.session.refresh(building)
    assert building.level == 1
    assert building.finishes_at is None


def test_category_edit_moves_historical_checkins_into_the_new_categorys_count(client, db):
    # Decision 5 (accepted tradeoff): the unlock count reads the habit's
    # CURRENT category, not a per-check-in snapshot - no edit route exists
    # yet (that's UI wiring, next commit), so this confirms the underlying
    # behavior directly at the model/query level.
    from habitual.colony import _category_checkin_counts

    user = _login(client, db)
    habit = _create_habit(db, user, category="fitness")
    _give_checkins(db, habit, 10)

    assert _category_checkin_counts(user).get("fitness", 0) == 10
    assert _category_checkin_counts(user).get("study", 0) == 0

    habit.category = "study"
    db.session.commit()

    assert _category_checkin_counts(user).get("fitness", 0) == 0
    assert _category_checkin_counts(user).get("study", 0) == 10
