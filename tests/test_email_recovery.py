import re
from datetime import datetime, timedelta, timezone as dt_timezone

from habitual.models import EmailToken, RateLimit, User, load_user

VALID_PASSWORD = "Tangerine7!Comet"
NEW_PASSWORD = "Obsidian9!Falcon"

LINK_RE = re.compile(r"https?://[^\s]+/(?:verify-email|reset-password)/([\w-]+)")


def _create_user(db, username="aadhira", email="aadhira@example.com", password=VALID_PASSWORD, verified=True):
    user = User(name="Aadhira", username=username, timezone="Asia/Kolkata", email=email)
    user.set_password(password)
    if verified:
        user.email_verified_at = datetime.now(dt_timezone.utc)
    db.session.add(user)
    db.session.commit()
    return user


def _login(client, db, username="aadhira", email="aadhira@example.com", password=VALID_PASSWORD, verified=True):
    user = _create_user(db, username=username, email=email, password=password, verified=verified)
    client.post("/login", data={"username": username, "password": password, "next": ""})
    return user


def _last_token(client):
    match = LINK_RE.search(client.sent_emails[-1]["text"])
    assert match is not None, f"no link found in {client.sent_emails[-1]['text']!r}"
    return match.group(1)


# -- signup requires + validates email ----------------------------------------


def test_signup_requires_email(client, db):
    response = client.post("/signup", data={
        "name": "Aadhira", "username": "aadhira", "password": VALID_PASSWORD,
        "confirm_password": VALID_PASSWORD, "timezone": "Asia/Kolkata",
    })
    assert response.status_code == 200
    assert User.query.count() == 0


def test_signup_rejects_malformed_email(client, db):
    response = client.post("/signup", data={
        "name": "Aadhira", "username": "aadhira", "email": "not-an-email",
        "password": VALID_PASSWORD, "confirm_password": VALID_PASSWORD, "timezone": "Asia/Kolkata",
    })
    assert response.status_code == 200
    assert User.query.count() == 0


def test_signup_rejects_email_already_verified_on_another_account(client, db):
    _create_user(db, username="owner", email="shared@example.com", verified=True)
    response = client.post("/signup", data={
        "name": "New", "username": "newperson", "email": "shared@example.com",
        "password": VALID_PASSWORD, "confirm_password": VALID_PASSWORD, "timezone": "Asia/Kolkata",
    })
    assert response.status_code == 200
    assert b"already registered" in response.data
    assert User.query.filter_by(username="newperson").count() == 0


def test_signup_allows_email_that_is_unverified_on_another_account(client, db):
    # Unverified claims are provisional - signing up with an address someone
    # else merely HASN'T verified yet must not be blocked.
    _create_user(db, username="owner", email="shared@example.com", verified=False)
    response = client.post("/signup", data={
        "name": "New", "username": "newperson", "email": "shared@example.com",
        "password": VALID_PASSWORD, "confirm_password": VALID_PASSWORD, "timezone": "Asia/Kolkata",
    })
    assert response.status_code == 302
    assert User.query.filter_by(username="newperson").count() == 1


def test_signup_sends_verification_email_and_logs_in(client, db):
    response = client.post("/signup", data={
        "name": "Aadhira", "username": "aadhira", "email": "aadhira@example.com",
        "password": VALID_PASSWORD, "confirm_password": VALID_PASSWORD, "timezone": "Asia/Kolkata",
    })
    assert response.status_code == 302
    assert response.location == "/check-email"
    assert client.sent_emails[-1]["to"] == "aadhira@example.com"
    assert client.get("/dashboard").status_code == 200

    user = User.query.filter_by(username="aadhira").first()
    assert user.email == "aadhira@example.com"
    assert user.email_verified_at is None


# -- verify-email click --------------------------------------------------------


def test_verify_email_link_marks_it_verified(client, db):
    _login(client, db, verified=False)
    client.post("/resend-verification", data={})
    token = _last_token(client)

    response = client.get(f"/verify-email/{token}")
    assert response.status_code == 200
    assert b"verified" in response.data.lower()
    assert response.headers["Referrer-Policy"] == "no-referrer"

    user = User.query.filter_by(username="aadhira").first()
    assert user.email_verified_at is not None


