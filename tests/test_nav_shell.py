import secrets
from datetime import date

from habitual import game
from habitual.models import Checkin, Habit, Room, RoomMember, User
from habitual.rooms import generate_join_code

VALID_PASSWORD = "Sup3r$ecret"


def _create_user(db, username="aadhira"):
    # avatar set (not the Phase 4b onboarding NULL sentinel) - this
    # file tests the persistent nav shell, not onboarding itself.
    user = User(name="Aadhira Kamal", username=username, timezone="Asia/Kolkata", avatar=dict(game.DEFAULT_AVATAR))
    user.set_password(VALID_PASSWORD)
    db.session.add(user)
    db.session.commit()
    return user


def _login(client, db, username="aadhira"):
    user = _create_user(db, username=username)
    client.post("/login", data={"username": username, "password": VALID_PASSWORD, "next": ""})
    return user


def _create_habit(db, user, title="Read", created_on=None, frequency_type="daily"):
    habit = Habit(
        user_id=user.id, title=title, emoji="📚", created_on=created_on or date.today(),
        frequency_type=frequency_type,
    )
    db.session.add(habit)
    db.session.commit()
    return habit


def _create_room(db, creator, title="Night Owls", start_date=None):
    start_date = start_date or date.today()
    room = Room(
        title=title, emoji="🦉", creator_id=creator.id, duration_days=14, start_date=start_date,
        invite_token=secrets.token_urlsafe(16), join_code=generate_join_code(),
        frequency_type="daily",
    )
    db.session.add(room)
    db.session.flush()
    db.session.add(RoomMember(room_id=room.id, user_id=creator.id, joined_on=start_date))
    db.session.add(Habit(
        user_id=creator.id, room_id=room.id, title=title, emoji="🦉", created_on=start_date,
        frequency_type="daily",
    ))
    db.session.commit()
    return room


def _active_nav_classes(html, href, label):
    """Pulls the class="..." of the sidebar <a> for `label` whose href is
    `href` - distinguishes the real nav link from the energy/streak pills,
    which also contain a label-less <svg> and could otherwise collide."""
    import re
    m = re.search(rf'<a\s+href="{re.escape(href)}"\s+class="([^"]*)"[^>]*>\s*<svg.*?</svg>\s*{label}', html, re.S)
    return m.group(1) if m else None


# -- which items render, driven by NAV_FEATURES ------------------------------


def test_dashboard_shows_only_the_enabled_nav_items(client, db):
    _login(client, db)

    html = client.get("/dashboard").get_data(as_text=True)

    assert "COLONY" in html
    assert "HABITS" in html
    assert "FLEET" in html
    assert "COMMANDER" in html
    assert "SECTOR" not in html
    assert "GALAXY" not in html
    assert "SHOP" not in html


def test_phone_tab_bar_has_no_empty_slots(client, db):
    # Colony, Habits and Fleet are the three NAV_FEATURES-enabled items
    # eligible for the phone tab bar now (Profile isn't - PhoneNav.dc.html
    # never has a Commander tab) - the grid must divide by that real
    # count (3), not a hardcoded 5, so the tabs fill the bar evenly.
    _login(client, db)

    html = client.get("/dashboard").get_data(as_text=True)

    assert "grid-template-columns: repeat(3, minmax(0, 1fr))" in html
    assert "repeat(5, minmax(0, 1fr))" not in html


def test_no_fake_xp_or_level_anywhere_in_the_shell(client, db):
    _login(client, db)

    html = client.get("/dashboard").get_data(as_text=True)

    assert "LV " not in html
    assert "XP" not in html
    assert "THIS WEEK" not in html  # the sector widget - needs real sector data, which doesn't exist yet


# -- active-state highlighting ------------------------------------------------


def test_habits_nav_item_is_active_on_dashboard(client, db):
    _login(client, db)

    html = client.get("/dashboard").get_data(as_text=True)

    assert "text-accent" in _active_nav_classes(html, "/dashboard", "HABITS")


