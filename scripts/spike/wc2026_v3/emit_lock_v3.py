"""Emit lock_v3.json — FAIL-verdict audit artifact (Ola 3.F).

Mirrors `wc2026_v2.lock_v2_emitter` pattern. Produces an audit-trail
lock file that documents the v3 spike outcome:

- Ola 1.C (hierarchical Bayesian pooling): NO-GO at toy feasibility
  (ESS 299 < 400, 24 divergences). Gelman 2005 small-n collapse
  validated empirically on toy that's MORE generous than real
  calibration corpus (~1.8 obs/team-tournament cell).

- Ola 2.A (Transfermarkt market value, Peeters 2018):
  - Attack-only mode, β ∈ {0.02, 0.05, 0.10, 0.15, 0.20}: monotonic
    worsening, 0/4 tournaments improved, β≥0.10 significantly worse.
  - Symmetric attack+defense mode, β ∈ {0.005, 0.01, 0.02, 0.05, 0.10}:
    no-harm (CI crosses zero) but no incremental signal either
    (Gate 3 ΔBrier ≥ +0.005 fails at every β). 2/4 tournaments improve
    at small β but Δ point estimate stays negative.

Both A and C ruled out → v3 predictor changes ship NOTHING new beyond
v2's already-FAILED baseline. Lock_v3 prediction VALUES are identical
to lock_v2's (same CalibratedDIBPPredictor with v2 toggles ON,
use_market_value=False). The v3 lock adds nothing predictively; it
exists purely as the audit artifact recording the additional v3
falsification evidence.

Lock_v1 (commit 8c0ce19, ``bayesian_bivariate_xg_blended`` ρ=0.0 α=0.20)
remains the WC2026 production path through the tournament.

Output: ``src/bip/evaluation/tournaments/locked_predictions/world_cup_2026/lock_v3.json``
SHA-256 content_hash verifiable in CI tests.

Usage:

    uv run python scripts/spike/wc2026_v3/emit_lock_v3.py
"""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime
from pathlib import Path

from bip.evaluation.tournaments.backtest.lock_emitter import (
    FixtureLockedPredictions,
    emit_lock_json,
)
from bip.evaluation.tournaments.backtest.lock_gate import (
    DEFAULT_COVERAGE_THRESHOLD,
    LockDecision,
    PredictorGateVerdict,
)
from bip.evaluation.tournaments.wc2026_v2.corpus import build_split
from bip.evaluation.tournaments.wc2026_v2.lock_v2_emitter import (
    _LOCK_V1_PATH,
    _load_lock_v1_fixtures,
)
from bip.evaluation.tournaments.wc2026_v2.pipeline import fit_v2_pipeline
from bip.evaluation.tournaments.wc2026_v2.v2_predictor import CalibratedDIBPPredictor


_REPO_ROOT = Path(__file__).resolve().parents[3]
LOCK_V3_PATH = (
    _REPO_ROOT
    / "src"
    / "bip"
    / "evaluation"
    / "tournaments"
    / "locked_predictions"
    / "world_cup_2026"
    / "lock_v3.json"
)

PREDICTOR_NAME = "wc2026_v3_calibrated_dibp_no_mv_no_hierarchy"

# Hold-out backtest metrics from Ola 2.A baseline (use_market_value=False).
# Lock_v3 uses these as the gate metrics since A FAIL means the v3
# predictor reduces to the v2 baseline.
BACKTEST_METRICS = {
    "1x2": {"brier_for_gate": 0.2126, "ece": 0.1145},
    "btts": {"brier_for_gate": 0.2586, "ece": 0.0802},
    "goals_total_o_u_2_5": {"brier_for_gate": 0.2508, "ece": 0.0668},
}

