from datetime import datetime, timedelta, timezone

from flask import Blueprint, abort, make_response, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import func

from habitual import db, game
from habitual.auth import _aware_utc
from habitual.habits import _habit_view, _header_stats, _user_habits, nav_shell_context
from habitual.models import Building, Checkin, Colony, Habit, PointTransaction, User
from habitual.utils.time import local_today

colony = Blueprint("colony", __name__)


def _get_or_create_colony(user):
    """One colony per user, auto-created on first visit (no onboarding
    step yet - that's Phase 4b) rather than a migration backfill, so a
    user created before this phase shipped gets one the moment they load
    the page, same idea as every other lazily-computed thing in this app."""
    existing = Colony.query.filter_by(user_id=user.id).first()
    if existing is not None:
        return existing
    new_colony = Colony(
        user_id=user.id, name=f"{user.name}'s Colony", planet_type="rust", created_on=local_today(user),
    )
    db.session.add(new_colony)
    db.session.commit()
    return new_colony


def _settle_finished_buildings(colony_row):
    """Lazily settles any building whose finishes_at has passed - no
    background job (CLAUDE.md's "no cron" rule): bump level, clear the
    pending timestamps. Idempotent (a building with finishes_at already
    NULL is simply skipped) and covers both a first build (level 0 -> 1)
    and an upgrade (level N -> N+1) the same way, since that's exactly
    what finishes_at being set means either way - see Building's own
    docstring in models.py."""
    now = datetime.now(timezone.utc)
    changed = False
    for building in colony_row.buildings:
        if building.finishes_at is not None and _aware_utc(building.finishes_at) <= now:
            building.level += 1
            building.finishes_at = None
            building.started_at = None
            changed = True
    if changed:
        db.session.commit()


def _category_checkin_counts(user):
    """{category: lifetime check-in count} for every habit this user has
    ever had, active or archived - the unlock rule counts archived
    habits too (same reasoning as the daily Energy cap and badges'
    lifetime achievement counting: archiving must never look like
    progress lost, and must never be a way to "reset" toward a threshold
    either)."""
    rows = (
        db.session.query(Habit.category, func.count(Checkin.id))
        .join(Checkin, Checkin.habit_id == Habit.id)
        .filter(Habit.user_id == user.id)
        .group_by(Habit.category)
        .all()
    )
    return {category: count for category, count in rows}


# Display only (not a game rule, so it lives here rather than game.py).
BUILDING_DISPLAY_NAME = {
    game.DEFENSE_TOWER: "Defense Tower",
    game.RESEARCH_LAB: "Research Lab",
    game.POWER_REACTOR: "Power Reactor",
    game.BIODOME: "Biodome",
    game.OBSERVATORY: "Observatory",
    game.CUSTOM_MODULE: "Custom Module",
}


def _building_tile_context(building_type, building, category_checkins, total_checkins, balance):
    """`can_afford` lets the templates grey out/hide the Build or Upgrade
    button instead of offering an action the route will just 400 on - the
    same "don't offer what you know will fail" lesson as the ended-fleet
    Check in fix. The route's own balance check (_spend_or_400) stays as
    the real defense - this is purely about not presenting a guaranteed-
    to-fail control in the common case."""
    category = game.CATEGORY_FOR_BUILDING_TYPE[building_type]
    unlocked = game.is_unlocked(building_type, category_checkins, total_checkins)
    name = BUILDING_DISPLAY_NAME[building_type]

    if building is None:
        cost = game.next_level_cost(building_type, 1) if unlocked else None
        return {
            "type": building_type,
            "name": name,
            "category": category,
            "state": "buildable" if unlocked else "locked",
            "level": 0,
            "checkins": total_checkins if building_type == game.CUSTOM_MODULE else category_checkins,
            "needed": game.UNLOCK_CHECKINS,
            "cost": cost,
            "can_afford": cost is not None and balance >= cost,
            "hours": game.build_time_hours(building_type),
            "building_id": None,
        }

    in_progress = building.finishes_at is not None
    maxed = game.is_max_level(building_type, building.level)
    if in_progress:
        state = "first_build_in_progress" if building.level == 0 else "upgrade_in_progress"
    elif maxed:
        state = "maxed"
    else:
        state = "built"

    cost = None if (in_progress or maxed) else game.next_level_cost(building_type, building.level + 1)
    return {
        "type": building_type,
        "name": name,
        "category": category,
        "state": state,
        "level": building.level,
        "finishes_at": building.finishes_at,
        "cost": cost,
        "can_afford": cost is not None and balance >= cost,
        "hours": game.build_time_hours(building_type),
        "building_id": building.id,
    }


