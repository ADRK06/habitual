"""Colonies game rules (Phase 4a, "Colony core"). Pure functions only — no
DB access — same discipline as points.py: callers (habitual/colony.py,
habitual/habits.py) do the querying and pass plain data in, so every rule
here is testable in isolation and never depends on when or in what order
a DB write happened.

Phase 4a scope: buildings are structural only (buildable, levelable, cost
Energy) and have no active gameplay effect yet - no storm defense, no
Energy bonus, no population. Commander rank/class and colony-level
population augmentation are explicitly deferred (rank/class to Phase 4b's
avatar system; population isn't implemented anywhere yet). colony_level()
below is XP-only on purpose - see CLAUDE.md for why.
"""

import math

# -- categories & buildings -------------------------------------------------

CATEGORY_CHOICES = ("fitness", "study", "sleep", "water_food", "mind", "other")

DEFENSE_TOWER = "defense_tower"
RESEARCH_LAB = "research_lab"
POWER_REACTOR = "power_reactor"
BIODOME = "biodome"
OBSERVATORY = "observatory"
CUSTOM_MODULE = "custom_module"

BUILDING_TYPES = (DEFENSE_TOWER, RESEARCH_LAB, POWER_REACTOR, BIODOME, OBSERVATORY, CUSTOM_MODULE)

# Habit.category -> the one building type it powers. "other" is the only
# category whose building (Custom Module) unlocks from ANY 10 check-ins
# rather than 10 in that specific category - see is_unlocked below.
BUILDING_TYPE_FOR_CATEGORY = {
    "fitness": DEFENSE_TOWER,
    "study": RESEARCH_LAB,
    "sleep": POWER_REACTOR,
    "water_food": BIODOME,
    "mind": OBSERVATORY,
    "other": CUSTOM_MODULE,
}
CATEGORY_FOR_BUILDING_TYPE = {building_type: category for category, building_type in BUILDING_TYPE_FOR_CATEGORY.items()}

# How many check-ins (in the building's category, or any category for
# Custom Module) unlock the ability to build it at all.
UNLOCK_CHECKINS = 10

# Highest level a building can reach in Phase 4a. The art has exactly one
# generic sprite per building type (no per-level variants at all - the mock
# screens show higher levels with the same icon plus a text label), so
# this isn't actually derived from the sprite manifest the way "sprites
# exist up to level N" implies; it's a flat cap pending confirmation.
MAX_LEVEL = 3

# (base, step): cost to reach level L = base + step * (L - 1).
BUILDING_COSTS = {
    DEFENSE_TOWER: (120, 60),
    RESEARCH_LAB: (100, 50),
    POWER_REACTOR: (150, 75),
    BIODOME: (100, 50),
    OBSERVATORY: (140, 70),
    CUSTOM_MODULE: (80, 40),
}

# Flat hours per build/upgrade action, regardless of level - the Game
# Plan's Buildings table gives one time per building, not one per level.
BUILD_TIME_HOURS = {
    DEFENSE_TOWER: 4,
    RESEARCH_LAB: 6,
    POWER_REACTOR: 3,
    BIODOME: 2,
    OBSERVATORY: 5,
    CUSTOM_MODULE: 1,
}

DAILY_ENERGY_CAP = 100


def next_level_cost(building_type: str, target_level: int) -> int:
    """Energy cost of the single build/upgrade action that brings this
    building TO `target_level` - 1 for a first build (level 0 -> 1), N+1
    for an upgrade from level N. Linear: base + step * (target_level - 1)."""
    base, step = BUILDING_COSTS[building_type]
    return base + step * (target_level - 1)


def build_time_hours(building_type: str) -> int:
    return BUILD_TIME_HOURS[building_type]


def is_unlocked(building_type: str, category_checkin_count: int, total_checkin_count: int) -> bool:
    """Whether `building_type` can be built at all yet. Custom Module is
    "any 10 check-ins" (any category); every other building needs 10
    check-ins specifically in the category it's mapped from."""
    if building_type == CUSTOM_MODULE:
        return total_checkin_count >= UNLOCK_CHECKINS
    return category_checkin_count >= UNLOCK_CHECKINS


def is_max_level(building_type: str, level: int) -> bool:
    return level >= MAX_LEVEL


def default_slot(building_type: str) -> int:
    """Fixed display position (0-5) on the planet's building grid - the
    canonical order BUILDING_TYPES is already declared in. Not user-
    editable in Phase 4a; a later rearrange feature would read/write the
    stored slot instead of always deriving it from this."""
    return BUILDING_TYPES.index(building_type)


def colony_level(xp: int) -> int:
    """XP-only, per the approved formula: 1 + floor(sqrt(xp / 25)).
    Deliberately ignores population/building-count augmentation (Game Plan
    mentions both, but population isn't implemented anywhere yet).

    floor(sqrt(xp / 25)) == floor(sqrt(xp)) // 5 for every non-negative xp
    (sqrt(xp)/5 and sqrt(xp/25) are the same real number, and dividing an
    already-floored integer by 5 can never cross a multiple-of-5 boundary
    that the un-floored value wouldn't have crossed too) - so this uses
    math.isqrt (exact integer square root) instead of math.sqrt, which has
    no floating-point risk right at the perfect-square boundaries the
    tests target (25, 100, 400, 2025, ...)."""
    return 1 + math.isqrt(xp) // 5


def energy_awarded_with_cap(already_earned_today: int, amount: int) -> int:
    """Partial top-up against the daily cap: awards `amount` in full if
    today's total (already_earned_today + amount) stays at or under
    DAILY_ENERGY_CAP, otherwise awards only what's left of the cap (never
    negative). A day already at or past the cap awards 0 for anything
    more. `already_earned_today` must already be scoped to the right
    reasons/day/user by the caller - this function only does the arithmetic."""
    remaining = DAILY_ENERGY_CAP - already_earned_today
    return max(0, min(amount, remaining))
