import re
import secrets
from datetime import datetime, timedelta, timezone as dt_timezone
from zoneinfo import ZoneInfo

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from flask_wtf import FlaskForm
from sqlalchemy.exc import IntegrityError
from wtforms import HiddenField, IntegerField, StringField
from wtforms.validators import DataRequired, NumberRange

from habitual import badges, db, points
from habitual.auth import _aware_utc
from habitual.habits import _analytics_context, _dashboard_context, _habit_view, _validate_emoji, _validate_title
from habitual.models import Checkin, Freeze, Habit, PointTransaction, Room, RoomCrown, RoomMember, User, Vouch
from habitual.utils.time import local_now, local_today

rooms = Blueprint("rooms", __name__)

VOUCH_EMOJIS = ("✅", "🔥")
MAX_ROOM_MEMBERS = 20

JOIN_CODE_LENGTH = 6
# Uppercase letters + digits, minus the ones easy to mix up at a glance or
# when read aloud (0/O, 1/I/L).
JOIN_CODE_ALPHABET = "".join(
    c for c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789" if c not in "0O1IL"
)
JOIN_CODE_MAX_FAILURES = 10
JOIN_CODE_LOCKOUT_MINUTES = 10


class RoomForm(FlaskForm):
    title = StringField("Title", validators=[DataRequired(), _validate_title])
    emoji = HiddenField("Emoji", validators=[DataRequired(), _validate_emoji])
    duration_days = IntegerField(
        "Duration (days)", validators=[DataRequired(), NumberRange(min=7, max=90, message="7-90 days.")]
    )


class JoinByCodeForm(FlaskForm):
    code = StringField("Code", validators=[DataRequired()])


# -- join codes -----------------------------------------------------------


def normalize_join_code(raw):
    """Upper-cases and strips spaces/dashes, so "k7m4-qx" and "K7M4 QX" and
    "K7M4QX" all look up the same room."""
    return re.sub(r"[\s-]", "", (raw or "")).upper()


def generate_join_code():
    while True:
        code = "".join(secrets.choice(JOIN_CODE_ALPHABET) for _ in range(JOIN_CODE_LENGTH))
        if Room.query.filter_by(join_code=code).first() is None:
            return code


def _join_locked_until(user):
    return _aware_utc(user.join_locked_until)


def _register_failed_code_attempt(user):
    now = datetime.now(dt_timezone.utc)
    user.failed_join_attempts += 1
    if user.failed_join_attempts >= JOIN_CODE_MAX_FAILURES:
        user.join_locked_until = now + timedelta(minutes=JOIN_CODE_LOCKOUT_MINUTES)
    db.session.commit()


def _clear_failed_code_attempts(user):
    if user.failed_join_attempts or user.join_locked_until:
        user.failed_join_attempts = 0
        user.join_locked_until = None
        db.session.commit()


# -- shared helpers -----------------------------------------------------------


def _room_or_404(room_id):
    return db.get_or_404(Room, room_id)


def _room_members(room):
    return RoomMember.query.filter_by(room_id=room.id).all()


def _member_habit(room, user):
    return Habit.query.filter_by(room_id=room.id, user_id=user.id).first()


def room_is_full(room, members=None):
    members = members if members is not None else _room_members(room)
    return len(members) >= MAX_ROOM_MEMBERS


def final_day(room):
    """The last date room membership is active for ANY member, in the
    sense of "room.start_date + duration". Each member's own participation
    actually ends on this date in their OWN timezone - see member_ended."""
    return room.start_date + timedelta(days=room.duration_days - 1)


def member_ended(room, user):
    """True once `user`'s own local date has moved past the room's final
    day - independent of whether other members (in other timezones) have
    gotten there yet. Gates check-in, undo, freeze-use and vouching for
    that member, even while the room is still live for teammates."""
    return local_today(user) > final_day(room)


def room_fully_ended(room, members):
    """True once every member's own final day has passed - this is when
    final standings lock and the room becomes read-only."""
    return all(member_ended(room, m.user) for m in members)


