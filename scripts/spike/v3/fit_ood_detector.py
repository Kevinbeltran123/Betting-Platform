"""Fit the v3 OOD detector and persist it to disk.

Cold-start strategy:
1. Try to load real GSVs from shadow-mode recorded states. Phase-1
   `LineRecorder` snapshots market lines, not full GSVs, so this path
   is empty for now (no full-GSV stream persists). Reserved for when
   the shadow logger grows that capability.
2. Fallback: synthesize a realistic spread of GSVs spanning common
   minute/score/stat regimes, plus the 50 anti-Napoli regression
   states (those are in-distribution by design — they're examples
   of "dominant trailing in window", a regime the v3 system needs
   to handle confidently, not flag away).

Output: `data/cache/ood_detector_v1.pkl` (joblib).

Usage:
    uv run python -m scripts.spike.v3.fit_ood_detector
    uv run python -m scripts.spike.v3.fit_ood_detector --n 400
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from bip.evaluation.live.engine_v3 import (  # noqa: E402
    GSVBuilder,
    MarketLine,
    MarketSnapshot,
    OODDetector,
    PreMatchPriors,
)
from bip.sports.football.sportmonks.types import StatType  # noqa: E402
from tests.evaluation.live.engine_v3.conftest import HOME_ID, make_state  # noqa: E402
from tests.evaluation.live.engine_v3.test_anti_napoli import (  # noqa: E402
    _synthesize_states,
)


from datetime import datetime, timedelta, timezone


def _minimal_markets() -> MarketSnapshot:
    now = datetime.now(timezone.utc)
    return MarketSnapshot(lines={
        "match_goals_over_2.5": MarketLine(
            market_id="match_goals_over_2.5",
            side_a_decimal=1.95, side_b_decimal=1.95,
            line_value=2.5, max_stake_cap=500.0,
            last_update_utc=now - timedelta(seconds=20),
        ),
    })


def _realistic_priors() -> PreMatchPriors:
    return PreMatchPriors(
        lambda_home_prematch=1.6, lambda_away_prematch=1.1,
        expected_corners_total=10.0, expected_cards_total=4.0,
    )


def _napoli_priors() -> PreMatchPriors:
    return PreMatchPriors(
        lambda_home_prematch=2.30, lambda_away_prematch=0.95,
        expected_corners_total=10.8, expected_cards_total=4.10,
        elo_diff=140.0,
    )


def _generate_realistic_gsvs(n: int, seed: int = 42):
    """Diverse realistic GSVs spanning common live-football regimes."""
    rng = np.random.default_rng(seed)
    builder = GSVBuilder()
    priors = _realistic_priors()
    markets = _minimal_markets()
    score_grid = [(0, 0), (1, 0), (0, 1), (1, 1), (2, 1), (1, 2), (2, 0), (0, 2)]
    out = []
    for _ in range(n):
        minute = int(rng.integers(5, 88))
        h, a = score_grid[int(rng.integers(0, len(score_grid)))]
        scale = max(0.4, minute / 60.0)
        home_stats = {
            StatType.SHOTS_TOTAL: int(rng.integers(2, 7) * scale),
            StatType.SHOTS_ON_TARGET: int(rng.integers(0, 4) * scale),
            StatType.SHOTS_INSIDEBOX: int(rng.integers(0, 4) * scale),
            StatType.BIG_CHANCES_CREATED: int(rng.integers(0, 2)),
            StatType.CORNERS: int(rng.integers(0, 5) * scale),
            StatType.BALL_POSSESSION: float(rng.normal(52.0, 6.0)),
            StatType.DANGEROUS_ATTACKS: int(rng.integers(8, 40) * scale),
            StatType.KEY_PASSES: int(rng.integers(1, 8) * scale),
        }
        away_stats = {
            StatType.SHOTS_TOTAL: int(rng.integers(1, 6) * scale),
            StatType.SHOTS_ON_TARGET: int(rng.integers(0, 3) * scale),
            StatType.SHOTS_INSIDEBOX: int(rng.integers(0, 3) * scale),
            StatType.BIG_CHANCES_CREATED: int(rng.integers(0, 2)),
            StatType.CORNERS: int(rng.integers(0, 4) * scale),
            StatType.BALL_POSSESSION: float(100.0 - home_stats[StatType.BALL_POSSESSION]),
            StatType.DANGEROUS_ATTACKS: int(rng.integers(6, 30) * scale),
            StatType.KEY_PASSES: int(rng.integers(1, 6) * scale),
        }
        state = make_state(
            home_goals=h, away_goals=a, minute=minute,
            home_stats=home_stats, away_stats=away_stats,
        )
        out.append(builder.build(state, priors=priors, markets=markets))
    return out


def _generate_napoli_gsvs():
    """The 50 anti-Napoli regression states. In-distribution by design."""
    builder = GSVBuilder()
    priors = _napoli_priors()
    markets = _minimal_markets()
    return [
        builder.build(s, priors=priors, markets=markets, dominant_team_id=HOME_ID)
        for s in _synthesize_states()
    ]


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--n", type=int, default=300,
                   help="Number of realistic synthetic GSVs to add (default 300)")
    p.add_argument("--out", type=Path,
                   default=Path("data/cache/ood_detector_v1.pkl"))
    p.add_argument("--threshold-percentile", type=float, default=99.0)
    p.add_argument("--regularization", type=float, default=1e-2)
    p.add_argument("--seed", type=int, default=42)
    args = p.parse_args()

    realistic = _generate_realistic_gsvs(args.n, seed=args.seed)
    napoli = _generate_napoli_gsvs()
    total = realistic + napoli
    print(f"Training GSVs: {len(realistic)} realistic + {len(napoli)} anti-Napoli = {len(total)}")

    det = OODDetector().fit(
        total,
        regularization=args.regularization,
        threshold_percentile=args.threshold_percentile,
    )
    print(f"Fitted: n_train={det.n_train}  threshold={det.threshold:.3f}  "
          f"regularization={det.regularization:.4g}")

    # Sanity: 50 Napoli states must mostly pass.
    flagged = sum(int(det.is_ood(g)) for g in napoli)
    print(f"Anti-Napoli sanity: {flagged}/{len(napoli)} flagged "
          f"({100 * flagged / len(napoli):.1f}%)")
    if flagged / len(napoli) > 0.05:
        print(f"WARNING: anti-Napoli flag rate > 5% — rule #9 may short-circuit rule #2",
              file=sys.stderr)

    out_path = det.save(args.out)
    print(f"Persisted to: {out_path}  ({out_path.stat().st_size:,} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
