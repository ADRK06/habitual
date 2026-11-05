import re
from datetime import date, timedelta
from pathlib import Path

from habitual import avatar as avatar_module
from habitual import colony as colony_module
from habitual import game
from habitual.models import Checkin, Colony, Habit, User

ART_DIR = Path(__file__).resolve().parent.parent / "habitual" / "static" / "art"

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


# -- bug-fix round: every swatch resolves, no broken <img>, Next tracks lock
# state correctly (reported from a /commander?onboarding=1 click-through) ---


def _img_srcs(html):
    """Every `src="..."` on a real <img> tag in server-rendered HTML -
    deliberately does NOT match Alpine's `:src="layerSrc(slot)"` binding
    (a literal attribute name, never interpolated server-side), since
    those live-preview layers were already verified directly in the
    browser for this bug-fix round; this only checks what the server
    itself writes into the page (picker-grid swatches, nav avatar
    layers, the moon overlay)."""
    return re.findall(r'<img\b[^>]*\bsrc="([^"]*)"', html)


def test_every_avatar_and_look_swatch_maps_to_a_file_that_exists(db):
    # (a) Sweep every (slot, value) swatch in both catalogs - starter
    # AND locked, since locked ones are try-on-able too - and confirm
    # the filename AVATAR_SWATCHES/PLANET_LOOK_SWATCHES actually built
    # exists on disk. None means "no layer", deliberately skipped (see
    # AVATAR_NO_LAYER_VALUE/PLANET_LOOK_SWATCHES' own comments).
    for (slot, value), filename in avatar_module.AVATAR_SWATCHES.items():
        if filename is None:
            continue
        assert (ART_DIR / filename).is_file(), f"missing avatar swatch for {slot}={value}: {filename}"

    for (slot, value), filename in colony_module.PLANET_LOOK_SWATCHES.items():
        if filename is None:
            continue
        assert (ART_DIR / filename).is_file(), f"missing look swatch for {slot}={value}: {filename}"


def test_commander_renders_no_broken_img_for_every_no_layer_slot(client, db):
    # (b) DEFAULT_AVATAR equips a "no layer" value on visor/hair/gear/
    # emblem simultaneously - the exact shape of the reported bug
    # (a broken-image icon at the top-left of the preview/sidebar).
    # Render the picker grid (the one place the server itself emits
    # real <img src="..."> tags for these slots, besides the nav - the
    # live preview's layers are Alpine-bound, see _img_srcs above) and
    # confirm: no empty/missing src, and every real src resolves.
    user = _login(client, db)
    user.avatar = dict(game.DEFAULT_AVATAR)
    db.session.commit()

    html = client.get("/commander").get_data(as_text=True)

    srcs = _img_srcs(html)
    assert srcs, "expected at least the picker-grid swatches to render some <img> tags"
    for src in srcs:
        assert src.strip() != "", "an <img> rendered with an empty src"
        if "/static/art/" in src:
            filename = src.rsplit("/", 1)[-1]
            assert (ART_DIR / filename).is_file(), f"<img src> points to a missing file: {src}"

    # The four no-layer values in DEFAULT_AVATAR must never appear as a
    # picker-grid thumbnail src - that slot's swatch is None, so the
    # template must fall back to the empty <span> placeholder instead.
    for slot, value in game.DEFAULT_AVATAR.items():
        if avatar_module.AVATAR_SWATCHES.get((slot, value)) is None:
            no_layer_filename = avatar_module.avatar_sprite_filename(slot, value)
            assert no_layer_filename not in html, (
                f"a 'no layer' value ({slot}={value}) must never reach an <img src>, "
                f"found {no_layer_filename} in the rendered page"
            )


def test_colony_nav_avatar_renders_no_broken_img_for_default_avatar(client, db):
    # Same DEFAULT_AVATAR, but hitting the nav shell (sidebar.html /
    # phone_hud.html both loop over nav_avatar_layers) rather than the
    # editor - the second place the original bug report named.
    user = _login(client, db)
    user.avatar = dict(game.DEFAULT_AVATAR)
    db.session.commit()
    client.post("/commander/skip")  # clears nothing (already set), just confirms the gate is open

    html = client.get("/colony").get_data(as_text=True)

    for src in _img_srcs(html):
        assert src.strip() != "", "an <img> in the nav shell rendered with an empty src"
        if "/static/art/" in src:
            filename = src.rsplit("/", 1)[-1]
            assert (ART_DIR / filename).is_file(), f"nav <img src> points to a missing file: {src}"


def test_edit_planet_renders_no_broken_img_for_default_look(client, db):
    user = _login(client, db)
    user.avatar = dict(game.DEFAULT_AVATAR)
    db.session.commit()

    html = client.get("/colony/edit").get_data(as_text=True)

    for src in _img_srcs(html):
        assert src.strip() != "", "an <img> on the planet editor rendered with an empty src"
        if "/static/art/" in src:
            filename = src.rsplit("/", 1)[-1]
            assert (ART_DIR / filename).is_file(), f"planet editor <img src> points to a missing file: {src}"