def _avg_checkin_time_seconds(user, checkins):
    """Average local time-of-day (seconds since midnight), in `user`'s own
    timezone, across `checkins` - a leaderboard tiebreaker only. A member
    with no check-ins sorts last (worst) on this dimension."""
    if not checkins:
        return float("inf")
    tz = ZoneInfo(user.timezone)
    seconds = []
    for c in checkins:
        local_dt = _aware_utc(c.created_at).astimezone(tz)
        seconds.append(local_dt.hour * 3600 + local_dt.minute * 60 + local_dt.second)
    return sum(seconds) / len(seconds)


def rank_members(room, members):
    """Leaderboard order: room habit points desc, fewest missed days,
    earliest average check-in time. Used both for the room page leaderboard
    and to pick the new owner when the creator leaves."""
    entries = []
    for member in members:
        user = member.user
        habit = _member_habit(room, user)
        today = local_today(user)
        completed = {c.date for c in habit.checkins}
        frozen = {f.used_on for f in habit.freezes if f.used_on is not None}
        amounts = [pt.amount for pt in habit.point_transactions]
        entries.append({
            "member": member,
            "user": user,
            "habit": habit,
            "points": points.earned_points(amounts),
            "current_streak": points.current_streak(completed, frozen, today),
            "missed_days": points.missed_days(completed, frozen, habit.created_on, today),
            "avg_checkin_seconds": _avg_checkin_time_seconds(user, habit.checkins),
        })
    entries.sort(key=lambda e: (-e["points"], e["missed_days"], e["avg_checkin_seconds"]))
    return entries


def _member_completed_dates(room, user):
    habit = _member_habit(room, user)
    return {c.date for c in habit.checkins} if habit else set()


def room_health_pct(room, members):
    """% of members checked in on their OWN local today - not a single
    shared "today", per member."""
    if not members:
        return 0
    checked_in_today = sum(
        1 for m in members if local_today(m.user) in _member_completed_dates(room, m.user)
    )
    return round(checked_in_today / len(members) * 100)


def room_streak_value(room, members):
    if not members:
        return 0
    member_states = [
        {"completed": _member_completed_dates(room, m.user), "joined_on": m.joined_on}
        for m in members
    ]
    # The most-behind member's own "today" - see points.room_streak's
    # docstring for why a day can't be judged "everyone made it" any
    # earlier than that.
    today_anchor = min(local_today(m.user) for m in members)
    return points.room_streak(member_states, today_anchor)


def room_card_extra(room, viewer):
    """Dashboard room-card fields - per-viewer (days remaining, ended) and
    room-wide (health, leader)."""
    members = _room_members(room)
    ranked = rank_members(room, members)
    leader = ranked[0] if ranked else None
    return {
        "room": room,
        "member_count": len(members),
        "days_remaining": max((final_day(room) - local_today(viewer)).days, 0),
        "viewer_ended": member_ended(room, viewer),
        "health_pct": room_health_pct(room, members),
        "leader_name": leader["user"].name if leader else None,
        "leader_is_viewer": bool(leader and leader["user"].id == viewer.id),
        "is_creator": room.creator_id == viewer.id,
    }


def _personal_stats(habit, viewer):
    """The room page's personal stats panel reuses the exact same pure
    display logic as the solo habit card/analytics page - a room habit is
    a normal habit (see CLAUDE.md's architecture decisions)."""
    today = local_today(viewer)
    now_hour = local_now(viewer).hour
    freezes_held = Freeze.query.filter_by(user_id=viewer.id, used_on=None).count()
    return {
        **_habit_view(habit, today, freezes_held),
        **_analytics_context(habit, today, now_hour),
    }


# -- crown finalization (lazy, idempotent, per-member local dates) ----------


def _date_closed(room, members, date_d):
    """True once every member who'd joined by `date_d` has moved past it in
    their own timezone - i.e. date_d can never receive another eligible
    check-in from anyone, so its crown can be decided for good."""
    joined = [m for m in members if m.joined_on <= date_d]
    if not joined:
        return False
    return all(local_today(m.user) > date_d for m in joined)


