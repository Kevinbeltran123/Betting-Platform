"""Iter 3 — Cross-confederation patterns in WC matches.

UNIQUE TO WC. AFCON / Copa / Euro are single-confederation. The World
Cup is the only tournament in our corpus that mixes UEFA, CONMEBOL,
CAF, AFC, CONCACAF, OFC.

HYPOTHESIS. Lock_v1's strength prior is dominated by intra-confederation
results (martj42 + StatsBomb tournaments). It may systematically
miscalibrate cross-confederation matches because the comparison scale
is implicit.

TESTS:
  1. Per-confederation pair, compute empirical win rates vs predictor-
     implied win rates (using the walk-forward Brier file from Lens 5
     for n=199 hold-out matches; restrict to WC22 for confederation-
     mixed analysis since AFCON/Euro/Copa are single-conf).
  2. Per-confederation team over-performance vs cohort (whole-WC22).
  3. Specifically: CAF vs UEFA, AFC vs CONMEBOL — the matchups most
     dependent on cross-region calibration.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import polars as pl

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "scripts" / "spike" / "wc2026_v3" / "patterns_v2"))

from _lib_v2 import CACHE, bootstrap_diff_ci, load_enriched_with_mv  # noqa: E402

OUT = CACHE / "wc2026_v3" / "patterns_v2_iter3_cross_confederation.json"

# Team -> confederation mapping. Sources: FIFA / confederation membership.
# Covers teams in the StatsBomb corpus + likely WC2026 contenders.
CONFEDERATION: dict[str, str] = {
    # UEFA
    "France": "UEFA", "Germany": "UEFA", "England": "UEFA", "Spain": "UEFA",
    "Italy": "UEFA", "Portugal": "UEFA", "Netherlands": "UEFA",
    "Belgium": "UEFA", "Croatia": "UEFA", "Switzerland": "UEFA",
    "Denmark": "UEFA", "Sweden": "UEFA", "Poland": "UEFA",
    "Russia": "UEFA", "Wales": "UEFA", "Iceland": "UEFA",
    "Serbia": "UEFA", "Ukraine": "UEFA", "Austria": "UEFA",
    "Czech Republic": "UEFA", "Slovakia": "UEFA", "Romania": "UEFA",
    "Republic of Ireland": "UEFA", "Northern Ireland": "UEFA",
    "Hungary": "UEFA", "Turkey": "UEFA", "Greece": "UEFA",
    "Scotland": "UEFA", "Albania": "UEFA", "Finland": "UEFA",
    "North Macedonia": "UEFA", "Norway": "UEFA", "Slovenia": "UEFA",
    "Georgia": "UEFA",
    # CONMEBOL
    "Brazil": "CONMEBOL", "Argentina": "CONMEBOL", "Uruguay": "CONMEBOL",
    "Colombia": "CONMEBOL", "Chile": "CONMEBOL", "Peru": "CONMEBOL",
    "Ecuador": "CONMEBOL", "Paraguay": "CONMEBOL", "Bolivia": "CONMEBOL",
    "Venezuela": "CONMEBOL",
    # CAF
    "Morocco": "CAF", "Senegal": "CAF", "Egypt": "CAF", "Algeria": "CAF",
    "Tunisia": "CAF", "Ghana": "CAF", "Nigeria": "CAF",
    "Côte d'Ivoire": "CAF", "Ivory Coast": "CAF",
    "Cameroon": "CAF", "South Africa": "CAF", "Mali": "CAF",
    "Burkina Faso": "CAF", "DR Congo": "CAF", "Cape Verde": "CAF",
    "Equatorial Guinea": "CAF", "Gabon": "CAF", "Mauritania": "CAF",
    "Namibia": "CAF", "Angola": "CAF", "Sudan": "CAF",
    "Guinea": "CAF", "Madagascar": "CAF", "Tanzania": "CAF",
    "Zambia": "CAF", "Uganda": "CAF", "Niger": "CAF", "Togo": "CAF",
    "Comoros": "CAF", "Mozambique": "CAF", "Ethiopia": "CAF", "Libya": "CAF",
    "Benin": "CAF",
    # AFC
    "Japan": "AFC", "South Korea": "AFC", "Korea Republic": "AFC",
    "Saudi Arabia": "AFC", "Iran": "AFC", "Australia": "AFC",
    "Qatar": "AFC",
    # CONCACAF
    "USA": "CONCACAF", "United States": "CONCACAF", "Mexico": "CONCACAF",
    "Canada": "CONCACAF", "Costa Rica": "CONCACAF", "Panama": "CONCACAF",
    "Honduras": "CONCACAF", "Jamaica": "CONCACAF",
    # OFC
    "New Zealand": "OFC",
}


def conf_of(team: str) -> str:
    return CONFEDERATION.get(team, "UNK")


def main() -> None:
    df = load_enriched_with_mv()
    print(f"Loaded {len(df)} matches\n")

    # ------ Tag each match with home_conf / away_conf
    df = df.with_columns(
        [
            pl.col("home_team").map_elements(conf_of, return_dtype=pl.Utf8).alias("home_conf"),
            pl.col("away_team").map_elements(conf_of, return_dtype=pl.Utf8).alias("away_conf"),
        ]
    )

    # ------ Filter to WC only (only tournament with cross-conf matches)
    wc = df.filter(pl.col("tournament_slug").is_in(["wc_2018", "wc_2022"]))
    print(f"WC matches: {len(wc)}")

    # ------ Same-conf vs cross-conf split
    wc = wc.with_columns(
        (pl.col("home_conf") != pl.col("away_conf")).alias("is_cross_conf")
    )
    same = wc.filter(~pl.col("is_cross_conf"))
    cross = wc.filter(pl.col("is_cross_conf"))
    print(f"  same-conf: {len(same)}, cross-conf: {len(cross)}")

    # Outcome by side: did the FIRST-confederation-listed side win?
    # We compute UEFA-vs-X, CONMEBOL-vs-X, CAF-vs-X, AFC-vs-X separately.
    print("\n=== Cross-confederation matchup win rates (WC18 + WC22) ===\n")

    confs = ["UEFA", "CONMEBOL", "CAF", "AFC", "CONCACAF", "OFC"]
    pair_stats = {}
    for c1 in confs:
        for c2 in confs:
            if c1 >= c2:
                continue
            # Filter matches where one side is c1 and the other is c2
            sub = wc.filter(
                ((pl.col("home_conf") == c1) & (pl.col("away_conf") == c2))
                | ((pl.col("home_conf") == c2) & (pl.col("away_conf") == c1))
            )
            if len(sub) < 3:
                continue
            # Compute c1 wins / draws / c2 wins
            c1_wins = 0
            c2_wins = 0
            draws = 0
            for row in sub.iter_rows(named=True):
                hg, ag = row["home_goals"], row["away_goals"]
                if hg == ag:
                    draws += 1
                elif row["home_conf"] == c1 and hg > ag:
                    c1_wins += 1
                elif row["away_conf"] == c1 and ag > hg:
                    c1_wins += 1
                else:
                    c2_wins += 1
            n = len(sub)
            print(
                f"  {c1} vs {c2}: n={n} | "
                f"{c1}_win={c1_wins}/{n}={c1_wins/n:.2%} | "
                f"draw={draws/n:.2%} | "
                f"{c2}_win={c2_wins/n:.2%}"
            )
            pair_stats[f"{c1}_vs_{c2}"] = {
                "n": n,
                "c1": c1,
                "c2": c2,
                f"{c1}_wins": c1_wins,
                f"{c2}_wins": c2_wins,
                "draws": draws,
            }

    # ------ Per-conf team over-performance vs WC cohort
    print("\n=== Per-confederation team over-performance in WC (vs WC cohort) ===\n")

    home_rows = wc.select(
        [
            pl.col("home_team").alias("team"),
            pl.col("home_conf").alias("conf"),
            pl.col("home_goals").alias("goals_for"),
            pl.col("away_goals").alias("goals_against"),
        ]
    )
    away_rows = wc.select(
        [
            pl.col("away_team").alias("team"),
            pl.col("away_conf").alias("conf"),
            pl.col("away_goals").alias("goals_for"),
            pl.col("home_goals").alias("goals_against"),
        ]
    )
    all_team = pl.concat([home_rows, away_rows]).with_columns(
        [
            pl.when(pl.col("goals_for") > pl.col("goals_against"))
            .then(3)
            .when(pl.col("goals_for") == pl.col("goals_against"))
            .then(1)
            .otherwise(0)
            .alias("points"),
            (pl.col("goals_for") - pl.col("goals_against")).alias("gd"),
        ]
    )
    conf_agg = (
        all_team.group_by("conf")
        .agg(
            [
                pl.len().alias("n_team_matches"),
                pl.col("team").n_unique().alias("n_teams"),
                pl.col("points").mean().alias("ppm"),
                pl.col("gd").mean().alias("gd_per_match"),
                pl.col("goals_for").mean().alias("gf_per_match"),
                pl.col("goals_against").mean().alias("ga_per_match"),
            ]
        )
        .sort("ppm", descending=True)
    )
    print(conf_agg)
    overall_ppm = float(all_team["points"].mean())
    print(f"\n  Overall WC ppm baseline: {overall_ppm:.3f}")

    # ------ Cross-conf hold-out Brier (use walk-forward predictions)
    brier_path = CACHE / "wc2026_v3" / "patterns_v2_lens5_brier.parquet"
    if brier_path.exists():
        brier_df = pl.read_parquet(brier_path).join(
            df.select(["match_id", "home_team", "away_team", "tournament_slug"]),
            on="match_id",
            how="left",
            suffix="_meta",
        )
        brier_df = brier_df.with_columns(
            [
                pl.col("home_team").map_elements(conf_of, return_dtype=pl.Utf8).alias("home_conf"),
                pl.col("away_team").map_elements(conf_of, return_dtype=pl.Utf8).alias("away_conf"),
            ]
        ).with_columns(
            (pl.col("home_conf") != pl.col("away_conf")).alias("is_cross_conf")
        )

        # Only wc_2022 from hold-out has cross-conf
        wc22 = brier_df.filter(pl.col("tournament_slug") == "wc_2022")
        print(f"\n=== WC22 Brier by cross-conf (hold-out walk-forward) ===")
        for is_cross, sub in [(True, wc22.filter(pl.col("is_cross_conf"))),
                              (False, wc22.filter(~pl.col("is_cross_conf")))]:
            if len(sub) >= 5:
                arr = sub["brier_1x2"].to_numpy()
                print(f"  cross_conf={is_cross}: n={len(sub)}, mean_brier={arr.mean():.4f}")

        # Per-pairwise conf brier
        print("\n  Per-conf-pair mean Brier (WC22):")
        for c1 in confs:
            for c2 in confs:
                if c1 >= c2:
                    continue
                sub = wc22.filter(
                    ((pl.col("home_conf") == c1) & (pl.col("away_conf") == c2))
                    | ((pl.col("home_conf") == c2) & (pl.col("away_conf") == c1))
                )
                if len(sub) >= 3:
                    arr = sub["brier_1x2"].to_numpy()
                    print(f"    {c1} vs {c2}: n={len(sub)}, mean_brier={arr.mean():.4f}")

    # ------ Save
    results = {
        "wc_total": len(wc),
        "same_conf": len(same),
        "cross_conf": len(cross),
        "pair_stats": pair_stats,
        "conf_aggregates": conf_agg.to_dicts(),
        "overall_wc_ppm_baseline": overall_ppm,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(results, indent=2, default=str))
    print(f"\nWrote {OUT}")


if __name__ == "__main__":
    main()
