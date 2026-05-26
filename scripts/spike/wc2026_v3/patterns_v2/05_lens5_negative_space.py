"""Lens 5 — Negative-space mapping for lock_v1 predictor.

Pre-registered tests L5.1 — L5.6 (see notes/v2_hypothesis_preregister.md).

Uses run_walk_forward_backtest with ALL v2-specific signals disabled
(no DIBP, no beta-cal, no match-importance, no market-value). This
approximates lock_v1's structural backbone (Poisson strength prior over
martj42 + StatsBomb calibration). The xG-blend on top of lock_v1 is a
refinement that should reduce Brier roughly uniformly across slices, so
blind-spot identification using the baseline is informative for lock_v1
too. (Caveat noted in paper.)

Hold-out only — n=199 (WC22 + AFCON23 + Copa24 + Euro24). The walk-forward
backtest cannot score WC18/Euro20 because they're used as the calibration
set in the v2 corpus split.
"""
from __future__ import annotations

import json

import numpy as np
import polars as pl

from bip.evaluation.tournaments.wc2026_v2.backtest import run_walk_forward_backtest
from bip.evaluation.tournaments.wc2026_v2.corpus import build_split

from _lib_v2 import (
    BOOTSTRAP_N,
    BOOTSTRAP_SEED,
    CACHE,
    bootstrap_ci,
    load_enriched_with_mv,
    representation_test,
    worst_decile_indices,
)

OUT_BRIER = CACHE / "wc2026_v3" / "patterns_v2_lens5_brier.parquet"
OUT = CACHE / "wc2026_v3" / "patterns_v2_lens5.json"


def run_backtest_and_dump_brier() -> pl.DataFrame:
    """Run walk-forward backtest with lock_v1-baseline config, return per-match Brier."""
    split = build_split()
    print(
        f"Walk-forward inputs: train={split.train.height}, "
        f"cal={split.calibration.height}, heldout={split.heldout.height}"
    )

    result = run_walk_forward_backtest(
        train=split.train,
        calibration=split.calibration,
        heldout=split.heldout,
        n_bootstrap=BOOTSTRAP_N,
        seed=BOOTSTRAP_SEED,
        use_dibp=False,
        use_beta_calibration=False,
        use_match_importance=False,
        use_market_value=False,
    )

    print(f"\nOverall Brier 1X2: {result.overall_brier_1x2}")
    print(f"Per-tournament Brier 1X2:")
    for slug, m in result.per_tournament.items():
        print(f"  {slug}: n={m.n_matches}, brier={m.brier_1x2}")

    # Reconstruct per-fixture rows. The walk-forward iterates per tournament,
    # iter_rows order in _evaluate_predictor_on_tournament matches the heldout
    # rows for that tournament filtered by tournament_slug.
    per_fixture_rows = []
    for slug, m in result.per_tournament.items():
        tourn_rows = (
            split.heldout.filter(pl.col("tournament_slug") == slug)
            .select(["match_id", "tournament_slug", "match_date", "home_team", "away_team"])
            .to_dicts()
        )
        assert len(tourn_rows) == len(m.per_fixture_brier_1x2), (
            f"Row count mismatch for {slug}: {len(tourn_rows)} vs {len(m.per_fixture_brier_1x2)}"
        )
        for row, brier in zip(tourn_rows, m.per_fixture_brier_1x2):
            row["brier_1x2"] = float(brier)
            per_fixture_rows.append(row)

    df = pl.DataFrame(per_fixture_rows)
    df.write_parquet(OUT_BRIER)
    print(f"\nWrote {OUT_BRIER} ({len(df)} rows)")
    return df