def _crown_candidates(room, members, date_d):
    """Eligible (local_time, created_at_utc, user_id, checkin_id, habit_id)
    tuples for `date_d` - only members who'd joined by then, only check-ins
    with a valid proof note."""
    candidates = []
    for member in members:
        if member.joined_on > date_d:
            continue
        habit = _member_habit(room, member.user)
        checkin = Checkin.query.filter_by(habit_id=habit.id, date=date_d).first()
        if checkin is None or not points.has_valid_proof_for_crown(checkin.proof_note):
            continue
        local_time = _aware_utc(checkin.created_at).astimezone(ZoneInfo(member.user.timezone)).time()
        candidates.append((local_time, _aware_utc(checkin.created_at), member.user.id, checkin.id, habit.id))
    return candidates


def finalize_due_crowns(room, members=None):
    """Lazily finalizes the crown for every date that's fully closed and
    not yet decided - safe to call on every room-page/dashboard load.
    Already-finalized dates are skipped outright, and the
    UNIQUE(room_id, date) constraint makes a concurrent double-finalize a
    no-op rather than a double-award, so this never needs a lock or a cron."""
    members = members if members is not None else _room_members(room)
    if not members:
        return

    already = {rc.date for rc in RoomCrown.query.filter_by(room_id=room.id)}
    # A date can only be closed once every member who could have earned it
    # has moved past it - so nothing newer than the most-behind member's
    # own "yesterday" is even worth checking yet.
    horizon = min(local_today(m.user) for m in members) - timedelta(days=1)

    cursor = room.start_date
    while cursor <= horizon:
        if cursor not in already and _date_closed(room, members, cursor):
            winner = points.crown_winner(_crown_candidates(room, members, cursor))
            if winner is not None:
                _, _, winner_user_id, winner_checkin_id, winner_habit_id = winner
                db.session.add(RoomCrown(
                    room_id=room.id, date=cursor, user_id=winner_user_id, checkin_id=winner_checkin_id,
                ))
                db.session.add(PointTransaction(
                    user_id=winner_user_id, habit_id=winner_habit_id,
                    amount=points.CROWN_BONUS, reason="crown", date=cursor,
                ))
                try:
                    db.session.commit()
                except IntegrityError:
                    db.session.rollback()
                else:
                    # Lands on whichever page load happened to finalize this
                    # date, not necessarily the winner's own - that's fine,
                    # the badge shows up next time they load a page.
                    winner_user = db.session.get(User, winner_user_id)
                    if winner_user is not None:
                        badges.check_and_award(winner_user)
        cursor += timedelta(days=1)


def finalize_due_crowns_for_user(user):
    """Called on dashboard load (and room-page load) so crown points reach
    the header/leaderboard even if nobody ever opens the room page itself."""
    room_ids = [m.room_id for m in RoomMember.query.filter_by(user_id=user.id)]
    for room_id in room_ids:
        room = db.session.get(Room, room_id)
        if room is not None:
            finalize_due_crowns(room)


def _crown_counts(room):
    counts = {}
    for rc in RoomCrown.query.filter_by(room_id=room.id):
        counts[rc.user_id] = counts.get(rc.user_id, 0) + 1
    return counts


def _crown_badges_for_checkins(room, members, checkins):
    """Maps checkin.id -> "final" | "provisional" for every date represented
    in `checkins`. A date with a RoomCrown row is decided for good; one
    without is re-raced fresh from current state on every call, so the
    provisional badge can still move to someone else before the date
    closes."""
    if not checkins:
        return {}
    dates = {c.date for c in checkins}
    finalized_checkin_by_date = {
        rc.date: rc.checkin_id
        for rc in RoomCrown.query.filter(RoomCrown.room_id == room.id, RoomCrown.date.in_(dates))
    }

    badges = {}
    for d in dates:
        if d in finalized_checkin_by_date:
            winner_checkin_id = finalized_checkin_by_date[d]
            if winner_checkin_id is not None:
                badges[winner_checkin_id] = "final"
            continue
        winner = points.crown_winner(_crown_candidates(room, members, d))
        if winner is not None:
            badges[winner[3]] = "provisional"
    return badges