def test_avatar_catalog_lock_flags_agree_with_the_starter_whitelist():
    # (c) "Next shows when every equipped value is starter, hides when
    # one is locked" is decided client-side by Alpine's isStarter(),
    # which reads lock_reason straight out of AVATAR_CATALOG/
    # PLANET_LOOK_CATALOG (the dict this test checks) - never game.
    # AVATAR_STARTER_VALUES/LOOK_STARTER_VALUES directly. If the two
    # ever drift apart, isStarter() would flag a free value as locked
    # (or the reverse) even though game.validate_avatar_payload still
    # judges correctly - this is the server-side guard against exactly
    # that class of bug (confirmed live in the browser for this round:
    # a fresh default avatar shows Next; selecting a locked gear value
    # hides it, marks the Gear tab, and names "Gear" in the note/button).
    for slot in game.AVATAR_SLOTS:
        starter_values = set(game.AVATAR_STARTER_VALUES[slot])
        for value, _label, lock_reason in avatar_module.AVATAR_CATALOG[slot]:
            is_starter = value in starter_values
            assert (lock_reason is None) == is_starter, (
                f"avatar.AVATAR_CATALOG[{slot!r}] marks {value!r} as "
                f"{'starter' if lock_reason is None else 'locked'} but game.AVATAR_STARTER_VALUES says "
                f"{'starter' if is_starter else 'locked'}"
            )

    for slot in game.LOOK_SLOTS:
        starter_values = set(game.LOOK_STARTER_VALUES[slot])
        for value, _label, lock_reason in colony_module.PLANET_LOOK_CATALOG[slot]:
            is_starter = value in starter_values
            assert (lock_reason is None) == is_starter, (
                f"colony.PLANET_LOOK_CATALOG[{slot!r}] marks {value!r} as "
                f"{'starter' if lock_reason is None else 'locked'} but game.LOOK_STARTER_VALUES says "
                f"{'starter' if is_starter else 'locked'}"
            )


def test_next_button_markup_is_present_and_free_default_avatar_has_no_locked_slot():
    # "Never hide content by default in CSS/JS" (CLAUDE.md) means both
    # the submit button (x-show="!hasLocked()") and the "use free
    # parts" button (x-show="hasLocked()") are always in the raw HTML -
    # Alpine only toggles visibility at runtime, never server-side. So
    # the one thing pytest can assert here is the data hasLocked() is
    # computed from: DEFAULT_AVATAR's every value is a starter value
    # (so Next correctly shows with no code changes needed), and that a
    # single locked substitution correctly flips it (so "Use free
    # parts" correctly shows instead) - both mirrored from the live
    # browser confirmation for this bug-fix round.
    ok, failing_slot = game.validate_avatar_payload(game.DEFAULT_AVATAR)
    assert ok is True
    assert failing_slot is None

    locked_payload = {**game.DEFAULT_AVATAR, "gear": "lights"}  # real value, 90 Energy, not starter
    ok, failing_slot = game.validate_avatar_payload(locked_payload)
    assert ok is False
    assert failing_slot == "gear"


# -- bug-fix round 2: locked-world preview art + post-onboarding nav --------
# (reported from the live site: Lava/Ice/Ringed Giant showed a broken
# image in the planet editor's try-on preview, and there was no way
# back to either editor once onboarding finished other than the one
# "Edit planet" button on /colony.)


def test_every_catalog_world_has_a_preview_entry_that_resolves_or_is_a_placeholder():
    # colony.PLANET_WORLD_PREVIEW is what the client's worldSrc() reads
    # instead of string-concatenating "planet_render_<world>_clean.png"
    # (that concatenation is exactly what broke Lava/Ice/Ringed Giant -
    # they never got a "_clean" variant). Every world in the catalog
    # must have an entry here - None is allowed (renders the "Preview
    # coming soon" placeholder instead of a broken <img>), a filename
    # that doesn't exist on disk is not.
    catalog_worlds = {value for value, _label, _lock_reason in colony_module.PLANET_LOOK_CATALOG["world"]}
    preview_worlds = set(colony_module.PLANET_WORLD_PREVIEW.keys())
    assert catalog_worlds == preview_worlds, (
        f"every catalog world needs a PLANET_WORLD_PREVIEW entry (even None) - "
        f"missing: {catalog_worlds - preview_worlds}, extra: {preview_worlds - catalog_worlds}"
    )
    for world, filename in colony_module.PLANET_WORLD_PREVIEW.items():
        if filename is None:
            continue
        assert (ART_DIR / filename).is_file(), f"PLANET_WORLD_PREVIEW[{world!r}] points to a missing file: {filename}"


def test_commander_locker_links_to_edit_planet(client, db):
    user = _login(client, db)
    user.avatar = dict(game.DEFAULT_AVATAR)
    db.session.commit()

    html = client.get("/commander").get_data(as_text=True)

    assert 'href="/colony/edit"' in html


def test_edit_planet_links_back_to_commander_locker(client, db):
    user = _login(client, db)
    user.avatar = dict(game.DEFAULT_AVATAR)
    db.session.commit()

    html = client.get("/colony/edit").get_data(as_text=True)

    assert 'href="/commander"' in html


def test_edit_planet_onboarding_step_links_back_to_commander_step_one(client, db):
    _login(client, db)
    client.post("/commander/skip")  # advances to the planet step, same as finishing step 1 for real

    html = client.get("/colony/edit?onboarding=1").get_data(as_text=True)

    assert 'href="/commander?onboarding=1"' in html


def test_edit_planet_in_locker_mode_does_not_link_back_to_commander_step_one(client, db):
    # The onboarding-only "Back" link must not leak into the permanent
    # locker's "Edit planet" page - that page already links to /commander
    # (tested above), never /commander?onboarding=1.
    user = _login(client, db)
    user.avatar = dict(game.DEFAULT_AVATAR)
    db.session.commit()

    html = client.get("/colony/edit").get_data(as_text=True)

    assert 'href="/commander?onboarding=1"' not in html
