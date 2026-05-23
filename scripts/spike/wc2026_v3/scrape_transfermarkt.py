"""Transfermarkt squad-value acquisition CLI (Wave 1.A.3).

Two modes:

1. ``--from-csv`` — read an operator-supplied CSV (one row per team) and
   write it as parquet ready for ``fit_v2_pipeline(market_values_path=...)``.
   This is the FAST path: the operator fills a template (see
   ``build_squad_values_template.py``) by hand or from any data source
   (Kaggle Transfermarkt dataset, manual TM browse, paid TM API). No
   network calls. Idempotent.

2. ``--scrape`` — NotImplemented STUB. The actual scraping protocol is
   documented below for the operator to either:
   (a) implement themselves when ready,
   (b) wait for v4 if Ola 2.A's ablation shows A isn't worth chasing.

   The scrape stub is deliberately left as NotImplemented in Wave 1.A
   because:
   - The full scrape takes ~4 hours wall-clock (rate-limited)
   - Transfermarkt ToS makes redistribution non-trivial
   - Operator may already have a TM dataset (Kaggle has yearly snapshots)
     that avoids scraping entirely
   - The pipeline is fully validated against --from-csv input today; the
     scraping mode adds zero pipeline coverage

   When implementing --scrape later: see the SCRAPE_PROTOCOL section
   below for the URL pattern, polite-scraping config, and HTML selectors.

Usage:

    # Convert operator-supplied CSV to parquet (FAST path)
    uv run python scripts/spike/wc2026_v3/scrape_transfermarkt.py \\
        --from-csv data/cache/transfermarkt/squad_values_template.csv \\
        --output data/cache/transfermarkt/squad_values.parquet

    # (Future) Scrape from TM directly
    uv run python scripts/spike/wc2026_v3/scrape_transfermarkt.py \\
        --scrape --tournament wc2026 \\
        --output data/cache/transfermarkt/squad_values_wc2026.parquet

SCRAPE_PROTOCOL (for future implementer):

- URL pattern: ``https://www.transfermarkt.com/{slug}/startseite/verein/{id}/saison_id/{year}``
  - Slug + id mapping for national teams: maintain a small JSON map at
    ``scripts/spike/wc2026_v3/data/tm_team_ids.json``
  - Year format: 4-digit start of the tournament season (e.g., 2025 for
    a 2025-26 squad snapshot)
- Polite scraping: 1.5s sleep between requests; rotating User-Agent
  pool (3-5 modern browser strings); single-thread (do NOT parallelize
  to avoid burst rate-limiting)
- HTML selector for total value: ``span.right-td`` (Transfermarkt
  refactors this occasionally — verify before run)
- Idempotency: write per-team JSON to a staging dir, only assemble
  parquet at the end. Skip teams whose staging file already exists.
- Cloudflare detection: if response is HTML containing "Just a moment...",
  back off for 5 minutes and retry once; fail fast on second hit.
- Legal: personal-use only. Do NOT redistribute the resulting dataset
  per Transfermarkt browsewrap ToS (per Papers/WC2026_V3_CANDIDATES_
  EVALUATION.md §2.A.4 risk register).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import polars as pl

# Re-export the validation logic from the loader so the script can
# fail fast on a malformed CSV before writing anything.
from bip.evaluation.tournaments.wc2026_v2._market_data import load_squad_values


def convert_csv_to_parquet(csv_path: Path, parquet_path: Path) -> int:
    """Validate the operator CSV and write it as parquet.

    Uses ``load_squad_values`` to enforce the schema (team_name,
    market_value_eur columns required; no duplicate team_name rows).
    Returns the number of squads written.

    Raises FileNotFoundError if csv_path is missing, ValueError if the
    schema is wrong or there are duplicate teams.
    """

    values = load_squad_values(csv_path)
    if not values:
        raise ValueError(f"Empty CSV at {csv_path} — nothing to write")

    parquet_path.parent.mkdir(parents=True, exist_ok=True)
    df = pl.DataFrame(
        [
            {"team_name": team, "market_value_eur": value}
            for team, value in sorted(values.items())
        ]
    )
    df.write_parquet(parquet_path)
    return len(values)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--from-csv",
        type=Path,
        help="Convert an operator-supplied CSV (team_name, market_value_eur) to parquet.",
    )
    parser.add_argument(
        "--scrape",
        action="store_true",
        help="(STUB) Scrape Transfermarkt directly. NotImplemented in Wave 1.A.",
    )
    parser.add_argument(
        "--tournament",
        type=str,
        help="Tournament slug for --scrape mode (e.g., wc2026, afcon2023).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Output parquet path. Parent dirs created if missing.",
    )
    args = parser.parse_args(argv)

    if args.scrape:
        raise NotImplementedError(
            "Direct Transfermarkt scraping is not implemented in Wave 1.A. "
            "See module docstring SCRAPE_PROTOCOL for the design. Use "
            "--from-csv with a manually-filled or Kaggle-sourced CSV instead."
        )

    if args.from_csv is None:
        parser.error("Either --from-csv or --scrape must be provided")

    n = convert_csv_to_parquet(args.from_csv, args.output)
    print(f"Wrote {n} squad values to {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
