import calendar as calendar_module
import json
from datetime import date, timedelta

from flask import Blueprint, abort, flash, make_response, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from flask_wtf import FlaskForm
from sqlalchemy.exc import IntegrityError
from wtforms import HiddenField, StringField
from wtforms.validators import DataRequired, Length, Optional, ValidationError

from habitual import analytics, badges, db, frequency, points
from habitual.models import Checkin, Freeze, Habit, PointTransaction, User
from habitual.utils.time import local_now, local_today, midnight_epoch_ms

FREQUENCY_CHOICES = ("daily", "days", "weekly")

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


def _validate_frequency_type(form, field):
    if field.data not in FREQUENCY_CHOICES:
        raise ValidationError("Pick a frequency.")


def _validate_frequency_days(form, field):
    if form.frequency_type.data != "days":
        return
    try:
        mask = int(field.data or 0)
    except (TypeError, ValueError):
        mask = 0
    if not (0 < mask <= frequency.ALL_DAYS_MASK):
        raise ValidationError("Pick at least one day.")


def _validate_frequency_target(form, field):
    if form.frequency_type.data != "weekly":
        return
    try:
        target = int(field.data or 0)
    except (TypeError, ValueError):
        target = 0
    if not (1 <= target <= 6):
        raise ValidationError("Pick 1-6 times a week.")


class HabitForm(FlaskForm):
    title = StringField("Title", validators=[DataRequired(), _validate_title])
    emoji = HiddenField("Emoji", validators=[DataRequired(), _validate_emoji])
    tiny_version = StringField("Tiny version", validators=[Optional(), Length(max=120)])
    frequency_type = HiddenField("Frequency", default="daily", validators=[DataRequired(), _validate_frequency_type])
    frequency_days = HiddenField("Days", validators=[Optional(), _validate_frequency_days])
    frequency_target = HiddenField("Target", validators=[Optional(), _validate_frequency_target])


class FrequencyForm(FlaskForm):
    """Just the frequency fields, reusing HabitForm's validators - used by
    the standalone edit-frequency route, which never touches title/emoji."""
    frequency_type = HiddenField("Frequency", default="daily", validators=[DataRequired(), _validate_frequency_type])
    frequency_days = HiddenField("Days", validators=[Optional(), _validate_frequency_days])
    frequency_target = HiddenField("Target", validators=[Optional(), _validate_frequency_target])


WEEKDAY_ABBREVIATIONS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def _not_scheduled_for(habit, start, end):
    """A habit's non-scheduled dates in [start, end] - empty for Daily (and,
    once it ships, Weekly). The integration point with points.py: union this
    into a habit's `frozen` set before calling its streak functions, since
    "bridges the chain without counting" is already exactly what `frozen`
    means - see habitual/frequency.py."""
    return frequency.not_scheduled_dates(habit.frequency_type, habit.frequency_days, start, end)


def _freeze_schedule_for(habit, today):
    """The (missed_candidate, window_end) pair points.freeze_target_date
    needs for a Specific-Days habit - None for Daily (points.py's own
    "yesterday" default applies)."""
    if habit.frequency_type != "days":
        return None
    missed_candidate = frequency.prev_scheduled(today, habit.frequency_type, habit.frequency_days)
    window_end = frequency.next_scheduled(missed_candidate, habit.frequency_type, habit.frequency_days)
    return missed_candidate, window_end


def _effective_start(habit):
    """The start boundary every frequency-aware stat (streak, success rate,
    habit strength, rings, insights) counts from - `habit.created_on` for a
    habit whose frequency has never been edited (`frequency_changed_on` is
    NULL), or the edit date otherwise. This is the restart mechanism: an
    edit doesn't rewrite history (the ledger is untouched, and the grid/
    calendar still show real pre-edit completions), but every *live-
    computed* number treats the edit date as a fresh start, so a streak
    broken before the edit can never bridge across it and resurrect
    itself - see habitual/points.py's `floor` parameter."""
    return habit.frequency_changed_on or habit.created_on


