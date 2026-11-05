from datetime import date, timedelta

from habitual import game
from habitual.models import Checkin, Colony, Habit, User

VALID_PASSWORD = "Sup3r$ecret"


def _create_user(db, username="aadhira", timezone="Asia/Kolkata"):
    # avatar deliberately NOT set - this IS the onboarding sentinel
    # this whole file exists to test (see habitual.avatar.
    # onboarding_redirect_or_none). Every other test file's own
    # _create_user sets a starter avatar instead, to simulate an
    # already-onboarded user.
    user = User(name="Aadhira", username=username, timezone=timezone)
    user.set_password(VALID_PASSWORD)
    db.session.add(user)
    db.session.commit()
    return user


def _login(client, db, username="aadhira", timezone="Asia/Kolkata"):
    user = _create_user(db, username=username, timezone=timezone)
    client.post("/login", data={"username": username, "password": VALID_PASSWORD, "next": ""})
    return user


def _create_habit(db, user, title="Run", category="fitness"):
    habit = Habit(user_id=user.id, title=title, emoji="🏃", category=category, created_on=date.today())
    db.session.add(habit)
    db.session.commit()
    return habit


VALID_AVATAR = {
    "helmet": "box", "visor": "rust", "face": "3", "hair": "silver",
    "suit": "phosphor", "gear": "antenna", "emblem": "bolt",
}
VALID_LOOK = {"world": "verdant", "atmosphere": "steel", "ring": "none", "moons": "one", "name": "Kepler-9"}


# -- the gate: avatar IS NULL is the one and only sentinel -------------------


def test_colony_gates_a_never_onboarded_user_to_commander(client, db):
    _login(client, db)

    response = client.get("/colony")

    assert response.status_code == 302
    assert response.location == "/commander?onboarding=1"


def test_dashboard_gates_a_never_onboarded_user_to_commander(client, db):
    _login(client, db)

    response = client.get("/dashboard")

    assert response.status_code == 302
    assert response.location == "/commander?onboarding=1"


def test_existing_user_with_null_avatar_is_gated_too(client, db):
    # Same sentinel covers a pre-Phase-4b account logging in for the
    # first time post-migration, not just a brand-new signup - there's
    # no separate "is this user new" flag anywhere.
    user = _login(client, db)
    assert user.avatar is None  # confirms this is really the post-migration case, not a fluke

    response = client.get("/colony")

    assert response.status_code == 302
    assert response.location == "/commander?onboarding=1"


def test_gate_does_not_fire_once_avatar_is_set(client, db):
    user = _login(client, db)
    user.avatar = dict(game.DEFAULT_AVATAR)
    db.session.commit()

    assert client.get("/colony").status_code == 200
    assert client.get("/dashboard").status_code == 200


# -- /commander ---------------------------------------------------------------


def test_commander_post_valid_starter_values_saves_and_clears_the_gate(client, db):
    user = _login(client, db)

    response = client.post("/commander", data=VALID_AVATAR)

    assert response.status_code == 302
    db.session.refresh(user)
    assert user.avatar == VALID_AVATAR
    assert client.get("/colony").status_code == 200  # gate cleared


def test_commander_onboarding_post_redirects_to_the_planet_step(client, db):
    _login(client, db)

    response = client.post("/commander?onboarding=1", data=VALID_AVATAR)

    assert response.status_code == 302
    assert response.location == "/colony/edit?onboarding=1"


def test_commander_rejects_a_locked_value_without_saving(client, db):
    user = _login(client, db)
    payload = {**VALID_AVATAR, "suit": "steel"}  # real value, bought (150 Energy) - not starter

    response = client.post("/commander", data=payload)

    assert response.status_code == 200  # re-rendered, not redirected - a soft block
    db.session.refresh(user)
    assert user.avatar is None  # never written - still the pre-onboarding sentinel


def test_commander_rejects_an_unknown_value_without_saving(client, db):
    user = _login(client, db)
    payload = {**VALID_AVATAR, "helmet": "xyz"}

    client.post("/commander", data=payload)

    db.session.refresh(user)
    assert user.avatar is None