def test_verify_email_token_is_single_use(client, db):
    _login(client, db, verified=False)
    client.post("/resend-verification", data={})
    token = _last_token(client)

    client.get(f"/verify-email/{token}")
    second = client.get(f"/verify-email/{token}")
    assert b"invalid or has expired" in second.data


def test_verify_email_rejects_unknown_token(client, db):
    response = client.get("/verify-email/not-a-real-token")
    assert response.status_code == 200
    assert b"invalid or has expired" in response.data
    assert response.headers["Referrer-Policy"] == "no-referrer"


def test_verify_email_expired_token_rejected(client, db):
    user = _login(client, db, verified=False)
    client.post("/resend-verification", data={})
    token_row = EmailToken.query.filter_by(user_id=user.id, purpose="verify_email").first()
    token_row.expires_at = datetime.now(dt_timezone.utc) - timedelta(minutes=1)
    db.session.commit()

    token = _last_token(client)
    response = client.get(f"/verify-email/{token}")
    assert b"invalid or has expired" in response.data


def test_verifying_claims_the_email_from_another_accounts_unverified_claim(client, db):
    # Two accounts both have the same unverified email (allowed - see
    # test_signup_allows_email_that_is_unverified_on_another_account).
    # Whoever verifies FIRST wins; the other account's unverified claim is
    # cleared rather than left dangling against a now-taken address.
    other = _create_user(db, username="other", email="shared@example.com", verified=False)
    _login(client, db, username="aadhira", email="shared@example.com", verified=False)
    client.post("/resend-verification", data={})
    token = _last_token(client)

    client.get(f"/verify-email/{token}")

    winner = User.query.filter_by(username="aadhira").first()
    loser = User.query.filter_by(username="other").first()
    assert winner.email_verified_at is not None
    assert winner.email == "shared@example.com"
    assert loser.email is None


def test_second_account_cannot_steal_an_already_verified_email(client, db):
    _create_user(db, username="owner", email="owner@example.com", verified=True)
    # A second account somehow has a leftover unverified claim on the same
    # address (e.g. signed up before "owner" verified) and tries to verify it.
    thief = _create_user(db, username="thief", email="owner@example.com", verified=False)
    from habitual.auth import _issue_email_token
    token = _issue_email_token(thief, "verify_email", "owner@example.com", timedelta(hours=24), datetime.now(dt_timezone.utc))
    db.session.commit()

    response = client.get(f"/verify-email/{token}")
    assert b"invalid or has expired" in response.data

    owner = User.query.filter_by(username="owner").first()
    assert owner.email_verified_at is not None  # untouched


# -- resend verification + cooldown -------------------------------------------


def test_resend_verification_respects_cooldown(client, db):
    _login(client, db, verified=False)
    first = client.post("/resend-verification", data={})
    assert first.status_code == 302
    sent_after_first = len(client.sent_emails)

    second = client.post("/resend-verification", data={})
    assert len(client.sent_emails) == sent_after_first  # no new email - still in cooldown


def test_resend_verification_no_op_once_verified(client, db):
    _login(client, db, verified=True)
    before = len(client.sent_emails)
    client.post("/resend-verification", data={})
    assert len(client.sent_emails) == before


# -- forgot-password: identical response regardless of account state ---------


def test_forgot_password_response_identical_for_unknown_unverified_and_verified_email(app, db):
    _create_user(db, username="verified_user", email="verified@example.com", verified=True)
    _create_user(db, username="unverified_user", email="unverified@example.com", verified=False)

    def ask(email, ip):
        c = app.test_client()
        from habitual import mailer
        c.sent_emails = []
        orig = mailer.send_email
        mailer.send_email = lambda *a, **k: (c.sent_emails.append(a), True)[1]
        try:
            return c.post("/forgot-password", data={"email": email}, headers={"X-Forwarded-For": ip})
        finally:
            mailer.send_email = orig

    unknown = ask("nobody@example.com", "10.0.0.1")
    unverified = ask("unverified@example.com", "10.0.0.2")
    verified = ask("verified@example.com", "10.0.0.3")

    bodies = [r.get_data(as_text=True) for r in (unknown, unverified, verified)]
    assert bodies[0] == bodies[1] == bodies[2]
    statuses = [r.status_code for r in (unknown, unverified, verified)]
    assert statuses[0] == statuses[1] == statuses[2]