def _frequency_label(habit):
    if habit.frequency_type == "days":
        return " ".join(
            WEEKDAY_ABBREVIATIONS[i] for i in range(7) if (habit.frequency_days or 0) & frequency.WEEKDAY_BIT[i]
        )
    if habit.frequency_type == "weekly":
        return f"{habit.frequency_target}x/week"
    return "Daily"


def _habit_view(habit, today, freezes_held):
    """Pricing/stats for one habit card, derived from points.py's pure
    functions. For Daily/Specific-Days, non-scheduled dates bridge the
    streak/freeze math exactly like a frozen day already does (`bridge`),
    but stay distinct from real freezes for success_rate, which excludes
    them from both sides of the ratio instead of bridging. Weekly habits
    use a parallel week-granularity family instead (`streak_unit` tells the
    templates which word - "day" or "week" - to use for the streak)."""
    completed = {c.date for c in habit.checkins}
    frozen = {f.used_on for f in habit.freezes if f.used_on is not None}
    amounts = [pt.amount for pt in habit.point_transactions]
    effective_start = _effective_start(habit)

    if habit.frequency_type == "weekly":
        target = habit.frequency_target or 1
        floor = points.week_start(effective_start)
        current_streak = points.weekly_streak(completed, target, today, frozen, floor)
        longest_streak = points.longest_weekly_streak(completed, target, effective_start, today, frozen)
        success_rate = round(points.weekly_success_rate(completed, effective_start, today, target))
        can_save_streak = points.weekly_freeze_available(completed, target, today, frozen, floor)
        is_due_today = True
        streak_unit = "week"
    else:
        not_scheduled = _not_scheduled_for(habit, effective_start, today)
        bridge = frozen | not_scheduled
        current_streak = points.current_streak(completed, bridge, today, effective_start)
        longest_streak = points.longest_streak(completed, bridge, effective_start, today)
        success_rate = round(points.success_rate(completed, effective_start, today, not_scheduled))
        can_save_streak = points.freeze_available(
            completed, bridge, today, _freeze_schedule_for(habit, today), effective_start
        )
        is_due_today = today not in not_scheduled
        streak_unit = "day"

    return {
        "habit": habit,
        "current_streak": current_streak,
        "longest_streak": longest_streak,
        "habit_points": points.earned_points(amounts),
        "success_rate": success_rate,
        "checked_in_today": today in completed,
        "can_save_streak": can_save_streak,
        "has_freeze_to_use": freezes_held > 0,
        "is_due_today": is_due_today,
        "frequency_label": _frequency_label(habit),
        "streak_unit": streak_unit,
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
        "badge_rows": badges.badge_rows_for(user),
    }


def _user_habits(user):
    return (
        Habit.query.filter_by(user_id=user.id)
        .order_by(Habit.created_on.desc(), Habit.id.desc())
        .all()
    )


def _overview_context(habit_rows, today):
    """Dashboard overview (Part B): a 30-day grid + line chart across every
    active habit, plus summary tiles. Built from analytics.py's pure
    aggregation functions so the math stays testable."""
    habit_infos = [
        {
            "id": h.id,
            "title": h.title,
            "emoji": h.emoji,
            "completed": {c.date for c in h.checkins},
            "frozen": {f.used_on for f in h.freezes if f.used_on is not None},
            # `created_on` stays the habit's true creation date - the 30-day
            # grid's day_state() call needs it unchanged so history from
            # before a frequency edit still renders as plain done/missed,
            # not "not tracked yet". `effective_start` is the restart floor
            # the month_success/best_streak/needs_attention aggregates below
            # use instead, so an edited habit's dashboard numbers can't
            # resurrect a pre-edit streak either.
            "created_on": h.created_on,
            "effective_start": _effective_start(h),
            "not_scheduled": _not_scheduled_for(h, _effective_start(h), today),
            "frequency_type": h.frequency_type,
            "frequency_days": h.frequency_days,
            "frequency_target": h.frequency_target,
        }
        for h in habit_rows
    ]
    grid_rows = analytics.thirty_day_grid(habit_infos, today)
    # The 30-day heatmap table (overview_rows) keeps its full fixed window -
    # a "not tracked yet" cell is a meaningful, intentional part of that
    # grid. The line chart is different: a flat 0% for every day before the
    # user's first habit existed reads as "you failed every day", not
    # "there was nothing to track yet" - so it starts at whichever is later,
    # the earliest habit's creation date or 30 days ago.
    earliest_created_on = min((h["created_on"] for h in habit_infos), default=today)
    chart_start = max(earliest_created_on, today - timedelta(days=29))
    chart_rows = [r for r in grid_rows if r["date"] >= chart_start]
    return {
        "overview_habits": habit_infos,
        "overview_rows": grid_rows,
        "overview_series": analytics.completion_series(chart_rows),
        "overview_chart_labels": [r["date"].strftime("%b %-d") for r in reversed(chart_rows)],
        **analytics.overview_summary(habit_infos, today),
    }


