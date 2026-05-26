"""Smoke test — verify API-Football connectivity + detect rate limit tier.

Makes ONE call to /status (free, doesn't consume request budget) to:
  1. Confirm the API key is valid.
  2. Read the X-RateLimit-* headers to know our tier (10 vs 300 req/min).

Logs everything; doesn't ingest any team data yet.
"""
from __future__ import annotations

import asyncio
import sys

import os
import httpx
import structlog
from dotenv import load_dotenv

logger = structlog.get_logger(__name__)


async def main() -> int:
    load_dotenv()
    api_key = os.environ.get("API_FOOTBALL_KEY", "")
    if not api_key or api_key == "your-api-football-key":
        print("ERROR: API_FOOTBALL_KEY not set in .env")
        return 1
    masked = api_key[:6] + "…" + api_key[-4:] if len(api_key) > 12 else "***"
    print(f"API key loaded: {masked}")

    async with httpx.AsyncClient(
        base_url="https://v3.football.api-sports.io",
        headers={"x-apisports-key": api_key},
        timeout=httpx.Timeout(30.0),
    ) as client:
        print("\nCalling /status...")
        r = await client.get("/status")
        r.raise_for_status()
        payload = r.json()

        print(f"\nResponse status: {r.status_code}")
        print("\nRelevant headers:")
        for h in [
            "x-ratelimit-limit",
            "x-ratelimit-remaining",
            "x-ratelimit-requests-limit",
            "x-ratelimit-requests-remaining",
            "server",
        ]:
            v = r.headers.get(h)
            if v:
                print(f"  {h}: {v}")

        # /status returns account info: subscription, plan, usage today
        account = payload.get("response", {})
        print("\nAccount info:")
        if isinstance(account, dict):
            sub = account.get("subscription", {})
            req = account.get("requests", {})
            print(f"  plan: {sub.get('plan', '?')}")
            print(f"  active: {sub.get('active', '?')}")
            print(f"  end date: {sub.get('end', '?')}")
            print(f"  requests today: {req.get('current', '?')} / {req.get('limit_day', '?')}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
