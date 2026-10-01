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