def test_forgot_password_sends_only_for_verified_matching_email(client, db):
    _create_user(db, username="verified_user", email="verified@example.com", verified=True)
    _create_user(db, username="unverified_user", email="unverified@example.com", verified=False)

    client.post("/forgot-password", data={"email": "unverified@example.com"})
    assert len(client.sent_emails) == 0

    client.post("/forgot-password", data={"email": "verified@example.com"})
    assert len(client.sent_emails) == 1
    assert client.sent_emails[0]["to"] == "verified@example.com"


def test_forgot_password_rejects_malformed_email(client, db):
    response = client.post("/forgot-password", data={"email": "not-an-email"})
    assert response.status_code == 200
    assert len(client.sent_emails) == 0


# -- reset-password via link ---------------------------------------------------


def test_reset_password_valid_flow_and_single_use(client, db):
    _create_user(db, email="verified@example.com", verified=True)
    client.post("/forgot-password", data={"email": "verified@example.com"})
    token = _last_token(client)

    response = client.post(f"/reset-password/{token}", data={
        "new_password": NEW_PASSWORD, "confirm_password": NEW_PASSWORD,
    })
    assert response.status_code == 302
    assert response.location == "/login"

    user = User.query.filter_by(username="aadhira").first()
    assert user.check_password(NEW_PASSWORD)

    # Same token again: rejected.
    replay = client.post(f"/reset-password/{token}", data={
        "new_password": "AnotherNew7!Zq", "confirm_password": "AnotherNew7!Zq",
    })
    assert b"invalid or has expired" in replay.data
    user = User.query.filter_by(username="aadhira").first()
    assert user.check_password(NEW_PASSWORD)  # unchanged by the replay


def test_reset_password_invalid_token_shows_generic_page_with_no_referrer_header(client, db):
    response = client.get("/reset-password/not-a-real-token")
    assert response.status_code == 200
    assert b"invalid or has expired" in response.data
    assert response.headers["Referrer-Policy"] == "no-referrer"


def test_reset_password_page_sets_no_referrer_header_on_valid_token_too(client, db):
    _create_user(db, email="verified@example.com", verified=True)
    client.post("/forgot-password", data={"email": "verified@example.com"})
    token = _last_token(client)
    response = client.get(f"/reset-password/{token}")
    assert response.headers["Referrer-Policy"] == "no-referrer"


def test_reset_password_expired_token_rejected(client, db):
    user = _create_user(db, email="verified@example.com", verified=True)
    client.post("/forgot-password", data={"email": "verified@example.com"})
    token = _last_token(client)
    row = EmailToken.query.filter_by(user_id=user.id, purpose="reset").first()
    row.expires_at = datetime.now(dt_timezone.utc) - timedelta(minutes=1)
    db.session.commit()

    response = client.post(f"/reset-password/{token}", data={
        "new_password": NEW_PASSWORD, "confirm_password": NEW_PASSWORD,
    })
    assert b"invalid or has expired" in response.data


def test_reset_password_rejects_a_password_failing_the_checklist(client, db):
    _create_user(db, email="verified@example.com", verified=True)
    client.post("/forgot-password", data={"email": "verified@example.com"})
    token = _last_token(client)

    # Fails the uppercase-letter rule - the server-side checklist is the
    # only password-strength gate now, so this must still be rejected.
    weak_password = "nouppercase1!"
    response = client.post(f"/reset-password/{token}", data={
        "new_password": weak_password, "confirm_password": weak_password,
    })
    assert response.status_code == 200
    user = User.query.filter_by(username="aadhira").first()
    assert user.check_password(VALID_PASSWORD)


def test_garbage_token_submissions_dont_lock_any_account(client, db):
    _create_user(db, email="verified@example.com", verified=True)
    for _ in range(5):
        client.post("/reset-password/garbage-token-never-issued", data={
            "new_password": NEW_PASSWORD, "confirm_password": NEW_PASSWORD,
        })
    # A garbage token (never issued) has no user_id to attribute to - only
    # a token that at least RESOLVES to an account (even if expired/reused)
    # can count against that account's lockout.
    user = User.query.filter_by(username="aadhira").first()
    assert user.failed_forgot_attempts == 0
    assert user.forgot_locked_until is None


