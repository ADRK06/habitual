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