def _feed_context(room, members, viewer, limit=20):
    """Recent check-ins across every member's room habit, newest first,
    each annotated with its crown badge and vouch state. There's no single
    shared "today" to scope this to (every member's today is their own
    local date), so it's simply the most recent activity in the room."""
    habit_by_id = {}
    user_by_habit_id = {}
    for m in members:
        habit = _member_habit(room, m.user)
        if habit is not None:
            habit_by_id[habit.id] = habit
            user_by_habit_id[habit.id] = m.user

    if not habit_by_id:
        return []

    checkins = (
        Checkin.query.filter(Checkin.habit_id.in_(habit_by_id.keys()))
        .order_by(Checkin.created_at.desc())
        .limit(limit)
        .all()
    )
    badges = _crown_badges_for_checkins(room, members, checkins)

    items = []
    for c in checkins:
        vouch_counts = {emoji: 0 for emoji in VOUCH_EMOJIS}
        viewer_vouch_emoji = None
        for v in c.vouches:
            vouch_counts[v.emoji] = vouch_counts.get(v.emoji, 0) + 1
            if v.user_id == viewer.id:
                viewer_vouch_emoji = v.emoji
        owner = user_by_habit_id.get(c.habit_id)
        items.append({
            "checkin": c,
            "user": owner,
            "crown_badge": badges.get(c.id),
            "vouch_counts": vouch_counts,
            "viewer_vouch_emoji": viewer_vouch_emoji,
            "can_vouch": owner is not None and owner.id != viewer.id,
        })
    return items


def _leaderboard_context(room, members, viewer):
    ranked = rank_members(room, members)
    crown_count_by_user = _crown_counts(room)
    return [
        {
            **entry,
            "crown_count": crown_count_by_user.get(entry["user"].id, 0),
            "is_viewer": entry["user"].id == viewer.id,
        }
        for entry in ranked
    ]


def _invite_message(room):
    join_url = url_for("rooms.join_landing", token=room.invite_token, _external=True)
    return f"Join my Habitual room 🔥 {room.emoji} {room.title} — code: {room.join_code} or {join_url}"


def render_room_live_update(room, viewer):
    """The OOB bundle rendered after a check-in/undo/freeze made from the
    room page itself (habits.py's checkin()/undo_checkin()/use_freeze()
    call this instead of their usual dashboard-shaped response when the
    request came from there) - personal panel, leaderboard, health, streak
    and feed, all re-derived from current state."""
    members = _room_members(room)
    viewer_habit = _member_habit(room, viewer)
    return render_template(
        "partials/room_live_update.html",
        room=room,
        leaderboard=_leaderboard_context(room, members, viewer),
        health_pct=room_health_pct(room, members),
        streak_value=room_streak_value(room, members),
        feed=_feed_context(room, members, viewer),
        **_personal_stats(viewer_habit, viewer),
    )


# -- routes -------------------------------------------------------------------


@rooms.post("/rooms")
@login_required
def create_room():
    form = RoomForm()
    if not form.validate_on_submit():
        context = _dashboard_context(room_form=form)
        context["new_habit_id"] = None
        return render_template("dashboard.html", **context), 400

    today = local_today(current_user)
    room = Room(
        title=form.title.data.strip(),
        emoji=form.emoji.data,
        creator_id=current_user.id,
        duration_days=form.duration_days.data,
        start_date=today,
        invite_token=secrets.token_urlsafe(16),
        join_code=generate_join_code(),
    )
    db.session.add(room)
    db.session.flush()  # need room.id before the member/habit rows below

    db.session.add(RoomMember(room_id=room.id, user_id=current_user.id, joined_on=today))
    db.session.add(Habit(
        user_id=current_user.id, room_id=room.id, title=room.title, emoji=room.emoji, created_on=today,
    ))
    db.session.commit()

    flash(f'"{room.title}" room created - share the invite link!', "success")
    return redirect(url_for("rooms.room_detail", room_id=room.id))


