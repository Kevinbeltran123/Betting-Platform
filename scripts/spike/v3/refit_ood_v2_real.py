"""Re-fit the OOD detector on the 1642 real Day-3 GSVs.

T1 of the V3_DAY3_DIAGNOSIS spike. The v1 pkl (`data/cache/ood_detector_v1.pkl`)
was fit on 350 synthetic GSVs (300 realistic + 50 anti-Napoli). The Day-3
shadow run gave us 1642 real game-state vectors covering 20 fixtures across
Premier ucraniana, Greek SL, Saudi Pro, La Liga, Championship, etc. — a
genuine empirical distribution.

This script:
1. Loads the 1642 real GSVs from `data/cache/v3_shadow/dt=2026-05-12/gsv_log.parquet`
2. Fits a fresh OODDetector on them (threshold = p99 of training scores)
3. Mixes in the 50 anti-Napoli synthetic states so they stay in-distribution
   (rule #9 must not short-circuit rule #2 — see the comment in fit_ood_detector.py)
4. Validates: false-positive rate over the training set ≤1% by construction;
   anti-Napoli flag rate ≤5% as a hard guard.
5. Compares v1 vs v2 over the Day-3 frames: how much does the OOD verdict change?

Output: `data/cache/ood_detector_v2_real.pkl`. The v1 file is left untouched.

Usage:
    uv run python scripts/spike/v3/refit_ood_v2_real.py
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import polars as pl  # noqa: E402

from bip.evaluation.live.engine_v3.gsv import GameStateVector  # noqa: E402
from bip.evaluation.live.engine_v3.ood_detector import OODDetector  # noqa: E402


def load_day3_gsvs(path: Path) -> list[GameStateVector]:
    df = pl.read_parquet(path)
    return [GameStateVector.model_validate_json(s) for s in df["gsv_json"]]


def load_anti_napoli_states() -> list[GameStateVector]:
    """Re-use the existing fit_ood_detector synthesis path to keep the
    anti-Napoli cohort identical to v1's reference set."""
    from bip.evaluation.live.engine_v3 import (
        GSVBuilder,
        MarketLine,
        MarketSnapshot,
        PreMatchPriors,
    )
    from datetime import datetime, timedelta, timezone
    from tests.evaluation.live.engine_v3.conftest import HOME_ID
    from tests.evaluation.live.engine_v3.test_anti_napoli import _synthesize_states

    now = datetime.now(timezone.utc)
    markets = MarketSnapshot(
        lines={
            "match_goals_over_2.5": MarketLine(
                market_id="match_goals_over_2.5",
                side_a_decimal=1.95,
                side_b_decimal=1.95,
                line_value=2.5,
                max_stake_cap=500.0,
                last_update_utc=now - timedelta(seconds=20),
            ),
        }
    )
    priors = PreMatchPriors(
        lambda_home_prematch=2.30,
        lambda_away_prematch=0.95,
        expected_corners_total=10.8,
        expected_cards_total=4.10,
        elo_diff=140.0,
    )
    builder = GSVBuilder()
    return [
        builder.build(s, priors=priors, markets=markets, dominant_team_id=HOME_ID)
        for s in _synthesize_states()
    ]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--src",
        type=Path,
        default=Path("data/cache/v3_shadow/dt=2026-05-12/gsv_log.parquet"),
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("data/cache/ood_detector_v2_real.pkl"),
    )
    parser.add_argument("--threshold-percentile", type=float, default=99.0)
    parser.add_argument("--regularization", type=float, default=1e-2)
    parser.add_argument(
        "--include-napoli",
        action="store_true",
        default=True,
        help="Include the 50 anti-Napoli states in the training set (default: True)",
    )
    args = parser.parse_args()

    print(f"Loading Day-3 shadow GSVs from {args.src}…")
    day3 = load_day3_gsvs(args.src)
    print(f"Loaded {len(day3)} real GSVs from {len({g.fixture_id for g in day3})} fixtures.")

    napoli = load_anti_napoli_states() if args.include_napoli else []
    print(f"Anti-Napoli synthetic states: {len(napoli)}")

    training = day3 + napoli
    print(f"Total training: {len(training)}")

    det = OODDetector().fit(
        training,
        regularization=args.regularization,
        threshold_percentile=args.threshold_percentile,
    )
    print(
        f"Fitted v2: n_train={det.n_train}  threshold={det.threshold:.4f}  "
        f"regularization={det.regularization:.4g}"
    )

    # ── Validation ───────────────────────────────────────────────────
    # By construction, p99 cutoff over training means exactly 1% of training
    # is flagged. Verify and break out the day-3 cohort vs the napoli cohort.
    day3_scores = [det.score(g) for g in day3]
    day3_flagged = sum(int(det.is_ood(g)) for g in day3)
    napoli_flagged = sum(int(det.is_ood(g)) for g in napoli)
    print()
    print(f"Day-3 false-positive rate: {day3_flagged}/{len(day3)} "
          f"({100 * day3_flagged / max(len(day3), 1):.2f}%)")
    print(f"Anti-Napoli flag rate:      {napoli_flagged}/{len(napoli)} "
          f"({100 * napoli_flagged / max(len(napoli), 1):.2f}%)")

    import numpy as np
    arr = np.asarray(day3_scores)
    print(f"Day-3 score distribution: "
          f"min={arr.min():.2f} p50={np.percentile(arr, 50):.2f} "
          f"p90={np.percentile(arr, 90):.2f} p99={np.percentile(arr, 99):.2f} "
          f"max={arr.max():.2f}")

    if napoli_flagged / max(len(napoli), 1) > 0.05:
        print("WARNING: anti-Napoli flag rate > 5% — rule #9 would short-circuit rule #2",
              file=sys.stderr)
        return 1

    # ── Compare against v1 over the same Day-3 frames ────────────────
    v1_path = Path("data/cache/ood_detector_v1.pkl")
    if v1_path.exists():
        v1 = OODDetector.load(v1_path)
        v1_flagged_day3 = sum(int(v1.is_ood(g)) for g in day3)
        print()
        print(f"v1 (synthetic, n=350)  threshold={v1.threshold:.4f}  "
              f"Day-3 flagged: {v1_flagged_day3}/{len(day3)} "
              f"({100 * v1_flagged_day3 / max(len(day3), 1):.2f}%)")
        print(f"v2 (real,      n={det.n_train})  threshold={det.threshold:.4f}  "
              f"Day-3 flagged: {day3_flagged}/{len(day3)} "
              f"({100 * day3_flagged / max(len(day3), 1):.2f}%)")
        delta = v1_flagged_day3 - day3_flagged
        print(f"Δ: v2 flags {-delta:+d} more frames than v1 (negative = fewer flags)")

    out_path = det.save(args.out)
    print()
    print(f"Persisted v2 to: {out_path}  ({out_path.stat().st_size:,} bytes)")
    print("v1 pkl untouched.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