def test_reused_token_submissions_lock_the_account_after_five(client, db):
    _create_user(db, email="verified@example.com", verified=True)
    client.post("/forgot-password", data={"email": "verified@example.com"})
    token = _last_token(client)

    # First use succeeds and consumes the token.
    client.post(f"/reset-password/{token}", data={
        "new_password": NEW_PASSWORD, "confirm_password": NEW_PASSWORD,
    })

    # The token still resolves to this account (even though it's now used),
    # so repeating it is attributed to the account, not just the IP.
    for _ in range(5):
        client.post(f"/reset-password/{token}", data={
            "new_password": "Xk9Zq!bear", "confirm_password": "Xk9Zq!bear",
        })

    user = User.query.filter_by(username="aadhira").first()
    assert user.failed_forgot_attempts == 5
    assert user.forgot_locked_until is not None
    assert user.check_password(NEW_PASSWORD)  # none of the replays took effect


def test_old_session_invalidated_after_reset(client, db):
    # See test_old_sessions comment in the previous recovery-codes test
    # suite: the harness wraps each test in one shared app context, so a
    # second logged-in client/session can't be simulated here - the actual
    # invalidation mechanism (load_user rejecting the stale session id) is
    # what's checked directly.
    user = _create_user(db, email="verified@example.com", verified=True)
    old_session_id = user.get_id()

    client.post("/forgot-password", data={"email": "verified@example.com"})
    token = _last_token(client)
    client.post(f"/reset-password/{token}", data={
        "new_password": NEW_PASSWORD, "confirm_password": NEW_PASSWORD,
    })

    user = User.query.filter_by(username="aadhira").first()
    assert load_user(old_session_id) is None
    assert load_user(user.get_id()) is not None
    assert user.failed_login_attempts == 0
    assert user.locked_until is None


# -- rate limiting: per-email and per-IP are independent ----------------------


def test_forgot_password_email_cooldown_blocks_second_immediate_request(client, db):
    _create_user(db, email="verified@example.com", verified=True)
    client.post("/forgot-password", data={"email": "verified@example.com"})
    assert len(client.sent_emails) == 1
    client.post("/forgot-password", data={"email": "verified@example.com"})
    assert len(client.sent_emails) == 1  # still within the resend cooldown


def test_forgot_password_two_ips_have_independent_limits(client, db):
    for i in range(10):
        _create_user(db, username=f"user{i}", email=f"user{i}@example.com", verified=True)

    # IP "1.2.3.4" uses up its hourly cap...
    for i in range(10):
        client.post(
            "/forgot-password", data={"email": f"user{i}@example.com"},
            headers={"X-Forwarded-For": "1.2.3.4"},
        )
    sent_from_first_ip = len(client.sent_emails)
    assert sent_from_first_ip == 10

    # ...one more request from that SAME ip is now blocked...
    client.post(
        "/forgot-password", data={"email": "user0@example.com"},
        headers={"X-Forwarded-For": "1.2.3.4, 9.9.9.9"},
    )
    assert len(client.sent_emails) == sent_from_first_ip  # no new send - email cooldown too, but also IP-capped

    # ...while a DIFFERENT ip, fresh account/email, still gets through.
    _create_user(db, username="freshuser", email="fresh@example.com", verified=True)
    client.post(
        "/forgot-password", data={"email": "fresh@example.com"},
        headers={"X-Forwarded-For": "5.6.7.8"},
    )
    assert len(client.sent_emails) == sent_from_first_ip + 1

    first_ip_row = RateLimit.query.filter_by(key="1.2.3.4", scope="forgot_ip").first()
    second_ip_row = RateLimit.query.filter_by(key="5.6.7.8", scope="forgot_ip").first()
    assert first_ip_row.attempts != second_ip_row.attempts


def test_client_ip_reads_first_x_forwarded_for_entry(app):
    with app.test_request_context(headers={"X-Forwarded-For": "1.1.1.1, 2.2.2.2, 3.3.3.3"}):
        from habitual.auth import _client_ip
        assert _client_ip() == "1.1.1.1"


