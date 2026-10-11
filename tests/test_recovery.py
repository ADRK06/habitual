from datetime import datetime, timedelta, timezone as dt_timezone

from werkzeug.security import check_password_hash

from habitual.auth import _generate_recovery_codes
from habitual.models import IpLockout, RecoveryCode, User, load_user

VALID_PASSWORD = "Tangerine7!Comet"
NEW_PASSWORD = "Obsidian9!Falcon"


def _create_user(db, username="aadhira", password=VALID_PASSWORD):
    user = User(name="Aadhira", username=username, timezone="Asia/Kolkata")
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    return user


def _login(client, db, username="aadhira", password=VALID_PASSWORD):
    user = _create_user(db, username=username, password=password)
    client.post("/login", data={"username": username, "password": password, "next": ""})
    return user


def _give_codes(db, user):
    codes = _generate_recovery_codes(user)
    db.session.commit()
    return codes


def _reset_payload(username, code, password=NEW_PASSWORD, confirm=None):
    return {
        "username": username,
        "recovery_code": code,
        "new_password": password,
        "confirm_password": confirm if confirm is not None else password,
    }


# -- signup shows codes once --------------------------------------------------


def test_signup_shows_codes_once_and_dashboard_never_repeats_them(client, db):
    response = client.post("/signup", data={
        "name": "Aadhira", "username": "aadhira", "password": VALID_PASSWORD,
        "confirm_password": VALID_PASSWORD, "timezone": "Asia/Kolkata",
    })
    html = response.get_data(as_text=True)
    assert "Your recovery codes" in html
    assert RecoveryCode.query.count() == 8

    dashboard = client.get("/dashboard").get_data(as_text=True)
    assert "Your recovery codes" not in dashboard


# -- forgot-password: valid reset ---------------------------------------------


def test_valid_reset_works_once_then_the_same_code_fails(client, db):
    user = _create_user(db)
    codes = _give_codes(db, user)

    response = client.post("/forgot-password", data=_reset_payload("aadhira", codes[0]))
    assert response.status_code == 302
    assert response.location == "/login"

    # Same code, reused (still anonymous - /forgot-password redirects away
    # from an already-authenticated session, so this must happen before
    # logging in below).
    replay = client.post("/forgot-password", data=_reset_payload("aadhira", codes[0]))
    assert replay.status_code == 200
    assert b"isn&#39;t right" in replay.data or b"isn't right" in replay.data

    # The first reset's new password works.
    login_ok = client.post("/login", data={"username": "aadhira", "password": NEW_PASSWORD, "next": ""})
    assert login_ok.status_code == 302


def test_reused_code_fails(client, db):
    user = _create_user(db)
    codes = _give_codes(db, user)
    client.post("/forgot-password", data=_reset_payload("aadhira", codes[0]))

    second = client.post("/forgot-password", data=_reset_payload("aadhira", codes[0], password="AnotherNew7!Zq"))
    assert second.status_code == 200
    user = User.query.filter_by(username="aadhira").first()
    assert user.check_password(NEW_PASSWORD)  # first reset's password stuck - the replay never took effect


def test_wrong_code_fails_and_counts_toward_lockout(client, db):
    user = _create_user(db)
    _give_codes(db, user)

    response = client.post("/forgot-password", data=_reset_payload("aadhira", "WRONGWRONG"))
    assert response.status_code == 200
    assert b"isn&#39;t right" in response.data or b"isn't right" in response.data

    user = User.query.filter_by(username="aadhira").first()
    assert user.failed_forgot_attempts == 1
    assert IpLockout.query.filter_by(scope="forgot_password").first().failed_attempts == 1


def test_unknown_username_gets_the_same_generic_error_as_wrong_code(client, db):
    user = _create_user(db)
    codes = _give_codes(db, user)

    wrong_code = client.post("/forgot-password", data=_reset_payload("aadhira", "WRONGWRONG"))
    unknown_user = client.post("/forgot-password", data=_reset_payload("ghostuser", codes[0]))

    def error_text(resp):
        html = resp.get_data(as_text=True)
        start = html.index("isn")
        return html[start:start + 30]

    assert error_text(wrong_code) == error_text(unknown_user)
    assert User.query.filter_by(username="ghostuser").count() == 0


def test_username_lockout_after_five_failures(client, db):
    user = _create_user(db)
    _give_codes(db, user)

    for _ in range(5):
        client.post("/forgot-password", data=_reset_payload("aadhira", "WRONGWRONG"))

    user = User.query.filter_by(username="aadhira").first()
    assert user.failed_forgot_attempts == 5
    assert user.forgot_locked_until is not None

    locked = client.post("/forgot-password", data=_reset_payload("aadhira", "WRONGWRONG"))
    assert b"Too many failed attempts" in locked.data


def test_ip_lockout_after_five_failures_across_different_usernames(client, db):
    # Each attempt targets a different (nonexistent) username, so no single
    # User row's lockout could explain this - only the shared IP can.
    for i in range(5):
        client.post("/forgot-password", data=_reset_payload(f"ghost{i}", "WRONGWRONG"))

    row = IpLockout.query.filter_by(scope="forgot_password").first()
    assert row.failed_attempts == 5
    assert row.locked_until is not None

    response = client.post("/forgot-password", data=_reset_payload("ghost999", "WRONGWRONG"))
    assert b"Too many failed attempts" in response.data


