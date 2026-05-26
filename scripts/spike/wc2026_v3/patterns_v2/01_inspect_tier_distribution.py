"""Inspect tier-A/B/C/D cell sizes for Lens 1 pre-registered boundaries.

If tier-A discovery n<30 or tier-D discovery n<30, boundaries are too tight —
flag and propose adjustment BEFORE running Lens 1.

Cell sizes determine whether tests are STRONG, MODERATE, or exploratory.
"""
from __future__ import annotations

import polars as pl

from _lib_v2 import load_enriched_with_mv, split_by, DISCOVERY_TOURNAMENTS, VALIDATION_TOURNAMENTS


def main() -> None:
    df = load_enriched_with_mv()
    print(f"Total matches: {len(df)}\n")

    print("=== Overall tier distribution ===")
    print(df.group_by("tier").len().sort("tier"))
    print()

    disc = split_by(df, DISCOVERY_TOURNAMENTS)
    val = split_by(df, VALIDATION_TOURNAMENTS)

    print(f"=== Discovery ({len(disc)} matches) ===")
    print(disc.group_by("tier").len().sort("tier"))
    print()

    print(f"=== Hold-out ({len(val)} matches) ===")
    print(val.group_by("tier").len().sort("tier"))
    print()

    print("=== Discovery × Phase ===")
    print(disc.group_by(["tier", "phase"]).len().sort(["tier", "phase"]))
    print()

    print("=== Hold-out × Phase ===")
    print(val.group_by(["tier", "phase"]).len().sort(["tier", "phase"]))
    print()

    print("=== Tier-A × Tournament (full corpus) ===")
    print(
        df.filter(pl.col("tier") == "A")
        .group_by("tournament_slug")
        .len()
        .sort("tournament_slug")
    )
    print()

    print("=== HT-state distribution (all matches with favorite defined) ===")
    print(
        df.filter(pl.col("favorite") != "none")
        .group_by("ht_state_relative")
        .len()
        .sort("ht_state_relative")
    )


if __name__ == "__main__":
    main()