def test_client_ip_falls_back_to_remote_addr_without_header(app):
    with app.test_request_context(environ_overrides={"REMOTE_ADDR": "127.0.0.1"}):
        from habitual.auth import _client_ip
        assert _client_ip() == "127.0.0.1"


# -- change email (account security) -------------------------------------------


def test_change_email_stages_pending_and_sends_to_new_address(client, db):
    _login(client, db, email="old@example.com", verified=True)
    response = client.post("/account/security/email", data={"email": "new@example.com"})
    assert response.status_code == 302

    user = User.query.filter_by(username="aadhira").first()
    assert user.email == "old@example.com"  # unchanged until verified
    assert user.pending_email == "new@example.com"
    assert client.sent_emails[-1]["to"] == "new@example.com"


def test_change_email_verification_promotes_pending_to_primary(client, db):
    _login(client, db, email="old@example.com", verified=True)
    client.post("/account/security/email", data={"email": "new@example.com"})
    token = _last_token(client)

    client.get(f"/verify-email/{token}")
    user = User.query.filter_by(username="aadhira").first()
    assert user.email == "new@example.com"
    assert user.pending_email is None
    assert user.email_verified_at is not None


def test_change_email_rejects_address_already_verified_elsewhere(client, db):
    _create_user(db, username="other", email="taken@example.com", verified=True)
    _login(client, db, username="aadhira", email="mine@example.com", verified=True)

    response = client.post("/account/security/email", data={"email": "taken@example.com"})
    assert response.status_code == 400
    assert b"already associated" in response.data

    user = User.query.filter_by(username="aadhira").first()
    assert user.pending_email is None


def test_change_email_allows_address_unverified_elsewhere(client, db):
    _create_user(db, username="other", email="shared@example.com", verified=False)
    _login(client, db, username="aadhira", email="mine@example.com", verified=True)

    response = client.post("/account/security/email", data={"email": "shared@example.com"})
    assert response.status_code == 302
    user = User.query.filter_by(username="aadhira").first()
    assert user.pending_email == "shared@example.com"


# -- change password (unchanged behaviour, carried over) -----------------------


def test_change_password_requires_current_password(client, db):
    _login(client, db)
    response = client.post("/account/security/password", data={
        "current_password": "wrongwrong", "new_password": NEW_PASSWORD, "confirm_password": NEW_PASSWORD,
    })
    assert response.status_code == 400
    assert b"Incorrect current password" in response.data


def test_change_password_keeps_current_session_but_bumps_version(client, db):
    user = _login(client, db)
    old_version = user.session_version

    client.post("/account/security/password", data={
        "current_password": VALID_PASSWORD, "new_password": NEW_PASSWORD, "confirm_password": NEW_PASSWORD,
    })

    user = User.query.filter_by(username="aadhira").first()
    assert user.session_version == old_version + 1
    assert client.get("/dashboard").status_code == 200  # this session still works


# -- dashboard nudges -----------------------------------------------------------


def test_dashboard_nudges_to_add_email_when_none(client, db):
    user = User(name="A", username="noemail", timezone="Asia/Kolkata")
    user.set_password(VALID_PASSWORD)
    db.session.add(user)
    db.session.commit()
    client.post("/login", data={"username": "noemail", "password": VALID_PASSWORD, "next": ""})

    response = client.get("/dashboard").get_data(as_text=True)
    assert "Add your email" in response
    assert "Add email" in response


def test_dashboard_nudges_to_verify_pending_email(client, db):
    _login(client, db, verified=False)
    response = client.get("/dashboard").get_data(as_text=True)
    assert "Verify your email" in response


def test_dashboard_nudges_to_confirm_a_change_in_progress(client, db):
    _login(client, db, verified=True)
    client.post("/account/security/email", data={"email": "new@example.com"})
    response = client.get("/dashboard").get_data(as_text=True)
    assert "Confirm your new email" in response
    assert "new@example.com" in response


def test_dashboard_has_no_nudge_once_verified(client, db):
    _login(client, db, verified=True)
    response = client.get("/dashboard").get_data(as_text=True)
    assert "Add your email" not in response
    assert "Verify your email" not in response
    assert "Confirm your new email" not in response


def test_login_page_has_forgot_password_link(client):
    response = client.get("/login").get_data(as_text=True)
    assert 'href="/forgot-password"' in response
