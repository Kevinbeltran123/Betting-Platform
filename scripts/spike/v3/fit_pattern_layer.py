"""Fit the v3 Pattern Layer kNN index and persist it.

Cold-start strategy (mirrors fit_ood_detector.py):
1. Try to load real (GSV, fired_thesis) pairs from shadow data. The
   Phase-1 ShadowLogger persists picks but not full GSVs yet; reserved
   for when the recorder grows that capability.
2. Fallback: synthesize a 250-sample mix of:
   - The 50 anti-Napoli regression states (each paired with the
     dominant_losing_napoli thesis they fire).
   - 200 generic realistic states (each paired with whichever archetype
     fires in the rule layer — silent states are skipped).

Output: `data/cache/pattern_layer_v1.pkl` (joblib).

Usage:
    uv run python -m scripts.spike.v3.fit_pattern_layer
    uv run python -m scripts.spike.v3.fit_pattern_layer --n 500
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from bip.evaluation.live.engine_v3 import (  # noqa: E402
    GSVBuilder,
    MarketLine,
    MarketSnapshot,
    PatternLayer,
    PreMatchPriors,
)
from bip.evaluation.live.engine_v3.archetypes import generate_theses  # noqa: E402
from bip.evaluation.live.engine_v3.thesis import ThesisArchetype  # noqa: E402
from bip.sports.football.sportmonks.types import StatType  # noqa: E402
from tests.evaluation.live.engine_v3.conftest import HOME_ID, make_state  # noqa: E402
from tests.evaluation.live.engine_v3.test_anti_napoli import (  # noqa: E402
    _synthesize_states,
)


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


def _napoli_priors() -> PreMatchPriors:
    return PreMatchPriors(
        lambda_home_prematch=2.30, lambda_away_prematch=0.95,
        expected_corners_total=10.8, expected_cards_total=4.10,
        elo_diff=140.0,
    )


def _realistic_priors() -> PreMatchPriors:
    return PreMatchPriors(
        lambda_home_prematch=1.6, lambda_away_prematch=1.1,
        expected_corners_total=10.0, expected_cards_total=4.0,
    )


def _napoli_pairs():
    builder = GSVBuilder()
    priors = _napoli_priors()
    markets = _minimal_markets()
    out = []
    for state in _synthesize_states():
        gsv = builder.build(state, priors=priors, markets=markets,
                            dominant_team_id=HOME_ID)
        theses = generate_theses(gsv)
        if not theses:
            continue
        napoli = next(
            (t for t in theses
             if t.archetype is ThesisArchetype.DOMINANT_LOSING_NAPOLI),
            theses[0],
        )
        out.append((gsv, napoli))
    return out


def _realistic_pairs(n: int, seed: int = 7):
    rng = np.random.default_rng(seed)
    builder = GSVBuilder()
    priors = _realistic_priors()
    markets = _minimal_markets()
    score_grid = [(0, 0), (1, 0), (0, 1), (1, 1), (2, 1), (1, 2), (2, 0), (0, 2)]
    out: list[tuple] = []
    attempts = 0
    # ~14% of random states fire a rule-layer thesis; budget 20× to hit n.
    while len(out) < n and attempts < 20 * n:
        attempts += 1
        minute = int(rng.integers(5, 88))
        h, a = score_grid[int(rng.integers(0, len(score_grid)))]
        scale = max(0.4, minute / 60.0)
        state = make_state(
            home_goals=h, away_goals=a, minute=minute,
            home_stats={
                StatType.SHOTS_TOTAL: int(rng.integers(2, 8) * scale),
                StatType.SHOTS_ON_TARGET: int(rng.integers(0, 4) * scale),
                StatType.SHOTS_INSIDEBOX: int(rng.integers(0, 4) * scale),
                StatType.BIG_CHANCES_CREATED: int(rng.integers(0, 2)),
                StatType.CORNERS: int(rng.integers(0, 6) * scale),
                StatType.BALL_POSSESSION: float(rng.normal(52.0, 6.0)),
                StatType.DANGEROUS_ATTACKS: int(rng.integers(8, 40) * scale),
                StatType.KEY_PASSES: int(rng.integers(1, 8) * scale),
            },
            away_stats={
                StatType.SHOTS_TOTAL: int(rng.integers(1, 6) * scale),
                StatType.SHOTS_ON_TARGET: int(rng.integers(0, 3) * scale),
                StatType.SHOTS_INSIDEBOX: int(rng.integers(0, 3) * scale),
                StatType.BIG_CHANCES_CREATED: int(rng.integers(0, 2)),
                StatType.CORNERS: int(rng.integers(0, 4) * scale),
                StatType.BALL_POSSESSION: 50.0,
                StatType.DANGEROUS_ATTACKS: int(rng.integers(6, 30) * scale),
                StatType.KEY_PASSES: int(rng.integers(1, 6) * scale),
            },
        )
        gsv = builder.build(state, priors=priors, markets=markets)
        theses = generate_theses(gsv)
        if not theses:
            continue
        out.append((gsv, theses[0]))
    return out


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--n", type=int, default=200,
                   help="Number of realistic synthetic pairs to add (default 200)")
    p.add_argument("--out", type=Path,
                   default=Path("data/cache/pattern_layer_v1.pkl"))
    p.add_argument("--seed", type=int, default=7)
    args = p.parse_args()

    napoli = _napoli_pairs()
    realistic = _realistic_pairs(args.n, seed=args.seed)
    pairs = napoli + realistic
    print(f"Training pairs: {len(napoli)} anti-Napoli + {len(realistic)} realistic = {len(pairs)}")

    layer = PatternLayer().fit(pairs)
    print(f"Fitted: n_records={len(layer.records)}  k={layer.cfg.k}  "
          f"max_neighbor_distance={layer.cfg.max_neighbor_distance}")

    out_path = layer.save(args.out)
    print(f"Persisted to: {out_path}  ({out_path.stat().st_size:,} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