OPERATOR_OVERRIDES_V3 = (
    "Ola 1.C (hierarchical Bayesian pooling, Macrì-Demartino 2024) feasibility "
    "check FAILED on toy synthetic corpus (3 tournaments × 10 teams × 50 matches): "
    "ESS 299 < 400 gate, 24 divergent transitions > 0 gate (max R-hat 1.010 ✓, "
    "p95 latency 6.81ms ✓). Toy is strictly MORE generous than the real "
    "calibration corpus (n=115 across 2 tournaments ≈ 1.8 obs per team-tournament "
    "cell). Gelman 2005 small-n complete-pooling collapse predicted and "
    "empirically confirmed. Non-centered parameterisation already in use. "
    "C killed; 7-day Wave 2.C budget reallocated.",
    "Ola 2.A (Transfermarkt squad market value, Peeters 2018) ATTACK-only "
    "mode, β sweep {0.02, 0.05, 0.10, 0.15, 0.20}: monotonic worsening. "
    "ΔBrier ranges from -0.0007 [-0.0017, +0.0002] (β=0.02, NS) to "
    "-0.0134 [-0.0224, -0.0046] (β=0.20, significantly WORSE). "
    "0/4 tournaments improved at any β. Confirms Brown et al. 2024 "
    "adversarial prediction: TM signal already absorbed by weighted-MLE "
    "strength prior fit on 49k martj42 matches.",
    "Ola 2.A.7 (Transfermarkt SYMMETRIC mode rescue) β sweep "
    "{0.005, 0.01, 0.02, 0.05, 0.10}: no-harm but no improvement. "
    "All ΔBrier CIs cross zero (NS); 2/4 tournaments improve at small β "
    "but Gate 3 (ΔBrier ≥ +0.005) fails at every β. Symmetric corrects "
    "the asymmetric bias but provides ZERO incremental signal on top of "
    "the strength prior. A ruled out in both modes.",
    "FAIL verdict: A + C both killed. No v3 predictor changes ship. "
    "Lock_v3 prediction values mirror lock_v2 (same CalibratedDIBPPredictor "
    "with v2 toggles ON, use_market_value=False). The v3 lock exists "
    "purely as the audit artifact documenting the additional A + C "
    "falsification evidence. See Papers/WC2026_V3_RESULTS.md for full "
    "methodology + per-tournament breakdowns.",
    "Lock_v1 (commit 8c0ce19, bayesian_bivariate_xg_blended ρ=0.0 α=0.20) "
    "remains the WC2026 production path. lock_v3.json NOT registered in "
    "ModelRegistry. Parent locks: lock.json (v1, production), lock_v2.json "
    "(v2 FAIL audit). v3 ships Pinnacle CLV infrastructure (Ola 2.D) "
    "in parallel; that's the only positive-functionality deliverable "
    "of this sprint.",
    "Sprint outcome distribution: matches the ~20% pessimistic case "
    "from Papers/WC2026_V3_CANDIDATES_EVALUATION.md §3.1 — both A and C "
    "fail gates, lock_v1 unchanged, v3 documented as rigorous negative "
    "result. Lock_v1 baseline confirmed as strong local optimum at this "
    "corpus scale across DIBP, beta-cal, match-importance (v2 spike), "
    "hierarchical Bayesian, and Transfermarkt market value (v3 spike).",
)

FORCED_EMIT_REASON = (
    "Ola 3.F FAIL-verdict v3 audit emission. The v3 spike (Olas 0-2.D) "
    "explored two new academic signals on the WC2026 hold-out: hierarchical "
    "Bayesian pooling (Macrì-Demartino 2024) for the AFCON regime, and "
    "Transfermarkt squad market value covariate (Peeters 2018) in both "
    "attack-only and symmetric variants. C killed at toy feasibility (PyMC "
    "NUTS divergences + ESS < gate). A killed across 10 β values × 2 modes "
    "(no improvement direction; mechanism subsumed by strength prior). "
    "Per .planning/wc2026-improvement-v3/PLAN.md §'Verdict matrix' = FAIL "
    "branch: lock_v3.json written for post-mortem but NOT registered; "
    "lock_v1 ships unchanged. Pinnacle CLV (Ola 2.D) ships separately as "
    "infrastructure."
)


