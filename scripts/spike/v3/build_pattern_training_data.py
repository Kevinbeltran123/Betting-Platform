"""Inspector CLI for the GSV-thesis-outcome attribution join.

Read-only diagnostic tool. Loads the shadow root, runs the
training_data join, prints a structured report. Useful to:

- Verify the shadow root has enough real pairs for refit.
- Audit archetype distribution before each refit.
- Spot orphaned picks (no matching GSV) — symptom of a config gap.
- Inspect outcome attribution coverage when picks_outcomes.parquet
  is being populated.

Usage::

    uv run python -m scripts.spike.v3.build_pattern_training_data
    uv run python -m scripts.spike.v3.build_pattern_training_data \\
        --shadow-root data/cache/v3_shadow \\
        --window-days 14 \\
        --require-outcome
"""
from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from bip.evaluation.live.engine_v3.runtime.training_data import (  # noqa: E402
    build_real_pattern_pairs,
)
from bip.evaluation.live.engine_v3.shadow_logger import (  # noqa: E402
    DEFAULT_SHADOW_ROOT,
)


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--shadow-root",
        type=Path,
        default=DEFAULT_SHADOW_ROOT,
        help="Root of v3 shadow log partitions",
    )
    p.add_argument(
        "--window-days",
        type=int,
        default=30,
        help="Lookback window in days (default 30)",
    )
    p.add_argument(
        "--require-outcome",
        action="store_true",
        help="Drop pairs without a settled outcome",
    )
    p.add_argument(
        "--only-won",
        action="store_true",
        help="Keep only winning pairs (implies --require-outcome)",
    )
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    today = datetime.now(timezone.utc)
    start = today - timedelta(days=args.window_days)

    pairs, report = build_real_pattern_pairs(
        shadow_root=args.shadow_root,
        date_range=(start, today),
        require_outcome=args.require_outcome,
        only_won=args.only_won,
    )

    print(
        f"\n=== Pattern training data — last {args.window_days} days ==="
    )
    print(f"shadow_root: {args.shadow_root}")
    print(f"window: {start.date()} to {today.date()}")
    print()
    print(f"GSVs loaded:        {report.n_gsvs_loaded:>6}")
    print(f"Picks loaded:       {report.n_picks_loaded:>6}")
    print(f"Outcomes loaded:    {report.n_outcomes_loaded:>6}")
    print(f"Pairs built:        {report.n_pairs_built:>6}")
    print(f"  with outcome:     {report.n_pairs_with_outcome:>6}")
    print(f"    won:            {report.n_pairs_won:>6}")
    print(f"    lost:           {report.n_pairs_lost:>6}")
    print(f"    void:           {report.n_pairs_void:>6}")
    print(f"    pending:        {report.n_pairs_pending:>6}")
    print(f"Picks without GSV:  {report.n_picks_without_gsv:>6}")
    print()
    if report.archetype_distribution:
        print("Archetype distribution:")
        for arch, n in sorted(
            report.archetype_distribution.items(),
            key=lambda kv: -kv[1],
        ):
            print(f"  {arch:<35} {n:>4}")
    print()

    if report.n_pairs_built >= 50:
        print("Sample size meets pattern_layer min_samples_active=50 floor.")
    elif report.n_pairs_built >= 10:
        print(f"Sample size {report.n_pairs_built} below floor — refit will use synthetic + blend.")
    else:
        print(
            f"Sample size {report.n_pairs_built} too small for refit — "
            "synthetic-only mode will trigger."
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
