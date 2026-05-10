"""Post-jornada inspector — summary of what was captured.

Usage::

    uv run python -m scripts.spike.sportmonks.inspect_capture

Reports:
- Per-fixture: # snapshots, first/last minute captured, FT-pickup present?
- Pre-match odds presence per fixture
- Picks DB stats (emits/flags/drops by reason)
- Team-form cache utilisation
- Top "data-rich" fixtures (most snapshots, full include coverage)

Read-only — never modifies cache.
"""

from __future__ import annotations

import json
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from bip.evaluation.live.pick_tracker import DEFAULT_DB_PATH, PickTracker  # noqa: E402
from bip.evaluation.live.team_form import DEFAULT_FORM_DB_PATH  # noqa: E402
from bip.sports.football.sportmonks.cache import (  # noqa: E402
    DEFAULT_CACHE_ROOT,
    SportmonksCache,
)


def inspect_snapshots(cache_root: Path) -> dict:
    """Walk the snapshot tree and summarise per fixture."""
    cache = SportmonksCache(root=cache_root)
    fixtures = cache.list_fixtures()
    summary: dict[int, dict] = {}
    totals = {"n_snapshots": 0, "n_with_odds": 0, "n_with_raw": 0,
              "n_with_prematch": 0, "n_final_pickup": 0}
    for fid in fixtures:
        paths = cache.list_snapshots(fid)
        per_fix = {
            "n_snapshots": len(paths),
            "minutes": [],
            "kinds": defaultdict(int),
            "has_odds": 0,
            "has_raw": 0,
            "has_prematch": False,
            "has_final_pickup": False,
            "final_state": None,
            "final_score": None,
        }
        for p in paths:
            try:
                payload = json.loads(p.read_text())
            except (OSError, json.JSONDecodeError):
                continue
            kind = payload.get("snapshot_kind", "scan")
            per_fix["kinds"][kind] += 1
            if kind == "prematch_odds":
                per_fix["has_prematch"] = True
                totals["n_with_prematch"] += 1
            elif kind in ("final_pickup", "final_pickup_on_exit"):
                per_fix["has_final_pickup"] = True
                totals["n_final_pickup"] += 1
            if payload.get("odds_snapshot"):
                per_fix["has_odds"] += 1
                totals["n_with_odds"] += 1
            if payload.get("raw"):
                per_fix["has_raw"] += 1
                totals["n_with_raw"] += 1
            data = payload.get("data") or payload.get("raw") or {}
            periods = data.get("periods") or []
            for prd in periods:
                m = prd.get("minutes")
                if isinstance(m, int):
                    per_fix["minutes"].append(m)
            state = (data.get("state") or {}).get("developer_name")
            if state:
                per_fix["final_state"] = state
            scores = data.get("scores") or []
            for s in scores:
                body = s.get("score") or {}
                if body.get("description") in ("CURRENT", "FT"):
                    per_fix["final_score"] = body.get("goals")
        per_fix["min_minute"] = min(per_fix["minutes"], default=0)
        per_fix["max_minute"] = max(per_fix["minutes"], default=0)
        per_fix["kinds"] = dict(per_fix["kinds"])
        summary[fid] = per_fix
        totals["n_snapshots"] += per_fix["n_snapshots"]
    return {"per_fixture": summary, "totals": totals,
            "n_fixtures": len(fixtures)}


def inspect_picks(db_path: Path) -> dict:
    if not db_path.exists():
        return {"error": f"picks db not found at {db_path}"}
    tracker = PickTracker(db_path=db_path)
    stats = tracker.stats_summary()
    rejection = tracker.gate_rejection_rates(hours=72)
    return {"stats": stats, "gate_rejection_rates_72h": rejection}


def inspect_team_form(db_path: Path) -> dict:
    if not db_path.exists():
        return {"error": f"team_form db not found at {db_path}"}
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT team_id, season_id, n_matches, "
            "first_half_goal_rate, late_goals_rate, last_updated "
            "FROM team_form ORDER BY last_updated DESC LIMIT 20",
        ).fetchall()
    return {
        "n_cached_teams": len(rows),
        "recent": [dict(r) for r in rows],
    }


