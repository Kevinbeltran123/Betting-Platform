"""Tests for scripts/run_phase5_backtest.py — Phase 5 Layer-2 runner.

Layer-1 tests: BayesianPoissonPredictor on synthetic snapshots, Poisson
score-grid → market-prob derivation, snapshot conversion, end-to-end
plumbing with stub StatsBomb outcomes.

Layer-2 tests: real backtest over the 6 men's tournaments — runs only
when the StatsBomb Parquet has been seeded.
"""

from __future__ import annotations

from datetime import date

import pytest

from bip.evaluation.tournaments.live.competition_weights import CompetitionType
from scripts.run_phase5_backtest import (
    BayesianPoissonPredictor,
    _poisson_score_grid_to_prediction,
    _tournament_to_competition,
    make_snapshots,
)
from scripts.seed_statsbomb_tournaments import (
    DEFAULT_OUTCOMES_PARQUET,
    StatsBombMatchOutcome,
)

# ── Poisson grid → market probabilities ──────────────────────────────────────


class TestPoissonGrid:
    def test_low_lambda_predicts_low_scoring(self):
        """Both teams λ=0.5 → most matches end 0-0 → low P(over 2.5).

        Math: total ~ Poisson(1.0), P(total ≥ 3) ≈ 0.080.
        """
        pred = _poisson_score_grid_to_prediction(0.5, 0.5)
        assert pred.p_over_2_5 < 0.10
        assert pred.p_btts < 0.30  # rare BTTS at low rates
        assert pred.p_draw > pred.p_home_win
        assert pred.p_draw > pred.p_away_win

    def test_high_lambda_predicts_high_scoring(self):
        """Both teams λ=2.5 → high-scoring expected."""
        pred = _poisson_score_grid_to_prediction(2.5, 2.5)
        assert pred.p_over_2_5 > 0.70
        assert pred.p_btts > 0.60

    def test_asymmetric_lambdas_favour_higher_team(self):
        """λ_home=2.5 vs λ_away=0.5 → home win much more likely."""
        pred = _poisson_score_grid_to_prediction(2.5, 0.5)
        assert pred.p_home_win > 0.70
        assert pred.p_away_win < 0.10

    def test_probabilities_sum_to_one(self):
        pred = _poisson_score_grid_to_prediction(1.5, 1.2)
        assert pytest.approx(
            pred.p_home_win + pred.p_draw + pred.p_away_win, abs=1e-6
        ) == 1.0

    def test_zero_lambda_handled_gracefully(self):
        """λ=0 should yield a valid prediction (no inf/nan)."""
        pred = _poisson_score_grid_to_prediction(1e-3, 1e-3)
        # All probabilities finite
        assert 0 <= pred.p_home_win <= 1
        assert 0 <= pred.p_btts <= 1
        assert 0 <= pred.p_over_2_5 <= 1


# ── Snapshot conversion ──────────────────────────────────────────────────────


def _outcome(
    match_id: int,
    home: str,
    away: str,
    hg: int,
    ag: int,
    hc: int = 5,
    ac: int = 5,
    d: date = date(2024, 7, 10),
    slug: str = "copa_2024",
) -> StatsBombMatchOutcome:
    return StatsBombMatchOutcome(
        match_id=match_id,
        tournament_slug=slug,
        match_date=d,
        home_team=home,
        away_team=away,
        home_goals=hg,
        away_goals=ag,
        home_corners=hc,
        away_corners=ac,
    )


