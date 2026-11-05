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
(freezes now; repairs/cosmetics/shop in later phases). colony_level()
below is XP-only on purpose - see CLAUDE.md for why.

Phase 4b adds commander rank/class and the starter-only avatar/planet-
look system. Rank is XP-derived (rank_for_xp, same `earned_points`
metric colony_level() uses); class is DERIVED on read from the user's
strongest category by check-in count (class_for_category_counts),
never stored - same "derived, not stored" discipline as building
levels. Avatar/look are starter-only in this phase: no shop, no
owned_items table, no purchases - AVATAR_STARTER_VALUES/
LOOK_STARTER_VALUES are each slot's complete and ONLY valid value set
(a locked/bought/earned-only option from the Game Plan's tables simply
isn't accepted yet; that's Phase 8). validate_avatar_payload/
validate_look_payload are the one and only save-time rule: every
equipped value must be in that slot's starter list, full stop.
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

# Habit.category -> the one building type it powers. A check-in always
# advances exactly one building, the one its habit's category maps to here
# - Custom Module is no exception, it's just whatever "other" (everything
# not in the five named categories) adds up to.
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
# Same thresholds apply to every building, Custom Module included, against
# its own category's count (see level_for_checkins). Max level (3) is
# len(LEVEL_THRESHOLDS) - still a guess pending real art, same reasoning
# as before: the sprite manifest has exactly one generic icon per
# building type, no per-level variants to derive a cap from.
LEVEL_THRESHOLDS = (10, 30, 60)
MAX_LEVEL = len(LEVEL_THRESHOLDS)

DAILY_ENERGY_CAP = 100


def level_for_checkins(count: int) -> int:
    """0 (not built yet) through MAX_LEVEL, from a lifetime check-in
    count - the same `count` means the same level regardless of which
    building/category it's for. `count` is always that ONE category's own
    check-in count (see colony._building_tile_context) - Custom Module's
    is "other", never a total across every category."""
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


# -- commander rank & class (Phase 4b) ---------------------------------------

# (name, xp threshold), ascending - same `earned_points` metric
# colony_level() uses. Mirrors LEVEL_THRESHOLDS/level_for_checkins'
# shape: a simple ascending-threshold lookup, no DB access.
RANK_THRESHOLDS = (
    ("Cadet", 0),
    ("Pilot", 150),
    ("Captain", 500),
    ("Commander", 1200),
    ("Admiral", 3000),
)


def rank_for_xp(xp: int) -> str:
    """The highest rank whose threshold `xp` meets or exceeds. Thresholds
    start at 0, so this always returns a rank, never None."""
    rank = RANK_THRESHOLDS[0][0]
    for name, threshold in RANK_THRESHOLDS:
        if xp >= threshold:
            rank = name
    return rank


# Habit.category -> class name, for the 5 categories with one (every
# category except "other" - Custom Module has no matching commander
# class, same way it has no matching real-world building analog).
CLASS_FOR_CATEGORY = {
    "fitness": "Guardian",
    "study": "Scientist",
    "sleep": "Engineer",
    "water_food": "Botanist",
    "mind": "Explorer",
}


def class_for_category_counts(category_counts: dict) -> str | None:
    """DERIVED on read from the user's strongest classed category by
    lifetime check-in count - never stored, same discipline as building
    levels (see colony._category_checkin_counts, which already produces
    exactly the dict this expects). None if every classed category is at
    0 (a brand-new user, or one who has only ever logged "other" habits).
    Ties go to whichever category is declared first in CLASS_FOR_CATEGORY
    - deterministic, not count-order-dependent."""
    best_category, best_count = None, 0
    for category in CLASS_FOR_CATEGORY:
        count = category_counts.get(category, 0)
        if count > best_count:
            best_category, best_count = category, count
    return CLASS_FOR_CATEGORY[best_category] if best_category else None


# -- commander avatar & planet look (Phase 4b, starter-only) ----------------

# Every slot's starter values, in display order - index 0 of each tuple
# is that slot's default (what Skip/a fresh signup equips). "none" marks
# the absence of that layer (e.g. no visor, bare head) - there's no
# avatar_visor_none.png to draw, the layer is simply omitted.
AVATAR_SLOTS = ("helmet", "visor", "face", "hair", "suit", "gear", "emblem")
AVATAR_STARTER_VALUES = {
    "helmet": ("round", "box"),
    "visor": ("open", "amber", "steel", "rust"),
    "face": ("1", "2", "3", "4", "5"),
    "hair": ("none", "dark", "brown", "silver"),
    "suit": ("phosphor",),
    "gear": ("none", "antenna"),
    "emblem": ("none", "star", "bolt"),
}
DEFAULT_AVATAR = {slot: values[0] for slot, values in AVATAR_STARTER_VALUES.items()}

LOOK_SLOTS = ("world", "atmosphere", "ring", "moons")
LOOK_STARTER_VALUES = {
    "world": ("rust", "dust", "verdant"),
    "atmosphere": ("steel",),
    "ring": ("none",),
    "moons": ("none", "one"),
}
DEFAULT_LOOK = {slot: values[0] for slot, values in LOOK_STARTER_VALUES.items()}


def _validate_slot_payload(payload, slots: tuple, starter_values: dict) -> tuple[bool, str | None]:
    """Shared shape for validate_avatar_payload/validate_look_payload:
    every slot must be present exactly once, with a value from that
    slot's starter list - no shop, no owned_items, nothing ownable yet
    in Phase 4b, so "locked/bought/earned-only" and "invalid" are the
    same rejection. Returns (ok, failing_slot) - failing_slot is an
    unknown/extra key's own name when the key set itself is wrong, so a
    caller can report exactly what was wrong."""
    if not isinstance(payload, dict):
        return False, None
    extra = set(payload) - set(slots)
    if extra:
        return False, min(extra)
    missing = set(slots) - set(payload)
    if missing:
        return False, min(missing)
    for slot in slots:
        value = payload[slot]
        if not isinstance(value, str) or value not in starter_values[slot]:
            return False, slot
    return True, None


def validate_avatar_payload(payload) -> tuple[bool, str | None]:
    return _validate_slot_payload(payload, AVATAR_SLOTS, AVATAR_STARTER_VALUES)


def validate_look_payload(payload) -> tuple[bool, str | None]:
    return _validate_slot_payload(payload, LOOK_SLOTS, LOOK_STARTER_VALUES)
