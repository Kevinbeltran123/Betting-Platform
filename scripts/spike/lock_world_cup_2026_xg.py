"""Lock WC2026 predictions via the xG-blended Bivariate predictor (R-08 slip plan).

Replaces the API-Football-dependent ``lock_world_cup_2026.py`` with a
fully-offline path:

1. Loads 72 group-stage fixtures from ``martj42_international_results.csv``
   (FIFA draw 2025-12-05 fixtures with home/away teams confirmed; goals null).
2. Warms up ``BayesianBivariateXGPredictor(rho=0.0, alpha=0.20)`` over the
   314 StatsBomb match outcomes already in the local cache. Every team that
   appears in WC 2018, Euro 2020, WC 2022, AFCON 2023, Copa 2024, Euro 2024
   carries its accumulated xG/goals state into WC2026.
3. Predicts each WC2026 fixture (no observe — match unplayed). Cold-start
   teams (Curaçao, Cabo Verde, Uzbekistan, etc.) use cohort priors.
4. Builds a ``LockDecision`` carrying the rolling-origin-CV verdict
   (n=135, calibration_status=below-gate) plus a substantive
   ``forced_emit_reason``.
5. Calls ``emit_lock_json(force=True, ...)`` per the R-08 slip plan and
   writes the artifact to ``locked_predictions/world_cup_2026/lock.json``.
6. Verifies the on-disk JSON via ``verify_lock_json``.

The forced_emit_reason cites the rolling-origin CV (commit 220cedb) so
post-tournament scoring has the full audit trail of why the predictor
locked below-gate. Per spike R-08: locking transparently with
``calibration_status='below-gate'`` is an honest fallback when iteration
won't reach pass before the deadline (2026-06-08).

Run::

    uv run python -m scripts.spike.lock_world_cup_2026_xg --confirm

NOT invoked by the scheduler.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import datetime, time, timezone
from pathlib import Path

# Allow running as `python scripts/spike/lock_world_cup_2026_xg.py`.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import polars as pl  # noqa: E402

from bip.evaluation.tournaments.backtest.calibration_report import (  # noqa: E402
    MARKET_1X2,
    MARKET_BTTS,
    MARKET_OU_2_5,
)
from bip.evaluation.tournaments.backtest.lock_emitter import (  # noqa: E402
    DEFAULT_LOCK_DIR,
    FixtureLockedPredictions,
    emit_lock_json,
    verify_lock_json,
)
from bip.evaluation.tournaments.backtest.lock_gate import (  # noqa: E402
    LockDecision,
    PredictorGateVerdict,
)
from scripts.backtest_int_tournaments import BacktestSnapshot  # noqa: E402
from scripts.run_phase5_backtest import (  # noqa: E402
    BayesianBivariateXGPredictor,
    make_snapshots,
)
from scripts.seed_statsbomb_tournaments import (  # noqa: E402
    DEFAULT_OUTCOMES_PARQUET as STATSBOMB_PARQUET,
)
from scripts.seed_statsbomb_tournaments import (  # noqa: E402
    load_outcomes_from_parquet,
)

# ── Paths ────────────────────────────────────────────────────────────────────

MARTJ42_CSV = Path("data/cache/martj42_international_results.csv")

# ── Predictor configuration (frozen at lock time) ────────────────────────────

# Per spike commits e05a5ec (ρ tuner) and 98c1812 (α tuner), the SOTA
# train-time parameters are:
LOCK_RHO = 0.0
LOCK_ALPHA = 0.20  # 80% xG, 20% goals — operator-empirical sweet spot
LOCK_PREDICTOR_NAME = "bayesian_bivariate_xg_blended"

# ── Rolling-origin CV verdict (commit 220cedb) ───────────────────────────────
# These are the n=135 forward-validated metrics from the chronologically-
# valid CV across 3 folds (AFCON 2023 + Copa 2024 + Euro 2024 held-out).
# See SPIKE-wc2026-calibration-lock.md decision log row 2026-05-09.

CV_METRICS = {
    MARKET_1X2:    {"brier": 0.2156, "ece": 0.1074, "ci": (0.2027, 0.2290)},
    MARKET_BTTS:   {"brier": 0.2542, "ece": 0.1068, "ci": (0.2475, 0.2609)},
    MARKET_OU_2_5: {"brier": 0.2536, "ece": 0.0931, "ci": (0.2438, 0.2634)},
}

CV_HELD_OUT_TOURNAMENTS = ("afcon_2023", "copa_2024", "euro_2024")
CV_N_TOTAL = 135  # 52 + 32 + 51

FORCED_EMIT_REASON = (
    "R-08 slip plan. Rolling-origin CV (n=135, 3 chronologically-valid "
    "folds: AFCON 2023, Copa 2024, Euro 2024) on the xG-blended Bivariate "
    "predictor (rho=0.0, alpha=0.20, LogisticLogitCalibrator post-hoc) "
    "yielded: 1X2 Brier=0.2156 cal [95% CI 0.2027-0.2290], "
    "1X2 ECE=0.1074 cal. The 0.21 Brier gate sits within the CI "
    "(P(true<=gate) approx 30%) but the mean is above; ECE is 2.1x over "
    "the 0.05 gate, with calibrator known to overfit at n<500 (Walsh & "
    "Joshi 2024). BTTS Brier=0.2542, OU2.5 Brier=0.2536 - both clearly "
    "above 0.20 gate. Per-fold reveals AFCON 2023 as the worst regime "
    "(1X2 Brier=0.2271 cal) - regime shift not captured by cohort priors. "
    "Architectural improvements exhausted within scope (Bivariate ρ "
    "tuning + xG blending + LogisticLogitCalibrator); further gains "
    "require Understat club xG transfer (cross-reference risk) or "
    "Bivariate Negative Binomial (Michels SYNTHESIS Conclusion 2, "
    "research-grade). Locking transparently with calibration_status="
    "'below-gate' for honest post-tournament scoring. Spike commits: "
    "9cf9954 (Bivariate), e05a5ec (ρ tuner), 98c1812 (xG predictor), "
    "220cedb (rolling-origin CV)."
)


# ── martj42 → BacktestSnapshot conversion ────────────────────────────────────


def load_wc2026_fixtures(csv_path: Path = MARTJ42_CSV) -> pl.DataFrame:
    """Load the 72 WC2026 group-stage fixtures from martj42 (no scores yet)."""
    df = pl.read_csv(csv_path, null_values=["NA", ""], infer_schema_length=10000)
    wc26 = df.filter(
        (pl.col("tournament") == "FIFA World Cup")
        & (pl.col("date") >= "2026-01-01")
        & pl.col("home_score").is_null()
    )
    if wc26.height == 0:
        raise RuntimeError(
            "No WC2026 fixtures found in martj42 cache. Run "
            "`scripts/seed_international_history.py --refresh` to update."
        )
    return wc26.sort("date")


def fixtures_to_snapshots(
    fixtures_df: pl.DataFrame,
    team_id_map: dict[str, int],
) -> list[BacktestSnapshot]:
    """Convert WC2026 fixture rows to BacktestSnapshots without observed outcomes.

    ``team_id_map`` is mutated in place: any team not seen during warmup
    is assigned a new id (cold-start path — predictor uses cohort priors).
    """
    def _id(name: str) -> int:
        if name not in team_id_map:
            team_id_map[name] = len(team_id_map)
        return team_id_map[name]

    snapshots: list[BacktestSnapshot] = []
    for i, row in enumerate(fixtures_df.iter_rows(named=True)):
        snapshots.append(BacktestSnapshot(
            match_id=f"wc2026_grp_{i:03d}",
            tournament="world_cup_2026",
            home_team_id=_id(row["home_team"]),
            away_team_id=_id(row["away_team"]),
            # Unused-but-required fields. observed_* must be valid types but
            # the predictor only reads observed_home_goals / observed_away_goals
            # to decide whether to update state — None skips the update.
            observed_1x2=0,
            observed_total_goals=0,
            observed_btts=0,
            observed_home_goals=None,
            observed_away_goals=None,
            match_date=row["date"],
        ))
    return snapshots


# ── Warmup + prediction pipeline ─────────────────────────────────────────────


def warmup_predictor(
    predictor: BayesianBivariateXGPredictor,
    statsbomb_outcomes_path: Path = STATSBOMB_PARQUET,
) -> dict[str, int]:
    """Warm up the predictor's state by walking the StatsBomb cache forward.

    Returns the team_id_map built during warmup so subsequent WC2026 fixture
    conversion can reuse the same canonical IDs (Brazil at WC 2018 == Brazil
    at WC 2026).
    """
    outcomes = load_outcomes_from_parquet(statsbomb_outcomes_path)
    if not outcomes:
        raise RuntimeError(
            f"No StatsBomb outcomes at {statsbomb_outcomes_path}. "
            "Run `scripts/seed_statsbomb_tournaments.py` first."
        )
    snapshots, team_id_map = make_snapshots(outcomes)
    for snap in snapshots:
        predictor.predict_fixture(snap)  # also observes via within_tournament_step
    return team_id_map


def predict_wc2026_fixtures(
    predictor: BayesianBivariateXGPredictor,
    fixture_snaps: list[BacktestSnapshot],
    inverse_team_map: dict[int, str],
) -> list[FixtureLockedPredictions]:
    """Predict each unplayed WC2026 fixture and assemble lock-shaped records."""
    fixtures_locked: list[FixtureLockedPredictions] = []
    for snap in fixture_snaps:
        pred = predictor.predict_fixture(snap)
        # Markets the predictor doesn't emit are set to None — drop them
        # from the predictions dict so probability validators don't trip.
        markets: dict[str, float] = {
            "p_home_win": pred.p_home_win,
            "p_draw": pred.p_draw,
            "p_away_win": pred.p_away_win,
        }
        if pred.p_btts is not None:
            markets["p_btts"] = pred.p_btts
        if pred.p_over_2_5 is not None:
            markets["p_over_2_5"] = pred.p_over_2_5

        # Kickoff stays at midnight UTC since martj42 only has dates;
        # operator can refine with kickoff times if needed before lock.
        kickoff = datetime.combine(
            datetime.fromisoformat(snap.match_date).date(),
            time.min,
            tzinfo=timezone.utc,
        )

        fixtures_locked.append(FixtureLockedPredictions(
            match_id=snap.match_id,
            tournament_phase="group",
            kickoff_utc=kickoff,
            home_team_id=snap.home_team_id,
            away_team_id=snap.away_team_id,
            home_team_name=inverse_team_map[snap.home_team_id],
            away_team_name=inverse_team_map[snap.away_team_id],
            predictions={LOCK_PREDICTOR_NAME: markets},
        ))
    return fixtures_locked


# ── LockDecision construction (carries rolling-origin CV verdict) ───────────


def build_lock_decision(*, git_sha: str | None = None) -> LockDecision:
    """Assemble the LockDecision carrying the n=135 rolling-origin CV verdict.

    The status precedence in lock_gate.py would block the lock by default;
    we will pass through emit_lock_json with force=True to invoke the R-08
    slip plan path.
    """
    verdict = PredictorGateVerdict(
        predictor_name=LOCK_PREDICTOR_NAME,
        n_markets=3,
        market_statuses={
            MARKET_1X2: "below-gate",
            MARKET_BTTS: "below-gate",
            MARKET_OU_2_5: "below-gate",
        },
        market_brier_for_gate={
            MARKET_1X2: CV_METRICS[MARKET_1X2]["brier"],
            MARKET_BTTS: CV_METRICS[MARKET_BTTS]["brier"],
            MARKET_OU_2_5: CV_METRICS[MARKET_OU_2_5]["brier"],
        },
        market_classwise_ece={
            MARKET_1X2: CV_METRICS[MARKET_1X2]["ece"],
            MARKET_BTTS: CV_METRICS[MARKET_BTTS]["ece"],
            MARKET_OU_2_5: CV_METRICS[MARKET_OU_2_5]["ece"],
        },
        overall_status="below-gate",
    )
    return LockDecision(
        held_out_tournaments=CV_HELD_OUT_TOURNAMENTS,
        n_fixtures_total=CV_N_TOTAL,
        n_fixtures_with_predictions=CV_N_TOTAL,
        coverage_threshold=0.90,
        predictor_verdicts=(verdict,),
        calibration_status="below-gate",
        operator_overrides=(
            "rolling-origin CV (n=135, 3 chronologically-valid folds) — "
            "n=83 single held-out had +0.007 sample bias",
            "1X2 95% CI [0.2027, 0.2290] straddles 0.21 gate — "
            "P(true ≤ gate) ≈ 30%, but mean is over",
            "calibrator overfits at n<500 per Walsh & Joshi 2024",
        ),
        git_sha=git_sha,
    )


# ── Orchestration ────────────────────────────────────────────────────────────


def _current_git_sha() -> str | None:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True, text=True, check=True,
        )
        return out.stdout.strip()
    except (FileNotFoundError, subprocess.CalledProcessError):
        return None


def lock_world_cup_2026(
    *,
    output_path: Path | None = None,
    confirm: bool = False,
    statsbomb_outcomes_path: Path = STATSBOMB_PARQUET,
    martj42_csv: Path = MARTJ42_CSV,
) -> Path:
    """End-to-end: warmup → predict → emit lock JSON. Returns the written path."""
    if not confirm:
        raise RuntimeError(
            "Re-run with confirm=True to acknowledge that this writes a LOCKED "
            "lock JSON to disk. Lock artifacts are committed and the WC2026 "
            "tournament starts on 2026-06-11; do not run accidentally."
        )

    target = output_path if output_path is not None else (DEFAULT_LOCK_DIR / "lock.json")
    target.parent.mkdir(parents=True, exist_ok=True)

    print(f"[lock] WC2026 lock pipeline starting → {target}", file=sys.stderr)
    print(f"[lock] predictor: xg_blended (ρ={LOCK_RHO}, α={LOCK_ALPHA})", file=sys.stderr)

    # 1. Build predictor + warm up state
    predictor = BayesianBivariateXGPredictor(rho=LOCK_RHO, alpha=LOCK_ALPHA)
    print("[lock] warming up predictor over StatsBomb cache (314 matches)...",
          file=sys.stderr)
    team_id_map = warmup_predictor(predictor, statsbomb_outcomes_path)
    print(f"[lock] warmup complete — {len(team_id_map)} teams have state",
          file=sys.stderr)

    # 2. Load WC2026 fixtures + register cold-start teams
    fixtures_df = load_wc2026_fixtures(martj42_csv)
    print(f"[lock] loaded {fixtures_df.height} WC2026 fixtures from martj42",
          file=sys.stderr)
    n_teams_pre = len(team_id_map)
    fixture_snaps = fixtures_to_snapshots(fixtures_df, team_id_map)
    n_cold_start = len(team_id_map) - n_teams_pre
    print(f"[lock] cold-start teams (no prior tournament data): {n_cold_start}",
          file=sys.stderr)

    inverse_team_map = {v: k for k, v in team_id_map.items()}

    # 3. Predict each fixture
    fixtures_locked = predict_wc2026_fixtures(predictor, fixture_snaps, inverse_team_map)
    print(f"[lock] predicted {len(fixtures_locked)} fixtures", file=sys.stderr)

    # 4. Build LockDecision + emit
    git_sha = _current_git_sha()
    decision = build_lock_decision(git_sha=git_sha)

    lock_json = emit_lock_json(
        decision, fixtures_locked,
        tournament_slug="world_cup_2026",
        git_sha=git_sha,
        output_path=target,
        force=True,
        forced_emit_reason=FORCED_EMIT_REASON,
    )

    # 5. Verify what we just wrote
    loaded, is_valid = verify_lock_json(target)
    if not is_valid:
        raise RuntimeError(f"Lock JSON tamper-verification FAILED at {target}")

    print(file=sys.stderr)
    print("=" * 78, file=sys.stderr)
    print(f"LOCKED — {target}", file=sys.stderr)
    print("=" * 78, file=sys.stderr)
    print(f"  schema_version:      {loaded.schema_version}", file=sys.stderr)
    print(f"  tournament_slug:     {loaded.tournament_slug}", file=sys.stderr)
    print(f"  locked_at:           {loaded.locked_at}", file=sys.stderr)
    print(f"  calibration_status:  {loaded.calibration_status}", file=sys.stderr)
    print(f"  fixtures_locked:     {len(loaded.fixtures)}", file=sys.stderr)
    print(f"  cold_start_teams:    {n_cold_start} of "
          f"{len(set(t for f in loaded.fixtures for t in (f.home_team_id, f.away_team_id)))}",
          file=sys.stderr)
    print(f"  content_hash:        {loaded.content_hash[:16]}...", file=sys.stderr)
    print(f"  git_sha:             {loaded.git_sha or '(none)'}", file=sys.stderr)
    print(f"  tamper_verified:     {is_valid}", file=sys.stderr)
    print(file=sys.stderr)

    return target


def _cli() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--confirm", action="store_true", required=True,
                   help="Required: acknowledges this writes a LOCKED artifact.")
    p.add_argument("--output", type=Path, default=None,
                   help=f"Override output path (default {DEFAULT_LOCK_DIR / 'lock.json'}).")
    args = p.parse_args()
    try:
        lock_world_cup_2026(output_path=args.output, confirm=args.confirm)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(_cli())
