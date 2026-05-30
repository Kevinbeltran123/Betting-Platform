"""Post-process raw FBref scrapes to produce qualitative summaries.

Reads data/cache/tsp/profiles_fbref/{team}_fbref.json (raw tables) and
generates {team}_fbref_summary.json with:
  - top scorers (last season)
  - top minute holders (the indisputable starters)
  - GK saves leader
  - YC/RC leaders (suspension risk)
  - n_players with stats
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
FBREF_DIR = ROOT / "data" / "cache" / "tsp" / "profiles_fbref"


def safe_int(x):
    try:
        return int(str(x).replace(",", "").strip())
    except (ValueError, TypeError):
        return None


def safe_float(x):
    try:
        return float(str(x).replace(",", "").strip())
    except (ValueError, TypeError):
        return None


def clean_rows(rows: list[dict]) -> list[dict]:
    """Drop the duplicate-header row that FBref tables emit as row[0]."""
    if not rows:
        return rows
    first = rows[0]
    # If 'Player' == 'Player' or 'Position' == 'Pos', it's the abbreviation header row
    if first.get("Player") in {"Player", None} or first.get("Position") == "Pos":
        return rows[1:]
    return rows


def summarize_team(data: dict) -> dict:
    """Generate qualitative summary from parsed tables."""
    summary = {
        "team_name": data.get("team_name"),
        "fbref_url": data.get("url"),
        "fbref_country_code": data.get("fbref_country_code"),
        "scraped_at": data.get("scraped_at"),
    }
    tables = data.get("tables", {})

    # Standard stats: top scorers, top minute holders
    std = None
    for tid, t in tables.items():
        if "standard" in tid:
            std = t
            break

    if std:
        rows = clean_rows(std.get("rows", []))
        # Filter to players with at least 1 match
        players = []
        for r in rows:
            mp = safe_int(r.get("Matches Played"))
            if mp is None or mp == 0:
                continue
            players.append({
                "name": r.get("Player"),
                "position": r.get("Position"),
                "age": r.get("Age"),
                "matches": mp,
                "minutes": safe_int(r.get("Minutes")),
                "goals": safe_int(r.get("Goals")),
                "assists": safe_int(r.get("Assists")),
                "yellow_cards": safe_int(r.get("Yellow Cards")),
                "red_cards": safe_int(r.get("Red Cards")),
            })

        # Top scorers
        scorers = [p for p in players if (p["goals"] or 0) > 0]
        scorers.sort(key=lambda p: (p["goals"] or 0), reverse=True)
        summary["top_scorers"] = scorers[:5]

        # Top minute holders = indisputable starters
        minutes_ranked = [p for p in players if (p["minutes"] or 0) > 0]
        minutes_ranked.sort(key=lambda p: (p["minutes"] or 0), reverse=True)
        summary["top_minute_holders"] = minutes_ranked[:11]

        # YC leaders (suspension risk)
        yc_ranked = [p for p in players if (p["yellow_cards"] or 0) > 0]
        yc_ranked.sort(key=lambda p: (p["yellow_cards"] or 0), reverse=True)
        summary["yc_leaders"] = yc_ranked[:5]

        # Aggregate
        total_goals = sum((p["goals"] or 0) for p in players)
        total_assists = sum((p["assists"] or 0) for p in players)
        total_yc = sum((p["yellow_cards"] or 0) for p in players)
        summary["aggregate_recent"] = {
            "n_players_active": len(players),
            "total_goals": total_goals,
            "total_assists": total_assists,
            "total_yellow_cards": total_yc,
        }

    # GK stats
    gk = None
    for tid, t in tables.items():
        if "keeper" in tid:
            gk = t
            break
    if gk:
        rows = clean_rows(gk.get("rows", []))
        gks = []
        for r in rows:
            saves = safe_int(r.get("Saves"))
            if saves is None:
                continue
            gks.append({
                "name": r.get("Player"),
                "matches": safe_int(r.get("Matches Played")),
                "minutes": safe_int(r.get("Minutes")),
                "goals_against": safe_int(r.get("Goals Against")),
                "ga_per_90": r.get("Goals Against/90"),
                "saves": saves,
                "save_pct": r.get("Save Percentage"),
                "wins": safe_int(r.get("Wins")),
                "draws": safe_int(r.get("Draws")),
                "losses": safe_int(r.get("Losses")),
            })
        gks.sort(key=lambda g: (g["minutes"] or 0), reverse=True)
        summary["goalkeepers"] = gks[:3]

    # Misc stats: crosses, interceptions, tackles, pens won/conceded
    misc = None
    for tid, t in tables.items():
        if "misc" in tid:
            misc = t
            break
    if misc:
        rows = clean_rows(misc.get("rows", []))
        crossers = []
        interceptors = []
        tacklers = []
        pen_concededers = []
        for r in rows:
            name = r.get("Player")
            if not name or name == "Player":
                continue
            crosses = safe_int(r.get("Crosses"))
            interceptions = safe_int(r.get("Interceptions"))
            tackles_won = safe_int(r.get("Tackles Won"))
            pens_conceded = safe_int(r.get("Penalty Kicks Conceded"))
            if crosses:
                crossers.append({"name": name, "crosses": crosses})
            if interceptions:
                interceptors.append({"name": name, "interceptions": interceptions})
            if tackles_won:
                tacklers.append({"name": name, "tackles_won": tackles_won})
            if pens_conceded:
                pen_concededers.append({"name": name, "pens_conceded": pens_conceded})

        crossers.sort(key=lambda x: x["crosses"], reverse=True)
        interceptors.sort(key=lambda x: x["interceptions"], reverse=True)
        tacklers.sort(key=lambda x: x["tackles_won"], reverse=True)

        summary["misc_leaders"] = {
            "top_crossers": crossers[:3],
            "top_interceptors": interceptors[:3],
            "top_tacklers": tacklers[:3],
            "penalty_concededers": pen_concededers[:3],
        }

    return summary


def main() -> int:
    files = sorted(FBREF_DIR.glob("*_fbref.json"))
    files = [f for f in files if not f.name.startswith("_")]
    print(f"=== Summarizing {len(files)} FBref scrapes ===\n")

    for f in files:
        data = json.loads(f.read_text())
        summary = summarize_team(data)
        out_path = FBREF_DIR / f.name.replace("_fbref.json", "_fbref_summary.json")
        out_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False))

        team = summary["team_name"]
        agg = summary.get("aggregate_recent") or {}
        top_scorer = (summary.get("top_scorers") or [{}])[0]
        gk = (summary.get("goalkeepers") or [{}])[0]
        print(f"  ✓ {team:25}: top scorer={top_scorer.get('name', '-')} ({top_scorer.get('goals', 0)}g) "
              f"GK={gk.get('name', '-')} ({gk.get('saves', 0)} saves)")

    print(f"\n=== Done. Summaries in {FBREF_DIR} ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