@rooms.get("/join/<token>")
def join_landing(token):
    room = Room.query.filter_by(invite_token=token).first_or_404()
    members = _room_members(room)
    is_member = current_user.is_authenticated and any(m.user_id == current_user.id for m in members)
    is_full = room_is_full(room, members)
    # Only meaningful once we know WHOSE timezone to check - an anonymous
    # visitor sees the plain login/signup prompt instead (full still wins
    # over that, below, since joining is impossible for anyone either way).
    ended_for_viewer = current_user.is_authenticated and member_ended(room, current_user)
    can_join = current_user.is_authenticated and not is_member and not ended_for_viewer and not is_full

    return render_template(
        "rooms/join.html",
        room=room,
        member_count=len(members),
        max_members=MAX_ROOM_MEMBERS,
        final_day=final_day(room),
        is_member=is_member,
        is_full=is_full,
        can_join=can_join,
        ended_for_viewer=ended_for_viewer,
    )


@rooms.post("/join/<token>")
@login_required
def join_room(token):
    room = Room.query.filter_by(invite_token=token).first_or_404()
    today = local_today(current_user)

    if RoomMember.query.filter_by(room_id=room.id, user_id=current_user.id).first():
        return redirect(url_for("rooms.room_detail", room_id=room.id))

    if member_ended(room, current_user):
        abort(400)

    if room_is_full(room):
        abort(400)

    db.session.add(RoomMember(room_id=room.id, user_id=current_user.id, joined_on=today))
    db.session.add(Habit(
        user_id=current_user.id, room_id=room.id, title=room.title, emoji=room.emoji, created_on=today,
    ))
    db.session.commit()

    flash(f'Joined "{room.title}"!', "success")
    return redirect(url_for("rooms.room_detail", room_id=room.id))


@rooms.get("/rooms/<int:room_id>")
@login_required
def room_detail(room_id):
    room = _room_or_404(room_id)
    members = _room_members(room)
    viewer_member = next((m for m in members if m.user_id == current_user.id), None)
    if viewer_member is None:
        abort(404)

    finalize_due_crowns(room, members)
    # Re-read members' habits fresh - finalize_due_crowns may have just
    # added crown PointTransactions that the leaderboard needs to reflect.
    viewer_habit = _member_habit(room, current_user)
    # Catches room_champion (this room may have just become fully ended) and
    # crown_collector for the viewer specifically, not just whoever happened
    # to trigger finalize_due_crowns above.
    newly_awarded_badges = badges.check_and_award(current_user)

    return render_template(
        "rooms/room.html",
        room=room,
        member_count=len(members),
        max_members=MAX_ROOM_MEMBERS,
        is_creator=room.creator_id == current_user.id,
        viewer_ended=member_ended(room, current_user),
        ended=room_fully_ended(room, members),
        days_remaining=max((final_day(room) - local_today(current_user)).days, 0),
        leaderboard=_leaderboard_context(room, members, current_user),
        health_pct=room_health_pct(room, members),
        streak_value=room_streak_value(room, members),
        feed=_feed_context(room, members, current_user),
        invite_message=_invite_message(room),
        newly_awarded_badges=newly_awarded_badges,
        **_personal_stats(viewer_habit, current_user),
    )


@rooms.post("/rooms/<int:room_id>/leave")
@login_required
def leave_room(room_id):
    room = _room_or_404(room_id)
    members = _room_members(room)
    member = next((m for m in members if m.user_id == current_user.id), None)
    if member is None:
        abort(404)

    was_creator = room.creator_id == current_user.id
    habit = _member_habit(room, current_user)

    if habit is not None:
        # RoomCrown rows referencing one of this habit's check-ins must
        # survive as history (per models.RoomCrown's docstring) - null the
        # reference before the habit's own cascade deletes those check-ins,
        # so the delete below never has a dangling/blocking FK to contend
        # with. The crown's +2 PointTransaction lives on this same habit, so
        # it (correctly) disappears with the rest of the habit's ledger.
        checkin_ids = [c.id for c in habit.checkins]
        if checkin_ids:
            RoomCrown.query.filter(RoomCrown.checkin_id.in_(checkin_ids)).update(
                {"checkin_id": None}, synchronize_session=False
            )
        db.session.delete(habit)

    db.session.delete(member)
    db.session.flush()

    remaining = [m for m in members if m.user_id != current_user.id]
    if not remaining:
        db.session.delete(room)
    elif was_creator:
        ranked = rank_members(room, remaining)
        room.creator_id = ranked[0]["user"].id

    db.session.commit()
    flash(f'Left "{room.title}".', "info")
    return redirect(url_for("habits.dashboard"))


