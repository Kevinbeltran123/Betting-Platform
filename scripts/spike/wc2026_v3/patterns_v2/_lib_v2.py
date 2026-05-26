"""Shared utilities for v2 pattern discovery — extends v1's _lib without forking it.

v2-specific additions:
- enriched + market value join with tier assignment
- HT scoreline derivation
- KM survival curve helpers (numpy-only — no lifelines dep)
- log-rank test
- worst-decile selector + over-representation chi-square / bootstrap
- predictor leave-one-tournament-out loader (Lens 5)
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Iterable

import numpy as np
import polars as pl

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "scripts" / "spike" / "wc2026_v3" / "patterns"))

from _lib import (  # noqa: E402
    BOOTSTRAP_N,
    BOOTSTRAP_SEED,
    CACHE,
    DISCOVERY_TOURNAMENTS,
    ENRICHED,
    SQUAD,
    VALIDATION_TOURNAMENTS,
    bh_fdr,
    bootstrap_ci,
    bootstrap_diff_ci,
)


TIER_BOUNDARIES = {
    "A": 3.0,
    "B": 1.8,
    "C": 1.3,
    "D": 1.0,
}


def load_enriched_with_mv() -> pl.DataFrame:
    """Enriched parquet joined with current TM market values for home and away.

    `tm_ratio = max/min`, always >= 1.0. tier ∈ {A, B, C, D, N (no MV)}.
    `favorite` ∈ {home, away, none}.
    """
    df = pl.read_parquet(ENRICHED)
    mv = pl.read_parquet(SQUAD).select(
        [pl.col("team_name").alias("_team"), pl.col("market_value_eur").alias("_mv")]
    )

    df = df.join(
        mv.rename({"_team": "home_team", "_mv": "home_mv"}),
        on="home_team",
        how="left",
    ).join(
        mv.rename({"_team": "away_team", "_mv": "away_mv"}),
        on="away_team",
        how="left",
    )

    df = df.with_columns(
        [
            pl.when(pl.col("home_mv").is_null() | pl.col("away_mv").is_null())
            .then(None)
            .otherwise(
                pl.max_horizontal("home_mv", "away_mv")
                / pl.min_horizontal("home_mv", "away_mv")
            )
            .alias("tm_ratio"),
            pl.when(pl.col("home_mv").is_null() | pl.col("away_mv").is_null())
            .then(pl.lit("none"))
            .when(pl.col("home_mv") > pl.col("away_mv"))
            .then(pl.lit("home"))
            .when(pl.col("away_mv") > pl.col("home_mv"))
            .then(pl.lit("away"))
            .otherwise(pl.lit("none"))
            .alias("favorite"),
        ]
    )

    df = df.with_columns(
        pl.when(pl.col("tm_ratio").is_null())
        .then(pl.lit("N"))
        .when(pl.col("tm_ratio") >= TIER_BOUNDARIES["A"])
        .then(pl.lit("A"))
        .when(pl.col("tm_ratio") >= TIER_BOUNDARIES["B"])
        .then(pl.lit("B"))
        .when(pl.col("tm_ratio") >= TIER_BOUNDARIES["C"])
        .then(pl.lit("C"))
        .otherwise(pl.lit("D"))
        .alias("tier")
    )

    # Result label from favorite's perspective: 'win' | 'draw' | 'loss' | None
    df = df.with_columns(
        [
            pl.when(pl.col("home_goals") > pl.col("away_goals"))
            .then(pl.lit("home"))
            .when(pl.col("away_goals") > pl.col("home_goals"))
            .then(pl.lit("away"))
            .otherwise(pl.lit("draw"))
            .alias("winner"),
        ]
    )
    df = df.with_columns(
        pl.when(pl.col("favorite") == "none")
        .then(None)
        .when(pl.col("favorite") == pl.col("winner"))
        .then(pl.lit("fav_win"))
        .when(pl.col("winner") == "draw")
        .then(pl.lit("draw"))
        .otherwise(pl.lit("fav_loss"))
        .alias("fav_outcome")
    )

    # HT scoreline buckets for v2's expanded 9-state matrix
    df = df.with_columns(
        [
            pl.when((pl.col("ht_home") == 0) & (pl.col("ht_away") == 0))
            .then(pl.lit("0-0"))
            .when((pl.col("ht_home") == 1) & (pl.col("ht_away") == 1))
            .then(pl.lit("1-1"))
            .when((pl.col("ht_home") == pl.col("ht_away")))
            .then(pl.lit("X-X"))
            .when(pl.col("ht_home") > pl.col("ht_away"))
            .then(pl.lit("home_up"))
            .otherwise(pl.lit("away_up"))
            .alias("ht_state"),
        ]
    )

    df = df.with_columns(
        pl.when(pl.col("favorite") == "none")
        .then(None)
        .when(pl.col("ht_state").is_in(["0-0", "1-1", "X-X"]))
        .then(pl.lit("tied"))
        .when(
            ((pl.col("favorite") == "home") & (pl.col("ht_state") == "home_up"))
            | ((pl.col("favorite") == "away") & (pl.col("ht_state") == "away_up"))
        )
        .then(pl.lit("fav_up"))
        .otherwise(pl.lit("fav_down"))
        .alias("ht_state_relative")
    )

    return df


def split_by(df: pl.DataFrame, tournaments: Iterable[str]) -> pl.DataFrame:
    return df.filter(pl.col("tournament_slug").is_in(list(tournaments)))


def proportion(mask: np.ndarray) -> float:
    return float(np.mean(mask))


def first_goal_minutes(df: pl.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    """Returns (times, observed) for time-to-first-goal Kaplan-Meier estimation.

    For each match, the time-to-first-goal is the minimum of any goal minute
    (home or away), with right-censoring at 90 if no goal in regulation.
    """
    times = []
    observed = []
    for row in df.iter_rows(named=True):
        home_min = row.get("goals_home_minutes") or []
        away_min = row.get("goals_away_minutes") or []
        all_goals = [m for m in list(home_min) + list(away_min) if m is not None and m <= 90]
        if all_goals:
            times.append(min(all_goals))
            observed.append(1)
        else:
            times.append(90)
            observed.append(0)
    return np.array(times, dtype=float), np.array(observed, dtype=int)


def kaplan_meier(times: np.ndarray, observed: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Returns (sorted unique times, KM survival at each)."""
    order = np.argsort(times)
    t = times[order]
    e = observed[order]
    n = len(t)
    unique_t = np.unique(t)
    surv = []
    at_risk = n
    cur_surv = 1.0
    for ut in unique_t:
        d = int(np.sum((t == ut) & (e == 1)))
        c = int(np.sum((t == ut) & (e == 0)))
        if at_risk > 0 and d > 0:
            cur_surv *= (1.0 - d / at_risk)
        surv.append(cur_surv)
        at_risk -= (d + c)
    return unique_t, np.array(surv)


