from flask import Blueprint, render_template
from flask_login import current_user, login_required
from sqlalchemy import func

from habitual import db, game
from habitual.habits import CATEGORY_DISPLAY_NAME, _habit_view, _header_stats, _user_habits, nav_shell_context
from habitual.models import Checkin, Colony, Habit
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


def _category_checkin_counts(user):
    """{category: lifetime check-in count} for every habit this user has
    ever had - active, archived, solo or fleet - in one grouped query
    (not N+1). Archived habits count (same reasoning as the daily Energy
    cap and badges' lifetime achievement counting: archiving must never
    look like progress lost, and must never be a way to "reset" a
    building's level either). Fleet habits count too, for free - they're
    normal Habit rows with a category copied from their room at join/
    create time (see rooms.py), so this query doesn't need to know or
    care whether a habit is solo or fleet."""
    rows = (
        db.session.query(Habit.category, func.count(Checkin.id))
        .join(Checkin, Checkin.habit_id == Habit.id)
        .filter(Habit.user_id == user.id)
        .group_by(Habit.category)
        .all()
    )
    return {category: count for category, count in rows}


def level_up_for_checkin(habit, user):
    """(building_type, old_level, new_level) for the building `habit`'s
    category powers, comparing habitual.game.level_for_checkins just
    before and after the check-in that was just committed. Must only be
    called once, right after habits.checkin() commits a genuinely NEW
    Checkin row (never on a duplicate/suppressed attempt, and never from
    a GET route/page load - decision 4) - that guarantee is what lets
    this derive "before" as count-1 instead of re-querying a snapshot
    from before the commit.

    Every building, Custom Module included, reads only its OWN category's
    count - a check-in always advances exactly one building, the one for
    its habit's category (Custom Module's is "other" - see game.py's
    BUILDING_TYPE_FOR_CATEGORY)."""
    building_type = game.BUILDING_TYPE_FOR_CATEGORY.get(habit.category, game.CUSTOM_MODULE)
    category_counts = _category_checkin_counts(user)
    count_after = category_counts.get(habit.category, 0)
    return building_type, game.level_for_checkins(count_after - 1), game.level_for_checkins(count_after)


# Display only (not a game rule, so it lives here rather than game.py).
BUILDING_DISPLAY_NAME = {
    game.DEFENSE_TOWER: "Defense Tower",
    game.RESEARCH_LAB: "Research Lab",
    game.POWER_REACTOR: "Power Reactor",
    game.BIODOME: "Biodome",
    game.OBSERVATORY: "Observatory",
    game.CUSTOM_MODULE: "Custom Module",
}

# CATEGORY_DISPLAY_NAME (imported above, from habitual.habits) is the
# label shown on a still-locked tile ("Fitness 7/10"), not the building's
# own name (it isn't built yet).

# One-line "what it will do" note for the tile's hover/tap card - no
# building has any gameplay effect yet (Phase 4a is visuals-only), so
# every note is future-tensed and tagged "(coming soon)". Wording drawn
# from docs/COLONIES_GAME_PLAN.md's building table, not invented here.
BUILDING_EFFECT_NOTE = {
    game.DEFENSE_TOWER: "Will block storm damage (coming soon)",
    game.RESEARCH_LAB: "Will unlock new building designs (coming soon)",
    game.POWER_REACTOR: "Will give a small Energy bonus on every check-in (coming soon)",
    game.BIODOME: "Will grow your colony's population (coming soon)",
    game.OBSERVATORY: "Will reveal rare events and new planets (coming soon)",
    game.CUSTOM_MODULE: "Purely cosmetic - you'll pick its design (coming soon)",
}

# Fixed pixel slot (top-left corner, for a PLANET_SPRITE_SIZE square) for
# each building type on the 240x240 planet image (habitual/static/art/
# planet_render_rust.png, displayed at that fixed size - see colony_panel.
# html). No mock gives real coordinates for this: every WebHome/PhoneHome/
# Globe/Isometric/SideView reference screen bakes its buildings into ONE
# static illustration PNG (confirmed by inspecting docs/reference/colonies/
# screens/*.dc.html and canvas.json - Globe.dc.html is "A - Round globe
# (chosen)"), which can't represent a user's own derived 0-6 built subset.
# These six slots are placed on our own plain planet_render_rust.png
# (confirmed to have no baked decorations of its own except a thin antenna
# mast and a couple of small debris pixels at the very top, roughly CSS
# x:75-115 y:0-55 at this 240x240 display size) - spaced 48 degrees apart
# around the lower 240 degrees of the sphere's rim (clockwise from top,
# skipping straight up +/-60 degrees so nothing lands on or near the
# antenna), at radius 68px from the sphere's own center (117, 130) and
# this file's own PLANET_SPRITE_SIZE.
PLANET_SPRITE_SIZE = 32
PLANET_SLOTS = {
    game.DEFENSE_TOWER: (160, 80),
    game.RESEARCH_LAB: (166, 135),
    game.POWER_REACTOR: (129, 176),
    game.BIODOME: (74, 176),
    game.OBSERVATORY: (37, 135),
    game.CUSTOM_MODULE: (43, 80),
}


def _building_tile_context(building_type, category_checkins):
    """Level is DERIVED from check-in counts, never stored - no Build
    menu, no Energy spend, no construction timer (see game.py's module
    docstring for why this phase dropped all of that). Every building,
    Custom Module included, reads only its own mapped category's count -
    Custom Module's category is "other" (everything not in the five named
    categories), never the total across every category."""
    category = game.CATEGORY_FOR_BUILDING_TYPE[building_type]
    level = game.level_for_checkins(category_checkins)
    target = game.next_threshold(category_checkins)
    slot_left, slot_top = PLANET_SLOTS[building_type]

    return {
        "type": building_type,
        "name": BUILDING_DISPLAY_NAME[building_type],
        "category": category,
        "category_name": CATEGORY_DISPLAY_NAME[category],
        "level": level,
        "checkins": category_checkins,
        "next_threshold": target,
        "maxed": target is None,
        "slot_left": slot_left,
        "slot_top": slot_top,
        "effect_note": BUILDING_EFFECT_NOTE[building_type],
    }


def _colony_context(user):
    colony_row = _get_or_create_colony(user)

    category_counts = _category_checkin_counts(user)

    building_tiles = [
        _building_tile_context(building_type, category_counts.get(game.CATEGORY_FOR_BUILDING_TYPE[building_type], 0))
        for building_type in game.BUILDING_TYPES
    ]

    header = _header_stats(user)
    today = local_today(user)
    habit_cards = [_habit_view(h, today, header["freezes_held"]) for h in _user_habits(user)]
    return {
        "colony": colony_row,
        "colony_level": game.colony_level(header["earned_points"]),
        "building_tiles": building_tiles,
        "habit_cards": habit_cards,
        "building_type_for_category": game.BUILDING_TYPE_FOR_CATEGORY,
        "planet_sprite_size": PLANET_SPRITE_SIZE,
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
