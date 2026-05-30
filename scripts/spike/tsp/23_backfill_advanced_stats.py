"""Backfill advanced team stats (xG-less Tier A) for all WC2026 profiled teams.

Iterates fixtures of every team with a green/yellow TSV. For each fixture,
pulls /fixtures/players and aggregates player stats to team-level via
extract_advanced_team_stats. Saves per-team aggregated profile.

Cost (rough): ~1500 calls (46 teams × ~30 fixtures avg).
Caches raw /fixtures/players in data/cache/tsp/raw_fixture_players/{fid}.json
so re-runs don't re-hit the API.

Output: data/cache/tsp/profiles_advanced/{team}_advanced.json
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from datetime import date, datetime
from pathlib import Path

import httpx
from dotenv import load_dotenv

from bip.evaluation.tournaments.team_style_profiler.advanced_stats import (
    AdvancedMatchStats,
    aggregate_advanced_profile,
    extract_advanced_team_stats,
)
from bip.evaluation.tournaments.team_style_profiler.api_football_parsers import (
    FixturesResponse,
)
from bip.evaluation.tournaments.team_style_profiler.coach_history import (
    CURRENT_COACHES,
    get_current_coach,
    get_effective_filter_date,
)


ROOT = Path(__file__).resolve().parents[4]
TEAM_IDS_PATH = ROOT / "data" / "cache" / "tsp" / "team_ids.json"
PROFILES_DIR = ROOT / "data" / "cache" / "tsp" / "profiles"
OUT_DIR = ROOT / "data" / "cache" / "tsp" / "profiles_advanced"
RAW_CACHE_DIR = ROOT / "data" / "cache" / "tsp" / "raw_fixture_players"


WC2026_TEAMS = [
    "Algeria", "Argentina", "Australia", "Austria", "Belgium",
    "Bosnia and Herzegovina", "Brazil", "Canada", "Cape Verde",
    "Colombia", "Croatia", "Curaçao", "Czech Republic", "DR Congo",
    "Ecuador", "Egypt", "England", "France", "Germany", "Ghana", "Haiti",
    "Iran", "Iraq", "Ivory Coast", "Japan", "Jordan", "Mexico", "Morocco",
    "Netherlands", "New Zealand", "Norway", "Panama", "Paraguay",
    "Portugal", "Qatar", "Saudi Arabia", "Scotland", "Senegal",
    "South Africa", "South Korea", "Spain", "Sweden", "Switzerland",
    "Tunisia", "Turkey", "USA", "Uruguay", "Uzbekistan",
]


async def get_fixture_players_cached(
    client: httpx.AsyncClient, fixture_id: int
) -> list[dict]:
    """Pull /fixtures/players for one fixture, caching the raw response."""
    cache_path = RAW_CACHE_DIR / f"{fixture_id}.json"
    if cache_path.exists():
        try:
            payload = json.loads(cache_path.read_text())
            return payload.get("response", [])
        except (json.JSONDecodeError, KeyError):
            pass  # fall through to re-fetch
    r = await client.get("/fixtures/players", params={"fixture": fixture_id})
    r.raise_for_status()
    payload = r.json()
    cache_path.write_text(json.dumps(payload, ensure_ascii=False))
    return payload.get("response", [])


async def backfill_one_team(
    client: httpx.AsyncClient,
    team_name: str,
    team_id: int,
    confederation: str,
    filter_date: date,
    today: date,
) -> tuple[str, int, float]:
    t0 = time.time()

    # Pull fixtures across seasons since filter_date
    seasons = list(range(filter_date.year, today.year + 1))
    all_fixtures = []
    for season in seasons:
        r = await client.get(
            "/fixtures", params={"team": team_id, "season": season}
        )
        r.raise_for_status()
        all_fixtures.extend(FixturesResponse.model_validate(r.json()).response)

    finished = [
        f for f in all_fixtures
        if f.is_finished and f.fixture.date.date() >= filter_date
    ]

    # Aggregate per-fixture
    matches_advanced: list[AdvancedMatchStats] = []
    for fix in finished:
        fid = fix.fixture_id
        try:
            players_resp = await get_fixture_players_cached(client, fid)
        except Exception as exc:
            print(f"    {team_name} fixture {fid}: skip ({type(exc).__name__})")
            continue
        if not players_resp:
            continue
        adv = extract_advanced_team_stats(players_resp, team_id, fid)
        matches_advanced.append(adv)

    if not matches_advanced:
        elapsed = time.time() - t0
        return (team_name, 0, elapsed)

    profile = aggregate_advanced_profile(
        team_name=team_name,
        api_football_team_id=team_id,
        confederation=confederation,
        matches=matches_advanced,
        last_updated=datetime.now(),
    )

    out_path = OUT_DIR / f"{team_name.replace(' ', '_').replace(chr(39), '').lower()}_advanced.json"
    out_path.write_text(profile.model_dump_json(indent=2))

    elapsed = time.time() - t0
    return (team_name, profile.n_matches, elapsed)


async def main() -> int:
    load_dotenv()
    api_key = os.environ.get("API_FOOTBALL_KEY", "")
    if not api_key:
        print("ERROR: no API_FOOTBALL_KEY")
        return 1

    team_ids = json.loads(TEAM_IDS_PATH.read_text())
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    RAW_CACHE_DIR.mkdir(parents=True, exist_ok=True)

    today = date.today()
    succeeded: list[tuple[str, int, float]] = []
    failed: list[tuple[str, str]] = []

    async with httpx.AsyncClient(
        base_url="https://v3.football.api-sports.io",
        headers={"x-apisports-key": api_key},
        timeout=httpx.Timeout(60.0),
    ) as client:
        print(f"\n=== Advanced stats backfill — {len(WC2026_TEAMS)} teams ===\n")
        t0 = time.time()

        # Coach-history key overrides for teams whose canonical name differs
        COACH_KEY = {"Ivory Coast": "Côte d'Ivoire"}

        for i, team_name in enumerate(WC2026_TEAMS, 1):
            entry = team_ids.get(team_name)
            if not entry:
                failed.append((team_name, "no team_id"))
                print(f"  [{i:2}/{len(WC2026_TEAMS)}] {team_name:30} -> SKIP (no team_id)")
                continue

            team_id = entry["id"]
            coach_lookup_name = COACH_KEY.get(team_name, team_name)
            coach_rec = get_current_coach(coach_lookup_name)
            if coach_rec is None:
                failed.append((team_name, "no coach"))
                print(f"  [{i:2}/{len(WC2026_TEAMS)}] {team_name:30} -> SKIP (no coach)")
                continue

            filter_date = get_effective_filter_date(coach_lookup_name)
            assert filter_date is not None

            try:
                result = await backfill_one_team(
                    client=client,
                    team_name=team_name,
                    team_id=team_id,
                    confederation=coach_rec.confederation,
                    filter_date=filter_date,
                    today=today,
                )
                succeeded.append(result)
                _, n, elapsed = result
                glyph = "✓" if n >= 5 else "·"
                print(f"  [{i:2}/{len(WC2026_TEAMS)}] {team_name:30} -> "
                      f"n={n:3} {glyph} ({elapsed:.1f}s)")
            except Exception as exc:
                msg = f"{type(exc).__name__}: {exc}"
                failed.append((team_name, msg))
                print(f"  [{i:2}/{len(WC2026_TEAMS)}] {team_name:30} -> FAIL ({msg})")

        total_elapsed = time.time() - t0
        print(f"\n=== Done in {total_elapsed:.1f}s ===\n")

    print(f"Profiled: {len(succeeded)}/{len(WC2026_TEAMS)}")
    if failed:
        print(f"\nFailed ({len(failed)}):")
        for n, e in failed:
            print(f"  {n}: {e}")

    diag = {
        "timestamp": datetime.now().isoformat(),
        "succeeded": [{"team": n, "n_matches": m, "elapsed_s": round(e, 1)}
                      for n, m, e in succeeded],
        "failed": [{"team": n, "error": e} for n, e in failed],
        "total_elapsed_s": round(total_elapsed, 1),
    }
    (OUT_DIR / "_diagnostic.json").write_text(json.dumps(diag, indent=2, ensure_ascii=False))
    print(f"\nDiagnostic: {OUT_DIR / '_diagnostic.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
