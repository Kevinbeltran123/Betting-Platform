"""Iter 4 — corpus cut >=2012 validation.

OPERATOR DIRECTIVE: "si tienes información muy antigua como mencionas,
empieza a tener en cuenta solo desde el año 2012 en adelante."

QUESTION 1: Is the confederation hierarchy (CONMEBOL > UEFA > CAF > AFC >
CONCACAF) time-stable, or has it shifted? If pre-2012 had a different
hierarchy, lock_v1's strength prior (using full martj42 history) is
calibrated to a now-stale hierarchy.

QUESTION 2: For each confederation, is per-team variance smaller >=2012
than pre-2012? Means we can rely on confederation labels less, individual
team strength more, in modern era.

QUESTION 3: Does the WC pattern hierarchy from StatsBomb 314 (2018-2022,
n=128 WC) match what we see in martj42 WC2014+2018+2022 (full WCs >=2012,
no xG but more matches)?
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import polars as pl

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "scripts" / "spike" / "wc2026_v3" / "patterns_v2"))

from _lib_v2 import CACHE  # noqa: E402

OUT = CACHE / "wc2026_v3" / "patterns_v2_iter4_era_check.json"


# Same mapping as iter 3 — keep canonical.
CONFEDERATION: dict[str, str] = {
    # UEFA
    "France": "UEFA", "Germany": "UEFA", "England": "UEFA", "Spain": "UEFA",
    "Italy": "UEFA", "Portugal": "UEFA", "Netherlands": "UEFA",
    "Belgium": "UEFA", "Croatia": "UEFA", "Switzerland": "UEFA",
    "Denmark": "UEFA", "Sweden": "UEFA", "Poland": "UEFA",
    "Russia": "UEFA", "Wales": "UEFA", "Iceland": "UEFA",
    "Serbia": "UEFA", "Ukraine": "UEFA", "Austria": "UEFA",
    "Czech Republic": "UEFA", "Czechoslovakia": "UEFA",
    "Slovakia": "UEFA", "Romania": "UEFA",
    "Republic of Ireland": "UEFA", "Ireland": "UEFA",
    "Northern Ireland": "UEFA",
    "Hungary": "UEFA", "Turkey": "UEFA", "Greece": "UEFA",
    "Scotland": "UEFA", "Albania": "UEFA", "Finland": "UEFA",
    "North Macedonia": "UEFA", "Norway": "UEFA", "Slovenia": "UEFA",
    "Georgia": "UEFA", "FR Yugoslavia": "UEFA", "Yugoslavia": "UEFA",
    "Soviet Union": "UEFA", "East Germany": "UEFA",
    "West Germany": "UEFA", "Bosnia and Herzegovina": "UEFA",
    "Bulgaria": "UEFA",
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
    "Zaire": "CAF",
    # AFC
    "Japan": "AFC", "South Korea": "AFC", "Korea Republic": "AFC",
    "Korea DPR": "AFC", "Saudi Arabia": "AFC", "Iran": "AFC",
    "Australia": "AFC", "Qatar": "AFC", "United Arab Emirates": "AFC",
    "China PR": "AFC", "China": "AFC", "Iraq": "AFC",
    "Kuwait": "AFC", "Indonesia": "AFC", "Dutch East Indies": "AFC",
    # CONCACAF
    "USA": "CONCACAF", "United States": "CONCACAF", "Mexico": "CONCACAF",
    "Canada": "CONCACAF", "Costa Rica": "CONCACAF", "Panama": "CONCACAF",
    "Honduras": "CONCACAF", "Jamaica": "CONCACAF", "Trinidad and Tobago": "CONCACAF",
    "Haiti": "CONCACAF", "El Salvador": "CONCACAF", "Cuba": "CONCACAF",
    # OFC
    "New Zealand": "OFC", "Tahiti": "OFC",
}


def conf_of(team: str) -> str:
    return CONFEDERATION.get(team, "UNK")


def main() -> None:
    martj42 = pl.read_csv(
        CACHE / "martj42_international_results.csv",
        null_values=["NA", ""],
    ).drop_nulls(subset=["home_score", "away_score"])
    print(f"Loaded martj42: {len(martj42)} rows")
    print(f"Cols: {martj42.columns}")
    print(f"Date range: {martj42['date'].min()} -> {martj42['date'].max()}")

    # Filter to WC matches only
    martj42 = martj42.with_columns(pl.col("date").str.to_date().alias("match_date"))
    martj42 = martj42.with_columns(pl.col("match_date").dt.year().alias("year"))

    wc_mask = martj42["tournament"] == "FIFA World Cup"
    wc_df = martj42.filter(wc_mask)
    print(f"\nWC matches in martj42: {len(wc_df)}")
    print(f"Year range: {wc_df['year'].min()} -> {wc_df['year'].max()}")
    print(wc_df.group_by("year").len().sort("year"))

    # Define era splits
    wc_df = wc_df.with_columns(
        pl.when(pl.col("year") < 2012).then(pl.lit("pre_2012"))
        .otherwise(pl.lit("post_2012"))
        .alias("era")
    )

    # Tag confederations
    wc_df = wc_df.with_columns(
        [
            pl.col("home_team").map_elements(conf_of, return_dtype=pl.Utf8).alias("home_conf"),
            pl.col("away_team").map_elements(conf_of, return_dtype=pl.Utf8).alias("away_conf"),
        ]
    )

    print(f"\nUnknown confederation home count: {(wc_df['home_conf'] == 'UNK').sum()}")
    print(f"Unknown confederation away count: {(wc_df['away_conf'] == 'UNK').sum()}")

    # Per-conf per-era points-per-match
    home = wc_df.select(
        [
            pl.col("era"),
            pl.col("home_team").alias("team"),
            pl.col("home_conf").alias("conf"),
            pl.col("home_score").alias("goals_for"),
            pl.col("away_score").alias("goals_against"),
        ]
    )
    away = wc_df.select(
        [
            pl.col("era"),
            pl.col("away_team").alias("team"),
            pl.col("away_conf").alias("conf"),
            pl.col("away_score").alias("goals_for"),
            pl.col("home_score").alias("goals_against"),
        ]
    )
    all_team = pl.concat([home, away]).with_columns(
        [
            pl.when(pl.col("goals_for") > pl.col("goals_against"))
            .then(3)
            .when(pl.col("goals_for") == pl.col("goals_against"))
            .then(1)
            .otherwise(0)
            .alias("points"),
            (pl.col("goals_for") - pl.col("goals_against")).alias("gd"),
        ]
    ).filter(pl.col("conf") != "UNK")

    print("\n=== Confederation hierarchy by era (WC matches, martj42) ===\n")
    summary = (
        all_team.group_by(["era", "conf"])
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
        .sort(["era", "ppm"], descending=[False, True])
    )
    print(summary)

    # Pivot for direct era comparison
    print("\n=== Era comparison (ppm) ===\n")
    pivot = summary.pivot(
        values="ppm", index="conf", on="era", aggregate_function="first"
    ).with_columns((pl.col("post_2012") - pl.col("pre_2012")).alias("delta"))
    print(pivot.sort("delta", descending=True))

    # Per-confederation pair head-to-head in modern era
    print("\n=== Modern (>=2012) confederation pair win rates ===\n")
    modern = wc_df.filter(pl.col("era") == "post_2012")
    print(f"Modern WC matches in martj42: {len(modern)}")

    confs = ["UEFA", "CONMEBOL", "CAF", "AFC", "CONCACAF", "OFC"]
    pair_stats = {}
    for c1 in confs:
        for c2 in confs:
            if c1 >= c2:
                continue
            sub = modern.filter(
                ((pl.col("home_conf") == c1) & (pl.col("away_conf") == c2))
                | ((pl.col("home_conf") == c2) & (pl.col("away_conf") == c1))
            )
            if len(sub) < 3:
                continue
            c1_wins = c2_wins = draws = 0
            for row in sub.iter_rows(named=True):
                hg, ag = row["home_score"], row["away_score"]
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

    results = {
        "n_wc_martj42_total": len(wc_df),
        "n_wc_post_2012": int((wc_df["era"] == "post_2012").sum()),
        "n_wc_pre_2012": int((wc_df["era"] == "pre_2012").sum()),
        "summary_by_era_conf": summary.to_dicts(),
        "pivot_era": pivot.to_dicts(),
        "modern_pair_stats": pair_stats,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(results, indent=2, default=str))
    print(f"\nWrote {OUT}")


if __name__ == "__main__":
    main()
