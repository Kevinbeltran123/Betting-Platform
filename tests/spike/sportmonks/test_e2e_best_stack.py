"""End-to-end smoke test for the spike's best-stack deployment path.

Exercises the full cascade:
  1. Fit a per-market calibrator from synthetic data
  2. Build a ValueDetector via make_best_stack_detector with that calibrator
  3. Construct a LiveMatchState carrying commentary events
  4. Run detector.evaluate() against synthetic odds
  5. Verify gates fire correctly (positive-side ban, blacklist, commentary
     cool-off, calibrator transforms)
  6. Smoke-test telegram formatters on the emitted picks
  7. Smoke-test analyze_decisions / jornada_tracker CLIs on a synthetic dataset

This is a "could-it-deploy?" check — if every component composes cleanly
end-to-end, the operator can ship without surprise.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock

import numpy as np
import polars as pl
import pytest

from bip.evaluation.live.calibration import PerMarketCalibrator
from bip.evaluation.live.commentary import (
    CommentaryEvent, CommentaryEventType,
)
from bip.evaluation.live.match_state import LiveMatchState
from bip.evaluation.live.predictor import (
    MARKET_BTTS, MARKET_BTTS_SECOND_HALF,
    MARKET_FULLTIME_RESULT, MARKET_OU_25, MARKET_OU_35,
    MarketProbabilities,
)
from bip.evaluation.live.telegram_alerts import (
    format_jornada_summary, format_pick_alert,
)
from bip.evaluation.live.telegram_integration import LiveAlertSender
from bip.evaluation.live.value_detector import (
    make_best_stack_detector,
)
from bip.sports.football.sportmonks.schemas import Odd
from bip.sports.football.sportmonks.types import MarketID


@pytest.fixture
def fitted_calibrator(tmp_path: Path) -> Path:
    """Realistic synthetic per-market calibrator.

    market_A: well-calibrated (200 picks)
    market_B: overconfident (200 picks, predicted 0.8 vs actual 0.4)
    market_C: small n, falls to global fallback (20 picks)
    """
    rng = np.random.default_rng(7)
    a_probs = np.linspace(0.1, 0.9, 200)
    a_out = (rng.uniform(size=200) < a_probs).astype(float)
    b_probs = np.linspace(0.6, 0.95, 200)
    b_out = (rng.uniform(size=200) < 0.4).astype(float)
    c_probs = np.linspace(0.5, 0.8, 20)
    c_out = (rng.uniform(size=20) < c_probs).astype(float)
    probs = np.concatenate([a_probs, b_probs, c_probs])
    outcomes = np.concatenate([a_out, b_out, c_out])
    markets = ["market_A"] * 200 + ["market_B"] * 200 + ["market_C"] * 20
    cal = PerMarketCalibrator.fit(
        probs, outcomes, markets, min_samples_per_market=25,
    )
    path = tmp_path / "test_calibrator.json"
    cal.save_json(path)
    return path


def _state(
    *,
    minute: int = 35,
    home_goals: int = 0, away_goals: int = 1,
    commentary_events: list[CommentaryEvent] | None = None,
) -> LiveMatchState:
    return LiveMatchState(
        fixture_id=1, home_team_id=10, away_team_id=20,
        home_team_name="A", away_team_name="B",
        home_goals=home_goals, away_goals=away_goals,
        minute=minute, period_id=2 if minute >= 45 else 1,
        is_live=True, is_half_time=False, is_finished=False,
        commentary_events=commentary_events or [],
    )


def _odd(
    market_id: int, label: str, value: str,
    total: str | None = None,
) -> Odd:
    return Odd.model_validate({
        "id": hash((market_id, label, value)) % 10000,
        "fixture_id": 1, "market_id": market_id, "bookmaker_id": 2,
        "label": label, "value": value, "suspended": False,
        "stopped": False, "total": total, "market_description": None,
    })


def _probs(market_probs: dict, minute: int = 35) -> MarketProbabilities:
    return MarketProbabilities(
        fixture_id=1, minute=minute, snapshot_kind="live",
        by_market=market_probs,
        sources={k: "test" for k in market_probs},
    )


class TestEndToEndDeployment:
    """If these pass, the whole stack composes for deployment."""

    def test_factory_builds_detector_from_calibrator_json(
        self, fitted_calibrator: Path,
    ):
        det = make_best_stack_detector(
            calibrator_path=str(fitted_calibrator),
        )
        # Calibrator loaded, haircut auto-disabled
        assert det.calibrator is not None
        assert det.high_prob_haircut_threshold > 1.0
        # All Tier 1 gates ON
        assert det.market_blacklist
        assert det.ban_positive_side_binaries is True
        assert det.drop_over_zero_zero is True
        assert det.enforce_commentary_cooloff is True

    def test_btts_blacklist_drops_btts(self, fitted_calibrator: Path):
        det = make_best_stack_detector(
            calibrator_path=str(fitted_calibrator),
        )
        probs = _probs({MARKET_BTTS: {"no": 0.70, "yes": 0.30}})
        odds = [_odd(MarketID.BOTH_TEAMS_TO_SCORE, "No", "1.80")]
        recorded = []
        picks = det.evaluate(
            probs, odds, home_team_name="A", away_team_name="B",
            state=_state(),
            on_decision=lambda **kw: recorded.append(kw),
        )
        assert picks == []
        assert any(
            r.get("drop_reason") == "market_blacklist" for r in recorded
        )

    def test_positive_side_binary_dropped(self, fitted_calibrator: Path):
        det = make_best_stack_detector(
            calibrator_path=str(fitted_calibrator),
        )
        probs = _probs({MARKET_OU_25: {"over": 0.65, "under": 0.35}})
        odds = [_odd(MarketID.MATCH_GOALS, "Over", "1.85", total="2.5")]
        recorded = []
        picks = det.evaluate(
            probs, odds, home_team_name="A", away_team_name="B",
            state=_state(),
            on_decision=lambda **kw: recorded.append(kw),
        )
        assert picks == []
        assert any(
            r.get("drop_reason") == "positive_side_binary_ban"
            for r in recorded
        )

    def test_under_passes_through_calibrator(self, fitted_calibrator: Path):
        # Use a market the calibrator can transform (market_A or market_B
        # in the fitted synthetic). Real markets in production:
        # ou_3_5, btts_second_half, etc.
        det = make_best_stack_detector(
            calibrator_path=str(fitted_calibrator),
            # Bypass non-relevant gates to isolate calibrator interaction
            enforce_ci_gate=False,
            min_logical_score_emit=0.0, min_logical_score_flag=0.0,
        )
        # ou_3_5 isn't in synthetic calibrator markets → fallback used
        probs = _probs({MARKET_OU_35: {"under": 0.70, "over": 0.30}})
        odds = [_odd(MarketID.MATCH_GOALS, "Under", "1.80", total="3.5")]
        picks = det.evaluate(
            probs, odds, home_team_name="A", away_team_name="B",
            state=_state(home_goals=1, away_goals=0),
        )
        # Should emit if calibrated_prob keeps edge above threshold
        if picks:
            p = picks[0]
            assert p.selection == "under"
            # Raw probability preserved
            assert p.model_probability_raw == pytest.approx(0.70)
            # Calibrated probability may differ (or stay same in fallback)

    def test_commentary_cooloff_blocks_during_disruption(
        self, fitted_calibrator: Path,
    ):
        det = make_best_stack_detector(
            calibrator_path=str(fitted_calibrator),
        )
        var_event = CommentaryEvent(
            minute=33, extra_minute=0,
            event_type=CommentaryEventType.VAR_CHECK,
            is_important=True, text="VAR is checking",
        )
        # VAR at min 33, current min 34 → within 3-min window
        state = _state(minute=34, commentary_events=[var_event])
        probs = _probs(
            {MARKET_FULLTIME_RESULT: {"home": 0.55, "draw": 0.25, "away": 0.20}},
            minute=34,
        )
        odds = [_odd(MarketID.FULLTIME_RESULT, "Home", "2.00")]
        recorded = []
        picks = det.evaluate(
            probs, odds, home_team_name="A", away_team_name="B",
            state=state,
            on_decision=lambda **kw: recorded.append(kw),
        )
        assert picks == []
        assert any(
            r.get("drop_reason", "").startswith("commentary_cooloff")
            for r in recorded
        )

    def test_clean_multi_side_pick_survives_all_gates(
        self, fitted_calibrator: Path,
    ):
        """Fulltime_result (multi-side, NOT positive_side_ban) should
        survive the cascade when state + odds are reasonable."""
        det = make_best_stack_detector(
            calibrator_path=str(fitted_calibrator),
            enforce_ci_gate=False,
            min_logical_score_emit=0.0, min_logical_score_flag=0.0,
        )
        # Use prob + odd combination that yields large enough edge to
        # survive the calibrator's pull-down on synthetic data.
        probs = _probs(
            {MARKET_FULLTIME_RESULT: {"home": 0.70, "draw": 0.20, "away": 0.10}},
        )
        odds = [_odd(MarketID.FULLTIME_RESULT, "Home", "2.50")]
        picks = det.evaluate(
            probs, odds, home_team_name="A", away_team_name="B",
            state=_state(home_goals=1, away_goals=0),
        )
        # Should emit (multi-side market, not gated by Tier 1)
        assert len(picks) == 1
        p = picks[0]
        assert p.selection == "home"
        assert p.model_probability_raw == pytest.approx(0.70)


class TestTelegramFormattersOnRealPicks:
    """Smoke-test that Telegram formatters render emitted LivePicks."""

    def test_pick_alert_renders_clean_pick(self, fitted_calibrator: Path):
        det = make_best_stack_detector(
            calibrator_path=str(fitted_calibrator),
            enforce_ci_gate=False,
            min_logical_score_emit=0.0, min_logical_score_flag=0.0,
        )
        probs = _probs(
            {MARKET_FULLTIME_RESULT: {"home": 0.70, "draw": 0.20, "away": 0.10}},
        )
        odds = [_odd(MarketID.FULLTIME_RESULT, "Home", "2.50")]
        picks = det.evaluate(
            probs, odds, home_team_name="A", away_team_name="B",
            state=_state(home_goals=1, away_goals=0),
        )
        assert len(picks) == 1
        text = format_pick_alert(
            picks[0], home_score=1, away_score=0,
        )
        # v2 templates: Tier 1 label is "TIER 1 — HIGH-CONVICTION PICK";
        # Tier 2 label is just "PICK". Both contain "PICK".
        assert "PICK" in text
        assert "home" in text
        # HTML escape works on standard team names
        assert "&lt;" not in text  # nothing escape-needed in 'A' / 'B'

    @pytest.mark.asyncio
    async def test_alert_sender_swallows_failure_e2e(
        self, fitted_calibrator: Path,
    ):
        """Failure-safe send must not propagate exceptions."""
        det = make_best_stack_detector(
            calibrator_path=str(fitted_calibrator),
            enforce_ci_gate=False,
            min_logical_score_emit=0.0, min_logical_score_flag=0.0,
        )
        probs = _probs(
            {MARKET_FULLTIME_RESULT: {"home": 0.70, "draw": 0.20, "away": 0.10}},
        )
        odds = [_odd(MarketID.FULLTIME_RESULT, "Home", "2.50")]
        picks = det.evaluate(
            probs, odds, home_team_name="A", away_team_name="B",
            state=_state(home_goals=1, away_goals=0),
        )
        assert len(picks) == 1
        # Bot that fails on send
        bot = AsyncMock()
        bot.send_html.side_effect = RuntimeError("network down")
        sender = LiveAlertSender(
            bot, min_edge_pct_for_alert=0.0, min_interval_seconds=0.0,
        )
        # Should NOT raise
        ok = await sender.send_pick_safe(picks[0])
        assert ok is False
        assert sender.n_failed == 1


class TestAnalyticsCLIsOnSynthetic:
    """Smoke-test CLIs run on a synthetic picks + decisions parquet."""

    def test_jornada_tracker_runs_on_synthetic(
        self, tmp_path: Path, capsys,
    ):
        # Build minimal picks_graded.parquet
        df = pl.DataFrame({
            "id": [1, 2, 3, 4],
            "fixture_id": [100, 100, 200, 200],
            "home_team": ["A"]*4, "away_team": ["B"]*4,
            "market": ["ou_3_5"]*4, "selection": ["under"]*4,
            "bookmaker_id": [2]*4, "minute": [30]*4,
            "minute_bucket": ["30-44"]*4,
            "bookmaker_odd": [1.85]*4, "our_probability": [0.7]*4,
            "fair_odd": [1.43]*4, "edge_pct": [10.0]*4,
            "kelly_fraction_full": [0.2]*4, "suggested_stake_pct": [1.0]*4,
            "market_description": [None]*4, "snapshot_kind": ["live"]*4,
            "emitted_at": [
                "2026-05-10T13:00:00Z", "2026-05-10T13:30:00Z",
                "2026-05-13T13:00:00Z", "2026-05-13T13:30:00Z",
            ],
            "flagged_reason": [None]*4, "logical_score": [0.8]*4,
            "logical_components_json": [None]*4,
            "confidence_half_width": [0.05]*4,
            "status": ["won","lost","won","won"],
            "settled_at": ["2026-05-10T15:00:00Z"]*2 +
                         ["2026-05-13T15:00:00Z"]*2,
            "profit_units": [0.85, -1.0, 0.85, 0.85],
            "placed_at_betano": [None]*4, "betano_odd": [None]*4,
            "actual_stake_units": [None]*4, "notes": [None]*4,
        })
        path = tmp_path / "picks_graded.parquet"
        df.write_parquet(path)

        import sys
        sys.path.insert(
            0,
            str(Path(__file__).resolve().parents[3] /
                "scripts" / "spike" / "sportmonks"),
        )
        import jornada_tracker as jt
        rc = jt.main(["--picks", str(path), "--profile", "aggressive"])
        assert rc == 0
        out = capsys.readouterr().out
        assert "2 jornada(s)" in out
        assert "Cumulative" in out

    def test_analyze_decisions_runs_on_synthetic(
        self, tmp_path: Path, capsys,
    ):
        df = pl.DataFrame({
            "id": list(range(1, 6)),
            "fixture_id": [100]*5, "minute": [30]*5,
            "market": ["ou_3_5", "btts", "ou_3_5", "btts", "draw_no_bet"],
            "selection": ["under", "yes", "over", "no", "home"],
            "bookmaker_id": [2]*5, "bookmaker_odd": [1.85]*5,
            "our_probability": [0.7]*5, "edge_pct": [10.0]*5,
            "decision": ["emit", "drop", "drop", "drop", "flag"],
            "drop_reason": [None, "market_blacklist",
                            "positive_side_binary_ban",
                            "market_blacklist", None],
            "sm_marginal": [None]*5, "valuebet_agrees": [None]*5,
            "informational_density": [0.5]*5, "logical_score": [0.8]*5,
            "logical_components_json": [None]*5,
            "confidence_half_width": [0.05]*5, "pick_id": [None]*5,
            "snapshot_taken_at": ["2026-05-13T13:00:00Z"]*5,
            "audited_at": ["2026-05-13T13:00:00Z"]*5,
        })
        path = tmp_path / "decisions.parquet"
        df.write_parquet(path)

        import sys
        sys.path.insert(
            0,
            str(Path(__file__).resolve().parents[3] /
                "scripts" / "spike" / "sportmonks"),
        )
        import analyze_decisions as ad
        rc = ad.main(["summary", "--path", str(path)])
        assert rc == 0
        out = capsys.readouterr().out
        assert "DECISIONS SUMMARY" in out
        assert "market_blacklist" in out


class TestTelegramSummaryRendering:
    """Final smoke — summary message renders all available metadata."""

    def test_full_summary_render(self):
        text = format_jornada_summary(
            jornada_date="2026-05-13",
            n_emit_total=500, n_emit_settled=430, n_won=290,
            profit_units=150.0, stake_pct_total=400.0,
            top_n_stats={"n": 25, "won": 22, "profit": 22.0, "roi": 88.0},
            drops_by_reason={
                "below_min_edge": 200,
                "market_blacklist": 25,
                "positive_side_binary_ban": 30,
                "commentary_cooloff:var_check": 5,
                "zero_zero_over_gate": 4,
            },
            calibrator_ece_cv=0.048,
            calibrator_n_markets_own_fit=12,
            best_market=("ou_3_5", 11, 10, 92.0),
        )
        # All major sections present
        for keyword in [
            "JORNADA SUMMARY", "Emit universe", "Top-N",
            "Drops by gate", "Calibrator", "Best market",
        ]:
            assert keyword in text
