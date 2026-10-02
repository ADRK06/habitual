from datetime import date, time, timedelta

from habitual.points import (
    balance,
    can_purchase_freeze,
    crown_winner,
    current_streak,
    earned_points,
    freeze_available,
    has_valid_proof_for_crown,
    longest_streak,
    milestone_bonus,
    milestone_label,
    missed_days,
    next_milestone,
    points_for_date,
    points_for_day,
    room_streak,
    streak_day_on,
    streak_length_through,
    success_rate,
)

D0 = date(2026, 1, 1)


def days(*offsets):
    return {D0 + timedelta(days=o) for o in offsets}


# --- milestones ---------------------------------------------------------


def test_normal_day_is_base_points():
    assert points_for_day(1) == 5
    assert points_for_day(6) == 5


def test_milestone_days_7_14_30_60_90():
    assert points_for_day(7) == 15
    assert points_for_day(14) == 25
    assert points_for_day(30) == 35
    assert points_for_day(60) == 35
    assert points_for_day(90) == 35


def test_milestone_bonus_only_on_exact_days():
    assert milestone_bonus(8) == 0
    assert milestone_bonus(29) == 0
    assert milestone_bonus(31) == 0


def test_milestone_label_matches_milestone_days():
    assert milestone_label(7) == "Week streak bonus!"
    assert milestone_label(14) == "Two-week streak bonus!"
    assert milestone_label(30) == "Milestone bonus!"
    assert milestone_label(60) == "Milestone bonus!"
    assert milestone_label(1) is None
    assert milestone_label(8) is None


def test_milestones_restart_after_a_break():
    # 7-day streak, miss a day unfrozen, build a fresh 7-day streak
    completed = days(*range(0, 7)) | days(*range(8, 15))
    frozen = set()
    today = D0 + timedelta(days=14)
    # day 14 overall, but only the 7th day of the *current* streak
    assert streak_day_on(completed, frozen, today) == 7
    assert points_for_date(completed, frozen, today) == 15


def test_next_milestone_targets():
    assert next_milestone(0) == 7
    assert next_milestone(6) == 7
    assert next_milestone(7) == 7
    assert next_milestone(13) == 14
    assert next_milestone(14) == 14
    assert next_milestone(29) == 30
    assert next_milestone(30) == 30
    assert next_milestone(31) == 60
    assert next_milestone(59) == 60
    assert next_milestone(60) == 60


# --- current streak ------------------------------------------------------


def test_current_streak_counts_consecutive_completed_days():
    completed = days(0, 1, 2)
    today = D0 + timedelta(days=2)
    assert current_streak(completed, set(), today) == 3


def test_current_streak_shows_yesterdays_count_until_today_checked_in():
    completed = days(0, 1, 2)
    today = D0 + timedelta(days=3)  # day 3 not checked in yet
    assert current_streak(completed, set(), today) == 3


def test_current_streak_resets_on_unfrozen_miss():
    completed = days(0, 1, 2)
    today = D0 + timedelta(days=4)  # day 3 missed, no freeze, now it's day 4
    assert current_streak(completed, set(), today) == 0


def test_freeze_bridges_without_adding_to_count():
    # days 0,1,2 completed, day 3 frozen (missed but saved), day 4 completed
    completed = days(0, 1, 2, 4)
    frozen = days(3)
    today = D0 + timedelta(days=4)
    assert current_streak(completed, frozen, today) == 4


# --- longest streak --------------------------------------------------------


def test_longest_streak_survives_a_later_shorter_run():
    completed = days(*range(0, 6)) | days(*range(7, 10))
    today = D0 + timedelta(days=9)
    assert longest_streak(completed, set(), D0, today) == 6


def test_longest_streak_counts_frozen_bridge():
    completed = days(0, 1, 2, 4, 5)
    frozen = days(3)
    today = D0 + timedelta(days=5)
    assert longest_streak(completed, frozen, D0, today) == 5


# --- streak_length_through (freeze_saver badge) -----------------------


def test_streak_length_through_counts_whole_bridged_chain():
    # days 0,1,2 completed, day 3 frozen, days 4,5,6 completed -> chain of 6
    completed = days(0, 1, 2, 4, 5, 6)
    frozen = days(3)
    assert streak_length_through(completed, frozen, D0 + timedelta(days=3)) == 6


