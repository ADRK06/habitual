"""Dev-only CLI commands. Never reachable over HTTP - these only run when
someone has a local shell and runs `flask --app app <command>` directly.
"""
import os
from datetime import timedelta
from pathlib import Path

import click
from dotenv import dotenv_values
from flask import current_app
from flask.cli import with_appcontext

from habitual import db, points
from habitual.config import _normalize_db_url
from habitual.models import Checkin, Freeze, Habit, PointTransaction, User
from habitual.utils.time import local_today


def _refuse_if_production():
    """Raises if this looks like it's running against prod, in any way we
    can detect. Checked at the start of every dev-only command's body (not
    just at registration time) so there's no way to bypass it."""
    if os.environ.get("VERCEL"):
        raise click.ClickException(
            "Refusing to run: the VERCEL env var is set, so this looks like a "
            "production or preview deployment."
        )

    current_url = current_app.config.get("SQLALCHEMY_DATABASE_URI") or ""
    prod_env_file = Path(current_app.root_path).parent / ".env.prod"
    if prod_env_file.exists() and current_url:
        prod_url = dotenv_values(prod_env_file).get("DATABASE_URL")
        if prod_url and _normalize_db_url(prod_url) == current_url:
            raise click.ClickException(
                "Refusing to run: the active DATABASE_URL matches .env.prod's "
                "(the Neon main/prod branch), not a dev branch."
            )


@click.command("dev-backdate")
@click.option("--habit", "habit_id", required=True, type=int, help="Habit id to backdate check-ins for.")
@click.option(
    "--days", default=10, type=int, show_default=True,
    help="How many days back to fill, ending yesterday (see --include-today).",
)
@click.option(
    "--skip-yesterday", is_flag=True, default=False,
    help="Leave yesterday as a gap, for testing the 'Save your streak' freeze prompt.",
)
@click.option("--include-today", is_flag=True, default=False, help="Also check in today.")
@with_appcontext
def dev_backdate(habit_id, days, skip_yesterday, include_today):
    """Dev-only: create past check-ins (with correctly priced ledger entries)
    for a habit, for testing milestones (day 7/14/30), freezes, and streaks
    without waiting real days. Refuses to run against production."""
    _refuse_if_production()

    habit = db.session.get(Habit, habit_id)
    if habit is None:
        raise click.ClickException(f"No habit with id {habit_id}.")

    user = db.session.get(User, habit.user_id)
    today = local_today(user)

    offsets = [o for o in range(days, 0, -1) if not (skip_yesterday and o == 1)]
    if include_today:
        offsets.append(0)
    if not offsets:
        raise click.ClickException("Nothing to do - --days is too small once --skip-yesterday is applied.")

    earliest_date = today - timedelta(days=max(offsets))
    if earliest_date < habit.created_on:
        raise click.ClickException(
            f"--days {days} would backdate to {earliest_date}, before this habit's "
            f"created_on ({habit.created_on}). Reduce --days or use a habit created earlier."
        )

    created = 0
    for offset in offsets:
        d = today - timedelta(days=offset)
        if Checkin.query.filter_by(habit_id=habit.id, date=d).first():
            click.echo(f"  {d}: already checked in, skipping.")
            continue

        db.session.add(Checkin(habit_id=habit.id, date=d))
        db.session.flush()

        completed = {c.date for c in Checkin.query.filter_by(habit_id=habit.id)}
        frozen = {
            f.used_on for f in Freeze.query.filter_by(habit_id=habit.id) if f.used_on is not None
        }
        streak_day = points.streak_day_on(completed, frozen, d)
        bonus = points.milestone_bonus(streak_day)

        db.session.add(PointTransaction(
            user_id=user.id, habit_id=habit.id, amount=points.BASE_POINTS, reason="daily", date=d,
        ))
        if bonus:
            db.session.add(PointTransaction(
                user_id=user.id, habit_id=habit.id, amount=bonus, reason="milestone", date=d,
            ))
        created += 1
        label = f" (+milestone day {streak_day})" if bonus else ""
        click.echo(f"  {d}: checked in, streak day {streak_day}{label}")

    db.session.commit()
    click.echo(f"Backdated {created} check-in(s) for habit {habit.id} ({habit.title!r}).")
