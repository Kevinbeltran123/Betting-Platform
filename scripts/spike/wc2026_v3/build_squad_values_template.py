"""Generate an empty CSV template for operator-driven squad-value entry.

Reads team names from the existing martj42 + StatsBomb training corpora
and emits a CSV with one row per unique team across the 4 hold-out
tournaments + WC2026 entrants, with the ``market_value_eur`` column
left blank for the operator to fill in.

This is the cheapest path to unblocking Ola 2.A's ablation. Operator
fills the template once (~2 hours of TM browsing or 30 min if a Kaggle
dataset is available), then runs scrape_transfermarkt.py --from-csv to
produce the parquet.

Usage:

    uv run python scripts/spike/wc2026_v3/build_squad_values_template.py \\
        --output data/cache/transfermarkt/squad_values_template.csv

The output CSV has 3 columns:
    team_name,tournament,market_value_eur

The tournament column is informational only (helps the operator group
entries) — load_squad_values() in the pipeline ignores it. The
``--filter-tournament`` flag emits a subset per tournament.

NOTE: The team-name canonicalization here must MATCH the names used in
the martj42 + StatsBomb corpora exactly. If the operator pastes values
for "Côte d'Ivoire" but the corpus calls them "Ivory Coast", the
offset lookup will silently fall through to 0.0 (graceful but useless
for that team). This script reads team names FROM the corpus directly
so the canonical spelling is preserved.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import polars as pl


# Hard-coded hold-out tournament boundaries — matches v2 PLAN.md
# §"Data split". When new tournaments are added, update here.
HOLD_OUT_TOURNAMENTS = [
    ("FIFA World Cup", "wc2022", "2022-11-20", "2022-12-18"),
    ("Africa Cup of Nations", "afcon2023", "2024-01-13", "2024-02-11"),
    ("Copa America", "copa2024", "2024-06-20", "2024-07-15"),
    ("UEFA Euro", "euro2024", "2024-06-14", "2024-07-15"),
    ("FIFA World Cup", "wc2026", "2026-06-11", "2026-07-19"),
]


def _safe_load_martj42() -> pl.DataFrame | None:
    """Best-effort load of martj42 from the canonical cache path."""
    candidates = [
        Path("data/cache/martj42_international_results.csv"),
        Path("data/cache/martj42/results.csv"),
    ]
    for c in candidates:
        if c.exists():
            return pl.read_csv(c)
    return None


def extract_tournament_teams(
    df: pl.DataFrame, tournament_name: str, start: str, end: str
) -> set[str]:
    """Return the set of distinct team names that played in the window."""
    subset = df.filter(
        (pl.col("tournament") == tournament_name)
        & (pl.col("date") >= start)
        & (pl.col("date") <= end)
    )
    home = set(subset["home_team"].to_list())
    away = set(subset["away_team"].to_list())
    return home | away


def build_template(filter_tournament: str | None = None) -> pl.DataFrame:
    """Build the template DataFrame (team_name, tournament, market_value_eur)."""
    df = _safe_load_martj42()
    if df is None:
        # Fall back to manual hard-coded list of WC2026 confederations
        # if martj42 isn't available. Operator fills in tournaments by hand.
        return pl.DataFrame(
            {
                "team_name": [],
                "tournament": [],
                "market_value_eur": [],
            },
            schema={
                "team_name": pl.String,
                "tournament": pl.String,
                "market_value_eur": pl.Float64,
            },
        )

    rows: list[dict] = []
    for tname, slug, start, end in HOLD_OUT_TOURNAMENTS:
        if filter_tournament and slug != filter_tournament:
            continue
        teams = extract_tournament_teams(df, tname, start, end)
        for team in sorted(teams):
            rows.append(
                {"team_name": team, "tournament": slug, "market_value_eur": None}
            )
    return pl.DataFrame(rows)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Output CSV path. Parent dirs created if missing.",
    )
    parser.add_argument(
        "--filter-tournament",
        type=str,
        default=None,
        help=(
            "Emit only one tournament's squads. Default: emit all 5. "
            "Slugs: wc2022, afcon2023, copa2024, euro2024, wc2026."
        ),
    )
    args = parser.parse_args(argv)

    df = build_template(filter_tournament=args.filter_tournament)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    df.write_csv(args.output)
    n_total = df.height
    print(f"Wrote {n_total} squad rows to {args.output}")
    if n_total == 0:
        print(
            "WARNING: martj42 corpus not found. Template is empty — "
            "operator must populate team_name + market_value_eur by hand.",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