def test_commander_ignores_an_extra_unrecognized_form_field(client, db):
    # The route builds the payload by enumerating game.AVATAR_SLOTS
    # (never by passing the raw request dict through), so an extra key
    # the form never declared is simply dropped, not a rejection - the
    # rest of a valid submission still saves normally. "Unknown slot"
    # rejection is still covered directly in tests/test_game.py for
    # game.validate_avatar_payload itself; it's unreachable via this
    # route by construction.
    user = _login(client, db)
    payload = {**VALID_AVATAR, "wings": "none"}

    client.post("/commander", data=payload)

    db.session.refresh(user)
    assert user.avatar == VALID_AVATAR


def test_commander_skip_writes_the_default_avatar_and_advances(client, db):
    user = _login(client, db)

    response = client.post("/commander/skip")

    assert response.status_code == 302
    assert response.location == "/colony/edit?onboarding=1"
    db.session.refresh(user)
    assert user.avatar == dict(game.DEFAULT_AVATAR)


def test_commander_skip_is_idempotent_never_overwrites_a_real_choice(client, db):
    user = _login(client, db)
    client.post("/commander", data=VALID_AVATAR)
    db.session.refresh(user)
    assert user.avatar == VALID_AVATAR

    client.post("/commander/skip")

    db.session.refresh(user)
    assert user.avatar == VALID_AVATAR  # untouched, not reset to DEFAULT_AVATAR


def test_commander_locker_links_to_account_security(client, db):
    # Addition: "Commander" now owns the nav slot auth.account_security
    # used to - keep password/email/delete-account settings reachable
    # from the commander page itself (this template is responsive, so
    # one link covers desktop and phone both).
    user = _login(client, db)
    user.avatar = dict(game.DEFAULT_AVATAR)
    db.session.commit()

    html = client.get("/commander").get_data(as_text=True)

    assert 'href="/account/security"' in html


def test_commander_stays_freely_resavable_after_onboarding(client, db):
    user = _login(client, db)
    client.post("/commander", data=VALID_AVATAR)

    other_avatar = {**VALID_AVATAR, "helmet": "round", "emblem": "star"}
    response = client.post("/commander", data=other_avatar)

    assert response.status_code == 302
    db.session.refresh(user)
    assert user.avatar == other_avatar  # no "only once" lock


# -- /colony/edit ---------------------------------------------------------------


def test_edit_planet_post_valid_values_saves(client, db):
    user = _login(client, db)
    user.avatar = dict(game.DEFAULT_AVATAR)
    db.session.commit()

    response = client.post("/colony/edit", data=VALID_LOOK)

    assert response.status_code == 302
    colony = Colony.query.filter_by(user_id=user.id).first()
    assert colony.look == {k: v for k, v in VALID_LOOK.items() if k != "name"}
    assert colony.name == "Kepler-9"


def test_edit_planet_onboarding_with_zero_habits_redirects_to_create_habit(client, db):
    _login(client, db)
    client.post("/commander/skip")

    response = client.post("/colony/edit?onboarding=1", data=VALID_LOOK)

    assert response.status_code == 302
    assert response.location == "/dashboard?open=create-habit&onboarding=1"


def test_edit_planet_onboarding_with_an_existing_habit_redirects_to_colony(client, db):
    # The "same two screens" design (not three) for a user who already
    # has habits - no separate "is this user new" flag, just a live
    # query against Habit.active().
    user = _login(client, db)
    client.post("/commander/skip")
    _create_habit(db, user)

    response = client.post("/colony/edit?onboarding=1", data=VALID_LOOK)

    assert response.status_code == 302
    assert response.location == "/colony"


def test_edit_planet_rejects_a_locked_world_without_saving(client, db):
    user = _login(client, db)
    user.avatar = dict(game.DEFAULT_AVATAR)
    db.session.commit()
    payload = {**VALID_LOOK, "world": "lava"}  # real value, bought (400 Energy) - not starter

    response = client.post("/colony/edit", data=payload)

    assert response.status_code == 200
    colony = Colony.query.filter_by(user_id=user.id).first()
    assert colony.look["world"] == "rust"  # unchanged (the auto-created default)