def test_habits_nav_item_is_active_on_habit_detail_too(client, db):
    user = _login(client, db)
    habit = _create_habit(db, user)

    html = client.get(f"/habits/{habit.id}").get_data(as_text=True)

    assert "text-accent" in _active_nav_classes(html, "/dashboard", "HABITS")


def test_commander_nav_item_is_active_on_the_commander_locker(client, db):
    # Phase 4b: "Commander" now points to avatar.commander_locker, not
    # auth.account_security (which stays reachable via a link on the
    # commander page itself - see tests/test_onboarding.py).
    _login(client, db)

    html = client.get("/commander").get_data(as_text=True)

    assert "text-accent" in _active_nav_classes(html, "/commander", "COMMANDER")


def test_fleet_nav_item_is_active_on_room_detail(client, db):
    user = _login(client, db)
    room = _create_room(db, user)

    html = client.get(f"/rooms/{room.id}").get_data(as_text=True)

    assert "text-accent" in _active_nav_classes(html, "/fleet", "FLEET")


# -- /fleet redirect -----------------------------------------------------


def test_fleet_index_redirects_to_dashboard_with_no_room(client, db):
    _login(client, db)

    response = client.get("/fleet")

    assert response.status_code == 302
    assert response.location == "/dashboard"


def test_fleet_index_redirects_to_the_users_room(client, db):
    user = _login(client, db)
    room = _create_room(db, user)

    response = client.get("/fleet")

    assert response.status_code == 302
    assert response.location == f"/rooms/{room.id}"


def test_fleet_index_redirects_to_fleet_list_with_several_rooms(client, db):
    # 2+ fleets used to guess (most recently joined) - now sent to the
    # "My fleets" list instead of picking one for the member.
    user = _login(client, db)
    _create_room(db, user, title="Night Owls")
    _create_room(db, user, title="Early Birds")

    response = client.get("/fleet")

    assert response.status_code == 302
    assert response.location == "/rooms"


def test_fleet_index_requires_login(client):
    response = client.get("/fleet")

    assert response.status_code == 302
    assert "/login" in response.location


def test_fleet_nav_item_is_active_on_fleet_list(client, db):
    user = _login(client, db)
    _create_room(db, user, title="Night Owls")
    _create_room(db, user, title="Early Birds")

    html = client.get("/rooms").get_data(as_text=True)

    assert "text-accent" in _active_nav_classes(html, "/fleet", "FLEET")


# -- real data, not placeholders ---------------------------------------------


def test_nav_streak_pill_reflects_a_real_streak(client, db):
    user = _login(client, db)
    habit = _create_habit(db, user, created_on=date(2026, 1, 1))
    db.session.add(Checkin(habit_id=habit.id, date=date(2026, 1, 1)))
    db.session.add(Checkin(habit_id=habit.id, date=date(2026, 1, 2)))
    db.session.add(Checkin(habit_id=habit.id, date=date(2026, 1, 3)))
    db.session.commit()

    html = client.get("/dashboard").get_data(as_text=True)

    assert "3d" in html


def test_nav_balance_pill_reflects_the_real_point_balance(client, db):
    import re

    user = _login(client, db)
    habit = _create_habit(db, user)
    # Through the real check-in route (not a raw Checkin insert) - that's
    # what actually writes the PointTransaction the balance pill reads.
    client.post(f"/habits/{habit.id}/checkin")

    html = client.get("/dashboard").get_data(as_text=True)

    # A fresh daily habit's first check-in = 5 balance (points.py) -
    # confirms the pill renders that real number, not an empty string
    # from a missing nav_balance key.
    m = re.search(r'text-phosphor">\s*<svg.*?</svg>\s*(\d+)\s*</span>', html, re.S)
    assert m is not None, "energy pill not found in rendered dashboard"
    assert m.group(1) == "5"