@rooms.post("/rooms/<int:room_id>/regenerate-invite")
@login_required
def regenerate_invite(room_id):
    room = _room_or_404(room_id)
    if room.creator_id != current_user.id:
        abort(404)

    # Both invalidated together - an old link and an old code are two paths
    # to the same door, so leaving one standing would defeat the point.
    room.invite_token = secrets.token_urlsafe(16)
    room.join_code = generate_join_code()
    db.session.commit()

    flash("Invite link and code regenerated.", "info")
    return redirect(url_for("rooms.room_detail", room_id=room.id))


@rooms.post("/rooms/find-by-code")
@login_required
def find_by_code():
    form = JoinByCodeForm()
    error = None
    now = datetime.now(dt_timezone.utc)
    locked_until = _join_locked_until(current_user)

    if locked_until and locked_until > now:
        minutes_left = int((locked_until - now).total_seconds() // 60) + 1
        error = f"Too many attempts. Try again in {minutes_left} minute(s)."
    elif form.validate_on_submit():
        code = normalize_join_code(form.code.data)
        room = Room.query.filter_by(join_code=code).first() if len(code) == JOIN_CODE_LENGTH else None
        if room is None:
            _register_failed_code_attempt(current_user)
            error = "No room found with that code."
        else:
            # Finding a real room isn't an abuse signal, even if the viewer
            # then can't actually join it (full/ended/already a member) -
            # join_landing (below) handles all of those with their own
            # messaging, so this route's only job is the lookup itself.
            _clear_failed_code_attempts(current_user)
            return redirect(url_for("rooms.join_landing", token=room.invite_token))
    else:
        error = "Enter the 6-character code."

    context = _dashboard_context(join_code_form=form, join_code_error=error)
    context["new_habit_id"] = None
    return render_template("dashboard.html", **context), 400


@rooms.post("/checkins/<int:checkin_id>/vouch")
@login_required
def vouch(checkin_id):
    checkin = db.get_or_404(Checkin, checkin_id)
    habit = checkin.habit
    if habit.room_id is None:
        abort(404)

    room = db.session.get(Room, habit.room_id)
    members = _room_members(room)
    member = next((m for m in members if m.user_id == current_user.id), None)
    if member is None:
        abort(404)
    if habit.user_id == current_user.id:
        abort(400)  # no self-vouch
    if member_ended(room, current_user):
        abort(400)  # fix #3: a member's own final day gates vouching too

    emoji = request.form.get("emoji")
    if emoji not in VOUCH_EMOJIS:
        abort(400)

    existing = Vouch.query.filter_by(checkin_id=checkin.id, user_id=current_user.id).first()
    if existing and existing.emoji == emoji:
        db.session.delete(existing)  # clicking your own emoji again toggles it off
    elif existing:
        existing.emoji = emoji  # switching emoji replaces it - one vouch per person
    else:
        db.session.add(Vouch(checkin_id=checkin.id, user_id=current_user.id, emoji=emoji))
    try:
        db.session.commit()
    except IntegrityError:
        # A near-simultaneous double-submit (e.g. a double-click) can race
        # two inserts past the "existing" check above - UNIQUE(checkin_id,
        # user_id) rejects the second, same double-submit-safety pattern as
        # habits.checkin(). The first request's vouch already landed, so
        # there's nothing left to do here but recover and re-render current
        # state below.
        db.session.rollback()
    db.session.refresh(checkin)

    vouch_counts = {e: 0 for e in VOUCH_EMOJIS}
    viewer_vouch_emoji = None
    for v in checkin.vouches:
        vouch_counts[v.emoji] = vouch_counts.get(v.emoji, 0) + 1
        if v.user_id == current_user.id:
            viewer_vouch_emoji = v.emoji

    return render_template(
        "partials/room_feed_item.html",
        item={
            "checkin": checkin,
            "user": db.session.get(User, habit.user_id),
            "crown_badge": _crown_badges_for_checkins(room, members, [checkin]).get(checkin.id),
            "vouch_counts": vouch_counts,
            "viewer_vouch_emoji": viewer_vouch_emoji,
            "can_vouch": True,
        },
    )
