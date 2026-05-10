"""End-of-jornada analysis — grade picks + comprehensive markdown report.

Designed to run AFTER the watcher has been stopped and all matches have
finished. Walks the snapshot cache to derive final outcomes, grades every
pick in picks.db, then produces:

1. Markdown report at ``reports/sportmonks_live/jornada_analysis_{date}.md``
2. Parquet exports for downstream Polars/DuckDB analysis:
   - ``reports/sportmonks_live/exports/picks_graded.parquet``
   - ``reports/sportmonks_live/exports/decisions.parquet``
   - ``reports/sportmonks_live/exports/snapshots_derived.parquet``

Usage::

    uv run python -m scripts.spike.sportmonks.analyze_jornada

    # Custom paths
    uv run python -m scripts.spike.sportmonks.analyze_jornada \\
        --cache-root data/cache/sportmonks \\
        --picks-db data/cache/sportmonks/picks.db

The grading step is IDEMPOTENT — re-running won't double-count. Only picks
with status='pending' get graded; already-graded picks stay locked.

Read-mostly: only the picks DB ``status`` column is mutated. Cache files
are never modified.
"""

from __future__ import annotations

import argparse
import json
import math
import sqlite3
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from bip.evaluation.live.match_state import LiveMatchState  # noqa: E402
from bip.evaluation.live.pick_tracker import (  # noqa: E402
    DEFAULT_DB_PATH,
    PickTracker,
)
from bip.sports.football.sportmonks.cache import (  # noqa: E402
    DEFAULT_CACHE_ROOT,
    SportmonksCache,
)
from bip.sports.football.sportmonks.schemas import Fixture  # noqa: E402


# ── Outcome derivation (mirrors backtest._derive_final_outcome) ──────────


@dataclass(frozen=True)
class FinalOutcome:
    fixture_id: int
    league_id: int | None
    home_goals: int
    away_goals: int
    home_goals_first_half: int
    away_goals_first_half: int
    total_cards: int
    total_corners: int
    is_finished: bool

    @property
    def fulltime_result(self) -> str:
        if self.home_goals > self.away_goals:
            return "home"
        if self.home_goals == self.away_goals:
            return "draw"
        return "away"

    @property
    def first_half_result(self) -> str:
        if self.home_goals_first_half > self.away_goals_first_half:
            return "home"
        if self.home_goals_first_half == self.away_goals_first_half:
            return "draw"
        return "away"

    @property
    def total_goals(self) -> int:
        return self.home_goals + self.away_goals

    @property
    def total_goals_first_half(self) -> int:
        return self.home_goals_first_half + self.away_goals_first_half

    @property
    def total_goals_second_half(self) -> int:
        return self.total_goals - self.total_goals_first_half

    @property
    def home_goals_second_half(self) -> int:
        return self.home_goals - self.home_goals_first_half

    @property
    def away_goals_second_half(self) -> int:
        return self.away_goals - self.away_goals_first_half

    @property
    def btts(self) -> bool:
        return self.home_goals > 0 and self.away_goals > 0

    @property
    def btts_first_half(self) -> bool:
        return (
            self.home_goals_first_half > 0
            and self.away_goals_first_half > 0
        )

    @property
    def btts_second_half(self) -> bool:
        return (
            self.home_goals_second_half > 0
            and self.away_goals_second_half > 0
        )


