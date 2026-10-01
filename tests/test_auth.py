from datetime import datetime, timedelta, timezone as dt_timezone

from habitual.auth import _aware_utc, safe_next_path
from habitual.models import User

VALID_PASSWORD = "Sup3r$ecret"


def _signup_payload(**overrides):
    payload = {
        "name": "Aadhira",
        "username": "aadhira",
        "password": VALID_PASSWORD,
        "confirm_password": VALID_PASSWORD,
        "timezone": "Asia/Kolkata",
    }
    payload.update(overrides)
    return payload


def _create_user(db, username="aadhira", password=VALID_PASSWORD):
    user = User(name="Aadhira", username=username, timezone="Asia/Kolkata")
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    return user


# -- safe next= redirect -----------------------------------------------------

def test_safe_next_path_allows_relative():
    assert safe_next_path("/join/abc123") == "/join/abc123"


def test_safe_next_path_rejects_external_url():
    assert safe_next_path("https://evil.com/phish") is None
    assert safe_next_path("//evil.com/phish") is None
    assert safe_next_path("javascript:alert(1)") is None
    assert safe_next_path("evil.com/phish") is None
    assert safe_next_path("") is None
    assert safe_next_path(None) is None


def test_login_redirects_to_safe_next(client, db):
    _create_user(db)
    response = client.post(
        "/login?next=/join/abc123",
        data={"username": "aadhira", "password": VALID_PASSWORD, "next": "/join/abc123"},
    )
    assert response.status_code == 302
    assert response.location == "/join/abc123"


def test_login_ignores_external_next(client, db):
    _create_user(db)
    response = client.post(
        "/login",
        data={"username": "aadhira", "password": VALID_PASSWORD, "next": "https://evil.com"},
    )
    assert response.status_code == 302
    assert response.location == "/dashboard"


# -- signup -------------------------------------------------------------------

def test_signup_creates_user_and_logs_in(client, db):
    response = client.post("/signup", data=_signup_payload())
    assert response.status_code == 302
    assert response.location == "/dashboard"
    assert User.query.filter_by(username="aadhira").count() == 1


def test_signup_password_mismatch_rejected(client, db):
    response = client.post("/signup", data=_signup_payload(confirm_password="Different1!"))
    assert response.status_code == 200
    assert b"Passwords must match" in response.data
    assert User.query.count() == 0


def test_signup_invalid_timezone_falls_back(client, db):
    client.post("/signup", data=_signup_payload(timezone="Not/ARealZone"))
    user = User.query.filter_by(username="aadhira").first()
    assert user.timezone == "Asia/Kolkata"


def test_signup_stores_browser_detected_timezone(client, db):
    client.post("/signup", data=_signup_payload(timezone="America/New_York"))
    user = User.query.filter_by(username="aadhira").first()
    assert user.timezone == "America/New_York"


def test_signup_page_renders_exactly_one_timezone_field(client):
    # Regression: form.hidden_tag() auto-renders every HiddenField (including
    # "timezone" and "next"), which previously duplicated the explicitly
    # re-rendered, JS-populated timezone input. The browser then submitted
    # both, and the first (empty, JS never touches it) value always won,
    # silently discarding the real browser-detected timezone.
    response = client.get("/signup")
    assert response.data.count(b'name="timezone"') == 1
    assert response.data.count(b'name="next"') == 1


def test_signup_duplicate_username_rejected(client, db):
    _create_user(db)
    response = client.post("/signup", data=_signup_payload(name="Someone Else"))
    assert response.status_code == 200
    assert b"taken" in response.data
    assert User.query.count() == 1


# -- login: generic error + lockout -------------------------------------------

def test_login_wrong_password_generic_message(client, db):
    _create_user(db)
    response = client.post("/login", data={"username": "aadhira", "password": "wrong", "next": ""})
    assert b"Incorrect username or password" in response.data


def test_login_unknown_username_generic_message(client, db):
    response = client.post("/login", data={"username": "ghost", "password": "whatever", "next": ""})
    assert b"Incorrect username or password" in response.data


def test_login_locks_after_five_failures(client, db):
    _create_user(db)
    for _ in range(5):
        client.post("/login", data={"username": "aadhira", "password": "wrong", "next": ""})

    user = User.query.filter_by(username="aadhira").first()
    assert user.failed_login_attempts == 5
    assert user.locked_until is not None
    assert _aware_utc(user.locked_until) > datetime.now(dt_timezone.utc)


def test_login_lockout_checked_before_password(client, db):
    user = _create_user(db)
    user.locked_until = datetime.now(dt_timezone.utc) + timedelta(minutes=10)
    db.session.commit()

    # Correct password, but still locked - lockout must be checked first.
    response = client.post("/login", data={"username": "aadhira", "password": VALID_PASSWORD, "next": ""})
    assert b"Too many failed attempts" in response.data


def test_successful_login_resets_lockout_counters(client, db):
    user = _create_user(db)
    user.failed_login_attempts = 3
    db.session.commit()

    client.post("/login", data={"username": "aadhira", "password": VALID_PASSWORD, "next": ""})

    user = User.query.filter_by(username="aadhira").first()
    assert user.failed_login_attempts == 0
    assert user.locked_until is None


# -- misc routes ----------------------------------------------------------------

def test_check_username_reports_taken(client, db):
    _create_user(db)
    response = client.get("/auth/check-username?username=aadhira")
    assert b"taken" in response.data


def test_check_username_reports_available(client, db):
    response = client.get("/auth/check-username?username=freshname")
    assert b"available" in response.data


def test_logout_requires_login(client):
    response = client.post("/logout")
    assert response.status_code == 302
    assert "/login" in response.location
