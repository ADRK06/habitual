from flask import Blueprint, render_template
from flask_login import current_user, login_required
from sqlalchemy import func

from habitual import db, game
from habitual.habits import CATEGORY_DISPLAY_NAME, _habit_view, _header_stats, _user_habits, nav_shell_context
from habitual.models import Checkin, Colony, Habit
from habitual.utils.time import local_today

colony = Blueprint("colony", __name__)


def _get_or_create_colony(user):
    """One colony per user, auto-created on first visit rather than a
    migration backfill, so a user created before this phase shipped gets
    one the moment they load the page, same idea as every other lazily-
    computed thing in this app. `look` is set explicitly to the starter
    default (same explicitness the pre-4b code used for planet_type, now
    legacy - see Colony's docstring) rather than relying solely on the
    column's own default."""
    existing = Colony.query.filter_by(user_id=user.id).first()
    if existing is not None:
        return existing
    new_colony = Colony(
        user_id=user.id, name=f"{user.name}'s Colony", created_on=local_today(user), look=dict(game.DEFAULT_LOOK),
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

# Native pixel size of planet_render_rust_clean.png (and the sprites
# below) - habitual/templates/partials/colony_panel.html displays it at
# an exact 5x (240px), the PLANET_SCALE every slot position/size here
# assumes.
PLANET_NATIVE_SIZE = 48
PLANET_SCALE = 5

# Fixed (left, top, width, height) in planet_render_rust_clean.png's own
# 48x48 pixel grid for each building's cluster sprite (habitual/static/
# art/planet_building_<type>_lv<N>.png) - round 3 of the Phase 4a planet-
# buildings follow-up. These decompose the ORIGINAL planet_render_rust.
# png's own baked decorations (antenna, green dome, two window blocks, a
# far-rim block) into per-building clusters, so built up to LV3 the
# planet reproduces that original bake - see scripts/make_sprites.py's
# PLANET_CLUSTER_PIXELS docstring for the exact mapping/rationale. Each
# value here is CLUSTER_ANCHORS[type] + _cluster_bbox_offset(type) (that
# script's own helpers) - a fixed box that's the same size at every
# level (LV1/LV2 just leave more of it transparent), which is what lets
# this dict be static: no Pillow dependency here (dev-only, see
# requirements-dev.txt), so this can't read the PNGs or recompute these
# itself. Keep in sync if that art changes.
#
# Round 4 (approved LV1-readability fix) enlarged biodome's and custom_
# module's full clusters (7->10px and 5->10px) so their LV1 alone is
# readable - CLUSTER_ANCHORS didn't move, but their bounding boxes grew,
# so those two rows below changed; the other four are untouched.
BUILDING_SLOTS = {
    game.DEFENSE_TOWER: (21, 0, 2, 12),
    game.BIODOME: (25, 8, 6, 3),
    game.RESEARCH_LAB: (13, 9, 6, 5),
    game.POWER_REACTOR: (9, 14, 5, 5),
    game.OBSERVATORY: (31, 11, 7, 5),
    game.CUSTOM_MODULE: (23, 6, 3, 4),
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
    slot_left, slot_top, slot_width, slot_height = BUILDING_SLOTS[building_type]

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
        "slot_width": slot_width,
        "slot_height": slot_height,
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
        "planet_scale": PLANET_SCALE,
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