def test_streak_length_through_zero_for_unrelated_date():
    completed = days(0, 1, 2)
    assert streak_length_through(completed, set(), D0 + timedelta(days=10)) == 0


def test_streak_length_through_stops_at_a_real_gap():
    # frozen day 3 bridges to day 4, but day 5 is a genuine miss - the chain
    # (and the count) stops there, not at the end of `completed`.
    completed = days(0, 1, 2, 4, 6)
    frozen = days(3)
    assert streak_length_through(completed, frozen, D0 + timedelta(days=3)) == 4


# --- success rate ------------------------------------------------------


def test_success_rate_basic():
    completed = days(0, 1)
    today = D0 + timedelta(days=1)
    assert success_rate(completed, D0, today) == 100.0


def test_success_rate_excludes_today_if_not_done_yet():
    completed = days(0)  # only day 0 done
    today = D0 + timedelta(days=1)  # day 1 (today) not completed
    # denominator is just day 0 (1 day elapsed), not 2 — today doesn't count
    # against the user until it's actually over/completed
    assert success_rate(completed, D0, today) == 100.0


def test_success_rate_zero_on_creation_day_before_checkin():
    assert success_rate(set(), D0, D0) == 0.0


def test_success_rate_with_a_miss():
    completed = days(0, 2)  # day 1 missed
    today = D0 + timedelta(days=2)
    assert success_rate(completed, D0, today) == (2 / 3) * 100


# --- freezes ------------------------------------------------------


def test_freeze_available_when_yesterday_missed_with_active_streak():
    completed = days(0, 1, 2)  # days 0-2 done, day 3 (yesterday) missed
    today = D0 + timedelta(days=4)
    assert freeze_available(completed, set(), today) is True


def test_freeze_not_available_if_yesterday_already_done():
    completed = days(0, 1, 2, 3)
    today = D0 + timedelta(days=4)
    assert freeze_available(completed, set(), today) is False


def test_freeze_not_available_without_a_prior_streak():
    today = D0 + timedelta(days=1)  # yesterday missed, but no streak existed
    assert freeze_available(set(), set(), today) is False


def test_freeze_not_available_if_yesterday_already_frozen():
    completed = days(0)
    frozen = days(1)
    today = D0 + timedelta(days=2)
    assert freeze_available(completed, frozen, today) is False


def test_can_purchase_freeze_respects_cost_and_cap():
    assert can_purchase_freeze(balance=50, unused_freeze_count=0) is True
    assert can_purchase_freeze(balance=49, unused_freeze_count=0) is False
    assert can_purchase_freeze(balance=100, unused_freeze_count=2) is False


# --- ledger sums ------------------------------------------------------


def test_earned_points_ignores_spends():
    assert earned_points([5, 10, -50, 5]) == 20


def test_balance_nets_earned_and_spent():
    assert balance([5, 10, -50, 5]) == -30


# --- order independence (freeze before vs. after a check-in) --------------


def _simulate_ledger(actions):
    """Mimics what the checkin/freeze routes will do: after every action,
    reprice every completed date from the *current* full state. Returns the
    final {date: points} ledger."""
    completed, frozen = set(), set()
    for kind, d in actions:
        if kind == "checkin":
            completed.add(d)
        else:
            frozen.add(d)
    return {d: points_for_date(completed, frozen, d) for d in completed}


def test_checkin_then_freeze_matches_freeze_then_checkin():
    # 6-day streak (days 0-5), day 6 missed, today is day 7.
    base = [("checkin", D0 + timedelta(days=i)) for i in range(6)]
    yesterday = D0 + timedelta(days=6)
    today = D0 + timedelta(days=7)

    checkin_then_freeze = base + [("checkin", today), ("freeze", yesterday)]
    freeze_then_checkin = base + [("freeze", yesterday), ("checkin", today)]

    ledger_a = _simulate_ledger(checkin_then_freeze)
    ledger_b = _simulate_ledger(freeze_then_checkin)

    assert ledger_a == ledger_b
    # the freeze bridges day 6, so "today" is really streak day 7 -> milestone
    assert ledger_a[today] == 15
    assert sum(ledger_a.values()) == sum(ledger_b.values())


