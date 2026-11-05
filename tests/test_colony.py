import json
from datetime import date, timedelta

from habitual import game
from habitual.models import Checkin, Colony, Habit, PointTransaction, User

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


# -- derived building level ---------------------------------------------------


def test_locked_building_shows_category_name_and_progress(client, db):
    user = _login(client, db)
    habit = _create_habit(db, user, category="study")
    _give_checkins(db, habit, 4)

    html = client.get("/colony").get_data(as_text=True)

    assert "Study" in html
    assert "4/10" in html
    assert "Research Lab" not in html  # not built yet - only the category label shows


def test_building_reaches_level_one_at_ten_checkins(client, db):
    user = _login(client, db)
    habit = _create_habit(db, user, category="fitness")
    _give_checkins(db, habit, 10)

    html = client.get("/colony").get_data(as_text=True)

    assert "Defense Tower" in html
    assert "LV1" in html
    assert "10/30" in html  # progress toward LV2


def test_building_reaches_level_two_at_thirty_checkins(client, db):
    user = _login(client, db)
    habit = _create_habit(db, user, category="fitness")
    _give_checkins(db, habit, 30)

    html = client.get("/colony").get_data(as_text=True)

    assert "LV2" in html
    assert "30/60" in html


def test_building_maxes_at_level_three_with_no_further_progress_shown(client, db):
    user = _login(client, db)
    habit = _create_habit(db, user, category="fitness")
    _give_checkins(db, habit, 60)

    html = client.get("/colony").get_data(as_text=True)

    assert "LV3" in html
    assert "60/" not in html  # maxed - no "next threshold" fraction


def test_building_level_never_regresses_past_max_with_more_checkins(client, db):
    user = _login(client, db)
    habit = _create_habit(db, user, category="fitness")
    _give_checkins(db, habit, 200)

    html = client.get("/colony").get_data(as_text=True)

    assert "LV3" in html
    assert "LV4" not in html


def test_a_checkin_only_ever_advances_its_own_habits_building(client, db):
    # Each check-in advances exactly one building - the one for its own
    # habit's category - never any other, and never Custom Module unless
    # the habit's own category IS "other".
    user = _login(client, db)
    habit = _create_habit(db, user, category="fitness")
    _give_checkins(db, habit, 10)

    html = client.get("/colony").get_data(as_text=True)

    assert "Defense Tower" in html  # fitness's building, built
    # A locked tile never renders the building's own name - only the
    # category label - so Custom Module staying locked means "Custom
    # Module" doesn't appear in the page at all, and "Other" (its locked
    # label) does.
    assert "Custom Module" not in html
    assert "Other" in html


def test_custom_module_counts_only_the_other_categorys_own_checkins(client, db):
    user = _login(client, db)
    other_habit = _create_habit(db, user, title="Journal", category="other")
    fitness_habit = _create_habit(db, user, title="Run", category="fitness")
    _give_checkins(db, other_habit, 10)
    _give_checkins(db, fitness_habit, 10)  # must NOT count toward Custom Module

    html = client.get("/colony").get_data(as_text=True)

    custom_module_start = html.index("Custom Module")
    assert "LV1" in html[custom_module_start:custom_module_start + 200]
    assert "LV2" not in html[custom_module_start:custom_module_start + 200]


def test_category_building_stays_locked_with_only_other_category_checkins(client, db):
    user = _login(client, db)
    habit = _create_habit(db, user, category="other")
    _give_checkins(db, habit, 10)

    html = client.get("/colony").get_data(as_text=True)

    # "Fitness" (the locked label) appears, Defense Tower (the built name) does not.
    assert "Fitness" in html
    assert "Defense Tower" not in html


def test_archiving_the_powering_habit_does_not_lower_the_level(client, db):
    # Archived habits still count toward a building's level - same
    # reasoning as the daily cap and badges' lifetime counting: archiving
    # must never look like losing progress.
    user = _login(client, db)
    habit = _create_habit(db, user, category="fitness")
    _give_checkins(db, habit, 10)
    db.session.commit()

    client.delete(f"/habits/{habit.id}")

    stored = db.session.get(Habit, habit.id)
    assert stored.archived_at is not None  # confirms it actually archived

    html = client.get("/colony").get_data(as_text=True)
    assert "LV1" in html