def log_rank_test(
    t1: np.ndarray, e1: np.ndarray, t2: np.ndarray, e2: np.ndarray
) -> tuple[float, float]:
    """Log-rank statistic and two-sided p-value (asymptotic chi-square df=1)."""
    from scipy.stats import chi2  # local import — only needed here

    t_all = np.concatenate([t1, t2])
    e_all = np.concatenate([e1, e2])
    grp = np.concatenate([np.zeros(len(t1)), np.ones(len(t2))])
    order = np.argsort(t_all)
    t_s = t_all[order]
    e_s = e_all[order]
    g_s = grp[order]

    O1, E1, V = 0.0, 0.0, 0.0
    n1, n2 = len(t1), len(t2)
    for ut in np.unique(t_s):
        at_risk_1 = int(np.sum((t1 >= ut)))
        at_risk_2 = int(np.sum((t2 >= ut)))
        at_risk = at_risk_1 + at_risk_2
        if at_risk == 0:
            continue
        d_at_t = int(np.sum((t_s == ut) & (e_s == 1)))
        d_at_t_1 = int(np.sum((t_s == ut) & (e_s == 1) & (g_s == 0)))
        if d_at_t == 0:
            continue
        e1_t = d_at_t * at_risk_1 / at_risk
        # Hypergeometric variance
        if at_risk > 1:
            v_t = (
                d_at_t
                * (at_risk_1 / at_risk)
                * (at_risk_2 / at_risk)
                * (at_risk - d_at_t)
                / (at_risk - 1)
            )
        else:
            v_t = 0.0
        O1 += d_at_t_1
        E1 += e1_t
        V += v_t

    if V == 0:
        return 0.0, 1.0
    stat = (O1 - E1) ** 2 / V
    p = float(chi2.sf(stat, df=1))
    return float(stat), p


def worst_decile_indices(brier: np.ndarray, frac: float = 0.10) -> np.ndarray:
    """Returns boolean mask for the worst (highest) Brier-decile."""
    n = len(brier)
    k = max(1, int(np.ceil(n * frac)))
    threshold = np.sort(brier)[-k]
    return brier >= threshold


def representation_test(
    is_in_group: np.ndarray, is_in_worst: np.ndarray, n_boot: int = BOOTSTRAP_N, seed: int = BOOTSTRAP_SEED
) -> tuple[float, float, float, float]:
    """Tests whether `is_in_group` is over-represented in `is_in_worst`.

    Returns (point_ratio, ci_low, ci_high, p) where ratio = obs_in_worst / expected_under_null.
    """
    rng = np.random.default_rng(seed)
    n = len(is_in_group)
    baseline = float(np.mean(is_in_group))
    if baseline == 0:
        return (0.0, 0.0, 0.0, 1.0)
    worst_share = float(np.mean(is_in_group[is_in_worst]))
    point = worst_share / baseline

    n_worst = int(np.sum(is_in_worst))
    boots = np.empty(n_boot)
    for i in range(n_boot):
        idx = rng.choice(n, size=n_worst, replace=False)
        boots[i] = float(np.mean(is_in_group[idx])) / baseline if baseline > 0 else 0.0
    p = float(np.mean(boots >= point))
    alpha = 0.05
    ci_lo = float(np.quantile(boots, alpha / 2))
    ci_hi = float(np.quantile(boots, 1 - alpha / 2))
    return point, ci_lo, ci_hi, p
