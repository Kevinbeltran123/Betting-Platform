"""Probe — figure out the right query params for national team fixtures."""
from __future__ import annotations

import asyncio
import os
import sys

import httpx
from dotenv import load_dotenv


async def main() -> int:
    load_dotenv()
    api_key = os.environ.get("API_FOOTBALL_KEY", "")
    if not api_key:
        return 1

    team_id = 26  # Argentina

    async with httpx.AsyncClient(
        base_url="https://v3.football.api-sports.io",
        headers={"x-apisports-key": api_key},
        timeout=httpx.Timeout(30.0),
    ) as client:
        # Variant 1: team + from/to without season
        for variant, params in [
            ("from+to no season", {"team": team_id, "from": "2024-01-01", "to": "2024-12-31"}),
            ("season=2024", {"team": team_id, "season": 2024}),
            ("season=2023", {"team": team_id, "season": 2023}),
            ("season+from+to", {"team": team_id, "season": 2024, "from": "2024-01-01", "to": "2024-12-31"}),
            ("last=5", {"team": team_id, "last": 5}),
        ]:
            r = await client.get("/fixtures", params=params)
            r.raise_for_status()
            payload = r.json()
            n_results = len(payload.get("response", []))
            errors = payload.get("errors", {})
            print(f"  {variant:30} → results={n_results:4}, errors={errors}")
            if n_results > 0 and not errors:
                # Show first result
                first = payload["response"][0]
                print(f"     first: id={first['fixture']['id']}, "
                      f"date={first['fixture']['date']}, "
                      f"{first['teams']['home']['name']} vs {first['teams']['away']['name']}")

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
