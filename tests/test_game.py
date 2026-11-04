import pytest

from habitual import game


# -- building costs (decision 1: cost(L) = base + step*(L-1)) --------------

BUILDING_COST_CASES = [
    (game.DEFENSE_TOWER, 1, 120),
    (game.DEFENSE_TOWER, 2, 180),
    (game.DEFENSE_TOWER, 3, 240),
    (game.RESEARCH_LAB, 1, 100),
    (game.RESEARCH_LAB, 2, 150),
    (game.RESEARCH_LAB, 3, 200),
    (game.POWER_REACTOR, 1, 150),
    (game.POWER_REACTOR, 2, 225),
    (game.POWER_REACTOR, 3, 300),
    (game.BIODOME, 1, 100),
    (game.BIODOME, 2, 150),
    (game.BIODOME, 3, 200),
    (game.OBSERVATORY, 1, 140),
    (game.OBSERVATORY, 2, 210),
    (game.OBSERVATORY, 3, 280),
    (game.CUSTOM_MODULE, 1, 80),
    (game.CUSTOM_MODULE, 2, 120),
    (game.CUSTOM_MODULE, 3, 160),
]


@pytest.mark.parametrize("building_type, level, expected_cost", BUILDING_COST_CASES)
def test_next_level_cost(building_type, level, expected_cost):
    assert game.next_level_cost(building_type, level) == expected_cost


def test_every_building_type_has_a_cost_and_a_build_time():
    for building_type in game.BUILDING_TYPES:
        assert game.next_level_cost(building_type, 1) > 0
        assert game.build_time_hours(building_type) > 0


BUILD_TIME_CASES = [
    (game.DEFENSE_TOWER, 4),
    (game.RESEARCH_LAB, 6),
    (game.POWER_REACTOR, 3),
    (game.BIODOME, 2),
    (game.OBSERVATORY, 5),
    (game.CUSTOM_MODULE, 1),
]


@pytest.mark.parametrize("building_type, expected_hours", BUILD_TIME_CASES)
def test_build_time_hours(building_type, expected_hours):
    assert game.build_time_hours(building_type) == expected_hours


# -- unlock rule -------------------------------------------------------------


def test_category_building_locked_below_ten_category_checkins():
    assert game.is_unlocked(game.DEFENSE_TOWER, category_checkin_count=9, total_checkin_count=50) is False


def test_category_building_unlocks_at_exactly_ten_category_checkins():
    assert game.is_unlocked(game.DEFENSE_TOWER, category_checkin_count=10, total_checkin_count=10) is True


def test_category_building_stays_unlocked_above_ten():
    assert game.is_unlocked(game.DEFENSE_TOWER, category_checkin_count=11, total_checkin_count=11) is True


def test_custom_module_ignores_category_count_uses_total():
    # 0 "other"-category check-ins, but 10 total across any categories.
    assert game.is_unlocked(game.CUSTOM_MODULE, category_checkin_count=0, total_checkin_count=10) is True


def test_custom_module_locked_below_ten_total_even_with_category_checkins():
    # category_checkin_count is irrelevant to Custom Module - only the total matters.
    assert game.is_unlocked(game.CUSTOM_MODULE, category_checkin_count=10, total_checkin_count=9) is False


# -- max level ----------------------------------------------------------------


def test_is_max_level_false_below_max():
    assert game.is_max_level(game.DEFENSE_TOWER, 2) is False


def test_is_max_level_true_at_max():
    assert game.is_max_level(game.DEFENSE_TOWER, game.MAX_LEVEL) is True


def test_is_max_level_true_above_max():
    assert game.is_max_level(game.DEFENSE_TOWER, game.MAX_LEVEL + 1) is True


def test_default_slot_is_stable_and_unique_per_building():
    slots = [game.default_slot(t) for t in game.BUILDING_TYPES]
    assert slots == list(range(len(game.BUILDING_TYPES)))


# -- colony level (decision 3: 1 + floor(sqrt(xp/25))) ------------------------

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


# -- daily Energy cap (decision 6: partial top-up, min 0) ---------------------


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