class TestMakeSnapshots:
    def test_sorts_by_match_date(self):
        outcomes = [
            _outcome(1, "A", "B", 1, 0, d=date(2024, 7, 10)),
            _outcome(2, "C", "D", 0, 0, d=date(2024, 6, 15)),
            _outcome(3, "E", "F", 2, 1, d=date(2024, 7, 1)),
        ]
        snapshots, _ = make_snapshots(outcomes)
        dates = [s.match_date for s in snapshots]
        assert dates == sorted(dates)

    def test_same_team_same_id_across_matches(self):
        outcomes = [
            _outcome(1, "Argentina", "Brazil", 1, 0),
            _outcome(2, "Brazil", "Uruguay", 2, 0),
        ]
        snapshots, team_id_map = make_snapshots(outcomes)
        # Brazil appears in both; should keep same id
        assert team_id_map["Brazil"] == snapshots[0].away_team_id
        assert team_id_map["Brazil"] == snapshots[1].home_team_id

    def test_propagates_observed_outcomes(self):
        outcomes = [_outcome(1, "A", "B", 2, 1, hc=4, ac=7)]
        snapshots, _ = make_snapshots(outcomes)
        snap = snapshots[0]
        assert snap.observed_1x2 == 0  # home win
        assert snap.observed_total_goals == 3
        assert snap.observed_btts == 1
        assert snap.observed_home_goals == 2
        assert snap.observed_away_goals == 1
        assert snap.observed_home_corners == 4
        assert snap.observed_away_corners == 7

    def test_team_id_map_is_deterministic_insertion_order(self):
        outcomes = [
            _outcome(1, "Z", "A", 0, 0),
            _outcome(2, "Z", "B", 0, 0),
            _outcome(3, "C", "A", 0, 0),
        ]
        _, team_id_map = make_snapshots(outcomes)
        # Sorted by date (all same) → insertion is in input order
        # First seen: Z → 0, A → 1, then B → 2, then C → 3
        # (But actually outcomes get sorted by date first, which is the same date,
        # so their relative order is preserved as Python sort is stable)
        assert team_id_map["Z"] == 0
        assert team_id_map["A"] == 1
        assert team_id_map["B"] == 2
        assert team_id_map["C"] == 3


# ── Tournament → competition mapping ─────────────────────────────────────────


class TestTournamentToCompetition:
    def test_world_cup_maps_to_wc(self):
        assert _tournament_to_competition("wc_2018") == CompetitionType.WORLD_CUP
        assert _tournament_to_competition("wc_2022") == CompetitionType.WORLD_CUP

    def test_continental_maps_to_confederation(self):
        assert _tournament_to_competition("euro_2024") == CompetitionType.CONFEDERATION
        assert _tournament_to_competition("copa_2024") == CompetitionType.CONFEDERATION
        assert _tournament_to_competition("afcon_2023") == CompetitionType.CONFEDERATION


# ── BayesianPoissonPredictor ─────────────────────────────────────────────────


class TestBayesianBivariatePoissonPredictor:
    def test_rho_zero_yields_independent_poisson_grid(self):
        """ρ=0 collapses to Independent Poisson (Bivariate is a strict generalization)."""
        from scripts.backtest_int_tournaments import BacktestSnapshot
        from scripts.run_phase5_backtest import (
            BayesianBivariatePoissonPredictor,
            BayesianPoissonPredictor,
        )

        snap = BacktestSnapshot(
            match_id="m1", tournament="wc_2018",
            home_team_id=0, away_team_id=1,
            observed_1x2=1, observed_total_goals=0, observed_btts=0,
            observed_home_goals=0, observed_away_goals=0,
            match_date="2018-06-14",
        )
        ind = BayesianPoissonPredictor()
        biv = BayesianBivariatePoissonPredictor(rho=0.0)
        ind_pred = ind.predict_fixture(snap)
        biv_pred = biv.predict_fixture(snap)
        assert biv_pred.p_home_win == pytest.approx(ind_pred.p_home_win, abs=1e-6)
        assert biv_pred.p_draw == pytest.approx(ind_pred.p_draw, abs=1e-6)
        assert biv_pred.p_btts == pytest.approx(ind_pred.p_btts, abs=1e-6)

    def test_positive_rho_inflates_draw_probability(self):
        """ρ>0 should yield higher P(draw) than ρ=0 — corrects Independent
        Poisson's draw underestimation per SYNTHESIS Conclusion 2."""
        from scripts.backtest_int_tournaments import BacktestSnapshot
        from scripts.run_phase5_backtest import BayesianBivariatePoissonPredictor

        snap = BacktestSnapshot(
            match_id="m1", tournament="wc_2018",
            home_team_id=0, away_team_id=1,
            observed_1x2=1, observed_total_goals=0, observed_btts=0,
            observed_home_goals=0, observed_away_goals=0,
            match_date="2018-06-14",
        )
        rho_0 = BayesianBivariatePoissonPredictor(rho=0.0).predict_fixture(snap)
        rho_high = BayesianBivariatePoissonPredictor(rho=0.20).predict_fixture(snap)
        assert rho_high.p_draw > rho_0.p_draw

    def test_invalid_rho_rejected(self):
        from scripts.run_phase5_backtest import BayesianBivariatePoissonPredictor

        with pytest.raises(ValueError, match="rho must be"):
            BayesianBivariatePoissonPredictor(rho=0.6)
        with pytest.raises(ValueError, match="rho must be"):
            BayesianBivariatePoissonPredictor(rho=-0.6)


