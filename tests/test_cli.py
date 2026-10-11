from datetime import date, timedelta

from habitual.models import Checkin, PointTransaction, User


def _create_user(db, username="aadhira"):
    user = User(name="Aadhira", username=username, timezone="Asia/Kolkata")
    user.set_password("Sup3r$ecret")
    db.session.add(user)
    db.session.commit()
    return user


def _create_habit(db, user, created_on):
    from habitual.models import Habit

    habit = Habit(user_id=user.id, title="Read", emoji="📚", created_on=created_on)
    db.session.add(habit)
    db.session.commit()
    return habit


def _allow(monkeypatch):
    """Make _refuse_if_production() see a clearly-non-prod environment,
    regardless of what VERCEL/.env.prod actually look like on this machine."""
    monkeypatch.delenv("VERCEL", raising=False)
    monkeypatch.setattr(
        "habitual.cli.dotenv_values", lambda path: {"DATABASE_URL": "postgresql://not-the-same-db/x"}
    )
    monkeypatch.setattr("pathlib.Path.exists", lambda self: True)


# -- happy path -----------------------------------------------------------


def test_dev_backdate_creates_checkins_with_priced_milestone(app, db, monkeypatch):
    _allow(monkeypatch)
    user = _create_user(db)
    today = date.today()
    habit = _create_habit(db, user, created_on=today - timedelta(days=10))

    runner = app.test_cli_runner()
    result = runner.invoke(args=["dev-backdate", "--habit", str(habit.id), "--days", "7"])

    assert result.exit_code == 0, result.output
    checkins = Checkin.query.filter_by(habit_id=habit.id).all()
    assert sorted(c.date for c in checkins) == [today - timedelta(days=i) for i in range(7, 0, -1)]

    day7 = today - timedelta(days=1)
    amounts = sorted(pt.amount for pt in PointTransaction.query.filter_by(habit_id=habit.id, date=day7))
    assert amounts == [5, 10]  # the 7th backdated day hits the milestone


def test_dev_backdate_skip_yesterday_leaves_a_gap(app, db, monkeypatch):
    _allow(monkeypatch)
    user = _create_user(db)
    today = date.today()
    habit = _create_habit(db, user, created_on=today - timedelta(days=10))

    runner = app.test_cli_runner()
    result = runner.invoke(
        args=["dev-backdate", "--habit", str(habit.id), "--days", "7", "--skip-yesterday"]
    )

    assert result.exit_code == 0, result.output
    assert Checkin.query.filter_by(habit_id=habit.id, date=today - timedelta(days=1)).count() == 0
    assert Checkin.query.filter_by(habit_id=habit.id).count() == 6


def test_dev_backdate_include_today_checks_in_today_too(app, db, monkeypatch):
    _allow(monkeypatch)
    user = _create_user(db)
    today = date.today()
    habit = _create_habit(db, user, created_on=today - timedelta(days=10))

    runner = app.test_cli_runner()
    result = runner.invoke(
        args=["dev-backdate", "--habit", str(habit.id), "--days", "3", "--include-today"]
    )

    assert result.exit_code == 0, result.output
    assert Checkin.query.filter_by(habit_id=habit.id, date=today).count() == 1


def test_dev_backdate_skips_a_day_already_checked_in(app, db, monkeypatch):
    _allow(monkeypatch)
    user = _create_user(db)
    today = date.today()
    habit = _create_habit(db, user, created_on=today - timedelta(days=10))
    existing = today - timedelta(days=3)
    db.session.add(Checkin(habit_id=habit.id, date=existing))
    db.session.add(PointTransaction(user_id=user.id, habit_id=habit.id, amount=5, reason="daily", date=existing))
    db.session.commit()

    runner = app.test_cli_runner()
    result = runner.invoke(args=["dev-backdate", "--habit", str(habit.id), "--days", "5"])

    assert result.exit_code == 0, result.output
    assert Checkin.query.filter_by(habit_id=habit.id, date=existing).count() == 1
    assert PointTransaction.query.filter_by(habit_id=habit.id, date=existing).count() == 1


# -- validation -------------------------------------------------------------


def test_dev_backdate_rejects_unknown_habit(app, db, monkeypatch):
    _allow(monkeypatch)
    runner = app.test_cli_runner()
    result = runner.invoke(args=["dev-backdate", "--habit", "999999", "--days", "5"])
    assert result.exit_code != 0


def test_dev_backdate_rejects_days_predating_habit_creation(app, db, monkeypatch):
    _allow(monkeypatch)
    user = _create_user(db)
    today = date.today()
    habit = _create_habit(db, user, created_on=today - timedelta(days=3))

    runner = app.test_cli_runner()
    result = runner.invoke(args=["dev-backdate", "--habit", str(habit.id), "--days", "10"])

    assert result.exit_code != 0
    assert Checkin.query.filter_by(habit_id=habit.id).count() == 0


# -- production guard -------------------------------------------------------


def test_dev_backdate_refuses_on_vercel(app, db, monkeypatch):
    user = _create_user(db)
    today = date.today()
    habit = _create_habit(db, user, created_on=today - timedelta(days=10))
    monkeypatch.setenv("VERCEL", "1")

    runner = app.test_cli_runner()
    result = runner.invoke(args=["dev-backdate", "--habit", str(habit.id), "--days", "5"])

    assert result.exit_code != 0
    assert Checkin.query.filter_by(habit_id=habit.id).count() == 0


