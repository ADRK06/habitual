"""Colonies game rules (Phase 4a, "Colony core"). Pure functions only — no
DB access — same discipline as points.py: callers (habitual/colony.py,
habitual/habits.py) do the querying and pass plain data in, so every rule
here is testable in isolation and never depends on when or in what order
a DB write happened.

Phase 4a design (revised): buildings are not bought or timed - a
building's level is DERIVED on read from the lifetime count of check-ins
in its category (archived habits and fleet habits both count - see
colony._category_checkin_counts). There's no Building table, no Energy
spend on buildings, no construction timer. Energy keeps its other jobs
(freezes now; repairs/cosmetics/shop in later phases). Commander rank/
class and colony-level population augmentation are explicitly deferred
(rank/class to Phase 4b's avatar system; population isn't implemented
anywhere yet). colony_level() below is XP-only on purpose - see
CLAUDE.md for why.
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
# category whose building (Custom Module) levels from ANY check-in rather
# than one in that specific category - see level_for_checkins below.
BUILDING_TYPE_FOR_CATEGORY = {
    "fitness": DEFENSE_TOWER,
    "study": RESEARCH_LAB,
    "sleep": POWER_REACTOR,
    "water_food": BIODOME,
    "mind": OBSERVATORY,
    "other": CUSTOM_MODULE,
}
CATEGORY_FOR_BUILDING_TYPE = {building_type: category for category, building_type in BUILDING_TYPE_FOR_CATEGORY.items()}

# Checkin counts that reach LV1/LV2/LV3 - index 0 is LV1's threshold, etc.
# Same thresholds apply to Custom Module against the TOTAL count instead
# of a single category's count (see level_for_checkins). Max level (3) is
# len(LEVEL_THRESHOLDS) - still a guess pending real art, same reasoning
# as before: the sprite manifest has exactly one generic icon per
# building type, no per-level variants to derive a cap from.
LEVEL_THRESHOLDS = (10, 30, 60)
MAX_LEVEL = len(LEVEL_THRESHOLDS)

DAILY_ENERGY_CAP = 100


def level_for_checkins(count: int) -> int:
    """0 (not built yet) through MAX_LEVEL, from a lifetime check-in
    count - the same `count` means the same level regardless of which
    building/category it's for; Custom Module just gets the total count
    instead of one category's count as its `count` (see
    colony._building_tile_context)."""
    level = 0
    for threshold in LEVEL_THRESHOLDS:
        if count >= threshold:
            level += 1
    return level


def next_threshold(count: int) -> int | None:
    """The check-in count that reaches the NEXT level, or None if already
    at MAX_LEVEL - for a progress display ("14/30")."""
    for threshold in LEVEL_THRESHOLDS:
        if count < threshold:
            return threshold
    return None


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
