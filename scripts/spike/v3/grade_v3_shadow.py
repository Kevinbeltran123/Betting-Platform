"""Grade v3 shadow picks for a given day.

Reads picks from ``data/cache/v3_shadow/dt=YYYY-MM-DD/picks.parquet``,
fetches each fixture's FT state via Sportmonks, computes win/loss/void/
pending per pick, writes ``picks_outcomes.parquet`` to the same
partition.

Idempotent. Picks for fixtures not yet finished are marked "pending"
and the next run picks them up.

Usage::

    uv run python -m scripts.spike.v3.grade_v3_shadow --date 2026-05-12
    uv run python -m scripts.spike.v3.grade_v3_shadow  # default = today UTC
    uv run python -m scripts.spike.v3.grade_v3_shadow --date 2026-05-12 --dry-run

Exit codes:
    0 — all picks for the day are settled (graded successfully)
    2 — partial: some picks remain pending (fixtures not finished yet)
    1 — runtime error
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from bip.evaluation.live.engine_v3.runtime.v3_grader import (  # noqa: E402
    grade_picks_for_date,
    write_outcomes_parquet,
)
from bip.evaluation.live.engine_v3.shadow_logger import (  # noqa: E402
    DEFAULT_SHADOW_ROOT,
)
from bip.sports.football.sportmonks.client import (  # noqa: E402
    sportmonks_client_from_env,
)


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--date",
        type=str,
        default=None,
        help="YYYY-MM-DD (UTC). Defaults to today UTC.",
    )
    p.add_argument(
        "--shadow-root",
        type=Path,
        default=DEFAULT_SHADOW_ROOT,
        help="Root of v3 shadow log partitions",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Compute outcomes but do not write picks_outcomes.parquet",
    )
    return p.parse_args(argv)


async def _run(args: argparse.Namespace) -> int:
    date_iso = args.date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    partition = args.shadow_root / f"dt={date_iso}"

    async with sportmonks_client_from_env() as client:
        graded, report = await grade_picks_for_date(
            date_iso, shadow_root=args.shadow_root, client=client,
        )

    print(f"=== v3 grade — {date_iso} UTC ===")
    print(f"picks input:        {report.n_picks_input}")
    print(f"fixtures:           {report.n_fixtures} ({report.n_fixtures_finished} finished)")
    print(f"won / lost / void:  {report.n_won} / {report.n_lost} / {report.n_void}")
    print(f"pending:            {report.n_pending}")
    print(f"ungradable:         {report.n_ungradable}")

    if not graded:
        print("no picks to grade — exiting")
        return 0

    if args.dry_run:
        print(f"--dry-run: not writing picks_outcomes.parquet to {partition}")
        return 2 if report.n_pending > 0 else 0

    path = write_outcomes_parquet(graded, partition)
    print(f"wrote {len(graded)} outcomes → {path}")
    return 2 if report.n_pending > 0 else 0


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    try:
        return asyncio.run(_run(args))
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
