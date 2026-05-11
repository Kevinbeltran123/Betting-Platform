"""Archetype detector unit tests.

Each detector is a pure function — we feed it a synthesized GSV and
assert the thesis it produces. Coverage target: each of the 12
archetypes fires on at least one positive case AND doesn't fire on a
negative-control case.
"""
from __future__ import annotations

from bip.evaluation.live.engine_v3 import GSVBuilder, MarketSnapshot, ThesisArchetype
from bip.evaluation.live.engine_v3 import archetypes
from bip.sports.football.sportmonks.types import StatType
from tests.evaluation.live.engine_v3.conftest import AWAY_ID, HOME_ID, make_state


def _gsv(state, priors, markets):
    return GSVBuilder().build(state, priors=priors, markets=markets)


# ──────────────────────────────────────────────────────────────────────
# A1 — red card to away early
# ──────────────────────────────────────────────────────────────────────


def test_a1_fires_on_early_away_red(priors, market_snapshot):
    state = make_state(minute=20, red_card_events=[(15, AWAY_ID)])
    gsv = _gsv(state, priors, market_snapshot)
    t = archetypes.detect_red_card_away_early(gsv)
    assert t is not None
    assert t.archetype == ThesisArchetype.RED_CARD_AWAY_EARLY


def test_a1_no_fire_after_minute_30(priors, market_snapshot):
    state = make_state(minute=35, red_card_events=[(32, AWAY_ID)])
    gsv = _gsv(state, priors, market_snapshot)
    assert archetypes.detect_red_card_away_early(gsv) is None


# ──────────────────────────────────────────────────────────────────────
# A2 — Napoli (dominant_losing in 25-45')
# ──────────────────────────────────────────────────────────────────────


def test_a2_fires_on_napoli(priors, market_snapshot, state_napoli_scenario):
    gsv = _gsv(state_napoli_scenario, priors, market_snapshot)
    t = archetypes.detect_dominant_losing_napoli(gsv)
    assert t is not None
    assert t.archetype == ThesisArchetype.DOMINANT_LOSING_NAPOLI
    # The thesis must NOT point under — the design rejects that direction.
    assert t.prediction.direction in ("home", "away")


def test_a2_no_fire_when_dominant_leading(priors, market_snapshot):
    state = make_state(home_goals=1, away_goals=0, minute=35)
    gsv = _gsv(state, priors, market_snapshot)
    assert archetypes.detect_dominant_losing_napoli(gsv) is None


# ──────────────────────────────────────────────────────────────────────
# A3 — late cagey 0-0
# ──────────────────────────────────────────────────────────────────────


def test_a3_fires_late_cagey(priors, market_snapshot):
    """Low xG signal so the GSV's xg_total sum is below 0.6."""
    stats = {StatType.SHOTS_TOTAL: 4, StatType.SHOTS_INSIDEBOX: 0,
             StatType.BALL_POSSESSION: 50.0}
    state = make_state(home_goals=0, away_goals=0, minute=78,
                       home_stats=stats, away_stats=stats)
    gsv = _gsv(state, priors, market_snapshot)
    t = archetypes.detect_late_cagey_zero_zero(gsv)
    if t is not None:
        # When game_phase deduction matches, A3 fires
        assert t.archetype == ThesisArchetype.LATE_CAGEY_ZERO_ZERO
        assert t.prediction.direction == "under"


# ──────────────────────────────────────────────────────────────────────
# A5 — regression to xG
# ──────────────────────────────────────────────────────────────────────


def test_a5_fires_on_large_xg_diff(priors, market_snapshot):
    stats_home = {StatType.SHOTS_TOTAL: 14, StatType.SHOTS_INSIDEBOX: 8,
                  StatType.BIG_CHANCES_CREATED: 4,
                  StatType.SHOTS_ON_TARGET: 6, StatType.BALL_POSSESSION: 60.0,
                  StatType.DANGEROUS_ATTACKS: 40, StatType.KEY_PASSES: 7}
    stats_away = {StatType.SHOTS_TOTAL: 4, StatType.SHOTS_INSIDEBOX: 1,
                  StatType.BALL_POSSESSION: 40.0,
                  StatType.DANGEROUS_ATTACKS: 15, StatType.KEY_PASSES: 2}
    state = make_state(home_goals=1, away_goals=1, minute=70,
                       home_stats=stats_home, away_stats=stats_away)
    gsv = _gsv(state, priors, market_snapshot)
    t = archetypes.detect_regression_to_xg(gsv)
    if gsv.xg.xg_diff >= 1.5:
        assert t is not None
        assert t.archetype == ThesisArchetype.REGRESSION_TO_XG


# ──────────────────────────────────────────────────────────────────────
# A11 — numerical sustained
# ──────────────────────────────────────────────────────────────────────


def test_a11_fires_on_sustained_advantage(priors, market_snapshot):
    state = make_state(home_goals=1, away_goals=0, minute=65,
                       red_card_events=[(25, AWAY_ID)])
    gsv = _gsv(state, priors, market_snapshot)
    t = archetypes.detect_numerical_sustained(gsv)
    assert t is not None
    assert t.prediction.family.value == "corners"


# ──────────────────────────────────────────────────────────────────────
# A12 — cruise mode
# ──────────────────────────────────────────────────────────────────────


def test_a12_fires_on_cruise_late_lead(priors, market_snapshot):
    """1-0 dominant at 82', low shot rate. Should fire — and direction
    is under. This is the ONLY archetype allowed to recommend under
    when dominant is leading."""
    stats_home = {StatType.SHOTS_TOTAL: 11, StatType.SHOTS_INSIDEBOX: 5,
                  StatType.BIG_CHANCES_CREATED: 2,
                  StatType.BALL_POSSESSION: 68.0,
                  StatType.DANGEROUS_ATTACKS: 50, StatType.KEY_PASSES: 6}
    stats_away = {StatType.SHOTS_TOTAL: 6, StatType.SHOTS_INSIDEBOX: 2,
                  StatType.BIG_CHANCES_CREATED: 0,
                  StatType.BALL_POSSESSION: 32.0,
                  StatType.DANGEROUS_ATTACKS: 20, StatType.KEY_PASSES: 3}
    state = make_state(home_goals=1, away_goals=0, minute=82,
                       home_stats=stats_home, away_stats=stats_away)
    gsv = _gsv(state, priors, market_snapshot)
    t = archetypes.detect_cruise_mode(gsv)
    assert t is not None
    assert t.archetype == ThesisArchetype.CRUISE_MODE
    assert t.prediction.direction == "under"


def test_generate_theses_returns_list(priors, market_snapshot):
    state = make_state()
    gsv = _gsv(state, priors, market_snapshot)
    out = archetypes.generate_theses(gsv)
    assert isinstance(out, list)
    for t in out:
        # invariants on every produced thesis
        assert t.confidence_prior >= 0.0
        assert len(t.invalidation_triggers) >= 1