def test_category_edit_moves_historical_checkins_into_the_new_categorys_count(client, db):
    # Accepted tradeoff (decided for Phase 4a): the level reads the
    # habit's CURRENT category, not a per-check-in snapshot - relabeling
    # a habit moves its historical check-ins with it. Visuals only right
    # now (buildings have no gameplay effect), explicitly accepted.
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


# -- UI / check-in integration -------------------------------------------------


def test_colony_home_renders_header_stats_and_habit_list(client, db):
    user = _login(client, db)
    habit = _create_habit(db, user, title="Morning run", category="fitness")
    _give_checkins(db, habit, 10)
    _give_energy(db, user, 500)

    html = client.get("/colony").get_data(as_text=True)

    assert "Morning run" in html
    assert "Colony LV" in html
    assert 'id="colony-planet"' in html
    assert "Defense Tower" in html


def test_colony_nav_item_links_to_colony_home(client, db):
    _login(client, db)
    html = client.get("/colony").get_data(as_text=True)
    assert 'href="/colony"' in html


def test_checkin_from_colony_page_swaps_the_colony_panel_and_carries_points_earned(client, db):
    user = _login(client, db)
    habit = _create_habit(db, user, title="Morning run", category="fitness")

    response = client.post(f"/habits/{habit.id}/checkin", data={"colony_view": "1"})

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert 'id="colony-panel"' in html
    trigger = json.loads(response.headers["HX-Trigger"])
    assert trigger["checkinCelebration"]["pointsEarned"] == 5
    assert trigger["checkinCelebration"]["habitId"] == habit.id


def test_colony_habit_row_has_a_proof_note_popover(client, db):
    user = _login(client, db)
    habit = _create_habit(db, user, title="Morning run", category="fitness")

    html = client.get("/colony").get_data(as_text=True)
    assert f"colony-proof-note-{habit.id}" in html
    assert "Add a note? (optional)" in html


def test_checkin_from_colony_page_saves_the_proof_note(client, db):
    user = _login(client, db)
    habit = _create_habit(db, user, title="Morning run", category="fitness")

    response = client.post(
        f"/habits/{habit.id}/checkin", data={"colony_view": "1", "proof_note": "Ran 5k"},
    )

    assert response.status_code == 200
    checkin = Checkin.query.filter_by(habit_id=habit.id).first()
    assert checkin.proof_note == "Ran 5k"


def test_undo_checkin_lowers_the_derived_level_back_down(client, db):
    # decision 3: undoing a check-in that had pushed a building over a
    # threshold must drop the level back down cleanly - no error, no
    # stale "built" state left over from before the undo.
    user = _login(client, db)
    habit = _create_habit(db, user, category="fitness")
    _give_checkins(db, habit, 9)
    today = date.today()
    client.post(f"/habits/{habit.id}/checkin")  # the 10th - crosses into LV1

    html = client.get("/colony").get_data(as_text=True)
    assert "LV1" in html

    response = client.delete(f"/habits/{habit.id}/checkin")
    assert response.status_code == 200

    html = client.get("/colony").get_data(as_text=True)
    assert "LV1" not in html
    assert "9/10" in html


def test_checkin_suppressed_by_anti_farming_still_counts_toward_building_level(client, db):
    # decision 3: a check-in whose Energy is withheld (here: the existing
    # archive-then-recreate-same-day suppression from Phase 3) still
    # counts toward the building's level - the Checkin row exists either
    # way, and level is derived from Checkin rows, never from the ledger.
    user = _login(client, db)
    habit1 = _create_habit(db, user, title="Run", category="fitness")
    _give_checkins(db, habit1, 9)
    client.delete(f"/habits/{habit1.id}")  # archives it today

    response = client.post(
        "/habits", data={"title": "Run", "emoji": "🏃", "category": "fitness", "frequency_type": "daily"},
    )
    assert response.status_code == 302
    habit2 = Habit.active().filter_by(user_id=user.id, title="Run").first()
    assert habit2.first_day_points_suppressed is True

    response = client.post(f"/habits/{habit2.id}/checkin")  # the 10th check-in overall, suppressed Energy
    assert PointTransaction.query.filter_by(habit_id=habit2.id).count() == 0  # confirms it was suppressed

    html = client.get("/colony").get_data(as_text=True)
    assert "LV1" in html  # still counted toward the level

    # decision 3 + 4 together: the level-up event fires even though Energy
    # was withheld - it's driven by the Checkin row, never the ledger.
    trigger = json.loads(response.headers["HX-Trigger"])
    assert trigger["buildingProgress"]["buildingType"] == "defense_tower"
    assert trigger["buildingProgress"]["level"] == 1