def test_edit_planet_rejects_an_unknown_moons_value_without_saving(client, db):
    user = _login(client, db)
    user.avatar = dict(game.DEFAULT_AVATAR)
    db.session.commit()
    payload = {**VALID_LOOK, "moons": "three"}

    client.post("/colony/edit", data=payload)

    colony = Colony.query.filter_by(user_id=user.id).first()
    assert colony.look["moons"] == "none"  # unchanged


def test_edit_planet_rejects_a_name_over_60_characters(client, db):
    user = _login(client, db)
    user.avatar = dict(game.DEFAULT_AVATAR)
    db.session.commit()
    payload = {**VALID_LOOK, "name": "x" * 61}

    response = client.post("/colony/edit", data=payload)

    assert response.status_code == 200
    colony = Colony.query.filter_by(user_id=user.id).first()
    assert colony.name != "x" * 61


def test_edit_planet_skip_leaves_look_untouched(client, db):
    user = _login(client, db)
    client.post("/commander/skip")
    client.get("/colony/edit?onboarding=1")  # creates the Colony row, same as a real visit would
    colony = Colony.query.filter_by(user_id=user.id).first()
    look_before = dict(colony.look)

    response = client.post("/colony/edit/skip")

    assert response.status_code == 302
    db.session.refresh(colony)
    assert colony.look == look_before


def test_planet_editor_stays_freely_resavable_after_onboarding(client, db):
    user = _login(client, db)
    user.avatar = dict(game.DEFAULT_AVATAR)
    db.session.commit()
    client.post("/colony/edit", data=VALID_LOOK)

    response = client.post("/colony/edit", data={**VALID_LOOK, "world": "dust", "name": "New Name"})

    assert response.status_code == 302
    colony = Colony.query.filter_by(user_id=user.id).first()
    assert colony.look["world"] == "dust"
    assert colony.name == "New Name"


# -- create_habit's onboarding branch -----------------------------------------


def test_create_habit_without_onboarding_flag_redirects_to_dashboard_as_before(client, db):
    user = _login(client, db)
    user.avatar = dict(game.DEFAULT_AVATAR)
    db.session.commit()

    response = client.post("/habits", data={"title": "Read", "emoji": "📚", "category": "study", "frequency_type": "daily"})

    assert response.status_code == 302
    assert response.location.startswith("/dashboard")
    assert "onboarding" not in response.location


def test_create_habit_with_onboarding_flag_redirects_to_colony(client, db):
    user = _login(client, db)
    user.avatar = dict(game.DEFAULT_AVATAR)
    db.session.commit()

    response = client.post(
        "/habits?onboarding=1", data={"title": "Read", "emoji": "📚", "category": "study", "frequency_type": "daily"},
    )

    assert response.status_code == 302
    assert response.location == "/colony"


# -- addition D: tampered values never reach a filename -----------------------


def test_tampered_avatar_value_is_rejected_before_any_render(client, db):
    # A direct validator check, not a 404-on-the-static-file check -
    # the guarantee is that game.validate_avatar_payload rejects this
    # BEFORE current_user.avatar is ever written, so no template ever
    # builds a filename from it in the first place.
    ok, failing_slot = game.validate_avatar_payload({**VALID_AVATAR, "suit": "../../etc/passwd"})
    assert ok is False
    assert failing_slot == "suit"


def test_tampered_look_value_is_rejected_before_any_render(client, db):
    ok, failing_slot = game.validate_look_payload({**{k: v for k, v in VALID_LOOK.items() if k != "name"}, "world": "../secret"})
    assert ok is False
    assert failing_slot == "world"


def test_tampered_value_posted_to_commander_never_reaches_the_db(client, db):
    user = _login(client, db)
    payload = {**VALID_AVATAR, "emblem": "<script>alert(1)</script>"}

    client.post("/commander", data=payload)

    db.session.refresh(user)
    assert user.avatar is None  # never written, regardless of what WTForms' own validator does with it