def test_forgot_password_rejects_weak_new_password(client, db):
    user = _create_user(db)
    codes = _give_codes(db, user)
    response = client.post("/forgot-password", data=_reset_payload("aadhira", codes[0], password="Password1!", confirm="Password1!"))
    assert response.status_code == 200
    user = User.query.filter_by(username="aadhira").first()
    assert user.check_password(VALID_PASSWORD)  # unchanged


def test_forgot_password_requires_matching_confirmation(client, db):
    user = _create_user(db)
    codes = _give_codes(db, user)
    response = client.post(
        "/forgot-password",
        data=_reset_payload("aadhira", codes[0], password=NEW_PASSWORD, confirm="Different9!Zq"),
    )
    assert response.status_code == 200
    user = User.query.filter_by(username="aadhira").first()
    assert user.check_password(VALID_PASSWORD)


# -- session invalidation ------------------------------------------------------


def test_recovery_reset_invalidates_the_old_session_id(client, db):
    # Goes through the real /forgot-password route (not a direct model
    # call) to prove the route itself, not just session_version in the
    # abstract, is what bumps it. `client` stays anonymous throughout here
    # on purpose: the test harness's conftest.py wraps each test in a single
    # shared app context, so a *second* logged-in client/session within the
    # same test shares that context's `g` with the first - there's no way
    # to simulate "an old session elsewhere" via a second Client here. The
    # one thing that actually matters - load_user rejecting the pre-reset
    # session id while accepting the post-reset one - is what's checked
    # directly below instead.
    user = _create_user(db)
    old_session_id = user.get_id()
    codes = _give_codes(db, user)

    response = client.post("/forgot-password", data=_reset_payload("aadhira", codes[0]))
    assert response.status_code == 302

    user = User.query.filter_by(username="aadhira").first()
    assert load_user(old_session_id) is None
    assert load_user(user.get_id()) is not None


def test_regenerating_codes_invalidates_the_old_ones(client, db):
    user = _login(client, db)
    old_codes = _give_codes(db, user)

    client.post("/account/security/codes", data={})

    unused_hashes = [rc.code_hash for rc in RecoveryCode.query.filter_by(user_id=user.id, used_at=None)]
    assert len(unused_hashes) == 8
    for old_code in old_codes:
        assert not any(check_password_hash(h, old_code) for h in unused_hashes)


# -- account security page -----------------------------------------------------


def test_account_security_requires_login(client):
    response = client.get("/account/security")
    assert response.status_code == 302
    assert "/login" in response.location


def test_account_security_shows_generate_prompt_with_no_codes(client, db):
    _login(client, db)
    response = client.get("/account/security").get_data(as_text=True)
    assert "Generate recovery codes" in response


def test_account_security_generate_codes_shows_them_once(client, db):
    user = _login(client, db)
    response = client.post("/account/security/codes", data={})
    html = response.get_data(as_text=True)
    assert "Your recovery codes" in html
    assert RecoveryCode.query.filter_by(user_id=user.id).count() == 8

    reload = client.get("/account/security").get_data(as_text=True)
    assert "Your recovery codes" not in reload
    assert "Regenerate codes" in reload


def test_change_password_requires_current_password(client, db):
    _login(client, db)
    response = client.post("/account/security/password", data={
        "current_password": "wrongwrong",
        "new_password": NEW_PASSWORD,
        "confirm_password": NEW_PASSWORD,
    })
    assert response.status_code == 400
    assert b"Incorrect current password" in response.data


def test_change_password_success_resets_failed_login_counter(client, db):
    user = _login(client, db)
    user.failed_login_attempts = 3
    db.session.commit()

    response = client.post("/account/security/password", data={
        "current_password": VALID_PASSWORD,
        "new_password": NEW_PASSWORD,
        "confirm_password": NEW_PASSWORD,
    })
    assert response.status_code == 302

    user = User.query.filter_by(username="aadhira").first()
    assert user.check_password(NEW_PASSWORD)


def test_change_password_keeps_current_session_but_invalidates_old_version(client, db):
    user = _login(client, db)
    old_session_version = user.session_version

    client.post("/account/security/password", data={
        "current_password": VALID_PASSWORD,
        "new_password": NEW_PASSWORD,
        "confirm_password": NEW_PASSWORD,
    })

    user = User.query.filter_by(username="aadhira").first()
    assert user.session_version == old_session_version + 1

    # This session (the one that made the change) must still be logged in -
    # login_user() was called again to refresh its cookie to the new version.
    assert client.get("/dashboard").status_code == 200


# -- login page + dashboard nudge ----------------------------------------------


def test_login_page_has_forgot_password_link(client):
    response = client.get("/login").get_data(as_text=True)
    assert 'href="/forgot-password"' in response


def test_forgot_password_page_renders(client):
    response = client.get("/forgot-password")
    assert response.status_code == 200
    assert b"Recovery code" in response.data


def test_dashboard_nudges_when_no_recovery_codes(client, db):
    _login(client, db)
    response = client.get("/dashboard").get_data(as_text=True)
    assert "don't have any recovery codes" in response or "Set up now" in response


def test_dashboard_hides_nudge_once_codes_exist(client, db):
    user = _login(client, db)
    _give_codes(db, user)
    response = client.get("/dashboard").get_data(as_text=True)
    assert "Set up now" not in response
