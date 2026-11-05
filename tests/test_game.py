import pytest

from habitual import game


# -- derived building level (10/30/60 check-ins -> LV1/LV2/LV3) --------------

LEVEL_CASES = [
    (0, 0),
    (9, 0),
    (10, 1),
    (29, 1),
    (30, 2),
    (59, 2),
    (60, 3),
    (1000, 3),  # stays at MAX_LEVEL, never climbs past it
]


@pytest.mark.parametrize("count, expected_level", LEVEL_CASES)
def test_level_for_checkins(count, expected_level):
    assert game.level_for_checkins(count) == expected_level


NEXT_THRESHOLD_CASES = [
    (0, 10),
    (9, 10),
    (10, 30),
    (29, 30),
    (30, 60),
    (59, 60),
    (60, None),  # already at MAX_LEVEL - nothing left to progress toward
    (1000, None),
]


@pytest.mark.parametrize("count, expected", NEXT_THRESHOLD_CASES)
def test_next_threshold(count, expected):
    assert game.next_threshold(count) == expected


def test_max_level_equals_number_of_thresholds():
    assert game.MAX_LEVEL == len(game.LEVEL_THRESHOLDS) == 3


# -- colony level (1 + floor(sqrt(xp/25))) ------------------------------------

COLONY_LEVEL_CASES = [
    (0, 1),
    (24, 1),
    (25, 2),
    (99, 2),
    (100, 3),
    (399, 4),
    (400, 5),
    (2024, 9),
    (2025, 10),
]


@pytest.mark.parametrize("xp, expected_level", COLONY_LEVEL_CASES)
def test_colony_level(xp, expected_level):
    assert game.colony_level(xp) == expected_level


# -- daily Energy cap (partial top-up, min 0) ---------------------------------


def test_energy_awarded_with_cap_partial_top_up():
    assert game.energy_awarded_with_cap(already_earned_today=98, amount=5) == 2


def test_energy_awarded_with_cap_exactly_at_cap_awards_zero():
    assert game.energy_awarded_with_cap(already_earned_today=100, amount=5) == 0


def test_energy_awarded_with_cap_past_cap_awards_zero():
    assert game.energy_awarded_with_cap(already_earned_today=140, amount=5) == 0


def test_energy_awarded_with_cap_exact_fill_awards_full_amount():
    assert game.energy_awarded_with_cap(already_earned_today=95, amount=5) == 5


def test_energy_awarded_with_cap_well_under_cap_awards_full_amount():
    assert game.energy_awarded_with_cap(already_earned_today=0, amount=5) == 5


# -- commander rank (XP-derived, same metric colony_level() uses) -----------

RANK_CASES = [
    (0, "Cadet"),
    (149, "Cadet"),
    (150, "Pilot"),
    (499, "Pilot"),
    (500, "Captain"),
    (1199, "Captain"),
    (1200, "Commander"),
    (2999, "Commander"),
    (3000, "Admiral"),
    (50000, "Admiral"),
]


@pytest.mark.parametrize("xp, expected_rank", RANK_CASES)
def test_rank_for_xp(xp, expected_rank):
    assert game.rank_for_xp(xp) == expected_rank


# -- commander class (derived on read from strongest classed category) -----


def test_class_for_category_counts_empty_dict_has_no_class():
    assert game.class_for_category_counts({}) is None


def test_class_for_category_counts_single_classed_category():
    assert game.class_for_category_counts({"fitness": 10}) == "Guardian"


def test_class_for_category_counts_strongest_category_wins():
    counts = {"fitness": 5, "study": 20, "sleep": 3}
    assert game.class_for_category_counts(counts) == "Scientist"


def test_class_for_category_counts_tie_goes_to_first_declared():
    # fitness and study tied at 10 - CLASS_FOR_CATEGORY declares fitness first.
    assert game.class_for_category_counts({"fitness": 10, "study": 10}) == "Guardian"


def test_class_for_category_counts_other_only_has_no_class():
    # "other" has no matching class (same reasoning Custom Module has no
    # real-world building analog) - counts there never produce a class.
    assert game.class_for_category_counts({"other": 50}) is None


# -- avatar/look starter-only validation (Phase 4b) --------------------------


def test_default_avatar_is_valid():
    # Skip's own default must always pass its own validator.
    assert game.validate_avatar_payload(game.DEFAULT_AVATAR) == (True, None)


def test_default_look_is_valid():
    assert game.validate_look_payload(game.DEFAULT_LOOK) == (True, None)


def test_valid_avatar_payload_with_every_slot_set():
    payload = {"helmet": "box", "visor": "rust", "face": "3", "hair": "silver",
               "suit": "phosphor", "gear": "antenna", "emblem": "bolt"}
    assert game.validate_avatar_payload(payload) == (True, None)


def test_avatar_payload_missing_a_slot_is_rejected():
    payload = dict(game.DEFAULT_AVATAR)
    del payload["emblem"]
    assert game.validate_avatar_payload(payload) == (False, "emblem")


def test_avatar_payload_with_unknown_slot_is_rejected():
    payload = dict(game.DEFAULT_AVATAR)
    payload["wings"] = "none"
    assert game.validate_avatar_payload(payload) == (False, "wings")


def test_avatar_payload_with_non_string_value_is_rejected():
    payload = dict(game.DEFAULT_AVATAR)
    payload["face"] = 3
    assert game.validate_avatar_payload(payload) == (False, "face")


def test_avatar_payload_with_locked_value_is_rejected():
    # "steel" suit is real (bought, 150 Energy) but not a starter value -
    # nothing is ownable yet in Phase 4b, so locked == invalid.
    payload = dict(game.DEFAULT_AVATAR)
    payload["suit"] = "steel"
    assert game.validate_avatar_payload(payload) == (False, "suit")


def test_avatar_payload_with_bogus_value_is_rejected():
    payload = dict(game.DEFAULT_AVATAR)
    payload["helmet"] = "xyz"
    assert game.validate_avatar_payload(payload) == (False, "helmet")


def test_avatar_payload_non_dict_is_rejected():
    assert game.validate_avatar_payload("not a dict") == (False, None)


def test_valid_look_payload_with_every_slot_set():
    payload = {"world": "verdant", "atmosphere": "steel", "ring": "none", "moons": "one"}
    assert game.validate_look_payload(payload) == (True, None)


def test_look_payload_missing_a_slot_is_rejected():
    payload = dict(game.DEFAULT_LOOK)
    del payload["moons"]
    assert game.validate_look_payload(payload) == (False, "moons")


def test_look_payload_with_unknown_slot_is_rejected():
    payload = dict(game.DEFAULT_LOOK)
    payload["layout"] = "default"
    assert game.validate_look_payload(payload) == (False, "layout")


def test_look_payload_with_locked_world_is_rejected():
    # "lava" world is real (bought, 400 Energy) but not a starter value.
    payload = dict(game.DEFAULT_LOOK)
    payload["world"] = "lava"
    assert game.validate_look_payload(payload) == (False, "world")


def test_look_payload_with_bogus_moons_value_is_rejected():
    payload = dict(game.DEFAULT_LOOK)
    payload["moons"] = "two"
    assert game.validate_look_payload(payload) == (False, "moons")
