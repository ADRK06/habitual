import json

from flask import Blueprint, abort, flash, make_response, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from flask_wtf import FlaskForm
from sqlalchemy.exc import IntegrityError
from wtforms import HiddenField, StringField
from wtforms.validators import DataRequired, Length, Optional, ValidationError

from habitual import db, points
from habitual.models import Checkin, Freeze, Habit, PointTransaction
from habitual.utils.time import local_today

habits = Blueprint("habits", __name__)

EMOJI_CHOICES = [
    "🏃", "💧", "📚", "🧘", "💪", "🥗", "😴", "✍️",
    "🎨", "🎵", "🚭", "🧹", "💊", "🙏", "☀️", "🦷",
    "🚴", "🎯", "💰", "📵", "🌱", "🧠", "🫧", "🔥",
]


def _validate_title(form, field):
    if not (1 <= len((field.data or "").strip()) <= 60):
        raise ValidationError("Title must be 1-60 characters.")


def _validate_emoji(form, field):
    if field.data not in EMOJI_CHOICES:
        raise ValidationError("Pick an emoji from the list.")


class HabitForm(FlaskForm):
    title = StringField("Title", validators=[DataRequired(), _validate_title])
    emoji = HiddenField("Emoji", validators=[DataRequired(), _validate_emoji])
    tiny_version = StringField("Tiny version", validators=[Optional(), Length(max=120)])


def _habit_view(habit, today):
    """Pricing/stats for one habit card, derived from points.py's pure functions."""
    completed = {c.date for c in habit.checkins}
    frozen = {f.used_on for f in habit.freezes if f.used_on is not None}
    amounts = [pt.amount for pt in habit.point_transactions]
    return {
        "habit": habit,
        "current_streak": points.current_streak(completed, frozen, today),
        "longest_streak": points.longest_streak(completed, frozen, habit.created_on, today),
        "habit_points": points.earned_points(amounts),
        "success_rate": round(points.success_rate(completed, habit.created_on, today)),
        "checked_in_today": today in completed,
    }


def _header_stats(user):
    amounts = [pt.amount for pt in PointTransaction.query.filter_by(user_id=user.id)]
    freezes_held = Freeze.query.filter_by(user_id=user.id, used_on=None).count()
    return {
        "earned_points": points.earned_points(amounts),
        "balance": points.balance(amounts),
        "freezes_held": freezes_held,
    }


def _dashboard_context(form=None):
    today = local_today(current_user)
    habit_rows = (
        Habit.query.filter_by(user_id=current_user.id)
        .order_by(Habit.created_on.desc(), Habit.id.desc())
        .all()
    )
    return {
        "habit_cards": [_habit_view(h, today) for h in habit_rows],
        "form": form or HabitForm(),
        "emoji_choices": EMOJI_CHOICES,
        **_header_stats(current_user),
    }


@habits.get("/dashboard")
@login_required
def dashboard():
    context = _dashboard_context()
    context["new_habit_id"] = request.args.get("new", type=int)
    return render_template("dashboard.html", **context)


@habits.post("/habits")
@login_required
def create_habit():
    form = HabitForm()
    if form.validate_on_submit():
        habit = Habit(
            user_id=current_user.id,
            title=form.title.data.strip(),
            emoji=form.emoji.data,
            tiny_version=(form.tiny_version.data or "").strip() or None,
            created_on=local_today(current_user),
        )
        db.session.add(habit)
        db.session.commit()
        flash(f'"{habit.title}" added - go check in!', "success")
        return redirect(url_for("habits.dashboard", new=habit.id))

    context = _dashboard_context(form=form)
    context["new_habit_id"] = None
    return render_template("dashboard.html", **context), 400


@habits.get("/habits/<int:habit_id>")
@login_required
def habit_detail(habit_id):
    habit = db.get_or_404(Habit, habit_id)
    if habit.user_id != current_user.id:
        abort(404)
    return render_template("habits/detail.html", habit=habit)


@habits.post("/habits/<int:habit_id>/checkin")
@login_required
def checkin(habit_id):
    habit = db.get_or_404(Habit, habit_id)
    if habit.user_id != current_user.id:
        abort(404)

    today = local_today(current_user)
    points_earned = 0

    # The checkin row and its point transactions commit as one transaction.
    # A double-submit fails the unique(habit_id, date) constraint on flush,
    # before any points are written, so the whole thing rolls back cleanly.
    db.session.add(Checkin(habit_id=habit.id, date=today))
    try:
        db.session.flush()
    except IntegrityError:
        db.session.rollback()
    else:
        completed = {c.date for c in Checkin.query.filter_by(habit_id=habit.id)}
        frozen = {
            f.used_on
            for f in Freeze.query.filter_by(habit_id=habit.id)
            if f.used_on is not None
        }
        streak_day = points.streak_day_on(completed, frozen, today)
        bonus = points.milestone_bonus(streak_day)

        db.session.add(PointTransaction(
            user_id=current_user.id, habit_id=habit.id,
            amount=points.BASE_POINTS, reason="daily", date=today,
        ))
        if bonus:
            db.session.add(PointTransaction(
                user_id=current_user.id, habit_id=habit.id,
                amount=bonus, reason="milestone", date=today,
            ))
        db.session.commit()
        points_earned = points.BASE_POINTS + bonus

    context = {**_habit_view(habit, today), **_header_stats(current_user), "oob": True}
    resp = make_response(render_template("partials/checkin_response.html", **context))
    if points_earned:
        resp.headers["HX-Trigger"] = json.dumps(
            {"toast": {"message": f"+{points_earned} points!", "type": "success"}}
        )
    return resp


@habits.delete("/habits/<int:habit_id>")
@login_required
def delete_habit(habit_id):
    habit = db.get_or_404(Habit, habit_id)
    if habit.user_id != current_user.id:
        abort(404)

    title = habit.title
    db.session.delete(habit)
    db.session.commit()

    remaining = Habit.query.filter_by(user_id=current_user.id).count()
    context = {**_header_stats(current_user), "oob": True, "no_habits_left": remaining == 0}
    resp = make_response(render_template("partials/delete_response.html", **context))
    resp.headers["HX-Trigger"] = json.dumps(
        {"toast": {"message": f'Deleted "{title}".', "type": "info"}}
    )
    return resp