def _weekly_progress_for(habit_rows, today):
    """Small 'Gym · 2/3 this week' chips, one per Weekly habit, always shown
    (not just when incomplete) - Weekly habits are excluded from the
    `habits_remaining` countdown entirely (a week isn't "due today"), so
    this is their only presence in the header."""
    week_start = points.week_start(today)
    chips = []
    for h in habit_rows:
        if h.frequency_type != "weekly":
            continue
        completed = {c.date for c in h.checkins}
        done_this_week = sum(1 for d in completed if week_start <= d <= today)
        chips.append({
            "id": h.id,
            "title": h.title,
            "emoji": h.emoji,
            "done_this_week": done_this_week,
            "target": h.frequency_target or 1,
        })
    return chips


def _day_status_context(user, today, habit_rows, habits_remaining):
    """Header countdown fields: time left until the user's own local
    midnight (computed here from the server, never guessed from the
    browser's clock/timezone - the client just ticks a fixed target) plus
    the urgency flag for the last-3-hours treatment. `habits_remaining` of
    None (nothing to track yet) propagates through so the template can skip
    the countdown widget, but `weekly_progress` is still computed either
    way (empty if there's really nothing, including no weekly habits)."""
    weekly_progress = _weekly_progress_for(habit_rows, today)
    if habits_remaining is None:
        return {"habits_remaining": None, "weekly_progress": weekly_progress}
    midnight_ms = midnight_epoch_ms(user)
    seconds_left = max(0.0, midnight_ms / 1000 - local_now(user).timestamp())
    return {
        "habits_remaining": habits_remaining,
        "midnight_epoch_ms": midnight_ms,
        "hours_left": int(seconds_left // 3600),
        "minutes_left": int((seconds_left % 3600) // 60),
        "is_urgent": habits_remaining > 0 and seconds_left <= 3 * 3600,
        "weekly_progress": weekly_progress,
    }


def _room_card_context(habit):
    """Extra Room-badge/leader/health/days-left fields for a dashboard card
    whose habit belongs to a room - {} for a solo habit."""
    if habit.room_id is None:
        return {}
    from habitual import rooms  # local import avoids a circular import with rooms.py
    return rooms.room_card_extra(habit.room, current_user)


def _dashboard_context(form=None, room_form=None, join_code_form=None, join_code_error=None):
    from habitual import rooms  # local import avoids a circular import with rooms.py
    rooms.finalize_due_crowns_for_user(current_user)  # fix #1: crown points land even if nobody opens the room page
    # Evaluated before _header_stats below, so its badge_rows (and the header
    # stats it re-renders) already reflect anything newly awarded this load.
    newly_awarded_badges = badges.check_and_award(current_user)

    today = local_today(current_user)
    header = _header_stats(current_user)
    habit_rows = _user_habits(current_user)
    context = {
        "habit_cards": [
            {**_habit_view(h, today, header["freezes_held"]), **_room_card_context(h)} for h in habit_rows
        ],
        "form": form or HabitForm(),
        "room_form": room_form or rooms.RoomForm(),
        "join_code_form": join_code_form or rooms.JoinByCodeForm(),
        "join_code_error": join_code_error,
        "emoji_choices": EMOJI_CHOICES,
        "habit_templates": HABIT_TEMPLATES,
        "newly_awarded_badges": newly_awarded_badges,
        **header,
    }
    if habit_rows:
        context.update(_overview_context(habit_rows, today))
    context.update(_day_status_context(current_user, today, habit_rows, context.get("habits_remaining")))
    return context


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
            frequency_type=form.frequency_type.data,
            frequency_days=int(form.frequency_days.data) if form.frequency_type.data == "days" else None,
            frequency_target=int(form.frequency_target.data) if form.frequency_type.data == "weekly" else None,
        )
        db.session.add(habit)
        db.session.commit()
        flash(f'"{habit.title}" added - go check in!', "success")
        return redirect(url_for("habits.dashboard", new=habit.id))

    context = _dashboard_context(form=form)
    context["new_habit_id"] = None
    return render_template("dashboard.html", **context), 400


@habits.post("/habits/<int:habit_id>/frequency")
@login_required
def edit_habit_frequency(habit_id):
    """Edits a habit's frequency - the only thing editable on an existing
    habit for now (title/emoji stay create-only). Room habits reject this
    entirely: a room's frequency is locked for every member and only ever
    set via the room itself (create_room/join_room), never per-member -
    mirrors delete_habit's existing `room_id is not None` guard."""
    habit = db.get_or_404(Habit, habit_id)
    if habit.user_id != current_user.id:
        abort(404)
    if habit.room_id is not None:
        abort(400)

    form = FrequencyForm()
    if not form.validate_on_submit():
        abort(400)

    habit.frequency_type = form.frequency_type.data
    habit.frequency_days = int(form.frequency_days.data) if form.frequency_type.data == "days" else None
    habit.frequency_target = int(form.frequency_target.data) if form.frequency_type.data == "weekly" else None
    # The restart mechanism (see _effective_start): this date becomes the
    # new floor every live-computed stat counts from. The ledger - every
    # PointTransaction already earned - is never touched.
    habit.frequency_changed_on = local_today(current_user)
    db.session.commit()

    flash("Frequency updated - your streak restarts from today. Points you've earned are kept.", "info")
    return redirect(url_for("habits.habit_detail", habit_id=habit.id))


WEEKDAY_LETTERS = "MTWTFSS"


def _weekly_analytics_context(habit, today, now_hour):
    """Weekly-habit twin of `_analytics_context` - same return shape, but
    everything is computed at week granularity (freezes key on a week's
    Monday, not a day) via points.py's weekly function family. Day cells
    (this week's row, the heatmap) have no frozen/not_scheduled distinction
    at the day level - a frozen WEEK isn't "this one day was saved", so
    they only ever show done/missed/future/before_created."""
    completed = {c.date for c in habit.checkins}
    frozen_weeks = {f.used_on for f in habit.freezes if f.used_on is not None}
    target = habit.frequency_target or 1
    effective_start = _effective_start(habit)
    floor = points.week_start(effective_start)

    this_week = points.week_start(today)
    last_week = this_week - timedelta(days=7)
    froze_last_week = last_week in frozen_weeks

    week_ring = analytics.weekly_week_ring(completed, today, target)
    month_ring = analytics.weekly_month_ring(completed, effective_start, today, target)
    streak = points.weekly_streak(completed, target, today, frozen_weeks, floor)
    status_label, status_variant = analytics.habit_status(
        completed, frozen_weeks, froze_last_week, effective_start, today, now_hour,
        not_due_today=(week_ring[0] >= target),
    )

    def _day_state(d):
        if d > today:
            return "future"
        if d < habit.created_on:
            return "before_created"
        return "done" if d in completed else "missed"

    week_days = [
        {
            "letter": WEEKDAY_LETTERS[i],
            "state": _day_state(this_week + timedelta(days=i)),
            "is_today": (this_week + timedelta(days=i)) == today,
        }
        for i in range(7)
    ]

    heatmap_start = this_week - timedelta(days=7 * 4)
    heatmap_weeks = [
        [_day_state(heatmap_start + timedelta(days=7 * w + i)) for i in range(7)]
        for w in range(5)
    ]

    return {
        "week_ring": week_ring,
        "month_ring": month_ring,
        "milestone_ring": (streak, points.next_milestone(streak)),
        "strength": round(analytics.weekly_habit_strength(completed, target, effective_start, today)),
        "status_label": status_label,
        "status_variant": status_variant,
        "week_days": week_days,
        "heatmap_weeks": heatmap_weeks,
        "insight": analytics.weekly_smart_insight(completed, target, effective_start, today),
        "streak_unit": "week",
        "ring_unit": "times",
    }


def _analytics_context(habit, today, now_hour):
    """Everything habits/detail.html's ring card needs, derived from
    analytics.py's pure functions."""
    if habit.frequency_type == "weekly":
        return _weekly_analytics_context(habit, today, now_hour)

    completed = {c.date for c in habit.checkins}
    frozen = {f.used_on for f in habit.freezes if f.used_on is not None}
    yesterday = today - timedelta(days=1)
    froze_used_yesterday = any(f.used_on == yesterday for f in habit.freezes)
    effective_start = _effective_start(habit)

    week_start = today - timedelta(days=today.weekday())
    heatmap_start = week_start - timedelta(days=7 * 4)  # 5 weeks total, current week last
    # Bounded below by effective_start (not heatmap_start) - a frequency
    # edit's restart floor, see _effective_start - so dates before an edit
    # lose the not_scheduled distinction and read as plain done/missed
    # instead (the accepted cosmetic trade-off; day_state's own
    # before_created check still uses habit.created_on, unchanged, so real
    # pre-edit history still renders instead of greying out).
    not_scheduled = _not_scheduled_for(habit, max(heatmap_start, effective_start), today)
    bridge = frozen | not_scheduled

    week_ring = analytics.week_ring(completed, effective_start, today, not_scheduled)
    month_ring = analytics.month_ring(completed, effective_start, today, not_scheduled)
    streak = points.current_streak(completed, bridge, today, effective_start)
    status_label, status_variant = analytics.habit_status(
        completed, frozen, froze_used_yesterday, effective_start, today, now_hour,
        not_due_today=(today in not_scheduled), not_scheduled=not_scheduled,
    )

    week_days = [
        {
            "letter": WEEKDAY_LETTERS[i],
            "state": analytics.day_state(
                week_start + timedelta(days=i), completed, frozen, habit.created_on, today, not_scheduled
            ),
            "is_today": (week_start + timedelta(days=i)) == today,
        }
        for i in range(7)
    ]

    heatmap_weeks = [
        [
            analytics.day_state(
                heatmap_start + timedelta(days=7 * w + i), completed, frozen, habit.created_on, today, not_scheduled
            )
            for i in range(7)
        ]
        for w in range(5)
    ]

    return {
        "week_ring": week_ring,
        "month_ring": month_ring,
        "milestone_ring": (streak, points.next_milestone(streak)),
        "strength": round(analytics.habit_strength(completed, frozen, effective_start, today, not_scheduled)),
        "status_label": status_label,
        "status_variant": status_variant,
        "week_days": week_days,
        "heatmap_weeks": heatmap_weeks,
        "insight": analytics.smart_insight(completed, effective_start, today, not_scheduled),
        "streak_unit": "day",
        "ring_unit": "days",
    }


def _month_calendar_context(habit, month_start, today):
    completed = {c.date for c in habit.checkins}
    frozen = {f.used_on for f in habit.freezes if f.used_on is not None}

    cal = calendar_module.Calendar(firstweekday=0)
    month_weeks = cal.monthdatescalendar(month_start.year, month_start.month)
    not_scheduled = _not_scheduled_for(
        habit, max(month_weeks[0][0], _effective_start(habit)), month_weeks[-1][-1]
    )
    weeks = [
        [
            {
                "day": d.day,
                "state": analytics.day_state(d, completed, frozen, habit.created_on, today, not_scheduled),
                "is_today": d == today,
            }
            if d.month == month_start.month
            else None
            for d in week
        ]
        for week in month_weeks
    ]

    prev_month = (month_start - timedelta(days=1)).replace(day=1)
    next_last_day = calendar_module.monthrange(month_start.year, month_start.month)[1]
    next_month = (month_start.replace(day=next_last_day) + timedelta(days=1)).replace(day=1)

    return {
        "month_start": month_start,
        "weeks": weeks,
        "prev_month": prev_month,
        "next_month": next_month,
        "can_go_prev": prev_month >= habit.created_on.replace(day=1),
        "can_go_next": next_month <= today.replace(day=1),
    }


@habits.get("/habits/<int:habit_id>")
@login_required
def habit_detail(habit_id):
    habit = db.get_or_404(Habit, habit_id)
    if habit.user_id != current_user.id:
        abort(404)

    today = local_today(current_user)
    now_hour = local_now(current_user).hour
    freezes_held = Freeze.query.filter_by(user_id=current_user.id, used_on=None).count()

    month_param = request.args.get("month")
    try:
        calendar_month = date.fromisoformat(f"{month_param}-01") if month_param else today.replace(day=1)
    except ValueError:
        calendar_month = today.replace(day=1)
    # Never show a month before the habit existed or after the current one.
    calendar_month = max(habit.created_on.replace(day=1), min(calendar_month, today.replace(day=1)))

    back_url = (
        url_for("rooms.room_detail", room_id=habit.room_id)
        if habit.room_id is not None
        else url_for("habits.dashboard")
    )
    context = {
        **_habit_view(habit, today, freezes_held),
        **_analytics_context(habit, today, now_hour),
        "calendar": _month_calendar_context(habit, calendar_month, today),
        "recent_checkins": (
            Checkin.query.filter_by(habit_id=habit.id).order_by(Checkin.date.desc()).limit(10).all()
        ),
        "back_url": back_url,
        "frequency_form": FrequencyForm(
            frequency_type=habit.frequency_type, frequency_days=habit.frequency_days,
            frequency_target=habit.frequency_target,
        ),
    }
    return render_template("habits/detail.html", **context)


def _room_gate_or_404(habit):
    """For a room habit, blocks the action once the current user's OWN
    local day has moved past the room's final day - independent of
    whether teammates in other timezones are still mid-room. Gates
    check-in, undo, freeze-use and vouching alike."""
    if habit.room_id is None:
        return
    from habitual import rooms  # local import avoids a circular import with rooms.py
    if rooms.member_ended(habit.room, current_user):
        abort(400)


def _schedule_gate_or_404(habit, today):
    """Blocks check-in/freeze-use on a day that isn't scheduled for a
    Specific-Days habit - "this action doesn't apply right now", same style
    as _room_gate_or_404. A no-op for Daily (and, once it ships, Weekly,
    which has no single-day due/not-due concept)."""
    if not frequency.is_scheduled(today, habit.frequency_type, habit.frequency_days):
        abort(404)


def _room_live_response(habit, toast=None, celebration=None, badges_earned=None):
    """If this check-in/undo/freeze came from the room page itself (its
    forms flag that with a `room_view` field) and the habit belongs to a
    room, renders that room's live-update partial instead of the usual
    dashboard-shaped one. Returns None otherwise - including for a room
    habit checked in from its dashboard card, which still wants the normal
    dashboard-shaped response below."""
    if not request.values.get("room_view") or habit.room_id is None:
        return None
    from habitual import rooms  # local import avoids a circular import with rooms.py
    rooms.finalize_due_crowns(habit.room)
    resp = make_response(rooms.render_room_live_update(habit.room, current_user))
    trigger = {}
    if toast:
        trigger["toast"] = toast
    if celebration:
        trigger["checkinCelebration"] = celebration
    if badges_earned:
        trigger["badgesEarned"] = badges_earned
    if trigger:
        resp.headers["HX-Trigger"] = json.dumps(trigger)
    return resp


@habits.post("/habits/<int:habit_id>/checkin")
@login_required
def checkin(habit_id):
    habit = db.get_or_404(Habit, habit_id)
    if habit.user_id != current_user.id:
        abort(404)
    _room_gate_or_404(habit)

    today = local_today(current_user)
    _schedule_gate_or_404(habit, today)
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
        effective_start = _effective_start(habit)
        if habit.frequency_type == "weekly":
            target = habit.frequency_target or 1
            floor = points.week_start(effective_start)
            bonus = points.weekly_milestone_bonus_for_checkin(completed, target, today, frozen, floor)
            streak_day = points.weekly_streak(completed, target, today, frozen, floor)
        else:
            bridge = frozen | _not_scheduled_for(habit, effective_start, today)
            streak_day = points.streak_day_on(completed, bridge, today, effective_start)
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

    toast, celebration, newly_badges = None, None, []
    if points_earned:
        label = points.milestone_label(streak_day)
        toast = {
            "message": f"+{points_earned} · {label}" if label else f"+{points_earned} points!",
            "type": "success",
        }
        celebration = {"habitId": habit.id, "milestone": bool(bonus)}
        newly_badges = badges.check_and_award(current_user)

    room_response = _room_live_response(habit, toast=toast, celebration=celebration, badges_earned=newly_badges)
    if room_response is not None:
        return room_response

    header = _header_stats(current_user)
    context = {
        **_habit_view(habit, today, header["freezes_held"]),
        **_room_card_context(habit),
        **header,
        **_overview_context(_user_habits(current_user), today),
        "oob": True,
    }
    context.update(_day_status_context(current_user, today, _user_habits(current_user), context["habits_remaining"]))
    resp = make_response(render_template("partials/checkin_response.html", **context))
    if toast:
        trigger = {"toast": toast, "checkinCelebration": celebration}
        if newly_badges:
            trigger["badgesEarned"] = newly_badges
        resp.headers["HX-Trigger"] = json.dumps(trigger)
    return resp


@habits.delete("/habits/<int:habit_id>/checkin")
@login_required
def undo_checkin(habit_id):
    habit = db.get_or_404(Habit, habit_id)
    if habit.user_id != current_user.id:
        abort(404)
    _room_gate_or_404(habit)

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

    toast = {"message": "Check-in undone.", "type": "info"}
    room_response = _room_live_response(habit, toast=toast)
    if room_response is not None:
        return room_response

    header = _header_stats(current_user)
    context = {
        **_habit_view(habit, today, header["freezes_held"]),
        **_room_card_context(habit),
        **header,
        **_overview_context(_user_habits(current_user), today),
        "oob": True,
    }
    context.update(_day_status_context(current_user, today, _user_habits(current_user), context["habits_remaining"]))
    resp = make_response(render_template("partials/checkin_response.html", **context))
    resp.headers["HX-Trigger"] = json.dumps({"toast": toast})
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
    _room_gate_or_404(habit)

    # Same lock as buy_freeze: serializes this against a concurrent buy or
    # another "use a freeze" for this user, so the specific Freeze row this
    # request commits to can't be silently overwritten by a second
    # near-simultaneous request before this one's changes land.
    db.session.query(User).filter_by(id=current_user.id).with_for_update().first()

    today = local_today(current_user)
    completed = {c.date for c in Checkin.query.filter_by(habit_id=habit.id)}
    frozen = {
        f.used_on for f in Freeze.query.filter_by(habit_id=habit.id) if f.used_on is not None
    }

    effective_start = _effective_start(habit)
    is_weekly = habit.frequency_type == "weekly"
    if is_weekly:
        target = habit.frequency_target or 1
        floor = points.week_start(effective_start)
        target_date = points.weekly_freeze_target_week(completed, target, today, frozen, floor)
    else:
        not_scheduled = _not_scheduled_for(habit, effective_start, today)
        bridge = frozen | not_scheduled
        target_date = points.freeze_target_date(
            completed, bridge, today, _freeze_schedule_for(habit, today), effective_start
        )

    if target_date is None:
        abort(400)

    freeze = Freeze.query.filter_by(user_id=current_user.id, used_on=None).first()
    if freeze is None:
        abort(400)

    freeze.habit_id = habit.id
    freeze.used_on = target_date

    # Order-independent reprice: if today was already checked in before this
    # freeze bridged the gap, today's streak day (or, for Weekly, this
    # week's milestone eligibility) - and therefore its points - may now be
    # higher. Replace today's ledger entries to match, same logic as pricing
    # a fresh check-in (habitual/points.py). Mon/Wed/Fri example: miss Wed,
    # check in Fri (prices without the bridge), *then* freeze Wed - this
    # reprices Friday (today, at that point) to exactly what it'd have been
    # freezing Wed first. Weekly example: miss last week, check in this week
    # (prices without the bridge), *then* freeze last week - this reprices
    # today's check-in to exactly what it'd have been freezing last week
    # first.
    if today in completed:
        if is_weekly:
            new_frozen_weeks = frozen | {target_date}
            new_bonus = points.weekly_milestone_bonus_for_checkin(completed, target, today, new_frozen_weeks, floor)
            new_total = points.BASE_POINTS + new_bonus
        else:
            new_bridge = bridge | {target_date}
            new_streak_day = points.streak_day_on(completed, new_bridge, today, effective_start)
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
            bonus = new_bonus if is_weekly else points.milestone_bonus(new_streak_day)
            if bonus:
                db.session.add(PointTransaction(
                    user_id=current_user.id, habit_id=habit.id,
                    amount=bonus, reason="milestone", date=today,
                ))

    db.session.commit()

    toast = {"message": "Streak saved with a freeze 🧊", "type": "info"}
    newly_badges = badges.check_and_award(current_user)
    room_response = _room_live_response(habit, toast=toast, badges_earned=newly_badges)
    if room_response is not None:
        return room_response

    header = _header_stats(current_user)
    context = {
        **_habit_view(habit, today, header["freezes_held"]),
        **_room_card_context(habit),
        **header,
        **_overview_context(_user_habits(current_user), today),
        "oob": True,
    }
    context.update(_day_status_context(current_user, today, _user_habits(current_user), context["habits_remaining"]))
    resp = make_response(render_template("partials/checkin_response.html", **context))
    trigger = {"toast": toast}
    if newly_badges:
        trigger["badgesEarned"] = newly_badges
    resp.headers["HX-Trigger"] = json.dumps(trigger)
    return resp


@habits.delete("/habits/<int:habit_id>")
@login_required
def delete_habit(habit_id):
    habit = db.get_or_404(Habit, habit_id)
    if habit.user_id != current_user.id:
        abort(404)
    if habit.room_id is not None:
        # A room habit only ever goes away through leave_room(), which also
        # cleans up the RoomMember row and (if needed) ownership transfer.
        abort(400)

    title = habit.title
    db.session.delete(habit)
    db.session.commit()

    today = local_today(current_user)
    remaining_rows = _user_habits(current_user)
    context = {
        **_header_stats(current_user),
        **_overview_context(remaining_rows, today),
        "oob": True,
        "no_habits_left": len(remaining_rows) == 0,
    }
    context.update(_day_status_context(current_user, today, remaining_rows, context["habits_remaining"]))
    resp = make_response(render_template("partials/delete_response.html", **context))
    resp.headers["HX-Trigger"] = json.dumps(
        {"toast": {"message": f'Deleted "{title}".', "type": "info"}}
    )
    return resp
