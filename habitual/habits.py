import json
from datetime import timedelta

from flask import Blueprint, abort, flash, make_response, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from flask_wtf import FlaskForm
from sqlalchemy.exc import IntegrityError
from wtforms import HiddenField, StringField
from wtforms.validators import DataRequired, Length, Optional, ValidationError

from habitual import db, points
from habitual.models import Checkin, Freeze, Habit, PointTransaction, User
from habitual.utils.time import local_today

habits = Blueprint("habits", __name__)

EMOJI_CHOICES = [
    "🏃", "💧", "📚", "🧘", "💪", "🥗", "😴", "✍️",
    "🎨", "🎵", "🚭", "🧹", "💊", "🙏", "☀️", "🦷",
    "🚴", "🎯", "💰", "📵", "🌱", "🧠", "🫧", "🔥",
]

HABIT_TEMPLATES = [
    {"title": "Drink water", "emoji": "💧", "tiny_version": "Drink one glass"},
    {"title": "Read", "emoji": "📚", "tiny_version": "Read one page"},
    {"title": "Move your body", "emoji": "🏃", "tiny_version": "Do 5 pushups"},
    {"title": "Meditate", "emoji": "🧘", "tiny_version": "Breathe for 1 minute"},
    {"title": "Sleep on time", "emoji": "😴", "tiny_version": "Lights off by 11pm"},
    {"title": "Journal", "emoji": "✍️", "tiny_version": "Write one sentence"},
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


def _habit_view(habit, today, freezes_held):
    """Pricing/stats for one habit card, derived from points.py's pure functions."""
    completed = {c.date for c in habit.checkins}
    frozen = {f.used_on for f in habit.freezes if f.used_on is not None}
    amounts = [pt.amount for pt in habit.point_transactions]
    can_save_streak = points.freeze_available(completed, frozen, today)
    return {
        "habit": habit,
        "current_streak": points.current_streak(completed, frozen, today),
        "longest_streak": points.longest_streak(completed, frozen, habit.created_on, today),
        "habit_points": points.earned_points(amounts),
        "success_rate": round(points.success_rate(completed, habit.created_on, today)),
        "checked_in_today": today in completed,
        "can_save_streak": can_save_streak,
        "has_freeze_to_use": freezes_held > 0,
    }


def _header_stats(user):
    amounts = [pt.amount for pt in PointTransaction.query.filter_by(user_id=user.id)]
    balance = points.balance(amounts)
    freezes_held = Freeze.query.filter_by(user_id=user.id, used_on=None).count()
    can_buy_freeze = points.can_purchase_freeze(balance, freezes_held)
    if can_buy_freeze:
        freeze_buy_disabled_reason = None
    elif freezes_held >= points.MAX_UNUSED_FREEZES:
        freeze_buy_disabled_reason = f"You already hold the max of {points.MAX_UNUSED_FREEZES} freezes."
    else:
        freeze_buy_disabled_reason = f"Need {points.FREEZE_COST} balance to buy a freeze (you have {balance})."
    return {
        "earned_points": points.earned_points(amounts),
        "balance": balance,
        "freezes_held": freezes_held,
        "can_buy_freeze": can_buy_freeze,
        "freeze_buy_disabled_reason": freeze_buy_disabled_reason,
    }


def _dashboard_context(form=None):
    today = local_today(current_user)
    header = _header_stats(current_user)
    habit_rows = (
        Habit.query.filter_by(user_id=current_user.id)
        .order_by(Habit.created_on.desc(), Habit.id.desc())
        .all()
    )
    return {
        "habit_cards": [_habit_view(h, today, header["freezes_held"]) for h in habit_rows],
        "form": form or HabitForm(),
        "emoji_choices": EMOJI_CHOICES,
        "habit_templates": HABIT_TEMPLATES,
        **header,
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
    bonus = 0
    streak_day = None
    # Defensive server-side cap - the textarea's maxlength is UX only.
    proof_note = (request.form.get("proof_note") or "").strip()[:280] or None

    # The checkin row and its point transactions commit as one transaction.
    # A double-submit fails the unique(habit_id, date) constraint on flush,
    # before any points are written, so the whole thing rolls back cleanly.
    db.session.add(Checkin(habit_id=habit.id, date=today, proof_note=proof_note))
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

    header = _header_stats(current_user)
    context = {**_habit_view(habit, today, header["freezes_held"]), **header, "oob": True}
    resp = make_response(render_template("partials/checkin_response.html", **context))
    if points_earned:
        label = points.milestone_label(streak_day)
        toast_message = f"+{points_earned} · {label}" if label else f"+{points_earned} points!"
        resp.headers["HX-Trigger"] = json.dumps({
            "toast": {"message": toast_message, "type": "success"},
            "checkinCelebration": {"habitId": habit.id, "milestone": bool(bonus)},
        })
    return resp


@habits.delete("/habits/<int:habit_id>/checkin")
@login_required
def undo_checkin(habit_id):
    habit = db.get_or_404(Habit, habit_id)
    if habit.user_id != current_user.id:
        abort(404)

    today = local_today(current_user)

    # Only today's checkin is ever targeted here (no date is accepted from the
    # client), so past days can never be undone through this route.
    checkin_row = Checkin.query.filter_by(habit_id=habit.id, date=today).first()
    if checkin_row is None:
        abort(404)

    # Checkin + every one of today's ledger entries (daily and milestone, but
    # never a freeze purchase - those carry no habit_id) are removed in one
    # transaction, so a later re-checkin reprices exactly as if today never
    # happened. Freeze rows are untouched, so a freeze used for yesterday
    # stays intact.
    for txn in PointTransaction.query.filter_by(habit_id=habit.id, date=today):
        db.session.delete(txn)
    db.session.delete(checkin_row)
    db.session.commit()

    header = _header_stats(current_user)
    context = {**_habit_view(habit, today, header["freezes_held"]), **header, "oob": True}
    resp = make_response(render_template("partials/checkin_response.html", **context))
    resp.headers["HX-Trigger"] = json.dumps(
        {"toast": {"message": "Check-in undone.", "type": "info"}}
    )
    return resp


@habits.post("/freezes/buy")
@login_required
def buy_freeze():
    # Lock this user's row for the rest of the transaction. Without it, two
    # near-simultaneous buys (a double-click, or two tabs) can both read
    # "balance is enough" before either commits, letting balance go negative
    # or freezes_held exceed MAX_UNUSED_FREEZES. The second request blocks
    # here until the first commits, then re-reads the now-current state.
    db.session.query(User).filter_by(id=current_user.id).with_for_update().first()

    header = _header_stats(current_user)
    if not header["can_buy_freeze"]:
        abort(400)

    db.session.add(Freeze(user_id=current_user.id))
    db.session.add(PointTransaction(
        user_id=current_user.id, habit_id=None,
        amount=-points.FREEZE_COST, reason="freeze_purchase", date=local_today(current_user),
    ))
    db.session.commit()

    resp = make_response(render_template("partials/header_stats.html", **_header_stats(current_user)))
    resp.headers["HX-Trigger"] = json.dumps(
        {"toast": {"message": "Freeze purchased 🧊", "type": "success"}}
    )
    return resp


@habits.post("/habits/<int:habit_id>/freeze")
@login_required
def use_freeze(habit_id):
    habit = db.get_or_404(Habit, habit_id)
    if habit.user_id != current_user.id:
        abort(404)

    # Same lock as buy_freeze: serializes this against a concurrent buy or
    # another "use a freeze" for this user, so the specific Freeze row this
    # request commits to can't be silently overwritten by a second
    # near-simultaneous request before this one's changes land.
    db.session.query(User).filter_by(id=current_user.id).with_for_update().first()

    today = local_today(current_user)
    yesterday = today - timedelta(days=1)
    completed = {c.date for c in Checkin.query.filter_by(habit_id=habit.id)}
    frozen = {
        f.used_on for f in Freeze.query.filter_by(habit_id=habit.id) if f.used_on is not None
    }

    if not points.freeze_available(completed, frozen, today):
        abort(400)

    freeze = Freeze.query.filter_by(user_id=current_user.id, used_on=None).first()
    if freeze is None:
        abort(400)

    freeze.habit_id = habit.id
    freeze.used_on = yesterday

    # Order-independent reprice: if today was already checked in before this
    # freeze bridged yesterday's gap, today's streak day - and therefore its
    # points - may now be higher. Replace today's ledger entries to match,
    # same logic as pricing a fresh check-in (habitual/points.py).
    if today in completed:
        new_frozen = frozen | {yesterday}
        new_streak_day = points.streak_day_on(completed, new_frozen, today)
        new_total = points.points_for_day(new_streak_day)
        todays_txns = PointTransaction.query.filter_by(habit_id=habit.id, date=today).all()
        old_total = sum(txn.amount for txn in todays_txns)
        if new_total != old_total:
            for txn in todays_txns:
                db.session.delete(txn)
            db.session.add(PointTransaction(
                user_id=current_user.id, habit_id=habit.id,
                amount=points.BASE_POINTS, reason="daily", date=today,
            ))
            bonus = points.milestone_bonus(new_streak_day)
            if bonus:
                db.session.add(PointTransaction(
                    user_id=current_user.id, habit_id=habit.id,
                    amount=bonus, reason="milestone", date=today,
                ))

    db.session.commit()

    header = _header_stats(current_user)
    context = {**_habit_view(habit, today, header["freezes_held"]), **header, "oob": True}
    resp = make_response(render_template("partials/checkin_response.html", **context))
    resp.headers["HX-Trigger"] = json.dumps(
        {"toast": {"message": "Streak saved with a freeze 🧊", "type": "info"}}
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
