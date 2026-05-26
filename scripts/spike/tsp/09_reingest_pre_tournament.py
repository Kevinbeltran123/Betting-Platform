"""Re-ingest TSV profiles per (tournament, team) with pre-tournament cutoff.

For each backtest tournament (AFCON23, Copa24, Euro24):
  - cutoff = tournament_start - 1 day
  - For each participant team (from participants.json):
      - If team in coach_history: profile fixtures in [filter_date, cutoff]
        with current DT.
      - Save to data/cache/tsp/profiles_backtest/{tournament}/{team}_tsv.json
      - Teams with <5 matches in window → red flag → will use cohort at backtest time
  - Teams NOT in coach_history are skipped (not perfilable).
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path

import httpx
from dotenv import load_dotenv

from bip.evaluation.tournaments.team_style_profiler.api_football_parsers import (
    EventsResponse,
    FixturesResponse,
    StatsResponse,
)
from bip.evaluation.tournaments.team_style_profiler.coach_history import (
    CURRENT_COACHES,
    get_current_coach,
    get_effective_filter_date,
)
from bip.evaluation.tournaments.team_style_profiler.tsv_calculator import (
    compute_tsv,
    extract_match_features,
)
from bip.evaluation.tournaments.team_style_profiler.tsv_schema import CoachInfo


ROOT = Path(__file__).resolve().parents[3]
TEAM_IDS_PATH = ROOT / "data" / "cache" / "tsp" / "team_ids.json"
TOURNAMENTS_DIR = ROOT / "data" / "cache" / "tsp" / "tournaments"
PROFILES_BT_DIR = ROOT / "data" / "cache" / "tsp" / "profiles_backtest"

TOURNAMENTS = ["AFCON_2023", "Copa_2024", "Euro_2024"]


def _safe_name(name: str) -> str:
    return name.replace(" ", "_").replace("'", "").replace("Ô", "o").replace("ô", "o").lower()


async def reingest_team_for_tournament(
    client: httpx.AsyncClient,
    team_name: str,
    team_id: int,
    coach_info: CoachInfo,
    confederation: str,
    filter_date: date,
    cutoff_date: date,
    conf_lookup,
    out_dir: Path,
) -> tuple[int, str]:
    """Returns (n_matches, flag)."""
    seasons = list(range(filter_date.year, cutoff_date.year + 1))
    all_fixtures = []
    for season in seasons:
        r = await client.get("/fixtures", params={"team": team_id, "season": season})
        r.raise_for_status()
        all_fixtures.extend(FixturesResponse.model_validate(r.json()).response)
    finished = [
        f for f in all_fixtures
        if f.is_finished
        and filter_date <= f.fixture.date.date() <= cutoff_date
    ]

    match_features = []
    for fix in finished:
        fid = fix.fixture_id
        r_stats = await client.get("/fixtures/statistics", params={"fixture": fid})
        r_stats.raise_for_status()
        stats_resp = StatsResponse.model_validate(r_stats.json())
        team_stats = stats_resp.for_team(team_id)
        opp_id = (
            fix.teams.away.id if team_id == fix.teams.home.id
            else fix.teams.home.id
        )
        opp_stats = stats_resp.for_team(opp_id)

        r_events = await client.get("/fixtures/events", params={"fixture": fid})
        r_events.raise_for_status()
        events_resp = EventsResponse.model_validate(r_events.json())

        mf = extract_match_features(
            fixture=fix, team_id=team_id,
            team_stats=team_stats, opponent_stats=opp_stats,
            events=events_resp.response,
            opponent_confederation_lookup=conf_lookup,
        )
        match_features.append(mf)

    tsv = compute_tsv(
        team_name=team_name,
        api_football_team_id=team_id,
        confederation=confederation,
        coach=coach_info,
        matches=match_features,
        last_updated=datetime.now(),
    )
    out_path = out_dir / f"{_safe_name(team_name)}_tsv.json"
    out_path.write_text(tsv.model_dump_json(indent=2))
    return (tsv.n_matches, tsv.flag)


async def main() -> int:
    load_dotenv()
    api_key = os.environ.get("API_FOOTBALL_KEY", "")
    if not api_key:
        return 1
    team_ids: dict = json.loads(TEAM_IDS_PATH.read_text())
    team_ids_by_id = {rec["id"]: name for name, rec in team_ids.items() if rec.get("id")}
    coach_map_conf = {n: r.confederation for n, r in CURRENT_COACHES.items()}

    def conf_lookup(tid: int) -> str:
        n = team_ids_by_id.get(tid)
        return coach_map_conf.get(n, "UNK") if n else "UNK"

    PROFILES_BT_DIR.mkdir(parents=True, exist_ok=True)
    summary = {}

    async with httpx.AsyncClient(
        base_url="https://v3.football.api-sports.io",
        headers={"x-apisports-key": api_key},
        timeout=httpx.Timeout(120.0),
    ) as client:
        for tournament_key in TOURNAMENTS:
            participants_path = TOURNAMENTS_DIR / f"{tournament_key}_participants.json"
            data = json.loads(participants_path.read_text())
            tournament_start = date.fromisoformat(data["tournament_start"])
            cutoff = tournament_start - timedelta(days=1)
            print(f"\n=== {tournament_key} (cutoff = {cutoff}) ===")

            tournament_out = PROFILES_BT_DIR / tournament_key
            tournament_out.mkdir(parents=True, exist_ok=True)

            t0 = time.time()
            per_team_summary = []
            for team_id in data["participant_team_ids"]:
                team_name = team_ids_by_id.get(team_id)
                if team_name is None:
                    # Team not in our coach_history → skip (will be UNK at backtest)
                    per_team_summary.append({
                        "team_id": team_id, "team_name": None,
                        "n_matches": 0, "flag": "UNAVAILABLE",
                    })
                    continue
                coach_rec = get_current_coach(team_name)
                if coach_rec is None:
                    per_team_summary.append({
                        "team_id": team_id, "team_name": team_name,
                        "n_matches": 0, "flag": "NO_COACH",
                    })
                    continue
                # Effective filter: max(coach_start, era_start=2023-01-01)
                fdate = get_effective_filter_date(team_name) or date(2023, 1, 1)
                if fdate >= cutoff:
                    # Coach started after tournament → no data possible
                    print(f"  {team_name:22} → DT post-tournament, skipping")
                    per_team_summary.append({
                        "team_id": team_id, "team_name": team_name,
                        "n_matches": 0, "flag": "DT_POST_TOURNAMENT",
                    })
                    continue
                try:
                    n, flag = await reingest_team_for_tournament(
                        client=client,
                        team_name=team_name,
                        team_id=team_id,
                        coach_info=CoachInfo(
                            coach_name=coach_rec.coach_name,
                            start_date=coach_rec.coach_start_date,
                        ),
                        confederation=coach_rec.confederation,
                        filter_date=fdate,
                        cutoff_date=cutoff,
                        conf_lookup=conf_lookup,
                        out_dir=tournament_out,
                    )
                    glyph = {"green": "✓", "yellow": "⚠", "red": "✗"}.get(flag, "?")
                    print(f"  {team_name:22} → n={n:3} {glyph} {flag}")
                    per_team_summary.append({
                        "team_id": team_id, "team_name": team_name,
                        "n_matches": n, "flag": flag,
                    })
                except Exception as exc:  # noqa: BLE001
                    print(f"  {team_name:22} → FAIL ({type(exc).__name__}: {exc})")
                    per_team_summary.append({
                        "team_id": team_id, "team_name": team_name,
                        "n_matches": 0, "flag": "FAIL",
                    })

            elapsed = time.time() - t0
            print(f"  Total: {elapsed:.1f}s")
            summary[tournament_key] = {
                "tournament_start": tournament_start.isoformat(),
                "cutoff": cutoff.isoformat(),
                "elapsed_s": round(elapsed, 1),
                "teams": per_team_summary,
            }

    # Save summary
    (PROFILES_BT_DIR / "summary.json").write_text(json.dumps(summary, indent=2))
    print("\n=== Re-ingest summary ===")
    for t, info in summary.items():
        flag_counts: dict[str, int] = {}
        for tt in info["teams"]:
            flag_counts[tt["flag"]] = flag_counts.get(tt["flag"], 0) + 1
        print(f"  {t}: {flag_counts}")

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