def main() -> None:
    brier_df = run_backtest_and_dump_brier()

    # Join with enriched data for stratification
    enriched = load_enriched_with_mv()
    full = brier_df.join(
        enriched.select(
            [
                "match_id",
                "tier",
                "favorite",
                "phase",
                "match_week",
                "ht_home",
                "ht_away",
                "home_goals",
                "away_goals",
                "tm_ratio",
                "home_mv",
                "away_mv",
            ]
        ),
        on="match_id",
        how="left",
    )

    print(f"\nFull joined: {full.height} rows")
    print(f"  Brier 1X2 stats: mean={full['brier_1x2'].mean():.4f}, "
          f"std={full['brier_1x2'].std():.4f}, min={full['brier_1x2'].min():.4f}, "
          f"max={full['brier_1x2'].max():.4f}")

    brier = full["brier_1x2"].to_numpy()
    worst = worst_decile_indices(brier, frac=0.10)
    n_worst = int(worst.sum())
    print(f"\nWorst-decile threshold: Brier >= {sorted(brier)[-n_worst]:.4f}")
    print(f"Worst-decile n: {n_worst}")
    print(f"Worst-decile mean Brier: {float(brier[worst].mean()):.4f}")
    print(f"Best 90% mean Brier:    {float(brier[~worst].mean()):.4f}")

    results: dict = {
        "n_holdout": full.height,
        "overall_brier_mean": float(brier.mean()),
        "worst_decile_threshold": float(sorted(brier)[-n_worst]),
        "n_worst": n_worst,
        "worst_decile_mean": float(brier[worst].mean()),
        "best90_mean": float(brier[~worst].mean()),
    }

    # ----- L5.1 — AFCON over-representation in worst-decile -----
    is_afcon = (full["tournament_slug"] == "afcon_2023").to_numpy()
    point, lo, hi, p = representation_test(is_afcon, worst)
    print(f"\nL5.1 AFCON: baseline={float(is_afcon.mean()):.3f}, "
          f"in_worst={float(is_afcon[worst].mean()):.3f}, "
          f"ratio={point:.2f} [{lo:.2f}, {hi:.2f}], p={p:.4f}")
    results["L5.1_afcon"] = {
        "baseline": float(is_afcon.mean()),
        "in_worst": float(is_afcon[worst].mean()),
        "ratio": point,
        "ci_low": lo,
        "ci_high": hi,
        "p": p,
        "flag": bool(point >= 1.5),
    }

    # ----- L5.2 — MD3 group over-representation -----
    is_md3 = ((full["phase"] == "group") & (full["match_week"] == 3)).to_numpy()
    point, lo, hi, p = representation_test(is_md3, worst)
    print(f"\nL5.2 MD3-group: baseline={float(is_md3.mean()):.3f}, "
          f"in_worst={float(is_md3[worst].mean()):.3f}, "
          f"ratio={point:.2f} [{lo:.2f}, {hi:.2f}], p={p:.4f}")
    results["L5.2_md3"] = {
        "baseline": float(is_md3.mean()),
        "in_worst": float(is_md3[worst].mean()),
        "ratio": point,
        "ci_low": lo,
        "ci_high": hi,
        "p": p,
        "flag": bool(point >= 1.5),
    }

    # ----- L5.3 — Parity (tm_ratio < 1.3) -----
    is_parity = ((full["tm_ratio"].is_null()) | (full["tm_ratio"] < 1.3)).to_numpy()
    point, lo, hi, p = representation_test(is_parity, worst)
    print(f"\nL5.3 Parity (tm_ratio<1.3 or missing): baseline={float(is_parity.mean()):.3f}, "
          f"in_worst={float(is_parity[worst].mean()):.3f}, "
          f"ratio={point:.2f} [{lo:.2f}, {hi:.2f}], p={p:.4f}")
    results["L5.3_parity"] = {
        "baseline": float(is_parity.mean()),
        "in_worst": float(is_parity[worst].mean()),
        "ratio": point,
        "ci_low": lo,
        "ci_high": hi,
        "p": p,
        "flag": bool(point >= 1.5),
    }

    # ----- L5.4 — Upset (loser had higher MV) -----
    # Upset = winner is the underdog by market value. Skip if mv missing.
    is_upset_full = np.zeros(full.height, dtype=bool)
    rows_list = full.to_dicts()
    for i, row in enumerate(rows_list):
        hmv, amv = row["home_mv"], row["away_mv"]
        if hmv is None or amv is None:
            continue
        hg, ag = row["home_goals"], row["away_goals"]
        if hg > ag and hmv < amv:
            is_upset_full[i] = True
        elif ag > hg and amv < hmv:
            is_upset_full[i] = True
    point, lo, hi, p = representation_test(is_upset_full, worst)
    print(f"\nL5.4 Upset (winner had lower MV): baseline={float(is_upset_full.mean()):.3f}, "
          f"in_worst={float(is_upset_full[worst].mean()):.3f}, "
          f"ratio={point:.2f} [{lo:.2f}, {hi:.2f}], p={p:.4f}")
    results["L5.4_upset"] = {
        "baseline": float(is_upset_full.mean()),
        "in_worst": float(is_upset_full[worst].mean()),
        "ratio": point,
        "ci_low": lo,
        "ci_high": hi,
        "p": p,
        "flag": bool(point >= 1.5),
    }

    # ----- L5.5 — HT 1-1 (regime-flip)
    is_ht11 = ((full["ht_home"] == 1) & (full["ht_away"] == 1)).to_numpy()
    point, lo, hi, p = representation_test(is_ht11, worst)
    print(f"\nL5.5 HT 1-1: baseline={float(is_ht11.mean()):.3f}, "
          f"in_worst={float(is_ht11[worst].mean()):.3f}, "
          f"ratio={point:.2f} [{lo:.2f}, {hi:.2f}], p={p:.4f}")
    results["L5.5_ht11"] = {
        "baseline": float(is_ht11.mean()),
        "in_worst": float(is_ht11[worst].mean()),
        "ratio": point,
        "ci_low": lo,
        "ci_high": hi,
        "p": p,
        "flag": bool(point >= 1.5),
    }

    # ----- L5.6 — Host nation (exploratory) -----
    HOSTS = {
        "wc_2022": "Qatar",
        "afcon_2023": "Côte d'Ivoire",
        "euro_2024": "Germany",
        "copa_2024": None,  # multi-host, skip
    }
    is_host_in_match = np.zeros(full.height, dtype=bool)
    for i, row in enumerate(full.iter_rows(named=True)):
        host = HOSTS.get(row["tournament_slug"])
        if host and (row["home_team"] == host or row["away_team"] == host):
            is_host_in_match[i] = True
    if is_host_in_match.sum() >= 5:
        point, lo, hi, p = representation_test(is_host_in_match, worst)
        print(f"\nL5.6 Host nation in match: baseline={float(is_host_in_match.mean()):.3f}, "
              f"in_worst={float(is_host_in_match[worst].mean()):.3f}, "
              f"ratio={point:.2f} [{lo:.2f}, {hi:.2f}], p={p:.4f}")
        results["L5.6_host"] = {
            "baseline": float(is_host_in_match.mean()),
            "in_worst": float(is_host_in_match[worst].mean()),
            "ratio": point,
            "ci_low": lo,
            "ci_high": hi,
            "p": p,
            "flag": bool(point >= 1.5),
        }

    # ----- Bonus: per-tournament Brier
    print(f"\nBrier by tournament:")
    for slug in sorted(full["tournament_slug"].unique().to_list()):
        sub = full.filter(pl.col("tournament_slug") == slug)
        if sub.height >= 5:
            arr = sub["brier_1x2"].to_numpy()
            point, lo, hi = bootstrap_ci(arr, np.mean)
            print(f"  {slug}: n={sub.height}, brier={point:.4f} [{lo:.4f}, {hi:.4f}]")
            results[f"brier_by_tournament_{slug}"] = {
                "n": sub.height,
                "point": point,
                "ci_low": lo,
                "ci_high": hi,
            }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(results, indent=2))
    print(f"\nWrote {OUT}")


if __name__ == "__main__":
    main()