def _derive_final_outcome(cache: SportmonksCache, fixture_id: int) -> FinalOutcome | None:
    """Walk the fixture's snapshots and extract the final state.

    Returns None when no snapshot has is_finished=True (match incomplete
    or capture stopped before FT).
    """
    paths = cache.list_snapshots(fixture_id)
    if not paths:
        return None
    # Walk newest-first, find the finished snapshot
    for p in reversed(paths):
        try:
            payload = json.loads(p.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        record = payload.get("data") or payload.get("raw")
        if not record:
            continue
        try:
            fixture = Fixture.model_validate(record)
            state = LiveMatchState.from_fixture(fixture)
        except Exception:
            continue
        if not state.is_finished:
            continue
        # Found FT snapshot — extract everything
        home_1h = sum(
            1 for minute, team in state.goal_events
            if minute <= 45 and team == state.home_team_id
        )
        away_1h = sum(
            1 for minute, team in state.goal_events
            if minute <= 45 and team == state.away_team_id
        )
        total_cards = (
            len(state.yellow_card_events) + len(state.red_card_events)
        )
        total_corners = state.home_corners + state.away_corners
        return FinalOutcome(
            fixture_id=fixture_id,
            league_id=fixture.league_id,
            home_goals=state.home_goals,
            away_goals=state.away_goals,
            home_goals_first_half=home_1h,
            away_goals_first_half=away_1h,
            total_cards=total_cards,
            total_corners=total_corners,
            is_finished=True,
        )
    return None


def _grade_pick(market: str, selection: str, outcome: FinalOutcome) -> bool | None:
    """Return True if the pick won, False if lost, None if ungradable."""
    if market == "fulltime_result":
        return selection == outcome.fulltime_result
    if market == "first_half_result":
        return selection == outcome.first_half_result
    if market == "double_chance":
        ft = outcome.fulltime_result
        return (
            (selection == "1x" and ft in ("home", "draw"))
            or (selection == "x2" and ft in ("draw", "away"))
            or (selection == "12" and ft in ("home", "away"))
        )
    if market == "draw_no_bet":
        ft = outcome.fulltime_result
        if ft == "draw":
            return None  # void
        return selection == ft
    if market == "btts":
        return (selection == "yes") == outcome.btts
    if market == "btts_first_half":
        return (selection == "yes") == outcome.btts_first_half
    if market == "btts_second_half":
        return (selection == "yes") == outcome.btts_second_half
    if market in ("home_clean_sheet", "away_clean_sheet"):
        opp_goals = (
            outcome.away_goals if market == "home_clean_sheet"
            else outcome.home_goals
        )
        return (selection == "yes") == (opp_goals == 0)
    if market == "team_to_score_first":
        if not outcome.is_finished:
            return None
        # Find first goal in event timeline — we don't have it directly here,
        # but home_1h/away_1h gives us hint. For full support we'd need
        # goal_events sorted; outcome doesn't carry them.
        # Approximation: if home_goals > 0 and away_goals == 0, home scored first
        # for sure. Otherwise we can't tell from outcome alone.
        if outcome.home_goals == 0 and outcome.away_goals == 0:
            return selection == "none"
        if outcome.home_goals > 0 and outcome.away_goals == 0:
            return selection == "home"
        if outcome.away_goals > 0 and outcome.home_goals == 0:
            return selection == "away"
        return None  # both scored — order unknown without event timeline
    if market.startswith("ou_"):
        line = float(market.split("_")[1] + "." + market.split("_")[2])
        if selection == "over":
            return outcome.total_goals > line
        if selection == "under":
            return outcome.total_goals < line + 1
        return None
    if market.startswith("first_half_ou_"):
        line = float(market.split("_")[3] + "." + market.split("_")[4])
        if selection == "over":
            return outcome.total_goals_first_half > line
        if selection == "under":
            return outcome.total_goals_first_half < line + 1
        return None
    if market in ("home_ou_1_5", "away_ou_1_5"):
        team_goals = (
            outcome.home_goals if market == "home_ou_1_5"
            else outcome.away_goals
        )
        if selection == "over":
            return team_goals > 1.5
        if selection == "under":
            return team_goals < 1.5
        return None
    if market.startswith("corners_total_"):
        # corners_total_8_5 → 8.5
        parts = market.split("_")
        line = float(parts[2] + "." + parts[3])
        if selection == "over":
            return outcome.total_corners > line
        if selection == "under":
            return outcome.total_corners < line + 1
    if market.startswith("cards_total_"):
        parts = market.split("_")
        line = float(parts[2] + "." + parts[3])
        if selection == "over":
            return outcome.total_cards > line
        if selection == "under":
            return outcome.total_cards < line + 1
    return None  # market we don't grade


# ── Grading pass ─────────────────────────────────────────────────────────


def grade_pending_picks(
    tracker: PickTracker, cache: SportmonksCache,
) -> tuple[int, int, int]:
    """Grade every pending pick. Returns (n_graded, n_won, n_void)."""
    n_graded = n_won = n_void = 0
    with sqlite3.connect(tracker.db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT id, fixture_id, market, selection, bookmaker_odd "
            "FROM picks WHERE status='pending'"
        ).fetchall()

    # Cache outcomes per fixture
    outcomes: dict[int, FinalOutcome | None] = {}

    for row in rows:
        fid = row["fixture_id"]
        if fid not in outcomes:
            outcomes[fid] = _derive_final_outcome(cache, fid)
        outcome = outcomes[fid]
        if outcome is None:
            continue  # match not finished → leave pending
        won = _grade_pick(row["market"], row["selection"], outcome)
        if won is None:
            tracker.update_outcome(row["id"], status="void", profit_units=0.0)
            n_graded += 1
            n_void += 1
            continue
        if won:
            profit = row["bookmaker_odd"] - 1.0
            tracker.update_outcome(row["id"], status="won", profit_units=profit)
            n_won += 1
        else:
            tracker.update_outcome(row["id"], status="lost", profit_units=-1.0)
        n_graded += 1
    return n_graded, n_won, n_void


# ── Reporting ────────────────────────────────────────────────────────────


def _edge_bucket(edge_pct: float) -> str:
    if edge_pct < 5:
        return "3-5%"
    if edge_pct < 8:
        return "5-8%"
    if edge_pct < 15:
        return "8-15%"
    if edge_pct < 30:
        return "15-30%"
    return "30%+"


def _logical_bucket(score: float | None) -> str:
    if score is None:
        return "no_score"
    if score < 0.5:
        return "0.40-0.50"
    if score < 0.6:
        return "0.50-0.60"
    if score < 0.7:
        return "0.60-0.70 (flagged)"
    if score < 0.85:
        return "0.70-0.85 (clean)"
    return "0.85+ (high-confidence)"


def headline_metrics(tracker: PickTracker) -> dict:
    """Top-line numbers from the picks table."""
    with sqlite3.connect(tracker.db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM picks").fetchall()
    n_total = len(rows)
    n_clean = sum(1 for r in rows if not r["flagged_reason"])
    n_flagged = n_total - n_clean
    graded = [r for r in rows if r["status"] in ("won", "lost", "void")]
    n_won = sum(1 for r in graded if r["status"] == "won")
    n_void = sum(1 for r in graded if r["status"] == "void")
    profit_total = sum(r["profit_units"] or 0 for r in graded)
    n_decided = len(graded) - n_void
    return {
        "n_total": n_total,
        "n_clean": n_clean,
        "n_flagged": n_flagged,
        "n_graded": len(graded),
        "n_won": n_won,
        "n_void": n_void,
        "win_rate": (n_won / n_decided) if n_decided else None,
        "total_profit_units": profit_total,
        "roi_pct": (profit_total / n_decided * 100) if n_decided else None,
        "rows": rows,
    }


def by_market_breakdown(rows) -> list[dict]:
    by: dict[str, dict] = defaultdict(
        lambda: {"n": 0, "won": 0, "void": 0, "profit": 0.0}
    )
    for r in rows:
        if r["status"] not in ("won", "lost", "void"):
            continue
        m = by[r["market"]]
        m["n"] += 1
        if r["status"] == "won":
            m["won"] += 1
        elif r["status"] == "void":
            m["void"] += 1
        m["profit"] += r["profit_units"] or 0
    out = []
    for market, agg in sorted(by.items()):
        n_decided = agg["n"] - agg["void"]
        out.append({
            "market": market,
            "n": agg["n"],
            "won": agg["won"],
            "void": agg["void"],
            "win_rate": (agg["won"] / n_decided) if n_decided else 0,
            "roi_pct": (agg["profit"] / n_decided * 100) if n_decided else 0,
        })
    return out


def by_edge_bucket(rows) -> list[dict]:
    by: dict[str, dict] = defaultdict(
        lambda: {"n": 0, "won": 0, "profit": 0.0, "edges": []}
    )
    for r in rows:
        if r["status"] not in ("won", "lost"):
            continue
        bucket = _edge_bucket(r["edge_pct"])
        b = by[bucket]
        b["n"] += 1
        if r["status"] == "won":
            b["won"] += 1
        b["profit"] += r["profit_units"] or 0
        b["edges"].append(r["edge_pct"])
    order = ["3-5%", "5-8%", "8-15%", "15-30%", "30%+"]
    return [
        {
            "bucket": k,
            "n": by[k]["n"],
            "won": by[k]["won"],
            "win_rate": by[k]["won"] / by[k]["n"] if by[k]["n"] else 0,
            "roi_pct": by[k]["profit"] / by[k]["n"] * 100 if by[k]["n"] else 0,
            "avg_edge": sum(by[k]["edges"]) / len(by[k]["edges"]) if by[k]["edges"] else 0,
        }
        for k in order if k in by
    ]


def by_logical_score_bucket(rows) -> list[dict]:
    by: dict[str, dict] = defaultdict(lambda: {"n": 0, "won": 0, "profit": 0.0})
    for r in rows:
        if r["status"] not in ("won", "lost"):
            continue
        bucket = _logical_bucket(r["logical_score"])
        b = by[bucket]
        b["n"] += 1
        if r["status"] == "won":
            b["won"] += 1
        b["profit"] += r["profit_units"] or 0
    return [
        {
            "bucket": k,
            "n": v["n"],
            "won": v["won"],
            "win_rate": v["won"] / v["n"] if v["n"] else 0,
            "roi_pct": v["profit"] / v["n"] * 100 if v["n"] else 0,
        }
        for k, v in sorted(by.items())
    ]


def gate_rejection_summary(tracker: PickTracker) -> list[dict]:
    """Aggregate drop_reason counts from pick_decisions."""
    with sqlite3.connect(tracker.db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT drop_reason, COUNT(*) AS n "
            "FROM pick_decisions WHERE decision='drop' "
            "GROUP BY drop_reason ORDER BY n DESC"
        ).fetchall()
    return [{"drop_reason": r["drop_reason"], "n": r["n"]} for r in rows]


def per_league_breakdown(rows, cache: SportmonksCache) -> list[dict]:
    """Map picks to leagues via fixture snapshots, aggregate ROI."""
    fixture_to_league: dict[int, int | None] = {}
    by_league: dict[int | None, dict] = defaultdict(
        lambda: {"n": 0, "won": 0, "profit": 0.0, "fixtures": set()}
    )
    for r in rows:
        if r["status"] not in ("won", "lost"):
            continue
        fid = r["fixture_id"]
        if fid not in fixture_to_league:
            paths = cache.list_snapshots(fid)
            league_id = None
            for p in paths[:1]:  # first snapshot has league_id
                try:
                    payload = json.loads(p.read_text())
                    league_id = (payload.get("data") or {}).get("league_id")
                except (OSError, json.JSONDecodeError):
                    continue
            fixture_to_league[fid] = league_id
        league_id = fixture_to_league[fid]
        b = by_league[league_id]
        b["n"] += 1
        if r["status"] == "won":
            b["won"] += 1
        b["profit"] += r["profit_units"] or 0
        b["fixtures"].add(fid)
    return [
        {
            "league_id": k if k is not None else "unknown",
            "n_picks": v["n"],
            "n_fixtures": len(v["fixtures"]),
            "won": v["won"],
            "win_rate": v["won"] / v["n"] if v["n"] else 0,
            "roi_pct": v["profit"] / v["n"] * 100 if v["n"] else 0,
        }
        for k, v in sorted(by_league.items(), key=lambda kv: -kv[1]["n"])
    ]


# ── Markdown render ──────────────────────────────────────────────────────


def render_report(
    headline: dict,
    by_market: list[dict],
    by_edge: list[dict],
    by_logical: list[dict],
    gate_rejections: list[dict],
    by_league: list[dict],
    grading_stats: tuple[int, int, int],
) -> str:
    lines: list[str] = []
    today = datetime.now().strftime("%Y-%m-%d %H:%M UTC")
    lines.append(f"# Jornada analysis — {today}\n")

    # ── Headline
    lines.append("## Headline\n")
    h = headline
    lines.append(f"- **Total picks emitted**: {h['n_total']}")
    lines.append(f"- **Clean (unflagged)**: {h['n_clean']}")
    lines.append(f"- **Flagged**: {h['n_flagged']}")
    lines.append(f"- **Graded this run**: {grading_stats[0]} "
                 f"(won: {grading_stats[1]}, void: {grading_stats[2]})")
    lines.append(f"- **Total graded**: {h['n_graded']}")
    if h["roi_pct"] is not None:
        lines.append(f"- **Win rate**: {h['win_rate']:.1%}")
        lines.append(f"- **ROI**: {h['roi_pct']:+.2f}%")
        lines.append(f"- **Total P/L**: {h['total_profit_units']:+.2f} units")
    else:
        lines.append("- **ROI**: n/a (no decided picks yet)")
    lines.append("")

    # ── Per-market
    lines.append("## ROI by market\n")
    if not by_market:
        lines.append("_No graded picks yet._\n")
    else:
        lines.append("| Market | n | won | void | Win% | ROI% |")
        lines.append("|--------|---|-----|------|------|------|")
        for m in by_market:
            lines.append(
                f"| {m['market']} | {m['n']} | {m['won']} | {m['void']} | "
                f"{m['win_rate']:.1%} | {m['roi_pct']:+.2f} |"
            )
        lines.append("")

    # ── Edge bucket
    lines.append("## Calibration: edge bucket\n")
    lines.append(
        "_If model is calibrated, win rate should track edge — bucket 8-15% "
        "with avg-edge ~11% should hit ~60% of fair-line probability._\n"
    )
    if not by_edge:
        lines.append("_No graded picks yet._\n")
    else:
        lines.append("| Edge bucket | n | won | Win% | Avg edge | ROI% |")
        lines.append("|-------------|---|-----|------|----------|------|")
        for b in by_edge:
            lines.append(
                f"| {b['bucket']} | {b['n']} | {b['won']} | "
                f"{b['win_rate']:.1%} | {b['avg_edge']:.1f}% | "
                f"{b['roi_pct']:+.2f} |"
            )
        lines.append("")

    # ── Logical score bucket
    lines.append("## Logical score bucket\n")
    lines.append(
        "_Higher score = more cross-checks agreed. Hit rate should rise "
        "monotonically with score if the cascade is well-calibrated._\n"
    )
    if not by_logical:
        lines.append("_No graded picks yet._\n")
    else:
        lines.append("| Bucket | n | won | Win% | ROI% |")
        lines.append("|--------|---|-----|------|------|")
        for b in by_logical:
            lines.append(
                f"| {b['bucket']} | {b['n']} | {b['won']} | "
                f"{b['win_rate']:.1%} | {b['roi_pct']:+.2f} |"
            )
        lines.append("")

    # ── Gate rejections
    lines.append("## Gate effectiveness (drops)\n")
    if not gate_rejections:
        lines.append("_No drops logged._\n")
    else:
        lines.append("| Gate | Drops |")
        lines.append("|------|-------|")
        for g in gate_rejections:
            lines.append(f"| `{g['drop_reason']}` | {g['n']} |")
        lines.append("")

    # ── Per-league
    lines.append("## Per-league breakdown\n")
    if not by_league:
        lines.append("_No graded picks yet._\n")
    else:
        lines.append("| League ID | Fixtures | Picks | Won | Win% | ROI% |")
        lines.append("|-----------|----------|-------|-----|------|------|")
        for L in by_league[:20]:
            lines.append(
                f"| {L['league_id']} | {L['n_fixtures']} | {L['n_picks']} | "
                f"{L['won']} | {L['win_rate']:.1%} | {L['roi_pct']:+.2f} |"
            )
        lines.append("")

    return "\n".join(lines)


# ── Parquet exports ──────────────────────────────────────────────────────


def export_parquet(
    db_path: Path, cache_root: Path, out_dir: Path,
) -> dict[str, Path]:
    """Export picks/decisions/derived to Parquet via Polars when available."""
    out_dir.mkdir(parents=True, exist_ok=True)
    paths: dict[str, Path] = {}
    try:
        import polars as pl
    except ImportError:
        return paths

    # picks_graded.parquet — fetch via sqlite to avoid Polars schema-
    # inference issues with mixed nullable types.
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        for table, fname in (
            ("picks", "picks_graded.parquet"),
            ("pick_decisions", "decisions.parquet"),
        ):
            try:
                rows = [dict(r) for r in conn.execute(f"SELECT * FROM {table}")]
                if not rows:
                    continue
                df = pl.from_dicts(rows, infer_schema_length=None)
                p = out_dir / fname
                df.write_parquet(p)
                paths[fname.removesuffix(".parquet")] = p
            except Exception as exc:  # noqa: BLE001
                print(f"[exports] {table} parquet write failed: {exc}")

    # snapshots_derived.parquet — flatten all derived blocks across snapshots
    cache = SportmonksCache(root=cache_root)
    derived_rows: list[dict] = []
    for fid in cache.list_fixtures():
        for snap_path in cache.list_snapshots(fid):
            try:
                payload = json.loads(snap_path.read_text())
            except (OSError, json.JSONDecodeError):
                continue
            der = payload.get("derived")
            if not der:
                continue
            derived_rows.append({
                "fixture_id": fid,
                "snapshot_taken_at": payload.get("snapshot_taken_at"),
                **{k: v for k, v in der.items()},
            })
    if derived_rows:
        df = pl.DataFrame(derived_rows)
        p = out_dir / "snapshots_derived.parquet"
        df.write_parquet(p)
        paths["snapshots_derived"] = p
    return paths


# ── CLI ──────────────────────────────────────────────────────────────────


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--cache-root", type=Path, default=DEFAULT_CACHE_ROOT)
    p.add_argument("--picks-db", type=Path, default=DEFAULT_DB_PATH)
    p.add_argument("--output-dir", type=Path,
                   default=Path("reports/sportmonks_live"))
    p.add_argument("--skip-grading", action="store_true",
                   help="Don't update pick statuses, only re-render report")
    return p.parse_args()


def main() -> int:
    args = _parse_args()
    cache = SportmonksCache(root=args.cache_root)
    tracker = PickTracker(db_path=args.picks_db)

    # Phase 1 — grade pending picks
    if args.skip_grading:
        grading_stats = (0, 0, 0)
        print("[skip_grading] Pick grading skipped — using existing statuses")
    else:
        print("[grade] Walking snapshots, deriving outcomes, grading picks...")
        grading_stats = grade_pending_picks(tracker, cache)
        print(
            f"[grade] {grading_stats[0]} graded "
            f"({grading_stats[1]} won, {grading_stats[2]} void)"
        )

    # Phase 2 — compute analyses
    headline = headline_metrics(tracker)
    rows = headline.pop("rows")
    bm = by_market_breakdown(rows)
    be = by_edge_bucket(rows)
    bl = by_logical_score_bucket(rows)
    gates = gate_rejection_summary(tracker)
    bleague = per_league_breakdown(rows, cache)

    # Phase 3 — render markdown
    report = render_report(
        headline=headline, by_market=bm, by_edge=be,
        by_logical=bl, gate_rejections=gates, by_league=bleague,
        grading_stats=grading_stats,
    )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    today = datetime.now().strftime("%Y-%m-%d")
    md_path = args.output_dir / f"jornada_analysis_{today}.md"
    md_path.write_text(report)
    print(f"\n[report] {md_path}")

    # Phase 4 — Parquet exports
    exports_dir = args.output_dir / "exports"
    paths = export_parquet(args.picks_db, args.cache_root, exports_dir)
    if paths:
        print("[exports] Parquet files:")
        for name, p in paths.items():
            print(f"  - {name}: {p}")
    else:
        print("[exports] Polars not available — skipped Parquet exports")

    print("\n" + "=" * 60)
    print(report.split("##")[0])  # just the headline
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
