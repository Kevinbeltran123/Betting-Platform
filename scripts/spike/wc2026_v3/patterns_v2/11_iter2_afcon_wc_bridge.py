"""Iter 2 — AFCON -> WC team-level transfer signal.

OPERATOR DIRECTIVE 2026-05-24: "esos equipos que venían siendo buenos en
la AFCON, lo fueron también en el mundial?"

METHOD. For each team that appears in AFCON AND in WC (across our 6
StatsBomb tournaments), compute per-tournament over-performance.

For "over-performance" we use TWO independent metrics, then check
agreement:

  1) actual points per match (3 win / 1 draw / 0 loss) minus expected
     points per match from lock_v1 baseline (the walk-forward backtest
     predictions stored in patterns_v2_lens5_brier.parquet — n=199
     hold-out tournaments only).

  2) actual goal difference per match minus tournament-cohort goal
     difference average (within-tournament z-score). Works on all 314
     matches including discovery (WC18 + Euro20).

If teams that over-perform in AFCON also over-perform in WC, the
signal transfers and we can tilt WC2026 picks for repeated
over-performers.

Specific bridge question: African teams who played in BOTH AFCON 2023
AND WC 2022 (Morocco, Senegal, Tunisia, Ghana, Cameroon) — does their
AFCON over-performance correlate with their WC over-performance?
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
import polars as pl

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "scripts" / "spike" / "wc2026_v3" / "patterns_v2"))

from _lib_v2 import CACHE, load_enriched_with_mv  # noqa: E402

OUT = CACHE / "wc2026_v3" / "patterns_v2_iter2_afcon_wc_bridge.json"

WC_SLUGS = ["wc_2018", "wc_2022"]
AFCON_SLUGS = ["afcon_2023"]

# African teams confirmed in WC 2026 qualifying or already qualified (May 2026).
# Source: FIFA WC2026 qualification standings. Used for the operator-level
# "which teams matter for WC26" filter.
AFRICAN_WC26_RELEVANT = frozenset({
    "Morocco", "Senegal", "Egypt", "Algeria", "Tunisia", "Ghana", "Nigeria",
    "Côte d'Ivoire", "Ivory Coast", "Cameroon", "South Africa", "Mali",
    "Burkina Faso", "DR Congo", "Cape Verde", "Equatorial Guinea", "Gabon",
    "Mauritania", "Namibia", "Angola", "Benin", "Sudan", "Guinea",
    "Madagascar", "Tanzania", "Zambia", "Uganda", "Niger", "Togo",
    "Comoros", "Mozambique", "Ethiopia", "Libya",
})


def per_team_per_tournament(df: pl.DataFrame) -> pl.DataFrame:
    """Compute per-team-per-tournament stats: points-per-match, goal-diff-per-match.

    Rows are one per (team, tournament) pair.
    """
    home_rows = df.select(
        [
            pl.col("tournament_slug"),
            pl.col("home_team").alias("team"),
            pl.col("home_goals").alias("goals_for"),
            pl.col("away_goals").alias("goals_against"),
        ]
    )
    away_rows = df.select(
        [
            pl.col("tournament_slug"),
            pl.col("away_team").alias("team"),
            pl.col("away_goals").alias("goals_for"),
            pl.col("home_goals").alias("goals_against"),
        ]
    )
    all_team = pl.concat([home_rows, away_rows])
    all_team = all_team.with_columns(
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
    agg = (
        all_team.group_by(["tournament_slug", "team"])
        .agg(
            [
                pl.len().alias("n_matches"),
                pl.col("points").mean().alias("ppm"),
                pl.col("gd").mean().alias("gd_per_match"),
                pl.col("goals_for").mean().alias("gf_per_match"),
                pl.col("goals_against").mean().alias("ga_per_match"),
            ]
        )
        .sort(["tournament_slug", "team"])
    )
    return agg


def add_cohort_zscores(team_stats: pl.DataFrame) -> pl.DataFrame:
    """Compute z-score of ppm and gd_per_match within each tournament."""
    return team_stats.with_columns(
        [
            (
                (pl.col("ppm") - pl.col("ppm").mean().over("tournament_slug"))
                / pl.col("ppm").std().over("tournament_slug")
            ).alias("ppm_z"),
            (
                (pl.col("gd_per_match") - pl.col("gd_per_match").mean().over("tournament_slug"))
                / pl.col("gd_per_match").std().over("tournament_slug")
            ).alias("gd_z"),
        ]
    )


def main() -> None:
    df = load_enriched_with_mv()
    print(f"Loaded {len(df)} matches across {df['tournament_slug'].n_unique()} tournaments")

    team_stats = per_team_per_tournament(df)
    team_stats = add_cohort_zscores(team_stats)
    print(f"\nTeam-tournament rows: {len(team_stats)}")
    print("Tournaments per team distribution:")
    per_team_count = team_stats.group_by("team").len().sort("len", descending=True)
    print(per_team_count.head(15))

    # --- Bridge 1: WC22 (incl. African teams) <-> AFCON 2023 ---
    print("\n\n=== Bridge analysis: WC 2022 <-> AFCON 2023 ===")
    wc22 = team_stats.filter(pl.col("tournament_slug") == "wc_2022").select(
        ["team", "n_matches", "ppm", "gd_per_match", "ppm_z", "gd_z"]
    )
    afcon = team_stats.filter(pl.col("tournament_slug") == "afcon_2023").select(
        ["team", "n_matches", "ppm", "gd_per_match", "ppm_z", "gd_z"]
    )
    bridge = wc22.join(afcon, on="team", how="inner", suffix="_afcon")
    print(f"Teams in both WC22 and AFCON23: {len(bridge)}")
    print(bridge.sort("ppm_z", descending=True))

    if len(bridge) >= 3:
        ppm_corr = np.corrcoef(bridge["ppm_z"].to_numpy(), bridge["ppm_z_afcon"].to_numpy())[0, 1]
        gd_corr = np.corrcoef(bridge["gd_z"].to_numpy(), bridge["gd_z_afcon"].to_numpy())[0, 1]
        print(f"\n  ppm-z correlation (WC22 vs AFCON23): {ppm_corr:+.3f}")
        print(f"  gd-z correlation (WC22 vs AFCON23):  {gd_corr:+.3f}")
    else:
        ppm_corr = float("nan")
        gd_corr = float("nan")

    bridge_dict = bridge.to_dicts()

    # --- Bridge 2: WC18 <-> AFCON 2023 ---
    print("\n\n=== Bridge analysis: WC 2018 <-> AFCON 2023 ===")
    wc18 = team_stats.filter(pl.col("tournament_slug") == "wc_2018").select(
        ["team", "n_matches", "ppm", "gd_per_match", "ppm_z", "gd_z"]
    )
    bridge_18 = wc18.join(afcon, on="team", how="inner", suffix="_afcon")
    print(f"Teams in both WC18 and AFCON23: {len(bridge_18)}")
    print(bridge_18.sort("ppm_z", descending=True))

    if len(bridge_18) >= 3:
        ppm_corr_18 = np.corrcoef(bridge_18["ppm_z"].to_numpy(), bridge_18["ppm_z_afcon"].to_numpy())[0, 1]
        gd_corr_18 = np.corrcoef(bridge_18["gd_z"].to_numpy(), bridge_18["gd_z_afcon"].to_numpy())[0, 1]
        print(f"\n  ppm-z correlation (WC18 vs AFCON23): {ppm_corr_18:+.3f}")
        print(f"  gd-z correlation (WC18 vs AFCON23):  {gd_corr_18:+.3f}")
    else:
        ppm_corr_18 = float("nan")
        gd_corr_18 = float("nan")

    # --- Bridge 3: WC18 <-> WC22 (validates the framework — same-tournament-type) ---
    print("\n\n=== Validation bridge: WC 2018 <-> WC 2022 (same comp type) ===")
    bridge_wc = wc18.join(wc22, on="team", how="inner", suffix="_wc22")
    print(f"Teams in both WC18 and WC22: {len(bridge_wc)}")
    print(bridge_wc.sort("ppm_z", descending=True))
    if len(bridge_wc) >= 3:
        ppm_corr_wc = np.corrcoef(bridge_wc["ppm_z"].to_numpy(), bridge_wc["ppm_z_wc22"].to_numpy())[0, 1]
        gd_corr_wc = np.corrcoef(bridge_wc["gd_z"].to_numpy(), bridge_wc["gd_z_wc22"].to_numpy())[0, 1]
        print(f"\n  ppm-z correlation (WC18 vs WC22): {ppm_corr_wc:+.3f}")
        print(f"  gd-z correlation (WC18 vs WC22):  {gd_corr_wc:+.3f}")
    else:
        ppm_corr_wc = float("nan")
        gd_corr_wc = float("nan")

    # --- Operator-relevant: African WC2026 contenders, AFCON23 performance ---
    print("\n\n=== African WC2026 contenders — AFCON 2023 performance ===")
    african_at_afcon = afcon.filter(pl.col("team").is_in(list(AFRICAN_WC26_RELEVANT)))
    print(african_at_afcon.sort("ppm_z", descending=True))

    print("\n\n=== African teams in WC 2022 (incl. shock performers like Morocco) ===")
    african_at_wc22 = wc22.filter(pl.col("team").is_in(list(AFRICAN_WC26_RELEVANT)))
    print(african_at_wc22.sort("ppm_z", descending=True))

    # --- Summary signal extraction ---
    results = {
        "n_teams_in_wc22_and_afcon23": len(bridge),
        "n_teams_in_wc18_and_afcon23": len(bridge_18),
        "n_teams_in_wc18_and_wc22": len(bridge_wc),
        "ppm_z_correlation_wc22_afcon23": float(ppm_corr) if not np.isnan(ppm_corr) else None,
        "gd_z_correlation_wc22_afcon23": float(gd_corr) if not np.isnan(gd_corr) else None,
        "ppm_z_correlation_wc18_afcon23": float(ppm_corr_18) if not np.isnan(ppm_corr_18) else None,
        "gd_z_correlation_wc18_afcon23": float(gd_corr_18) if not np.isnan(gd_corr_18) else None,
        "ppm_z_correlation_wc18_wc22": float(ppm_corr_wc) if not np.isnan(ppm_corr_wc) else None,
        "gd_z_correlation_wc18_wc22": float(gd_corr_wc) if not np.isnan(gd_corr_wc) else None,
        "bridge_wc22_afcon23": bridge_dict,
        "bridge_wc18_afcon23": bridge_18.to_dicts(),
        "bridge_wc18_wc22": bridge_wc.to_dicts(),
        "african_at_afcon23": african_at_afcon.to_dicts(),
        "african_at_wc22": african_at_wc22.to_dicts(),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(results, indent=2, default=str))
    print(f"\nWrote {OUT}")


if __name__ == "__main__":
    main()
