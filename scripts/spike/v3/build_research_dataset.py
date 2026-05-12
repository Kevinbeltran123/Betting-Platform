"""CLI for the v3 research dataset builder.

Joins gsv_log + picks + denials + outcomes from shadow log into one
canonical Polars parquet ready for any analysis notebook. Read-only
over the shadow source.

Usage::

    # Single day (today by default)
    uv run python -m scripts.spike.v3.build_research_dataset

    # Specific day
    uv run python -m scripts.spike.v3.build_research_dataset --date 2026-05-12

    # Multi-day range
    uv run python -m scripts.spike.v3.build_research_dataset \\
        --start 2026-05-10 --end 2026-05-12

    # Drop the heavy gsv_json column (smaller parquet, faster reload)
    uv run python -m scripts.spike.v3.build_research_dataset --no-gsv-json
"""
from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from bip.evaluation.live.engine_v3.runtime.research_dataset import (  # noqa: E402
    DEFAULT_RESEARCH_ROOT,
    build_research_dataset,
)
from bip.evaluation.live.engine_v3.shadow_logger import (  # noqa: E402
    DEFAULT_SHADOW_ROOT,
)


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--date", type=str, default=None,
                   help="YYYY-MM-DD single-day (mutually exclusive with --start/--end)")
    p.add_argument("--start", type=str, default=None, help="YYYY-MM-DD range start")
    p.add_argument("--end", type=str, default=None, help="YYYY-MM-DD range end")
    p.add_argument("--shadow-root", type=Path, default=DEFAULT_SHADOW_ROOT)
    p.add_argument("--output-root", type=Path, default=DEFAULT_RESEARCH_ROOT)
    p.add_argument("--no-gsv-json", action="store_true",
                   help="Drop the gsv_json column (smaller parquet)")
    return p.parse_args(argv)


def _resolve_range(args) -> tuple[datetime, datetime]:
    if args.date and (args.start or args.end):
        raise SystemExit("--date is mutually exclusive with --start/--end")

    def parse(d: str) -> datetime:
        return datetime.strptime(d, "%Y-%m-%d").replace(tzinfo=timezone.utc)

    if args.start and args.end:
        return parse(args.start), parse(args.end)
    if args.start or args.end:
        raise SystemExit("--start and --end must be provided together")
    if args.date:
        d = parse(args.date)
        return d, d
    today = datetime.now(timezone.utc)
    today = today.replace(hour=0, minute=0, second=0, microsecond=0)
    return today, today


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    start, end = _resolve_range(args)
    report = build_research_dataset(
        shadow_root=args.shadow_root,
        date_range=(start, end),
        output_root=args.output_root,
        include_gsv_json=not args.no_gsv_json,
    )

    print(f"=== v3 research dataset — {start.date()} to {end.date()} ===")
    print(f"partitions loaded:    {report.n_partitions_loaded}")
    print(f"frames (GSVs):        {report.n_frames}")
    print(f"picks:                {report.n_picks}")
    print(f"  with outcome:       {report.n_picks_with_outcome}")
    print(f"denials:              {report.n_denials}")
    print(f"output:               {report.output_path}")
    print()
    if report.n_frames == 0:
        print("WARNING: 0 frames loaded. Verify shadow_root has gsv_log.parquet")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
