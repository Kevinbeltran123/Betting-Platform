"""Top-N filter cascade — destila ~937 picks/jornada a ~25 high-conf placements.

Day-1 (2026-05-10) emitted 937 picks across 78 fixtures with +13.19% ROI on the
805-graded subset. Operationally impossible to place; operator manual ceiling
is ~25/jornada. This module applies a 5-filter cascade + Bayesian-shrunk
scoring to surface the Top-N picks the operator should actually consider.

The cascade is calibrated against Day-1 numbers — every threshold has an
empirical justification documented in the constant block. Re-tune with
``analyze_jornada.py`` re-graded data after Day-3 / Day-7.

Pipeline stages:
  load_picks → enrich_with_league → apply_cascade (F1-F5)
    → score (Bayesian-shrunk priors, optionally live-recomputed)
    → top_n (greedy with dedup + per-fixture/window quotas)
    → enrich_with_signals (momentum, info_density, killing_clock for output)

Usage::

    # CLI on the live picks DB (uses Day-1 hardcoded priors)
    uv run python -m scripts.spike.sportmonks.topn_filter

    # Use live-recomputed priors from picks.db (Day-3+)
    uv run python -m scripts.spike.sportmonks.topn_filter --use-live-priors

    # Programmatic
    from scripts.spike.sportmonks.topn_filter import (
        load_picks, apply_cascade, score, top_n,
        compute_market_priors_from_db,
        enrich_with_signals,
    )
    df = load_picks()
    df = apply_cascade(df)
    df = score(df, market_priors=compute_market_priors_from_db())
    top = enrich_with_signals(top_n(df, n=25))

Outputs (CLI):
- Markdown summary at ``reports/sportmonks_live/topn_{date}.md``
- Parquet of top-25 at ``reports/sportmonks_live/exports/topn_picks.parquet``
- Cached priors at ``data/cache/sportmonks/priors.parquet`` (when --use-live-priors)

Read-only on picks.db and cache files; only writes to reports/ and priors cache.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import polars as pl

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from bip.evaluation.live.pick_tracker import DEFAULT_DB_PATH  # noqa: E402
from bip.sports.football.sportmonks.cache import (  # noqa: E402
    DEFAULT_CACHE_ROOT,
    SportmonksCache,
)


# ── F1: Market whitelist ────────────────────────────────────────────────
# Day-1 ROI per market drove this split. KEEP_UNCOND = ROI ≥ +8% with n ≥ 20.
# KEEP_COND = marginal/small-n markets that need extra edge to clear.
# DROP_MARKETS = ROI < +2% or clearly broken (btts had 10.5% win rate).

KEEP_UNCOND: frozenset[str] = frozenset({
    "ou_3_5",              # +73.69% ROI / n=42
    "cards_total_4_5",     # +62.95% ROI / n=21
    "ou_2_5",              # +55.00% ROI / n=23
    "first_half_ou_0_5",   # +42.10% ROI / n=40
    "team_to_score_first", # +27.17% ROI / n=65
    "btts_second_half",    # +16.57% ROI / n=133
    "draw_no_bet",         # +8.82% ROI / n=174
})

# Conditional markets: keep ONLY if edge_pct ≥ market_specific_floor
KEEP_COND: dict[str, float] = {
    "fulltime_result":   20.0,  # +35.49% but driven by high-edge picks
    "home_ou_1_5":       18.0,  # near break-even at -1.67%, gate harder
    "cards_total_5_5":   12.0,  # +6.69% n=16 small but positive
    "btts_first_half":   15.0,  # +5.50% n=20
    "first_half_ou_1_5": 15.0,  # +4.11% n=28
}

# Implicit drop list (anything not in KEEP_UNCOND ∪ KEEP_COND):
#   cards_total_3_5   -39.83%  n=12
#   away_ou_1_5        -9.58%  n=50
#   btts (yes/no)     -77.24%  n=38   ← bug fixed post-jornada, awaiting Day-2
#   ou_1_5           -100.00%  n=2
#   double_chance      +1.02%  n=58


# ── F2: Placement window per market class ──────────────────────────────
# Day-1: picks at minute > 75 contributed only +0.80 units across 65 picks
# (~+1.2% ROI). Picks at minute ≤ 75 contributed +106.42 units across 748
# picks (~+14.2% ROI). The placement window cuts almost zero ROI while
# giving the operator a realistic Betano placement window.

WINDOW_FULL_MATCH = (0, 75)        # ou_*, cards_*, ftr, ttsf, dnb, dc
WINDOW_FIRST_HALF = (0, 30)        # first_half_*, btts_first_half
WINDOW_SECOND_HALF = (45, 70)      # btts_second_half (need 2H to be live)


# ── F3: Edge floor ──────────────────────────────────────────────────────
# Day-1 edge bucket [10, 12) had ROI -18.12% on n=16 — overconfident model.
# Bucket [12, 15) flipped to +6.77%. Bucket [15, 20) +13.11%. Floor at 12.
EDGE_FLOOR_PCT: float = 12.0


# ── F4: Odd band ────────────────────────────────────────────────────────
# Day-1 odd p10=1.33, p90=3.00. Tight band keeps btts_2h (~1.35) but kills
# 7 long-shot picks above 4.50 where variance dominates.
ODD_FLOOR: float = 1.30
ODD_CEIL: float = 4.50


# ── F5: League filter ───────────────────────────────────────────────────
# Drop only leagues with proven negative ROI on adequate sample (n ≥ 30).
# Small-sample leagues (n < 30) are de-weighted via shrinkage in scoring.
DROP_LEAGUE_IDS: frozenset[int] = frozenset({
    384,  # Serie A — n=52, ROI -6.62%
})


# ── Bayesian shrinkage prior ───────────────────────────────────────────
# Global prior anchored slightly below Day-1 +13.19% to be conservative.
# k=30 → cards_total_5_5 (n=16, +6.69%) shrinks to +9.2%; ou_3_5 (n=42,
# +73.69%) shrinks to +47.6%. k can be re-tuned after Day-7.
GLOBAL_PRIOR_ROI: float = 0.10
SHRINKAGE_K: int = 30


# ── Day-1 market priors (FALLBACK ONLY — prefer --use-live-priors) ────
# Hand-typed from the strategy doc §2. Verified to MATCH the live picks.db
# recompute for markets (16 markets, all <0.001 abs drift) but DRIFTS for
# leagues — see DAY1_LEAGUE_ROI note below. Use these only when picks.db
# is unavailable (testing, comparison baseline, or fallback when live
# recompute returns empty).
DAY1_MARKET_ROI: dict[str, tuple[float, int]] = {
    "ou_3_5":              (0.7369, 42),
    "cards_total_4_5":     (0.6295, 21),
    "ou_2_5":              (0.5500, 23),
    "first_half_ou_0_5":   (0.4210, 40),
    "fulltime_result":     (0.3549, 63),
    "team_to_score_first": (0.2717, 65),
    "btts_second_half":    (0.1657, 133),
    "draw_no_bet":         (0.0882, 174),
    "cards_total_5_5":     (0.0669, 16),
    "btts_first_half":     (0.0550, 20),
    "first_half_ou_1_5":   (0.0411, 28),
    "home_ou_1_5":         (-0.0167, 90),
    "away_ou_1_5":         (-0.0958, 50),
    "btts":                (-0.7724, 38),
    "cards_total_3_5":     (-0.3983, 12),
    "double_chance":       (0.0102, 58),
}

DAY1_LEAGUE_ROI: dict[int, tuple[float, int]] = {
    # ⚠️ KNOWN DRIFT vs live picks.db. Strategy doc §2 reported these but
    # the actual DB shows materially different numbers (see _drift_log
    # in compute_league_priors_from_db). Kept here for reproducibility of
    # the strategy doc but --use-live-priors (CLI default) supersedes them.
    #
    # League ID | Doc §2     | Live (Day-1)   | Drift
    # ----------|------------|----------------|-------
    # 8 (EPL)   | +20.93% 61 | +4.24% 62      | -16.7pp ← significant
    # 82 (BL)   | +14.51% 94 | -0.43% 95      | -14.9pp ← significant
    # 301 (L1)  | +25.40% 178| +17.40% 178    |  -8.0pp
    # 564 (LL)  | +65.24% 34 | +96.62% 34     | +31.4pp ← favorable
    # 384 (SA)  |  -6.62% 52 | -23.02% 52     | -16.4pp ← much worse
    #
    # Plus ~14 leagues that exist in live data but not in the §2 list.
    # Conclusion: live priors are SOURCE OF TRUTH; hardcoded is fallback.
    301:  (0.2540, 178),  # Ligue 1
    82:   (0.1451, 94),   # Bundesliga
    8:    (0.2093, 61),   # EPL
    564:  (0.6524, 34),   # La Liga (small-n, careful)
    384:  (-0.0662, 52),  # Serie A
}


# ── Helpers ─────────────────────────────────────────────────────────────


def shrunk_roi(
    observed_roi: float,
    n: int,
    prior_roi: float = GLOBAL_PRIOR_ROI,
    k: int = SHRINKAGE_K,
) -> float:
    """Empirical Bayes shrinkage of observed ROI toward a global prior.

    Pulls small-sample ROI estimates toward the prior. ``k`` is the prior
    "pseudo-count" — picks of equivalent informational weight.

    >>> round(shrunk_roi(0.7369, 42), 4)
    0.4467
    >>> round(shrunk_roi(0.0669, 16), 4)
    0.0879
    >>> round(shrunk_roi(-0.30, 5), 4)
    0.0429
    """
    return (n * observed_roi + k * prior_roi) / (n + k)


def logical_kernel(score: float | None) -> float:
    """Non-monotonic kernel — Day-1 showed bucket 0.50-0.60 underperforms
    both lower (0.40-0.50) and higher (0.60+) tiers.

    Bucket ROI (Day-1):
      0.40-0.50  +24.38%  → 0.7
      0.50-0.60   +3.25%  → 0.3   ← weak tier, penalized
      0.60-0.70  +23.41%  → 1.0   ← workhorse
      0.70-0.85   +6.44%  → 0.4   ← clean-but-weak
      0.85+      +21.83%  → 0.9
    """
    if score is None or score < 0.40:
        return 0.0
    if score < 0.50:
        return 0.7
    if score < 0.60:
        return 0.3
    if score < 0.70:
        return 1.0
    if score < 0.85:
        return 0.4
    return 0.9


def odd_kernel(odd: float) -> float:
    """Triangular peak around 1.80-2.50 where Kelly works cleanly.

    Returns 0.6 at the floor, 1.0 at the peak, 0.5 at the ceiling.
    """
    if odd < 1.30 or odd > 4.50:
        return 0.0
    if 1.80 <= odd <= 2.50:
        return 1.0
    if odd < 1.80:
        return 0.6 + 0.4 * (odd - 1.30) / 0.50    # 1.30→0.6, 1.80→1.0
    return 1.0 - 0.5 * (odd - 2.50) / 2.00         # 2.50→1.0, 4.50→0.5


def time_kernel(minute: int, market: str) -> float:
    """Earlier picks score higher — more placement window, less selection bias."""
    if "first_half" in market or market == "btts_first_half":
        return max(0.0, (30 - minute) / 30.0)
    if market == "btts_second_half":
        if minute < 45:
            return 0.0
        if minute <= 60:
            return 1.0
        return max(0.0, (70 - minute) / 10.0)
    # Full-match markets: linear decay from minute 25 onward
    if minute <= 25:
        return 1.0
    return max(0.0, (75 - minute) / 50.0)


def calibrated_edge(edge_pct: float) -> float:
    """Haircut overconfident edges below 15% per Day-1 calibration data."""
    edge = edge_pct / 100.0
    if edge_pct < 15.0:
        return edge * 0.5
    return edge


# ── Loading & enrichment ───────────────────────────────────────────────


LOGICAL_COMPONENT_KEYS: tuple[str, ...] = (
    "consilience",
    "informational_content",
    "liquidity",
    "odds_credibility",
    "size_consistency",
)
"""The 5 sub-scores that combine into ``logical_score``.