def test_dev_backdate_refuses_against_prod_database_url(app, db, monkeypatch):
    user = _create_user(db)
    today = date.today()
    habit = _create_habit(db, user, created_on=today - timedelta(days=10))

    monkeypatch.delenv("VERCEL", raising=False)
    monkeypatch.setattr("habitual.cli.dotenv_values", lambda path: {"DATABASE_URL": "sqlite://"})
    monkeypatch.setattr("pathlib.Path.exists", lambda self: True)

    runner = app.test_cli_runner()
    result = runner.invoke(args=["dev-backdate", "--habit", str(habit.id), "--days", "5"])

    assert result.exit_code != 0
    assert Checkin.query.filter_by(habit_id=habit.id).count() == 0


# -- admin-reset-password ----------------------------------------------------


def test_admin_reset_password_sets_a_working_temporary_password(app, db, monkeypatch):
    _allow(monkeypatch)
    user = _create_user(db)
    user.failed_login_attempts = 3
    user.locked_until = user.created_at  # any past/irrelevant value
    db.session.commit()
    old_session_id = user.get_id()

    runner = app.test_cli_runner()
    result = runner.invoke(args=["admin-reset-password", "aadhira"])
    assert result.exit_code == 0, result.output

    import re
    match = re.search(r"Temporary password for aadhira: (\S+)", result.output)
    assert match is not None
    temp_password = match.group(1)

    user = User.query.filter_by(username="aadhira").first()
    assert user.check_password(temp_password)
    assert not user.check_password("Sup3r$ecret")
    assert user.failed_login_attempts == 0
    assert user.locked_until is None

    from habitual.models import load_user
    assert load_user(old_session_id) is None  # old sessions invalidated too


def test_admin_reset_password_rejects_unknown_username(app, db, monkeypatch):
    _allow(monkeypatch)
    runner = app.test_cli_runner()
    result = runner.invoke(args=["admin-reset-password", "ghost"])
    assert result.exit_code != 0


def test_admin_reset_password_refuses_on_vercel(app, db, monkeypatch):
    user = _create_user(db)
    monkeypatch.setenv("VERCEL", "1")

    runner = app.test_cli_runner()
    result = runner.invoke(args=["admin-reset-password", "aadhira"])

    assert result.exit_code != 0
    user = User.query.filter_by(username="aadhira").first()
    assert user.check_password("Sup3r$ecret")  # unchanged


def test_admin_reset_password_refuses_against_prod_database_url(app, db, monkeypatch):
    user = _create_user(db)
    monkeypatch.delenv("VERCEL", raising=False)
    monkeypatch.setattr("habitual.cli.dotenv_values", lambda path: {"DATABASE_URL": "sqlite://"})
    monkeypatch.setattr("pathlib.Path.exists", lambda self: True)

    runner = app.test_cli_runner()
    result = runner.invoke(args=["admin-reset-password", "aadhira"])

    assert result.exit_code != 0
    user = User.query.filter_by(username="aadhira").first()
    assert user.check_password("Sup3r$ecret")


def test_admin_reset_password_override_flag_bypasses_the_prod_check(app, db, monkeypatch):
    _create_user(db)
    monkeypatch.delenv("VERCEL", raising=False)
    monkeypatch.setattr("habitual.cli.dotenv_values", lambda path: {"DATABASE_URL": "sqlite://"})
    monkeypatch.setattr("pathlib.Path.exists", lambda self: True)

    runner = app.test_cli_runner()
    result = runner.invoke(args=["admin-reset-password", "aadhira", "--i-know-this-is-prod"])

    assert result.exit_code == 0, result.output
    user = User.query.filter_by(username="aadhira").first()
    assert not user.check_password("Sup3r$ecret")


# -- send-test-email ----------------------------------------------------------


def test_send_test_email_refuses_when_provider_unset(app, monkeypatch):
    monkeypatch.delenv("EMAIL_PROVIDER", raising=False)
    runner = app.test_cli_runner()
    result = runner.invoke(args=["send-test-email", "someone@example.com"])
    assert result.exit_code != 0
    assert "console" in result.output.lower()


def test_send_test_email_refuses_when_provider_is_console(app, monkeypatch):
    monkeypatch.setenv("EMAIL_PROVIDER", "console")
    runner = app.test_cli_runner()
    result = runner.invoke(args=["send-test-email", "someone@example.com"])
    assert result.exit_code != 0


def test_send_test_email_reports_success(app, monkeypatch):
    monkeypatch.setenv("EMAIL_PROVIDER", "smtp")
    monkeypatch.setattr("habitual.mailer.send_email", lambda *a, **k: True)

    runner = app.test_cli_runner()
    result = runner.invoke(args=["send-test-email", "someone@example.com"])

    assert result.exit_code == 0, result.output
    assert "someone@example.com" in result.output
    assert "EMAIL_PROVIDER=smtp" in result.output


def test_send_test_email_reports_the_masked_failure_reason(app, monkeypatch):
    import habitual.mailer as mailer

    monkeypatch.setenv("EMAIL_PROVIDER", "smtp")

    def fake_send_email(*args, **kwargs):
        mailer.logger.error("email send failed: provider=smtp reason=auth")
        return False

    monkeypatch.setattr(mailer, "send_email", fake_send_email)

    runner = app.test_cli_runner()
    result = runner.invoke(args=["send-test-email", "someone@example.com"])

    assert result.exit_code != 0
    assert "reason=auth" in result.output
    # No secret ever shows up in the command's own output either.
    assert "SMTP_PASSWORD" not in result.output