class TestPredictorFactory:
    def test_independent_kind(self):
        from scripts.run_phase5_backtest import (
            BayesianPoissonPredictor,
            _make_predictor,
        )

        p = _make_predictor("independent", sigma_s_per_day=0.0001)
        assert isinstance(p, BayesianPoissonPredictor)

    def test_bivariate_kind_uses_rho(self):
        from scripts.run_phase5_backtest import (
            BayesianBivariatePoissonPredictor,
            _make_predictor,
        )

        p = _make_predictor("bivariate", sigma_s_per_day=0.0001, rho=0.10)
        assert isinstance(p, BayesianBivariatePoissonPredictor)
        assert p.rho == 0.10

    def test_unknown_kind_raises(self):
        from scripts.run_phase5_backtest import _make_predictor

        with pytest.raises(ValueError, match="Unknown predictor_kind"):
            _make_predictor("nonexistent", sigma_s_per_day=0.0001)


class TestBayesianPoissonPredictor:
    def test_first_match_uses_priors(self):
        """Cold-start: with both teams unseen, prediction uses cohort priors
        (λ_home ≈ λ_away ≈ prior_goals → balanced 1X2 with high draw)."""
        from scripts.backtest_int_tournaments import BacktestSnapshot

        predictor = BayesianPoissonPredictor(prior_goals=1.30)
        snap = BacktestSnapshot(
            match_id="m1",
            tournament="wc_2018",
            home_team_id=0,
            away_team_id=1,
            observed_1x2=1,
            observed_total_goals=0,
            observed_btts=0,
            observed_home_goals=0,
            observed_away_goals=0,
            match_date="2018-06-14",
        )
        pred = predictor.predict_fixture(snap)
        # Symmetric priors → balanced home/away win probability
        assert abs(pred.p_home_win - pred.p_away_win) < 0.02
        # Probabilities valid
        assert 0 <= pred.p_btts <= 1
        assert 0 <= pred.p_over_2_5 <= 1

    def test_state_advances_after_prediction(self):
        """Predicting + observing one fixture should leave state with
        non-zero observations for both teams."""
        from scripts.backtest_int_tournaments import BacktestSnapshot

        predictor = BayesianPoissonPredictor()
        snap = BacktestSnapshot(
            match_id="m1",
            tournament="wc_2018",
            home_team_id=0,
            away_team_id=1,
            observed_1x2=0,
            observed_total_goals=3,
            observed_btts=1,
            observed_home_goals=2,
            observed_away_goals=1,
            match_date="2018-06-14",
        )
        predictor.predict_fixture(snap)
        # State should reflect the observation
        assert predictor._state.team_states[0].n_matches_played == 1
        assert predictor._state.team_states[1].n_matches_played == 1
        # obs_weight_total scaled by competition weight (WC = 4×)
        assert predictor._state.team_states[0].obs_weight_total == 4.0

    def test_two_fixtures_chain_state(self):
        """Same team appearing in multiple fixtures accumulates observations."""
        from scripts.backtest_int_tournaments import BacktestSnapshot

        predictor = BayesianPoissonPredictor()
        snap1 = BacktestSnapshot(
            match_id="m1", tournament="wc_2018",
            home_team_id=0, away_team_id=1,
            observed_1x2=0, observed_total_goals=3, observed_btts=1,
            observed_home_goals=2, observed_away_goals=1,
            match_date="2018-06-14",
        )
        snap2 = BacktestSnapshot(
            match_id="m2", tournament="wc_2018",
            home_team_id=0, away_team_id=2,
            observed_1x2=2, observed_total_goals=1, observed_btts=0,
            observed_home_goals=0, observed_away_goals=1,
            match_date="2018-06-19",
        )
        predictor.predict_fixture(snap1)
        predictor.predict_fixture(snap2)
        # Team 0 played twice
        assert predictor._state.team_states[0].n_matches_played == 2
        # Team 1 played once, team 2 played once
        assert predictor._state.team_states[1].n_matches_played == 1
        assert predictor._state.team_states[2].n_matches_played == 1


