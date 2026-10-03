from datetime import date, time, timedelta

import pytest

from habitual.points import (
    balance,
    can_purchase_freeze,
    crown_winner,
    current_streak,
    earned_points,
    freeze_available,
    freeze_target_date,
    has_valid_proof_for_crown,
    longest_streak,
    longest_weekly_streak,
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
    week_start,
    weekly_completions,
    weekly_freeze_available,
    weekly_freeze_target_week,
    weekly_milestone_bonus_for_checkin,
    weekly_missed_weeks,
    weekly_room_streak,
    weekly_streak,
    weekly_success_rate,
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


# --- freeze_target_date: Specific-Days schedule-aware window --------------

MON = date(2026, 1, 5)  # a Monday
TUE = MON + timedelta(days=1)
WED = MON + timedelta(days=2)
THU = MON + timedelta(days=3)
FRI = MON + timedelta(days=4)
SAT = MON + timedelta(days=5)


def test_freeze_target_date_specific_days_offered_the_day_after_a_miss():
    # Mon/Wed/Fri: Monday done, Wednesday missed, checking in on Thursday.
    completed = {MON}
    schedule = (WED, FRI)  # (missed_candidate, window_end)
    assert freeze_target_date(completed, set(), THU, schedule) == WED


def test_freeze_target_date_specific_days_still_offered_on_window_end_regardless_of_checkin():
    # Friday (window_end) already checked in - freeze for Wed must still be
    # offered (order-independent, same as Daily never caring what "today"
    # itself looks like).
    completed = {MON, FRI}
    schedule = (WED, FRI)
    assert freeze_target_date(completed, set(), FRI, schedule) == WED


def test_freeze_target_date_specific_days_window_closes_after_window_end():
    completed = {MON, FRI}
    schedule = (WED, FRI)
    assert freeze_target_date(completed, set(), SAT, schedule) is None


def test_freeze_target_date_specific_days_none_if_missed_day_already_frozen():
    completed = {MON}
    frozen = {WED}
    schedule = (WED, FRI)
    assert freeze_target_date(completed, frozen, THU, schedule) is None


def test_freeze_target_date_specific_days_requires_a_prior_streak():
    schedule = (WED, FRI)
    assert freeze_target_date(set(), set(), THU, schedule) is None


# --- success_rate with a `not_scheduled` set (Specific Days) ----------------


def test_success_rate_not_scheduled_ignores_non_scheduled_gaps():
    # Mon/Wed scheduled only - Tuesday being incomplete (it's never due)
    # shouldn't drag the rate down.
    not_scheduled = {TUE}
    completed = {MON, WED}
    assert success_rate(completed, MON, WED, not_scheduled) == 100.0


def test_success_rate_not_scheduled_missed_scheduled_day_lowers_rate():
    not_scheduled = {TUE, THU}  # Mon/Wed/Fri schedule
    completed = {MON, FRI}  # Wed missed
    assert success_rate(completed, MON, FRI, not_scheduled) == pytest.approx(66.66666666666667)


def test_success_rate_not_scheduled_defaults_to_all_days_behavior():
    completed = {MON, WED}
    assert success_rate(completed, MON, WED) == success_rate(completed, MON, WED, set())


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


def test_weekly_room_streak_requires_every_joined_member_to_hit_target_each_week():
    target = 2
    members = [
        {"completed": {WEEK0, WEEK0 + timedelta(days=1), WEEK1, WEEK1 + timedelta(days=1)}, "joined_on": WEEK0},
        {"completed": {WEEK0, WEEK0 + timedelta(days=1)}, "joined_on": WEEK0},  # misses week1's target
    ]
    today_anchor = WEEK1 + timedelta(days=3)
    assert weekly_room_streak(members, target, today_anchor) == 1  # week0 only


def test_weekly_room_streak_ignores_weeks_before_a_member_joined():
    target = 1
    members = [
        {"completed": {WEEK0, WEEK1}, "joined_on": WEEK0},
        {"completed": {WEEK1}, "joined_on": WEEK1},  # joined in week1, week0 isn't held against them
    ]
    today_anchor = WEEK1 + timedelta(days=2)
    assert weekly_room_streak(members, target, today_anchor) == 2


def test_weekly_room_streak_grace_period_before_this_weeks_anchor_is_decided():
    target = 1
    members = [
        {"completed": {WEEK0}, "joined_on": WEEK0},  # this week not hit yet
    ]
    today_anchor = WEEK1 + timedelta(days=1)
    assert weekly_room_streak(members, target, today_anchor) == 1  # falls back to last week


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


def test_weekly_missed_weeks_counts_weeks_under_target_excluding_the_current_one():
    target = 2
    completed = {WEEK0, WEEK0 + timedelta(days=1)}  # week0 hit, week1 (current) not yet
    today = WEEK1 + timedelta(days=2)
    assert weekly_missed_weeks(completed, target, WEEK0, today) == 0


def test_weekly_missed_weeks_counts_a_fully_elapsed_short_week():
    target = 2
    completed = {WEEK0}  # only 1 completion in week0 - misses target
    today = WEEK1 + timedelta(days=2)
    assert weekly_missed_weeks(completed, target, WEEK0, today) == 1


# --- weekly frequency (X times/week) -------------------------------------

WEEK0 = MON  # 2026-01-05, a Monday
WEEK1 = WEEK0 + timedelta(days=7)
WEEK2 = WEEK0 + timedelta(days=14)
WEEK3 = WEEK0 + timedelta(days=21)


def test_week_start_returns_the_monday():
    assert week_start(WEEK0 + timedelta(days=3)) == WEEK0
    assert week_start(WEEK0) == WEEK0


def test_weekly_completions_buckets_by_week():
    completed = {WEEK0, WEEK0 + timedelta(days=1), WEEK1 + timedelta(days=2)}
    assert weekly_completions(completed) == {WEEK0: 2, WEEK1: 1}


def test_weekly_streak_counts_consecutive_weeks_hitting_target():
    target = 3
    completed = {
        WEEK0, WEEK0 + timedelta(days=1), WEEK0 + timedelta(days=2),
        WEEK1, WEEK1 + timedelta(days=1), WEEK1 + timedelta(days=2),
        WEEK2, WEEK2 + timedelta(days=1), WEEK2 + timedelta(days=2),
    }
    today = WEEK2 + timedelta(days=2)  # Wednesday of week 2, already at target
    assert weekly_streak(completed, target, today) == 3


def test_weekly_streak_gives_grace_for_an_in_progress_week():
    target = 3
    completed = {
        WEEK0, WEEK0 + timedelta(days=1), WEEK0 + timedelta(days=2),
        WEEK1, WEEK1 + timedelta(days=1), WEEK1 + timedelta(days=2),
        WEEK2, WEEK2 + timedelta(days=1),  # only 2 so far this week
    }
    today = WEEK2 + timedelta(days=3)  # Thursday - week 2 hasn't hit target yet
    assert weekly_streak(completed, target, today) == 2


def test_weekly_streak_breaks_on_a_missed_week():
    target = 2
    completed = {WEEK0, WEEK0 + timedelta(days=1), WEEK2, WEEK2 + timedelta(days=1)}
    today = WEEK2 + timedelta(days=3)
    assert weekly_streak(completed, target, today) == 1  # week1 missed entirely


def test_weekly_streak_frozen_week_bridges_the_chain():
    target = 2
    completed = {WEEK0, WEEK0 + timedelta(days=1), WEEK2, WEEK2 + timedelta(days=1)}
    today = WEEK2 + timedelta(days=3)
    assert weekly_streak(completed, target, today, frozen_weeks={WEEK1}) == 3


def test_longest_weekly_streak_finds_the_best_run_even_after_a_break():
    target = 2
    completed = {
        WEEK0, WEEK0 + timedelta(days=1),
        WEEK1, WEEK1 + timedelta(days=1),
        WEEK3, WEEK3 + timedelta(days=1),
    }  # week2 missed, breaking the chain before a fresh 1-week run
    today = WEEK3 + timedelta(days=2)
    assert longest_weekly_streak(completed, target, WEEK0, today) == 2
    assert weekly_streak(completed, target, today) == 1


def test_longest_weekly_streak_frozen_week_counts_toward_the_best_run():
    target = 2
    completed = {
        WEEK0, WEEK0 + timedelta(days=1),
        WEEK2, WEEK2 + timedelta(days=1),
    }
    today = WEEK2 + timedelta(days=2)
    assert longest_weekly_streak(completed, target, WEEK0, today, frozen_weeks={WEEK1}) == 3


def test_weekly_success_rate_basic():
    # 2 weeks elapsed, target 3/week, 4 completions total -> 4/6 = 66.67%
    completed = {WEEK0, WEEK0 + timedelta(days=1), WEEK1, WEEK1 + timedelta(days=1)}
    today = WEEK1 + timedelta(days=3)
    assert weekly_success_rate(completed, WEEK0, today, 3) == pytest.approx(200 / 3)


def test_weekly_success_rate_current_week_counts_fully_even_if_just_started():
    completed = set()
    today = WEEK0  # Monday, the very first day
    assert weekly_success_rate(completed, WEEK0, today, 3) == 0.0


def test_weekly_freeze_target_week_offered_when_last_week_missed_with_active_streak():
    target = 2
    completed = {WEEK0, WEEK0 + timedelta(days=1)}  # week0 hit target, week1 missed
    today = WEEK2  # first day of week 2
    assert weekly_freeze_target_week(completed, target, today) == WEEK1
    assert weekly_freeze_available(completed, target, today) is True


def test_weekly_freeze_target_week_still_offered_even_if_this_week_already_hit():
    target = 2
    completed = {
        WEEK0, WEEK0 + timedelta(days=1),  # week0 hit
        WEEK2, WEEK2 + timedelta(days=1),  # week2 (this week) already hit too
    }
    today = WEEK2 + timedelta(days=2)
    # order-independence, one granularity up from the daily freeze: whether
    # this week is already done doesn't change whether last week's miss is
    # still coverable.
    assert weekly_freeze_target_week(completed, target, today) == WEEK1


def test_weekly_freeze_target_week_none_without_a_prior_streak():
    target = 2
    completed = set()  # week1 missed, but there was no streak going into it
    today = WEEK2
    assert weekly_freeze_target_week(completed, target, today) is None


def test_weekly_freeze_target_week_none_if_last_week_already_frozen():
    target = 2
    completed = {WEEK0, WEEK0 + timedelta(days=1)}
    today = WEEK2
    assert weekly_freeze_target_week(completed, target, today, frozen_weeks={WEEK1}) is None


def test_weekly_milestone_bonus_only_fires_on_the_target_reaching_checkin():
    target = 3
    week_completions = [WEEK0, WEEK0 + timedelta(days=2), WEEK0 + timedelta(days=4)]
    completed = set(week_completions)
    assert weekly_milestone_bonus_for_checkin(completed, target, week_completions[0]) == 0
    assert weekly_milestone_bonus_for_checkin(completed, target, week_completions[1]) == 0
    assert weekly_milestone_bonus_for_checkin(completed, target, week_completions[2]) == milestone_bonus(1)


def test_weekly_milestone_bonus_checkins_beyond_target_earn_no_bonus():
    target = 2
    completed = {WEEK0, WEEK0 + timedelta(days=2), WEEK0 + timedelta(days=4)}
    extra = WEEK0 + timedelta(days=4)
    assert weekly_milestone_bonus_for_checkin(completed, target, extra) == 0


def test_weekly_milestone_bonus_reprices_identically_regardless_of_freeze_order():
    # Mirrors test_checkin_then_freeze_matches_freeze_then_checkin, one
    # granularity up: weeks 0-4 hit target (5-week streak), week 5 is
    # missed, week 6 hits target again. Freezing week 5 bridges the chain
    # into a 7-week streak (the week-7 milestone) - this must award the
    # exact same bonus whether the freeze happens before or after week 6's
    # target-reaching check-in prices.
    target = 2
    weeks = [WEEK0 + timedelta(days=7 * i) for i in range(7)]
    completed = set()
    for wk in weeks[:5]:
        completed |= {wk, wk + timedelta(days=1)}
    missed_week = weeks[5]
    target_reaching_checkin = weeks[6] + timedelta(days=1)
    completed |= {weeks[6], target_reaching_checkin}

    checkin_then_freeze = weekly_milestone_bonus_for_checkin(completed, target, target_reaching_checkin, frozen_weeks=set())
    freeze_then_checkin = weekly_milestone_bonus_for_checkin(
        completed, target, target_reaching_checkin, frozen_weeks={missed_week}
    )
    assert checkin_then_freeze == 0  # priced without the bridge: week 6 alone, streak 1 - no milestone
    assert freeze_then_checkin == milestone_bonus(7)  # priced with the bridge: a 7-week streak
    assert freeze_then_checkin > checkin_then_freeze


# --- frequency-edit restart (`floor`) -------------------------------------


def test_current_streak_floor_is_a_noop_when_there_is_no_gap_to_cross():
    completed = days(0, 1, 2)
    today = D0 + timedelta(days=2)
    assert current_streak(completed, set(), today, floor=D0) == 3


def test_current_streak_floor_truncates_an_unbroken_chain_at_the_edit_date():
    # No real gap at all - every day is genuinely completed - but a
    # frequency edit still unconditionally restarts the count from the
    # edit date forward, per the approved design ("streak restarts on
    # change", not just "restarts if it would otherwise be exploitable").
    completed = days(0, 1, 2, 3, 4)
    today = D0 + timedelta(days=4)
    floor = D0 + timedelta(days=3)  # edited on day 3
    assert current_streak(completed, set(), today, floor=floor) == 2  # days 3-4 only


def test_streak_day_on_returns_zero_before_the_floor():
    completed = days(0, 1, 2)
    floor = D0 + timedelta(days=1)
    assert streak_day_on(completed, set(), D0, floor=floor) == 0  # day 0 predates the edit
    assert streak_day_on(completed, set(), D0 + timedelta(days=1), floor=floor) == 1  # restarts at day 1


def test_freeze_target_date_floor_blocks_saving_a_day_before_the_edit():
    # 3-day streak, miss day 3, then edit frequency on day 4 (today). The
    # missed day predates the edit, so a freeze bought today has nothing
    # to cover - it can't resurrect pre-edit history either.
    completed = days(0, 1, 2)
    today = D0 + timedelta(days=4)
    floor = today
    assert freeze_target_date(completed, set(), today, floor=floor) is None
    assert freeze_available(completed, set(), today, floor=floor) is False


def test_weekly_streak_floor_truncates_an_unbroken_chain_at_the_edit_week():
    target = 2
    completed = {WEEK0, WEEK0 + timedelta(days=1), WEEK1, WEEK1 + timedelta(days=1)}
    today = WEEK1 + timedelta(days=2)
    assert weekly_streak(completed, target, today) == 2
    assert weekly_streak(completed, target, today, floor=WEEK1) == 1  # edited during week 1


def test_weekly_freeze_target_week_floor_blocks_a_pre_edit_week():
    target = 1
    completed = {WEEK0}  # week0 hit, week1 missed entirely
    today = WEEK2
    assert weekly_freeze_target_week(completed, target, today) == WEEK1
    assert weekly_freeze_target_week(completed, target, today, floor=WEEK2) is None