def _colony_context(user):
    colony_row = _get_or_create_colony(user)
    _settle_finished_buildings(colony_row)

    header = _header_stats(user)
    category_counts = _category_checkin_counts(user)
    total_checkins = sum(category_counts.values())
    buildings_by_type = {b.type: b for b in colony_row.buildings}

    building_tiles = [
        _building_tile_context(
            building_type, buildings_by_type.get(building_type),
            category_counts.get(game.CATEGORY_FOR_BUILDING_TYPE[building_type], 0), total_checkins,
            header["balance"],
        )
        for building_type in game.BUILDING_TYPES
    ]
    today = local_today(user)
    habit_cards = [_habit_view(h, today, header["freezes_held"]) for h in _user_habits(user)]
    return {
        "colony": colony_row,
        "colony_level": game.colony_level(header["earned_points"]),
        "building_tiles": building_tiles,
        "habit_cards": habit_cards,
        "building_type_for_category": game.BUILDING_TYPE_FOR_CATEGORY,
        **header,
    }


@colony.get("/colony")
@login_required
def colony_home():
    context = {
        **_colony_context(current_user),
        **nav_shell_context(current_user),
    }
    return render_template("colony/home.html", **context)


def _spend_or_400(user, cost):
    """Locks this user's row for the rest of the transaction (same
    pattern as habits.buy_freeze) so two near-simultaneous builds/
    upgrades can't both read "balance is enough" before either commits -
    the second blocks here until the first's transaction ends, then
    re-reads the now-current balance. Aborts 400 if it's still not
    enough even after that."""
    db.session.query(User).filter_by(id=user.id).with_for_update().first()
    header = _header_stats(user)
    if header["balance"] < cost:
        abort(400)


@colony.post("/colony/build")
@login_required
def build():
    building_type = request.form.get("type")
    if building_type not in game.BUILDING_TYPES:
        abort(400)

    colony_row = _get_or_create_colony(current_user)
    _settle_finished_buildings(colony_row)

    if Building.query.filter_by(colony_id=colony_row.id, type=building_type).first() is not None:
        abort(400)  # already built or being built - use /colony/upgrade/<id> instead

    category = game.CATEGORY_FOR_BUILDING_TYPE[building_type]
    category_counts = _category_checkin_counts(current_user)
    total_checkins = sum(category_counts.values())
    if not game.is_unlocked(building_type, category_counts.get(category, 0), total_checkins):
        abort(400)

    cost = game.next_level_cost(building_type, 1)
    _spend_or_400(current_user, cost)

    now = datetime.now(timezone.utc)
    db.session.add(Building(
        colony_id=colony_row.id, type=building_type, level=0, slot=game.default_slot(building_type),
        started_at=now, finishes_at=now + timedelta(hours=game.build_time_hours(building_type)),
    ))
    db.session.add(PointTransaction(
        user_id=current_user.id, habit_id=None, amount=-cost, reason="build", date=local_today(current_user),
    ))
    db.session.commit()
    return redirect(url_for("colony.colony_home"))


@colony.post("/colony/upgrade/<int:building_id>")
@login_required
def upgrade(building_id):
    colony_row = _get_or_create_colony(current_user)
    _settle_finished_buildings(colony_row)

    building = Building.query.filter_by(id=building_id, colony_id=colony_row.id).first()
    if building is None:
        abort(404)
    if building.finishes_at is not None:
        abort(400)  # already mid-build/upgrade
    if game.is_max_level(building.type, building.level):
        abort(400)

    target_level = building.level + 1
    cost = game.next_level_cost(building.type, target_level)
    _spend_or_400(current_user, cost)

    now = datetime.now(timezone.utc)
    building.started_at = now
    building.finishes_at = now + timedelta(hours=game.build_time_hours(building.type))
    db.session.add(PointTransaction(
        user_id=current_user.id, habit_id=None, amount=-cost, reason="upgrade", date=local_today(current_user),
    ))
    db.session.commit()
    return redirect(url_for("colony.colony_home"))