# ── Layer-2: real-data integration ───────────────────────────────────────────


def _real_data_available() -> bool:
    return DEFAULT_OUTCOMES_PARQUET.exists()


@pytest.mark.skipif(
    not _real_data_available(),
    reason=(
        "Run `uv run python scripts/seed_statsbomb_tournaments.py` first "
        "to seed the StatsBomb match-outcomes Parquet."
    ),
)
class TestRealBacktestLayer2:
    def test_full_backtest_emits_lock_decision(self, tmp_path):
        from scripts.run_phase5_backtest import run_phase5_backtest

        out = tmp_path / "lock_decision.json"
        decision, reports = run_phase5_backtest(output_path=out)

        # Pipeline ran end-to-end
        assert decision.calibration_status in (
            "pass",
            "marginal",
            "below-gate",
            "unreliable-bins",
        )
        assert decision.n_fixtures_with_predictions > 250
        assert out.exists()

        # Reports cover the expected markets (1X2 + BTTS + OU 2.5)
        markets = {r.market for r in reports}
        from bip.evaluation.tournaments.backtest.calibration_report import (
            MARKET_1X2,
            MARKET_BTTS,
            MARKET_OU_2_5,
        )
        assert MARKET_1X2 in markets
        assert MARKET_BTTS in markets
        assert MARKET_OU_2_5 in markets

    def test_lock_decision_is_loadable(self, tmp_path):
        from bip.evaluation.tournaments.backtest.lock_gate import LockDecision
        from scripts.run_phase5_backtest import run_phase5_backtest

        out = tmp_path / "lock_decision.json"
        run_phase5_backtest(output_path=out)
        loaded = LockDecision.from_json(out)
        assert loaded.held_out_tournaments == ("copa_2024", "euro_2024")

    def test_calibrated_backtest_emits_two_predictor_verdicts(self, tmp_path):
        """Phase 2 ∘ Phase 5: side-by-side raw vs calibrated."""
        from scripts.run_phase5_backtest import run_phase5_backtest_calibrated

        out = tmp_path / "lock_decision.json"
        decision, reports = run_phase5_backtest_calibrated(output_path=out)

        # Two predictors: raw + logit-calibrated, both with 3 markets each
        names = {v.predictor_name for v in decision.predictor_verdicts}
        assert "bayesian_independent_poisson_raw" in names
        assert "bayesian_independent_poisson_logit_calibrated" in names
        # Held-out scope: ~83 fixtures (Copa 2024 + Euro 2024)
        assert decision.n_fixtures_with_predictions > 50
        assert decision.n_fixtures_with_predictions < 100

    def test_calibrated_backtest_calibrator_helps_at_least_one_market(self, tmp_path):
        """The post-hoc calibrator should improve ECE on at least one
        market vs the raw baseline. (Football data + small test set
        means improvements are mixed; we only assert that the calibrator
        is not strictly worse on every market.)"""
        from scripts.run_phase5_backtest import run_phase5_backtest_calibrated

        decision, _ = run_phase5_backtest_calibrated(output_path=None)
        raw_v = next(
            v for v in decision.predictor_verdicts
            if v.predictor_name == "bayesian_independent_poisson_raw"
        )
        cal_v = next(
            v for v in decision.predictor_verdicts
            if v.predictor_name == "bayesian_independent_poisson_logit_calibrated"
        )
        # At least one market should have lower ECE after calibration
        improved = sum(
            1 for m in raw_v.market_classwise_ece
            if cal_v.market_classwise_ece.get(m, 1.0) < raw_v.market_classwise_ece[m]
        )
        assert improved >= 1, (
            f"Calibrator did not improve any market. raw={raw_v.market_classwise_ece}, "
            f"cal={cal_v.market_classwise_ece}"
        )
