"""Top-N filter cascade — destila ~937 picks/jornada a ~25 high-conf placements.

Day-1 (2026-05-10) emitted 937 picks across 78 fixtures with +13.19% ROI on the
805-graded subset. Operationally impossible to place; operator manual ceiling
is ~25/jornada. This module applies a 5-filter cascade + Bayesian-shrunk
scoring to surface the Top-N picks the operator should actually consider.

The cascade is calibrated against Day-1 numbers — every threshold has an
empirical justification documented in the constant block. Re-tune with
``analyze_jornada.py`` re-graded data after Day-3 / Day-7.

Usage::

    # CLI on the live picks DB
    uv run python -m scripts.spike.sportmonks.topn_filter

    # Programmatic
    from scripts.spike.sportmonks.topn_filter import (
        load_picks, apply_cascade, score, top_n,
    )
    df = load_picks()
    df = apply_cascade(df)
    df = score(df)
    top = top_n(df, n=25)

Outputs (CLI):
- Markdown summary at ``reports/sportmonks_live/topn_{date}.md``
- Parquet of top-25 at ``reports/sportmonks_live/exports/topn_picks.parquet``

Read-only: never mutates picks.db, never modifies cache files.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import datetime
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


# ── Day-1 market priors (frozen — used for pre-Day-2 scoring) ─────────
# These get overwritten if `analyze_jornada.py` produces a fresher snapshot.
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


def load_picks(db_path: Path = DEFAULT_DB_PATH) -> pl.DataFrame:
    """Read picks table from SQLite into Polars."""
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = [dict(r) for r in conn.execute("SELECT * FROM picks")]
    if not rows:
        return pl.DataFrame()
    return pl.from_dicts(rows, infer_schema_length=None)


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


def top_n(
    df: pl.DataFrame,
    n: int = 25,
    max_per_fixture: int = 3,
    max_per_window: int = 5,
    window_min: int = 15,
) -> pl.DataFrame:
    """Greedy selection: walk picks in score order, accept while quotas hold.

    - max_per_fixture: avoids correlated-loss exposure (no pile-on)
    - max_per_window: distributes across 15-min review windows
    - n: hard cap on total picks (operator throughput ceiling)
    """
    if df.is_empty() or "score" not in df.columns:
        return df

    sorted_df = df.sort(
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

        # The actual picks
        lines.append(f"### Top-{top.height} picks (sorted by score)\n")
        cols_show = [
            "fixture_id", "home_team", "away_team", "market", "selection",
            "minute", "bookmaker_odd", "edge_pct", "logical_score",
            "score", "status", "profit_units",
        ]
        cols_show = [c for c in cols_show if c in top.columns]
        lines.append("| " + " | ".join(cols_show) + " |")
        lines.append("|" + "|".join(["---"] * len(cols_show)) + "|")
        for row in top.iter_rows(named=True):
            cells = []
            for c in cols_show:
                v = row[c]
                if isinstance(v, float):
                    cells.append(f"{v:+.3f}" if c in ("score", "profit_units")
                                 else f"{v:.2f}")
                else:
                    cells.append(str(v) if v is not None else "—")
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
    return p.parse_args()


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

    scored = score(survivors)
    top = top_n(
        scored,
        n=args.top_n,
        max_per_fixture=args.max_per_fixture,
        max_per_window=args.max_per_window,
    )

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