def render_report(snap: dict, picks: dict, form: dict) -> str:
    lines: list[str] = []
    lines.append("# Capture inspection report\n")
    t = snap["totals"]
    lines.append(f"## Snapshots ({snap['n_fixtures']} fixtures)\n")
    lines.append(f"- Total snapshots: **{t['n_snapshots']}**")
    lines.append(f"- With in-play odds: {t['n_with_odds']}")
    lines.append(f"- With raw payload: {t['n_with_raw']}")
    lines.append(f"- With prematch odds: {t['n_with_prematch']}")
    lines.append(f"- Final-pickup snapshots: {t['n_final_pickup']}\n")

    finished = sum(
        1 for fix in snap["per_fixture"].values()
        if fix["final_state"] in ("FT", "AET", "FT_PEN", "FINISHED")
    )
    lines.append(f"- Fixtures with FT state captured: **{finished}** "
                 f"({finished / max(snap['n_fixtures'], 1):.0%})\n")

    lines.append("## Top 10 most-captured fixtures\n")
    top = sorted(
        snap["per_fixture"].items(),
        key=lambda kv: kv[1]["n_snapshots"], reverse=True,
    )[:10]
    lines.append("| Fixture | Snapshots | Min..Max | Final | Odds | Prematch | Final-pickup |")
    lines.append("|---------|-----------|----------|-------|------|----------|--------------|")
    for fid, info in top:
        lines.append(
            f"| {fid} | {info['n_snapshots']} | "
            f"{info['min_minute']}..{info['max_minute']} | "
            f"{info['final_state'] or '—'} | "
            f"{info['has_odds']} | "
            f"{'✓' if info['has_prematch'] else '—'} | "
            f"{'✓' if info['has_final_pickup'] else '—'} |"
        )
    lines.append("")

    lines.append("## Picks DB\n")
    if "error" in picks:
        lines.append(f"_{picks['error']}_\n")
    else:
        s = picks["stats"]
        lines.append(f"- Total picks: {s.get('n_total', 0)}")
        lines.append(f"- Graded: {s.get('n_graded', 0)}, won: {s.get('n_won', 0)}")
        roi = s.get("roi_pct")
        lines.append(f"- ROI: {roi:+.2f}%" if roi is not None else "- ROI: n/a")
        lines.append(f"- Placed on Betano: {s.get('n_placed_betano', 0)}\n")
        lines.append("### Gate-rejection rates (last 72h)\n")
        if not picks["gate_rejection_rates_72h"]:
            lines.append("_No drops recorded_")
        else:
            for r in picks["gate_rejection_rates_72h"]:
                lines.append(f"- `{r['drop_reason']}`: {r['n']}")
        lines.append("")

    lines.append("## Team form cache\n")
    if "error" in form:
        lines.append(f"_{form['error']}_\n")
    else:
        lines.append(f"- Cached teams: {form['n_cached_teams']}")
        if form["recent"]:
            lines.append("\n### Recent updates\n")
            lines.append("| Team | Season | Matches | 1H rate | Late rate | Updated |")
            lines.append("|------|--------|---------|---------|-----------|---------|")
            for r in form["recent"][:10]:
                lines.append(
                    f"| {r['team_id']} | {r['season_id']} | {r['n_matches']} | "
                    f"{r['first_half_goal_rate']:.2f} | "
                    f"{r['late_goals_rate']:.2f} | {r['last_updated'][:19]} |"
                )
    return "\n".join(lines)


def main() -> int:
    snap = inspect_snapshots(DEFAULT_CACHE_ROOT)
    picks = inspect_picks(DEFAULT_DB_PATH)
    form = inspect_team_form(DEFAULT_FORM_DB_PATH)
    report = render_report(snap, picks, form)
    print(report)
    out_path = Path("reports/sportmonks_live/capture_inspection.md")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(report)
    print(f"\nSaved to {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