# -- check-in level-up event (toast/pulse, decision 4) -----------------------


def test_checkin_that_crosses_a_threshold_fires_building_level_up_event(client, db):
    user = _login(client, db)
    habit = _create_habit(db, user, category="fitness")
    _give_checkins(db, habit, 9)

    response = client.post(f"/habits/{habit.id}/checkin")  # the 10th - crosses into LV1

    trigger = json.loads(response.headers["HX-Trigger"])
    assert trigger["buildingProgress"] == {
        "buildingType": "defense_tower", "level": 1, "message": "Defense Tower built!",
    }


def test_checkin_that_reaches_a_higher_level_says_reached_not_built(client, db):
    user = _login(client, db)
    habit = _create_habit(db, user, category="fitness")
    _give_checkins(db, habit, 29)

    response = client.post(f"/habits/{habit.id}/checkin")  # the 30th - crosses into LV2

    trigger = json.loads(response.headers["HX-Trigger"])
    assert trigger["buildingProgress"] == {
        "buildingType": "defense_tower", "level": 2, "message": "Defense Tower reached LV2!",
    }


def test_checkin_that_does_not_cross_a_threshold_fires_no_building_level_up_event(client, db):
    user = _login(client, db)
    habit = _create_habit(db, user, category="fitness")
    _give_checkins(db, habit, 4)

    response = client.post(f"/habits/{habit.id}/checkin")  # the 5th - nowhere near LV1's 10

    trigger = json.loads(response.headers["HX-Trigger"])
    assert "buildingProgress" not in trigger


def test_checkin_already_at_max_level_fires_no_building_level_up_event(client, db):
    user = _login(client, db)
    habit = _create_habit(db, user, category="fitness")
    _give_checkins(db, habit, 60)

    response = client.post(f"/habits/{habit.id}/checkin")  # the 61st - already LV3 (max)

    trigger = json.loads(response.headers["HX-Trigger"])
    assert "buildingProgress" not in trigger


def test_checkin_in_other_category_level_up_counts_only_its_own_checkins(client, db):
    user = _login(client, db)
    # A distractor habit in a different category, well past Custom
    # Module's own LV1 threshold on its own - must never count toward it.
    fitness_habit = _create_habit(db, user, title="Run", category="fitness")
    other_habit = _create_habit(db, user, title="Journal", category="other")
    _give_checkins(db, fitness_habit, 50)
    _give_checkins(db, other_habit, 9)

    response = client.post(f"/habits/{other_habit.id}/checkin")  # other's own 10th - crosses Custom Module into LV1

    trigger = json.loads(response.headers["HX-Trigger"])
    assert trigger["buildingProgress"] == {
        "buildingType": "custom_module", "level": 1, "message": "Custom Module built!",
    }


def test_loading_the_colony_page_never_fires_a_building_level_up_event(client, db):
    # decision 4: the event is computed exactly once, inside checkin()
    # itself, right after a NEW Checkin row commits - a GET never goes
    # anywhere near that code path, even when a habit is already sitting
    # exactly at a level threshold.
    user = _login(client, db)
    habit = _create_habit(db, user, category="fitness")
    _give_checkins(db, habit, 10)

    response = client.get("/colony")

    assert "HX-Trigger" not in response.headers


def test_undo_checkin_fires_no_building_level_up_event(client, db):
    user = _login(client, db)
    habit = _create_habit(db, user, category="fitness")
    _give_checkins(db, habit, 9)
    client.post(f"/habits/{habit.id}/checkin")  # the 10th - crosses into LV1

    response = client.delete(f"/habits/{habit.id}/checkin")

    if "HX-Trigger" in response.headers:
        trigger = json.loads(response.headers["HX-Trigger"])
        assert "buildingProgress" not in trigger


# -- account deletion -----------------------------------------------------


def test_account_deletion_removes_the_colony(client, db):
    user = _login(client, db)
    habit = _create_habit(db, user, category="fitness")
    _give_checkins(db, habit, 10)
    client.get("/colony")
    user_id = user.id

    db.session.delete(db.session.get(User, user_id))
    db.session.commit()

    assert Colony.query.filter_by(user_id=user_id).count() == 0