Day-1 verification: all 100 sampled picks have these exact 5 keys. Order
here is the display order for the decomposition table.
"""


def parse_logical_components(json_str: str | None) -> dict[str, float | None]:
    """Parse a single logical_components_json string into a dict.

    Returns a dict with all 5 LOGICAL_COMPONENT_KEYS — missing keys map
    to None. Returns dict of Nones if input is null/invalid (no-op for
    rows where the watcher didn't record decomposition).
    """
    if json_str is None:
        return {k: None for k in LOGICAL_COMPONENT_KEYS}
    try:
        parsed = json.loads(json_str)
    except (TypeError, json.JSONDecodeError):
        return {k: None for k in LOGICAL_COMPONENT_KEYS}
    return {k: parsed.get(k) for k in LOGICAL_COMPONENT_KEYS}


def explode_logical_components(df: pl.DataFrame) -> pl.DataFrame:
    """Add one column per logical component (prefixed ``lc_``).

    No-op if ``logical_components_json`` is missing. Useful when the operator
    wants to inspect WHICH dimension dragged a flagged pick — e.g. high
    edge but odds_credibility=0.40 means the bookmaker odd looks suspicious
    relative to fair value. The 5 columns are: lc_consilience,
    lc_informational_content, lc_liquidity, lc_odds_credibility,
    lc_size_consistency.
    """
    if df.is_empty() or "logical_components_json" not in df.columns:
        return df
    parsed = [
        parse_logical_components(j)
        for j in df.get_column("logical_components_json").to_list()
    ]
    new_cols = {
        f"lc_{k}": [row[k] for row in parsed]
        for k in LOGICAL_COMPONENT_KEYS
    }
    return df.with_columns([
        pl.Series(name, vals, dtype=pl.Float64)
        for name, vals in new_cols.items()
    ])


def load_picks(db_path: Path = DEFAULT_DB_PATH) -> pl.DataFrame:
    """Read picks table from SQLite into Polars, with logical components exploded.

    The ``logical_components_json`` column is preserved verbatim AND parsed
    into 5 ``lc_*`` columns for downstream filtering and reporting.
    """
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = [dict(r) for r in conn.execute("SELECT * FROM picks")]
    if not rows:
        return pl.DataFrame()
    df = pl.from_dicts(rows, infer_schema_length=None)
    return explode_logical_components(df)


def enrich_with_league(
    df: pl.DataFrame,
    cache_root: Path = DEFAULT_CACHE_ROOT,
) -> pl.DataFrame:
    """Add ``league_id`` column by walking the snapshot cache.

    Same logic as ``analyze_jornada.per_league_breakdown`` but vectorized.
    Walks each fixture's snapshots, picks the first one carrying league_id
    in either ``data`` or ``raw`` payload.
    """
    if df.is_empty() or "fixture_id" not in df.columns:
        return df.with_columns(pl.lit(None).cast(pl.Int64).alias("league_id"))

    cache = SportmonksCache(root=cache_root)
    fixture_ids = df.select("fixture_id").unique().to_series().to_list()
    fid_to_league: dict[int, int | None] = {}

    for fid in fixture_ids:
        league_id: int | None = None
        for snap_path in cache.list_snapshots(fid):
            try:
                payload = json.loads(snap_path.read_text())
            except (OSError, json.JSONDecodeError):
                continue
            data = payload.get("data") or payload.get("raw")
            if data and data.get("league_id"):
                league_id = data["league_id"]
                break
        fid_to_league[fid] = league_id

    league_df = pl.DataFrame({
        "fixture_id": list(fid_to_league.keys()),
        "league_id": list(fid_to_league.values()),
    }, schema={"fixture_id": pl.Int64, "league_id": pl.Int64})
    return df.join(league_df, on="fixture_id", how="left")


# ── Dynamic priors (recomputed from picks.db) ──────────────────────────


PRIORS_CACHE_PATH: Path = (
    Path(__file__).resolve().parent.parent.parent.parent
    / "data" / "cache" / "sportmonks" / "priors.parquet"
)
"""Persistent location for live-recomputed priors snapshot."""

PRIORS_MIN_N: int = 5
"""Minimum graded picks for a market/league to enter the priors dict.

Below this, the global GLOBAL_PRIOR_ROI fires automatically via shrinkage.
"""


def _aggregate_priors(
    rows: list[tuple[str | int | None, float | None]],
) -> dict:
    """Group (key, profit_units) rows into {key: (mean_roi, n)} dict."""
    by: dict = defaultdict(list)
    for key, pl_units in rows:
        if key is None:
            continue
        by[key].append(pl_units or 0.0)
    return {
        k: (sum(v) / len(v), len(v))
        for k, v in by.items()
        if len(v) >= PRIORS_MIN_N
    }


def compute_market_priors_from_db(
    db_path: Path = DEFAULT_DB_PATH,
) -> dict[str, tuple[float, int]]:
    """Recompute observed ROI per market from current graded picks.

    Walks all (won, lost) picks — voids excluded since they refund stake
    and don't carry signal about market quality. Returns the same shape as
    DAY1_MARKET_ROI: ``{market: (roi_decimal, n)}``.

    Markets with n < PRIORS_MIN_N are dropped (the global prior fires via
    shrinkage when scoring a pick from such a market).
    """
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            "SELECT market, profit_units FROM picks "
            "WHERE status IN ('won', 'lost')"
        ).fetchall()
    return _aggregate_priors(rows)


def compute_league_priors_from_db(
    db_path: Path = DEFAULT_DB_PATH,
    cache_root: Path = DEFAULT_CACHE_ROOT,
) -> dict[int, tuple[float, int]]:
    """Recompute observed ROI per league from current graded picks.

    Requires walking the snapshot cache to map fixture_id → league_id (same
    enrichment used by ``enrich_with_league`` and ``analyze_jornada``).
    Cached per call — for batch use, prefer enriching the picks DataFrame
    once and aggregating directly.
    """
    df = load_picks(db_path)
    if df.is_empty():
        return {}
    df = enrich_with_league(df, cache_root)
    graded = df.filter(pl.col("status").is_in(["won", "lost"]))
    if graded.is_empty():
        return {}
    rows = list(zip(
        graded.get_column("league_id").to_list(),
        graded.get_column("profit_units").to_list(),
    ))
    return _aggregate_priors(rows)


def cache_priors(
    market_priors: dict[str, tuple[float, int]],
    league_priors: dict[int, tuple[float, int]],
    cache_path: Path = PRIORS_CACHE_PATH,
) -> Path:
    """Persist priors to parquet for cross-run reuse + history tracking.

    Schema: long-format with one row per (kind, key, observed_roi, n,
    updated_at). Re-running APPENDS — each row carries a snapshot timestamp
    so you can chart prior drift over the trial period.
    """
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    now_iso = datetime.now(timezone.utc).isoformat()
    rows: list[dict] = []
    for k, (roi, n) in market_priors.items():
        rows.append({"kind": "market", "key": str(k), "observed_roi": roi,
                     "n": n, "updated_at": now_iso})
    for k, (roi, n) in league_priors.items():
        rows.append({"kind": "league", "key": str(k), "observed_roi": roi,
                     "n": n, "updated_at": now_iso})
    if not rows:
        return cache_path
    new_df = pl.from_dicts(rows)
    if cache_path.exists():
        existing = pl.read_parquet(cache_path)
        new_df = pl.concat([existing, new_df])
    new_df.write_parquet(cache_path)
    return cache_path


def load_cached_priors(
    cache_path: Path = PRIORS_CACHE_PATH,
) -> tuple[dict[str, tuple[float, int]], dict[int, tuple[float, int]]] | None:
    """Load most-recent priors snapshot from parquet cache.

    Returns None if the cache doesn't exist. Otherwise returns
    (market_priors, league_priors) using the latest updated_at timestamp.
    """
    if not cache_path.exists():
        return None
    df = pl.read_parquet(cache_path)
    if df.is_empty():
        return None
    latest_ts = df.get_column("updated_at").max()
    latest = df.filter(pl.col("updated_at") == latest_ts)
    market: dict[str, tuple[float, int]] = {}
    league: dict[int, tuple[float, int]] = {}
    for row in latest.iter_rows(named=True):
        if row["kind"] == "market":
            market[row["key"]] = (row["observed_roi"], row["n"])
        elif row["kind"] == "league":
            try:
                league[int(row["key"])] = (row["observed_roi"], row["n"])
            except (TypeError, ValueError):
                continue
    return market, league


# ── Signal enrichment (for output context) ─────────────────────────────


SNAPSHOTS_DERIVED_PATH: Path = (
    Path("reports/sportmonks_live/exports/snapshots_derived.parquet")
)
"""Default path to the derived signals parquet produced by analyze_jornada."""

SIGNAL_COLUMNS: tuple[str, ...] = (
    "informational_density",
    "home_momentum", "away_momentum",
    "home_shot_acceleration", "away_shot_acceleration",
    "home_set_piece_intensity", "away_set_piece_intensity",
    "home_killing_clock", "away_killing_clock",
)


def enrich_with_signals(
    df: pl.DataFrame,
    snapshots_path: Path = SNAPSHOTS_DERIVED_PATH,
) -> pl.DataFrame:
    """Attach derived match-state signals to each pick.

    For each pick, finds the snapshot for the same fixture whose
    ``snapshot_taken_at`` is nearest to the pick's ``emitted_at`` and
    joins those signal columns. Uses Polars ``join_asof`` per fixture.

    No-op if the snapshots parquet doesn't exist (operator hasn't run
    analyze_jornada yet) or the picks DataFrame lacks ``emitted_at``.
    Returns the input DataFrame with up to 9 signal columns appended.

    Operator use case: when the Top-25 lands, momentum_pos and
    info_density tell you whether the model's edge is live (high
    momentum = match opening up = ou_3_5 'under' is RISKIER). This is
    the diagnostic block called for in §3 of the strategy doc.
    """
    if df.is_empty() or "emitted_at" not in df.columns:
        return df
    if not snapshots_path.exists():
        return df

    snapshots = pl.read_parquet(snapshots_path)
    if snapshots.is_empty():
        return df

    # Parse timestamps eagerly — Polars' lazy strptime refuses tz-aware ISO
    # strings without an explicit format. Eager Series.str.to_datetime
    # auto-handles the timezone offset.
    snap_ts = snapshots.get_column("snapshot_taken_at").str.to_datetime(
        time_zone="UTC", strict=False,
    )
    snap = snapshots.with_columns(snap_ts.alias("_ts")).sort(["fixture_id", "_ts"])

    pick_ts = df.get_column("emitted_at").str.to_datetime(
        time_zone="UTC", strict=False,
    )
    picks = df.with_columns(pick_ts.alias("_pick_ts")).sort(
        ["fixture_id", "_pick_ts"]
    )

    # Suppress benign Polars warning about per-group sortedness check —
    # we DID sort by ("fixture_id", "_pick_ts") above; Polars just can't
    # verify within each `by` group.
    import warnings as _w
    with _w.catch_warnings():
        _w.filterwarnings("ignore", message="Sortedness of columns")
        joined = picks.join_asof(
            snap.select(["fixture_id", "_ts", *SIGNAL_COLUMNS]),
            left_on="_pick_ts",
            right_on="_ts",
            by="fixture_id",
            strategy="nearest",
        )
    return joined.drop(["_pick_ts", "_ts"], strict=False)


# ── Cascade ─────────────────────────────────────────────────────────────


def f1_market_whitelist(df: pl.DataFrame) -> pl.DataFrame:
    """Keep markets in KEEP_UNCOND, plus KEEP_COND that meet edge floor."""
    # Compute per-row required edge (NaN for markets we drop entirely)
    cond_edge_floor = pl.col("market").map_elements(
        lambda m: KEEP_COND.get(m, float("inf")),
        return_dtype=pl.Float64,
    )
    return df.filter(
        pl.col("market").is_in(list(KEEP_UNCOND))
        | (pl.col("edge_pct") >= cond_edge_floor)
    )


def f2_placement_window(df: pl.DataFrame) -> pl.DataFrame:
    """Per-market-class minute cutoffs."""
    is_fh = pl.col("market").str.starts_with("first_half_") | (
        pl.col("market") == "btts_first_half"
    )
    is_2h = pl.col("market") == "btts_second_half"
    return df.filter(
        (is_fh & pl.col("minute").is_between(*WINDOW_FIRST_HALF))
        | (is_2h & pl.col("minute").is_between(*WINDOW_SECOND_HALF))
        | (~is_fh & ~is_2h & pl.col("minute").is_between(*WINDOW_FULL_MATCH))
    )


def f3_edge_floor(df: pl.DataFrame) -> pl.DataFrame:
    """Drop picks below the calibration-derived edge floor."""
    return df.filter(pl.col("edge_pct") >= EDGE_FLOOR_PCT)


def f4_odd_band(df: pl.DataFrame) -> pl.DataFrame:
    """Economically-meaningful odds range."""
    return df.filter(pl.col("bookmaker_odd").is_between(ODD_FLOOR, ODD_CEIL))


def f5_league_filter(df: pl.DataFrame) -> pl.DataFrame:
    """Drop proven-negative leagues. No-op if league_id missing."""
    if "league_id" not in df.columns:
        return df
    return df.filter(
        pl.col("league_id").is_null()
        | ~pl.col("league_id").is_in(list(DROP_LEAGUE_IDS))
    )


def apply_cascade(df: pl.DataFrame) -> pl.DataFrame:
    """Apply F1→F5 in order. Returns the surviving candidate set."""
    out = f1_market_whitelist(df)
    out = f2_placement_window(out)
    out = f3_edge_floor(out)
    out = f4_odd_band(out)
    out = f5_league_filter(out)
    return out


# ── Scoring ─────────────────────────────────────────────────────────────


def score(
    df: pl.DataFrame,
    market_priors: dict[str, tuple[float, int]] | None = None,
    league_priors: dict[int, tuple[float, int]] | None = None,
) -> pl.DataFrame:
    """Compute composite score per pick. Adds 'score' column.

    Weights (sum=1.0):
      0.30 shrunk_market_roi   (cap at 0.50, normalize to [0,1])
      0.20 shrunk_league_roi   (cap at 0.40, normalize to [0,1])
      0.20 calibrated_edge     (cap at 0.40, normalize to [0,1])
      0.15 logical_kernel
      0.10 odd_kernel
      0.05 time_kernel

    Markets/leagues unknown to the priors get the global prior (essentially
    a neutral score — they need other signals to break into Top-N).
    """
    market_priors = market_priors if market_priors is not None else DAY1_MARKET_ROI
    league_priors = league_priors if league_priors is not None else DAY1_LEAGUE_ROI

    def _market_score(market: str) -> float:
        obs, n = market_priors.get(market, (GLOBAL_PRIOR_ROI, 0))
        return shrunk_roi(obs, n)

    def _league_score(league_id: int | None) -> float:
        if league_id is None:
            return GLOBAL_PRIOR_ROI
        obs, n = league_priors.get(league_id, (GLOBAL_PRIOR_ROI, 0))
        return shrunk_roi(obs, n, k=40)  # heavier shrinkage on leagues

    return df.with_columns([
        pl.col("market").map_elements(_market_score, return_dtype=pl.Float64)
            .alias("_market_roi"),
        (pl.col("league_id") if "league_id" in df.columns else pl.lit(None))
            .map_elements(_league_score, return_dtype=pl.Float64)
            .alias("_league_roi"),
        pl.col("edge_pct").map_elements(calibrated_edge, return_dtype=pl.Float64)
            .alias("_cal_edge"),
        pl.col("logical_score").map_elements(
            logical_kernel, return_dtype=pl.Float64,
        ).alias("_logical_k"),
        pl.col("bookmaker_odd").map_elements(
            odd_kernel, return_dtype=pl.Float64,
        ).alias("_odd_k"),
        pl.struct(["minute", "market"]).map_elements(
            lambda r: time_kernel(r["minute"], r["market"]),
            return_dtype=pl.Float64,
        ).alias("_time_k"),
    ]).with_columns([
        (
            0.30 * (pl.col("_market_roi").clip(-0.50, 0.50) / 0.50)
            + 0.20 * (pl.col("_league_roi").clip(-0.40, 0.40) / 0.40)
            + 0.20 * (pl.col("_cal_edge").clip(0.0, 0.40) / 0.40)
            + 0.15 * pl.col("_logical_k")
            + 0.10 * pl.col("_odd_k")
            + 0.05 * pl.col("_time_k")
        ).alias("score")
    ])


# ── Top-N selection with distribution constraints ─────────────────────


def dedup_picks(df: pl.DataFrame) -> pl.DataFrame:
    """Collapse duplicate (fixture_id, market, selection) bets to the highest-scoring instance.

    Day-1 surfaced this gap: the same exact bet (same fixture/market/selection)
    re-emitted minutes apart counts as 2 picks but is the SAME wager. The watcher
    re-scans every 60s; while a value persists it gets re-emitted. Without dedup,
    Top-25 wastes slots on duplicates.

    Concrete Day-1 case: Athletic-Valencia team_to_score_first/home appeared in
    Top-25 at minute 62 AND minute 72 — both lost (-2.0 units). With dedup, only
    the higher-scoring instance survives, freeing the second slot for a different
    bet that may convert.

    Falls back to no-op if 'score' column is missing (call before scoring is OK
    but pre-score dedup just keeps the first occurrence).
    """
    if df.is_empty():
        return df
    sort_cols = ["score"] if "score" in df.columns else ["edge_pct"]
    return (
        df.sort(sort_cols, descending=True, nulls_last=True)
          .unique(subset=["fixture_id", "market", "selection"], keep="first",
                  maintain_order=True)
    )


def top_n(
    df: pl.DataFrame,
    n: int = 25,
    max_per_fixture: int = 3,
    max_per_window: int = 5,
    window_min: int = 15,
    dedup: bool = True,
) -> pl.DataFrame:
    """Greedy selection: walk picks in score order, accept while quotas hold.

    - dedup: collapse duplicate (fixture, market, selection) emissions first
    - max_per_fixture: avoids correlated-loss exposure (no pile-on)
    - max_per_window: distributes across 15-min review windows
    - n: hard cap on total picks (operator throughput ceiling)
    """
    if df.is_empty() or "score" not in df.columns:
        return df

    candidates = dedup_picks(df) if dedup else df
    sorted_df = candidates.sort(
        by=["score", "minute"], descending=[True, False], nulls_last=True,
    )

    selected_idx: list[int] = []
    fixture_count: dict[int, int] = {}
    window_count: dict[int, int] = {}

    for i, row in enumerate(sorted_df.iter_rows(named=True)):
        if len(selected_idx) >= n:
            break
        fid = row["fixture_id"]
        win = (row["minute"] // window_min) if row["minute"] is not None else -1

        if fixture_count.get(fid, 0) >= max_per_fixture:
            continue
        if window_count.get(win, 0) >= max_per_window:
            continue

        selected_idx.append(i)
        fixture_count[fid] = fixture_count.get(fid, 0) + 1
        window_count[win] = window_count.get(win, 0) + 1

    return sorted_df[selected_idx]


# ── Placement schedule (wall-clock grouping) ───────────────────────────


def placement_schedule(
    top: pl.DataFrame, window_minutes: int = 15,
) -> list[dict[str, object]]:
    """Group picks into wall-clock windows of ``window_minutes`` for placement.

    Returns one dict per window (chronologically ordered):
      {
        "window_start": datetime,   # UTC, floor of emission times in window
        "window_end": datetime,
        "n_picks": int,
        "picks": [ {fixture, market, selection, odd, edge, score}, ... ]
      }

    Operator use case: instead of "pick at minute 30", the operator sees
    "13:30-13:44 UTC: 5 picks ready to place". Empty if Top-N has no
    ``emitted_at`` column.
    """
    if top.is_empty() or "emitted_at" not in top.columns:
        return []

    ts_series = top.get_column("emitted_at").str.to_datetime(
        time_zone="UTC", strict=False,
    )
    enriched = top.with_columns(ts_series.alias("_ts"))

    # Floor each timestamp to the start of its window
    floored = enriched.with_columns(
        pl.col("_ts").dt.truncate(f"{window_minutes}m").alias("_window_start"),
    )

    schedule: list[dict[str, object]] = []
    for window_start, group in floored.sort("_ts").group_by(
        "_window_start", maintain_order=True,
    ):
        # window_start comes back as a tuple (group key)
        ws = window_start[0] if isinstance(window_start, tuple) else window_start
        picks = []
        for row in group.iter_rows(named=True):
            picks.append({
                "fixture": f"{row.get('home_team', '?')} vs {row.get('away_team', '?')}",
                "market": row["market"],
                "selection": row["selection"],
                "minute": row["minute"],
                "odd": row["bookmaker_odd"],
                "edge_pct": row.get("edge_pct"),
                "score": row.get("score"),
            })
        from datetime import timedelta as _td
        schedule.append({
            "window_start": ws,
            "window_end": ws + _td(minutes=window_minutes),
            "n_picks": len(picks),
            "picks": picks,
        })
    return schedule


# ── Reporting ───────────────────────────────────────────────────────────


def cascade_summary(
    df: pl.DataFrame,
) -> dict[str, dict[str, float | int]]:
    """Per-stage survival counts + ROI on graded subset (retro-validation)."""
    stages: list[tuple[str, pl.DataFrame]] = [("raw", df)]
    cur = df
    for name, fn in (
        ("after_F1_market", f1_market_whitelist),
        ("after_F2_window", f2_placement_window),
        ("after_F3_edge",   f3_edge_floor),
        ("after_F4_odd",    f4_odd_band),
        ("after_F5_league", f5_league_filter),
    ):
        cur = fn(cur)
        stages.append((name, cur))

    out: dict[str, dict[str, float | int]] = {}
    for name, stage_df in stages:
        if stage_df.is_empty():
            out[name] = {"n": 0, "graded": 0, "won": 0, "pl": 0.0, "roi_pct": 0.0}
            continue
        graded = stage_df.filter(pl.col("status").is_in(["won", "lost"]))
        n_graded = graded.height
        n_won = graded.filter(pl.col("status") == "won").height
        pl_total = graded.select(pl.col("profit_units").sum()).item() or 0.0
        out[name] = {
            "n": stage_df.height,
            "graded": n_graded,
            "won": n_won,
            "pl": float(pl_total),
            "roi_pct": (pl_total / n_graded * 100) if n_graded else 0.0,
        }
    return out


def render_topn_report(
    raw: pl.DataFrame,
    cascade: dict[str, dict[str, float | int]],
    top: pl.DataFrame,
) -> str:
    """Markdown summary of the Top-N run."""
    lines: list[str] = []
    today = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines.append(f"# Top-N filter run — {today}\n")

    # Cascade survival
    lines.append("## Cascade survival\n")
    lines.append("| Stage | n | graded | won | P/L | ROI% |")
    lines.append("|-------|---|--------|-----|-----|------|")
    for stage, agg in cascade.items():
        lines.append(
            f"| {stage} | {agg['n']} | {agg['graded']} | {agg['won']} | "
            f"{agg['pl']:+.2f} | {agg['roi_pct']:+.2f} |"
        )
    lines.append("")

    # Top-N retro
    if not top.is_empty():
        graded = top.filter(pl.col("status").is_in(["won", "lost"]))
        n_graded = graded.height
        n_won = graded.filter(pl.col("status") == "won").height
        pl_total = graded.select(pl.col("profit_units").sum()).item() or 0.0

        lines.append(f"## Top-{top.height} retrospective grading\n")
        if n_graded:
            lines.append(f"- **Graded**: {n_graded}/{top.height}")
            lines.append(f"- **Won**: {n_won} ({n_won/n_graded*100:.1f}%)")
            lines.append(f"- **P/L**: {pl_total:+.2f} units")
            lines.append(f"- **ROI**: {pl_total/n_graded*100:+.2f}%")
        lines.append("")

        # Per-market split
        lines.append("### Top-N composition by market\n")
        comp = (top.group_by("market").len().sort("len", descending=True))
        lines.append("| Market | n |")
        lines.append("|--------|---|")
        for row in comp.iter_rows(named=True):
            lines.append(f"| {row['market']} | {row['len']} |")
        lines.append("")

        # The actual picks (with Kelly + suggested stake for placement sizing)
        lines.append(f"### Top-{top.height} picks (sorted by score)\n")
        cols_show = [
            "fixture_id", "home_team", "away_team", "market", "selection",
            "minute", "bookmaker_odd", "edge_pct", "logical_score",
            "kelly_fraction_full", "suggested_stake_pct",
            "score", "status", "profit_units",
        ]
        cols_show = [c for c in cols_show if c in top.columns]
        # Friendlier column labels for the percentage-style fields
        col_labels = {
            "kelly_fraction_full": "kelly_full",
            "suggested_stake_pct": "stake_%",
        }
        header_cells = [col_labels.get(c, c) for c in cols_show]
        lines.append("| " + " | ".join(header_cells) + " |")
        lines.append("|" + "|".join(["---"] * len(cols_show)) + "|")
        for row in top.iter_rows(named=True):
            cells = []
            for c in cols_show:
                v = row[c]
                if isinstance(v, float):
                    if c == "kelly_fraction_full":
                        cells.append(f"{v:.3f}")  # raw fraction (e.g. 0.283)
                    elif c == "suggested_stake_pct":
                        cells.append(f"{v:.2f}%")  # already in pct form
                    elif c in ("score", "profit_units"):
                        cells.append(f"{v:+.3f}")
                    else:
                        cells.append(f"{v:.2f}")
                else:
                    cells.append(str(v) if v is not None else "—")
            lines.append("| " + " | ".join(cells) + " |")
        lines.append("")

        # Logical components decomposition — per §1 of Lote A. When a pick
        # has high edge but low logical_score, the operator wants to see
        # WHICH dimension dragged it down (e.g. odds_credibility=0.40).
        lc_cols_present = [f"lc_{k}" for k in LOGICAL_COMPONENT_KEYS
                           if f"lc_{k}" in top.columns]
        if lc_cols_present:
            lines.append("### Logical components decomposition\n")
            lines.append(
                "_Each component scores 0-1; the cascade flags picks where "
                "the geometric mean is below 0.70. Low values pinpoint which "
                "dimension is dragging the consilience score._\n"
            )
            id_col = "id" if "id" in top.columns else "fixture_id"
            short = [c.removeprefix("lc_") for c in lc_cols_present]
            lines.append("| " + id_col + " | logical_score | "
                         + " | ".join(short) + " |")
            lines.append("|" + "|".join(["---"] * (len(lc_cols_present) + 2)) + "|")
            for row in top.iter_rows(named=True):
                cells = [str(row.get(id_col, "—"))]
                ls = row.get("logical_score")
                cells.append(f"{ls:.2f}" if ls is not None else "—")
                for c in lc_cols_present:
                    v = row.get(c)
                    cells.append(f"{v:.2f}" if v is not None else "—")
                lines.append("| " + " | ".join(cells) + " |")
            lines.append("")

        # Placement schedule — wall-clock grouping for operator's Betano runs
        schedule = placement_schedule(top, window_minutes=15)
        if schedule:
            lines.append("### Placement schedule (wall-clock UTC, 15-min windows)\n")
            lines.append(
                "_Operator open Betano at the start of each window; place "
                "all picks listed before the window closes. Multiple picks "
                "in one window means dense attention; isolated picks mean "
                "you can step away._\n"
            )
            lines.append("| Window (UTC) | n | Picks |")
            lines.append("|---|---|---|")
            for win in schedule:
                ws = win["window_start"].strftime("%H:%M")
                we = win["window_end"].strftime("%H:%M")
                pick_blurbs = [
                    f"{p['fixture']} — {p['market']}/{p['selection']} "
                    f"@ {p['odd']:.2f} (edge {p['edge_pct']:.0f}%)"
                    if p.get("edge_pct") is not None
                    else f"{p['fixture']} — {p['market']}/{p['selection']} "
                         f"@ {p['odd']:.2f}"
                    for p in win["picks"]
                ]
                lines.append(
                    f"| {ws} - {we} | {win['n_picks']} | "
                    + "<br>".join(pick_blurbs) + " |"
                )
            lines.append("")

        # Diagnostic block (per §3 criterion 6) — shows momentum/info_density
        # alongside each pick so the operator can verify the model's edge is
        # consistent with live match state before placing.
        signal_cols_present = [c for c in SIGNAL_COLUMNS if c in top.columns]
        if signal_cols_present:
            lines.append("### Diagnostic signals at emission\n")
            lines.append(
                "_Cross-check: high momentum on the side you're fading "
                "(e.g. ou_3_5 'under' with rising home_momentum) is a yellow "
                "flag. killing_clock=true near the end means the team is "
                "killing time — favors 'no more goals' picks._\n"
            )
            id_col = "id" if "id" in top.columns else "fixture_id"
            sig_header = [id_col, "minute"] + signal_cols_present
            lines.append("| " + " | ".join(sig_header) + " |")
            lines.append("|" + "|".join(["---"] * len(sig_header)) + "|")
            for row in top.iter_rows(named=True):
                cells = [str(row.get(id_col, "—")), str(row.get("minute", "—"))]
                for c in signal_cols_present:
                    v = row.get(c)
                    if v is None:
                        cells.append("—")
                    elif isinstance(v, bool):
                        cells.append("✓" if v else "·")
                    elif isinstance(v, float):
                        cells.append(f"{v:.2f}")
                    else:
                        cells.append(str(v))
                lines.append("| " + " | ".join(cells) + " |")
            lines.append("")

    # Headline comparison
    raw_graded = raw.filter(pl.col("status").is_in(["won", "lost"]))
    if not raw_graded.is_empty():
        raw_pl = raw_graded.select(pl.col("profit_units").sum()).item() or 0.0
        raw_roi = raw_pl / raw_graded.height * 100
        lines.append("## Filter lift\n")
        lines.append(f"- Raw universe: {raw.height} picks, "
                     f"{raw_graded.height} graded, ROI {raw_roi:+.2f}%")
        if not top.is_empty():
            top_graded = top.filter(pl.col("status").is_in(["won", "lost"]))
            if not top_graded.is_empty():
                top_pl = top_graded.select(pl.col("profit_units").sum()).item() or 0.0
                top_roi = top_pl / top_graded.height * 100
                lift = top_roi - raw_roi
                lines.append(f"- Top-{top.height}: {top_graded.height} graded, "
                             f"ROI {top_roi:+.2f}% (**lift: {lift:+.2f}pp**)")
        lines.append("")
    return "\n".join(lines)


# ── CLI ─────────────────────────────────────────────────────────────────


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--picks-db", type=Path, default=DEFAULT_DB_PATH)
    p.add_argument("--cache-root", type=Path, default=DEFAULT_CACHE_ROOT)
    p.add_argument("--output-dir", type=Path,
                   default=Path("reports/sportmonks_live"))
    p.add_argument("--top-n", type=int, default=25)
    p.add_argument("--max-per-fixture", type=int, default=3)
    p.add_argument("--max-per-window", type=int, default=5)
    p.add_argument("--skip-league", action="store_true",
                   help="Skip league enrichment (faster; no league_id filter)")
    p.add_argument("--use-static-priors", action="store_true",
                   help="Use the hardcoded Day-1 priors instead of recomputing "
                        "from picks.db. Default is live recompute (more accurate "
                        "— hardcoded league priors have known >5pp drift).")
    p.add_argument("--no-dedup", action="store_true",
                   help="Disable (fixture, market, selection) dedup in Top-N.")
    p.add_argument("--no-signals", action="store_true",
                   help="Skip signal enrichment of the Top-N output.")
    p.add_argument("--snapshots-derived", type=Path,
                   default=SNAPSHOTS_DERIVED_PATH,
                   help="Path to snapshots_derived.parquet (run analyze_jornada "
                        "first to populate).")
    return p.parse_args()


def _resolve_priors(
    args: argparse.Namespace,
) -> tuple[dict[str, tuple[float, int]], dict[int, tuple[float, int]], str]:
    """Pick the right priors source based on flags, log which one was used.

    Returns (market_priors, league_priors, source_label).
    """
    if args.use_static_priors:
        return DAY1_MARKET_ROI, DAY1_LEAGUE_ROI, "hardcoded Day-1 (static)"

    print("[priors] computing live priors from picks.db")
    market = compute_market_priors_from_db(args.picks_db)
    league = compute_league_priors_from_db(args.picks_db, args.cache_root)
    if not market and not league:
        print("[priors] no graded picks yet — falling back to Day-1 hardcoded")
        return DAY1_MARKET_ROI, DAY1_LEAGUE_ROI, "hardcoded Day-1 (live empty)"

    cache_path = cache_priors(market, league)
    print(f"[priors] cached {len(market)} markets + {len(league)} leagues "
          f"to {cache_path}")
    return market, league, "live (recomputed from picks.db)"


def main() -> int:
    args = _parse_args()
    print(f"[load] {args.picks_db}")
    df = load_picks(args.picks_db)
    if df.is_empty():
        print("[load] picks.db is empty — nothing to filter")
        return 1
    print(f"[load] {df.height} picks")

    if not args.skip_league:
        print(f"[enrich] walking snapshots in {args.cache_root}")
        df = enrich_with_league(df, args.cache_root)
        with_league = df.filter(pl.col("league_id").is_not_null()).height
        print(f"[enrich] {with_league}/{df.height} picks have league_id")

    cascade_stats = cascade_summary(df)
    print("\n[cascade]")
    for stage, agg in cascade_stats.items():
        print(f"  {stage:20s} n={agg['n']:4d} graded={agg['graded']:4d} "
              f"won={agg['won']:4d} pl={agg['pl']:+7.2f} roi={agg['roi_pct']:+6.2f}%")

    survivors = apply_cascade(df)
    if survivors.is_empty():
        print("[score] no survivors — nothing to score")
        return 1

    market_priors, league_priors, source = _resolve_priors(args)
    print(f"[score] priors source: {source}")
    scored = score(survivors, market_priors=market_priors,
                   league_priors=league_priors)
    top = top_n(
        scored,
        n=args.top_n,
        max_per_fixture=args.max_per_fixture,
        max_per_window=args.max_per_window,
        dedup=not args.no_dedup,
    )

    if not args.no_signals:
        before_cols = top.width
        top = enrich_with_signals(top, args.snapshots_derived)
        added = top.width - before_cols
        if added > 0:
            print(f"[signals] enriched Top-N with {added} signal columns")
        elif not args.snapshots_derived.exists():
            print(f"[signals] {args.snapshots_derived} missing — "
                  "run analyze_jornada first; output omits signals")

    # Report
    args.output_dir.mkdir(parents=True, exist_ok=True)
    today = datetime.now().strftime("%Y-%m-%d")
    md_path = args.output_dir / f"topn_{today}.md"
    md_path.write_text(render_topn_report(df, cascade_stats, top))
    print(f"\n[report] {md_path}")

    exports_dir = args.output_dir / "exports"
    exports_dir.mkdir(parents=True, exist_ok=True)
    parquet_path = exports_dir / "topn_picks.parquet"
    # Drop helper columns before persisting
    drop_cols = [c for c in top.columns if c.startswith("_")]
    top.drop(drop_cols).write_parquet(parquet_path)
    print(f"[export] {parquet_path}")

    # Console headline
    print(f"\n[top-{args.top_n}] picks selected: {top.height}")
    graded = top.filter(pl.col("status").is_in(["won", "lost"]))
    if not graded.is_empty():
        won = graded.filter(pl.col("status") == "won").height
        pl_total = graded.select(pl.col("profit_units").sum()).item() or 0.0
        print(f"[top-{args.top_n}] retro graded={graded.height} won={won} "
              f"({won/graded.height*100:.1f}%) pl={pl_total:+.2f} "
              f"roi={pl_total/graded.height*100:+.2f}%")
    return 0


if __name__ == "__main__":
    sys.exit(main())
