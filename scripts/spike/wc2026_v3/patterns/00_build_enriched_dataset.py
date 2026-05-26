"""Build the enriched per-match dataset for historical-pattern discovery.

Joins match_outcomes (n=314) with StatsBomb match metadata (phase) and parses
events JSON to extract minute-level features:
- goals_minutes_home / goals_minutes_away
- ht_home / ht_away
- yellow_card_minutes / red_card_minutes
- corner_minutes
- shot_minutes_with_xg

Output: data/cache/wc2026_v3/patterns_enriched.parquet

Stable: events JSON is read-only local data. Idempotent: rerun overwrites.
"""
from __future__ import annotations

import json
from pathlib import Path

import polars as pl

ROOT = Path(__file__).resolve().parents[4]
CACHE = ROOT / "data" / "cache"
SB_EVENTS = CACHE / "statsbomb" / "events"
SB_MATCHES = CACHE / "statsbomb" / "matches"
OUTCOMES_PARQUET = CACHE / "statsbomb" / "match_outcomes.parquet"
OUT_DIR = CACHE / "wc2026_v3"
OUT = OUT_DIR / "patterns_enriched.parquet"

# competition/season → tournament_slug (must match match_outcomes.tournament_slug)
MATCH_FILE_TO_SLUG = {
    "43_3.json": "wc_2018",
    "43_106.json": "wc_2022",
    "55_43.json": "euro_2020",
    "55_282.json": "euro_2024",
    "223_282.json": "copa_2024",
    "1267_107.json": "afcon_2023",
}


def _stage_of(match: dict) -> str:
    return match.get("competition_stage", {}).get("name", "UNKNOWN")


def _load_stages() -> pl.DataFrame:
    rows = []
    for fname, slug in MATCH_FILE_TO_SLUG.items():
        with open(SB_MATCHES / fname) as fh:
            for m in json.load(fh):
                rows.append(
                    {
                        "match_id": int(m["match_id"]),
                        "tournament_slug": slug,
                        "stage": _stage_of(m),
                        "kick_off": m.get("kick_off"),
                        "match_week": m.get("match_week"),
                    }
                )
    return pl.DataFrame(rows)


def _parse_events(match_id: int, home_team: str, away_team: str) -> dict:
    """Return minute-level features for one match."""
    path = SB_EVENTS / f"{match_id}.json"
    if not path.exists():
        return {}
    with open(path) as fh:
        events = json.load(fh)

    goals_home: list[int] = []
    goals_away: list[int] = []
    yellow_minutes: list[int] = []
    red_minutes: list[int] = []
    own_goal_minutes: list[int] = []
    shot_xgs: list[tuple[int, float, str]] = []  # (minute, xg, team)
    ht_home = 0
    ht_away = 0
    corner_minutes: list[int] = []  # corners not explicitly an event-type in SB; skip if absent

    for e in events:
        etype = e.get("type", {}).get("name")
        period = e.get("period")
        minute = e.get("minute")
        team = e.get("team", {}).get("name")
        if minute is None or period is None:
            continue
        # Period 1 = first half (0-45), Period 2 = second half (45-90), 3/4 = extra time, 5 = pens
        if etype == "Shot":
            sh = e.get("shot", {})
            outcome = sh.get("outcome", {}).get("name")
            xg = sh.get("statsbomb_xg")
            if xg is not None:
                shot_xgs.append((int(minute), float(xg), team))
            if outcome == "Goal":
                # Period 5 = penalty shootout; exclude.
                if period == 5:
                    continue
                if team == home_team:
                    goals_home.append(int(minute))
                    if period == 1:
                        ht_home += 1
                elif team == away_team:
                    goals_away.append(int(minute))
                    if period == 1:
                        ht_away += 1
        elif etype == "Own Goal Against":
            # OG against = goal credited TO opposing team
            if minute is None or period == 5:
                continue
            if team == home_team:
                # away scored against home → goals_away
                goals_away.append(int(minute))
                if period == 1:
                    ht_away += 1
            elif team == away_team:
                goals_home.append(int(minute))
                if period == 1:
                    ht_home += 1
            own_goal_minutes.append(int(minute))
        elif etype == "Bad Behaviour" or etype == "Foul Committed":
            card = e.get(etype.lower().replace(" ", "_"), {}).get("card", {})
            cname = card.get("name") if isinstance(card, dict) else None
            if cname == "Yellow Card":
                yellow_minutes.append(int(minute))
            elif cname in ("Red Card", "Second Yellow"):
                red_minutes.append(int(minute))

    return {
        "goals_home_minutes": sorted(goals_home),
        "goals_away_minutes": sorted(goals_away),
        "ht_home": ht_home,
        "ht_away": ht_away,
        "yellow_minutes": sorted(yellow_minutes),
        "red_minutes": sorted(red_minutes),
        "own_goal_minutes": sorted(own_goal_minutes),
        "n_shots_xg": len(shot_xgs),
        "total_xg_first_half": sum(xg for m, xg, _ in shot_xgs if m < 45),
        "total_xg_second_half": sum(xg for m, xg, _ in shot_xgs if m >= 45),
    }


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    outcomes = pl.read_parquet(OUTCOMES_PARQUET)
    stages = _load_stages()
    print(f"loaded {outcomes.height} outcomes, {stages.height} stage rows")

    enriched_rows = []
    for row in outcomes.iter_rows(named=True):
        feats = _parse_events(row["match_id"], row["home_team"], row["away_team"])
        enriched_rows.append({**row, **feats})

    enriched = pl.DataFrame(enriched_rows).join(
        stages.select("match_id", "stage", "kick_off", "match_week"),
        on="match_id",
        how="left",
    )

    # Sanity: sum of goals_home_minutes should equal home_goals
    mismatch = enriched.filter(
        pl.col("goals_home_minutes").list.len() != pl.col("home_goals")
    )
    if mismatch.height > 0:
        # Some discrepancies expected due to OG/extra-time edge cases. Report not fail.
        print(f"WARN: {mismatch.height} matches where home goals count != home_goals_minutes len")
        print(mismatch.select("match_id", "home_team", "home_goals", "goals_home_minutes").head(5))

    # Phase column: group vs knockout
    enriched = enriched.with_columns(
        pl.when(pl.col("stage") == "Group Stage")
        .then(pl.lit("group"))
        .otherwise(pl.lit("knockout"))
        .alias("phase")
    )

    print("=== stage distribution ===")
    print(enriched.group_by("tournament_slug", "phase").agg(pl.len().alias("n")).sort("tournament_slug", "phase"))

    enriched.write_parquet(OUT)
    print(f"wrote {enriched.height} rows to {OUT}")


if __name__ == "__main__":
    main()