# --- crown eligibility ---------------------------------------------------


def test_crown_requires_at_least_3_non_whitespace_chars():
    assert has_valid_proof_for_crown("gym") is True
    assert has_valid_proof_for_crown("gy") is False
    assert has_valid_proof_for_crown("  ") is False
    assert has_valid_proof_for_crown("") is False
    assert has_valid_proof_for_crown(None) is False


def test_crown_counts_non_whitespace_chars_not_total_length():
    # "a  b" has 4 chars but only 2 non-whitespace ones - not enough.
    assert has_valid_proof_for_crown("a  b") is False
    assert has_valid_proof_for_crown("a b c") is True  # 3 non-whitespace chars


# --- crown winner (timezone-fair) -----------------------------------------


def test_crown_winner_picks_earliest_local_clock_time():
    # An IST member checking in at 9am local is NOT "earlier" than an
    # EST member checking in at 7am local just because IST is ahead of UTC -
    # the earlier *local* time wins.
    ist_9am = (time(9, 0), "2026-01-01T03:30:00+00:00", "ist_user", 1, 10)
    est_7am = (time(7, 0), "2026-01-01T12:00:00+00:00", "est_user", 2, 20)
    assert crown_winner([ist_9am, est_7am]) == est_7am


def test_crown_winner_ties_break_on_real_utc_timestamp():
    same_local_time_earlier_utc = (time(8, 0), "2026-01-01T03:00:00+00:00", "a", 1, 10)
    same_local_time_later_utc = (time(8, 0), "2026-01-01T03:05:00+00:00", "b", 2, 20)
    winner = crown_winner([same_local_time_later_utc, same_local_time_earlier_utc])
    assert winner == same_local_time_earlier_utc


def test_crown_winner_empty_candidates_is_none():
    assert crown_winner([]) is None


# --- room streak (per-member local dates) ----------------------------------


def test_room_streak_requires_every_joined_member_on_each_day():
    members = [
        {"completed": days(0, 1, 2), "joined_on": D0},
        {"completed": days(0, 1), "joined_on": D0},  # missed day 2
    ]
    today_anchor = D0 + timedelta(days=2)
    assert room_streak(members, today_anchor) == 2  # days 0,1 only


def test_room_streak_ignores_days_before_a_member_joined():
    members = [
        {"completed": days(0, 1, 2), "joined_on": D0},
        {"completed": days(2), "joined_on": D0 + timedelta(days=2)},  # joined late
    ]
    today_anchor = D0 + timedelta(days=2)
    # Day 2 only needs the late joiner (who did complete it) plus the
    # original member (also completed) - streak isn't held back by days
    # before the second member even existed.
    assert room_streak(members, today_anchor) == 3


def test_room_streak_freezes_do_not_bridge_a_gap():
    # Unlike a solo habit's streak, a frozen day still breaks a room streak.
    members = [{"completed": days(0, 2), "joined_on": D0}]
    today_anchor = D0 + timedelta(days=2)
    assert room_streak(members, today_anchor) == 1  # only day 2, day 1 broke it


def test_room_streak_grace_period_before_todays_anchor_is_done():
    members = [
        {"completed": days(0, 1), "joined_on": D0},
        {"completed": days(0), "joined_on": D0},  # hasn't done "today" yet
    ]
    today_anchor = D0 + timedelta(days=1)
    assert room_streak(members, today_anchor) == 1  # falls back to yesterday's count


# --- missed days (leaderboard tiebreaker) -----------------------------------


def test_missed_days_counts_unfrozen_gaps_before_today():
    completed = days(0, 2)  # day 1 missed
    today = D0 + timedelta(days=3)
    assert missed_days(completed, set(), D0, today) == 1


def test_missed_days_excludes_today_even_if_not_done_yet():
    completed = days(0)
    today = D0 + timedelta(days=1)  # day 1 (today) not completed
    assert missed_days(completed, set(), D0, today) == 0


def test_missed_days_frozen_gap_does_not_count_as_missed():
    completed = days(0, 2)
    frozen = days(1)
    today = D0 + timedelta(days=3)
    assert missed_days(completed, frozen, D0, today) == 0