def emit_lock_v3(
    git_sha: str | None = None,
    output_path: Path | None = None,
    locked_at: datetime | None = None,
) -> Path:
    """Emit lock_v3.json with FAIL-verdict audit metadata."""
    target = output_path or LOCK_V3_PATH

    print("Building v2 baseline predictor (v3 A+C both FAIL ⇒ no signal added)...")
    split = build_split()
    pipeline_result = fit_v2_pipeline(
        train=split.train,
        calibration=split.calibration,
        reference_date=datetime.now(UTC).date(),
        use_dibp=True,
        use_beta_calibration=True,
        use_match_importance=True,
        use_market_value=False,  # A FAIL — explicit
    )
    predictor: CalibratedDIBPPredictor = pipeline_result.predictor
    print(
        f"  Pipeline fit: n_train={split.train.height}, "
        f"n_cal={split.calibration.height}, n_heldout={split.heldout.height}"
    )

    print(f"Loading lock_v1 fixtures from {_LOCK_V1_PATH}...")
    lock_v1_fixtures = _load_lock_v1_fixtures()
    print(f"  {len(lock_v1_fixtures)} fixtures to predict")

    print("Building fixture predictions...")
    fixtures: list[FixtureLockedPredictions] = []
    for fx in lock_v1_fixtures:
        pred = predictor.predict(fx["home_team_name"], fx["away_team_name"])
        fixtures.append(
            FixtureLockedPredictions(
                match_id=fx["match_id"],
                tournament_phase=fx["tournament_phase"],
                kickoff_utc=datetime.fromisoformat(
                    fx["kickoff_utc"].replace("Z", "+00:00")
                ),
                home_team_id=fx["home_team_id"],
                away_team_id=fx["away_team_id"],
                home_team_name=fx["home_team_name"],
                away_team_name=fx["away_team_name"],
                predictions={
                    PREDICTOR_NAME: {
                        "p_home_win": pred.p_home_win,
                        "p_draw": pred.p_draw,
                        "p_away_win": pred.p_away_win,
                        "p_btts": pred.p_btts,
                        "p_over_2_5": pred.p_over_2_5,
                    }
                },
            )
        )

    verdict = PredictorGateVerdict(
        predictor_name=PREDICTOR_NAME,
        n_markets=3,
        market_statuses={
            "1X2": "below-gate",
            "btts": "below-gate",
            "goals_total_o_u_2_5": "below-gate",
        },
        market_brier_for_gate={
            "1X2": BACKTEST_METRICS["1x2"]["brier_for_gate"],
            "btts": BACKTEST_METRICS["btts"]["brier_for_gate"],
            "goals_total_o_u_2_5": BACKTEST_METRICS["goals_total_o_u_2_5"][
                "brier_for_gate"
            ],
        },
        market_classwise_ece={
            "1X2": BACKTEST_METRICS["1x2"]["ece"],
            "btts": BACKTEST_METRICS["btts"]["ece"],
            "goals_total_o_u_2_5": BACKTEST_METRICS["goals_total_o_u_2_5"]["ece"],
        },
        overall_status="below-gate",
    )
    decision = LockDecision(
        evaluated_at=datetime.now(UTC),
        git_sha=git_sha,
        held_out_tournaments=("wc_2022", "afcon_2023", "copa_2024", "euro_2024"),
        n_fixtures_total=72,
        n_fixtures_with_predictions=72,
        coverage_threshold=DEFAULT_COVERAGE_THRESHOLD,
        predictor_verdicts=(verdict,),
        calibration_status="below-gate",
        operator_overrides=OPERATOR_OVERRIDES_V3,
    )

    print(f"Emitting lock to {target}...")
    emit_lock_json(
        decision=decision,
        fixtures=tuple(fixtures),
        tournament_slug="world_cup_2026",
        git_sha=git_sha,
        output_path=target,
        force=True,  # below-gate status requires explicit force
        forced_emit_reason=FORCED_EMIT_REASON,
        locked_at=locked_at,
    )
    print(f"Wrote {target}")
    return target


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help=f"Output path (default: {LOCK_V3_PATH})",
    )
    parser.add_argument(
        "--git-sha", type=str, default=None, help="Optional git SHA stamp."
    )
    args = parser.parse_args(argv)

    out = emit_lock_v3(git_sha=args.git_sha, output_path=args.output)
    print(f"\nLock_v3 emitted: {out}")
    print(f"Size: {out.stat().st_size:,} bytes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
