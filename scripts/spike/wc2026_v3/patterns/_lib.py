"""Shared utilities for pattern discovery scripts."""
from __future__ import annotations

from pathlib import Path
from typing import Callable

import numpy as np
import polars as pl

ROOT = Path(__file__).resolve().parents[4]
CACHE = ROOT / "data" / "cache"
ENRICHED = CACHE / "wc2026_v3" / "patterns_enriched.parquet"
SQUAD = CACHE / "transfermarkt" / "squad_values_current.parquet"

DISCOVERY_TOURNAMENTS = ["wc_2018", "euro_2020"]  # n=115
VALIDATION_TOURNAMENTS = ["wc_2022", "afcon_2023", "euro_2024", "copa_2024"]  # n=199

BOOTSTRAP_SEED = 42
BOOTSTRAP_N = 2000


def load_enriched() -> pl.DataFrame:
    return pl.read_parquet(ENRICHED)


def split_discovery(df: pl.DataFrame) -> pl.DataFrame:
    return df.filter(pl.col("tournament_slug").is_in(DISCOVERY_TOURNAMENTS))


def split_validation(df: pl.DataFrame) -> pl.DataFrame:
    return df.filter(pl.col("tournament_slug").is_in(VALIDATION_TOURNAMENTS))


def bootstrap_ci(
    data: np.ndarray,
    stat_fn: Callable[[np.ndarray], float],
    *,
    n_boot: int = BOOTSTRAP_N,
    seed: int = BOOTSTRAP_SEED,
    ci: float = 0.95,
) -> tuple[float, float, float]:
    """Returns (point_estimate, ci_low, ci_high) for stat_fn over bootstrap resamples."""
    rng = np.random.default_rng(seed)
    point = stat_fn(data)
    n = len(data)
    boots = np.empty(n_boot)
    for i in range(n_boot):
        idx = rng.integers(0, n, size=n)
        boots[i] = stat_fn(data[idx])
    alpha = (1 - ci) / 2
    return float(point), float(np.quantile(boots, alpha)), float(np.quantile(boots, 1 - alpha))


def bootstrap_diff_ci(
    a: np.ndarray,
    b: np.ndarray,
    stat_fn: Callable[[np.ndarray], float] = np.mean,
    *,
    n_boot: int = BOOTSTRAP_N,
    seed: int = BOOTSTRAP_SEED,
    ci: float = 0.95,
) -> tuple[float, float, float, float]:
    """Bootstrap difference of stat_fn(a) - stat_fn(b). Returns (diff, ci_low, ci_high, p_two_sided)."""
    rng = np.random.default_rng(seed)
    point = stat_fn(a) - stat_fn(b)
    boots = np.empty(n_boot)
    na, nb = len(a), len(b)
    for i in range(n_boot):
        ia = rng.integers(0, na, size=na)
        ib = rng.integers(0, nb, size=nb)
        boots[i] = stat_fn(a[ia]) - stat_fn(b[ib])
    alpha = (1 - ci) / 2
    ci_lo = float(np.quantile(boots, alpha))
    ci_hi = float(np.quantile(boots, 1 - alpha))
    # Two-sided bootstrap p-value: prob a bootstrap diff has opposite sign of point
    if point >= 0:
        p = 2 * float(np.mean(boots <= 0))
    else:
        p = 2 * float(np.mean(boots >= 0))
    return float(point), ci_lo, ci_hi, min(p, 1.0)


def bh_fdr(pvals: list[float], q: float = 0.10) -> list[bool]:
    """Benjamini-Hochberg. Returns list of booleans (True = survives at FDR=q)."""
    pvals_arr = np.asarray(pvals)
    n = len(pvals_arr)
    order = np.argsort(pvals_arr)
    sorted_p = pvals_arr[order]
    thresh = q * (np.arange(1, n + 1) / n)
    passed = sorted_p <= thresh
    # find largest k where passed
    if not passed.any():
        max_k = -1
    else:
        max_k = int(np.max(np.where(passed)[0]))
    # everything up to and including max_k survives
    survives_sorted = np.zeros(n, dtype=bool)
    if max_k >= 0:
        survives_sorted[: max_k + 1] = True
    # un-sort
    survives = np.empty(n, dtype=bool)
    survives[order] = survives_sorted
    return survives.tolist()


def total_goals(df: pl.DataFrame) -> np.ndarray:
    return (df["home_goals"] + df["away_goals"]).to_numpy()


def btts_mask(df: pl.DataFrame) -> np.ndarray:
    return ((df["home_goals"] > 0) & (df["away_goals"] > 0)).to_numpy().astype(int)


def over25_mask(df: pl.DataFrame) -> np.ndarray:
    return ((df["home_goals"] + df["away_goals"]) > 2.5).to_numpy().astype(int)


def draw_mask(df: pl.DataFrame) -> np.ndarray:
    return (df["home_goals"] == df["away_goals"]).to_numpy().astype(int)
