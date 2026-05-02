"""One-shot probe: does /odds?league&season return historical data? (D-07 / Pitfall 3).

Phase 02.1 Wave 1 reconnaissance. Not production code. Run once:
    uv run python scripts/probe_odds_bulk.py --league-id 39 --season 2024

Answers:
  A1: Does bulk endpoint return non-empty rows for a historical season?
  A2: What is the pagination shape (items per page, total pages)?
  +   Is "Betano" present in the bookmakers[] list at all?
"""
from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

import httpx
import structlog

from bip.core.settings import Settings

logger = structlog.get_logger(__name__)

BASE_URL = "https://v3.football.api-sports.io"
PROBE_DOC = Path(
    ".planning/phases/02.1-close-phase-2-verification-gaps-clv-end-to-end-test-logloss-/"
    "02.1-ODDS-PROBE.md"
)


async def probe(league_id: int, season: int, api_key: str) -> dict:
    """Make exactly ONE call to /odds?league&season and summarise the response.

    T-02.1-01: api_key is set as a header at client construction; never logged or
    interpolated into any log/print/f-string.
    T-02.1-05: Exactly one HTTP call per invocation — no loops, no retries.
    """
    async with httpx.AsyncClient(
        base_url=BASE_URL,
        headers={"x-apisports-key": api_key},
        timeout=httpx.Timeout(30.0),
    ) as client:
        logger.info("odds_probe_request", league=league_id, season=season)
        resp = await client.get("/odds", params={"league": league_id, "season": season})
        resp.raise_for_status()
        data = resp.json()

    results_count = data.get("results", 0)
    paging = data.get("paging", {})
    response_rows = data.get("response", [])

    # Betano presence check across first page
    betano_present = False
    sample_fixture_id = None
    sample_bookmakers: list[str] = []
    if response_rows:
        first = response_rows[0]
        sample_fixture_id = first.get("fixture", {}).get("id")
        sample_bookmakers = [bm.get("name", "?") for bm in first.get("bookmakers", [])]
        for row in response_rows:
            for bm in row.get("bookmakers", []):
                if bm.get("name") == "Betano":
                    betano_present = True
                    break
            if betano_present:
                break

    return {
        "league_id": league_id,
        "season": season,
        "results_count": results_count,
        "paging": paging,
        "rows_on_this_page": len(response_rows),
        "sample_fixture_id": sample_fixture_id,
        "sample_bookmakers": sample_bookmakers,
        "betano_present_in_sample": betano_present,
    }


def write_findings(report: dict) -> None:
    PROBE_DOC.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Phase 02.1 — Bulk /odds Endpoint Probe Findings",
        "",
        f"**League ID:** {report['league_id']}",
        f"**Season:** {report['season']}",
        f"**Total results (API-reported):** {report['results_count']}",
        f"**Paging:** {report['paging']}",
        f"**Rows on page 1:** {report['rows_on_this_page']}",
        f"**Sample fixture_id:** {report['sample_fixture_id']}",
        f"**Sample bookmakers (page 1 row 0):** {report['sample_bookmakers']}",
        f"**Betano present on page 1:** {report['betano_present_in_sample']}",
        "",
        "## Answers to Research Assumptions",
        "",
        f"- **A1 (bulk returns historical data):** {'PASS' if report['results_count'] > 0 else 'FAIL'}",
        f"- **A2 (pagination shape):** {report['paging']}",
        f"- **D-02 (Betano is present):** {'PASS' if report['betano_present_in_sample'] else 'FAIL — re-evaluate D-02 opening-odds source'}",
        "",
        "## Implications",
        "",
        "- If Betano is absent, plan 02.1-06 `get_odds` must be parametric on `bookmaker` and",
        "  the seed parser must tolerate missing Betano entries (null odds rows, per D-03).",
        "- If `paging.total > 1`, plan 02.1-09 (seed extend) must loop over pages — add",
        "  `&page=<n>` and sleep `INTER_REQUEST_DELAY_S` between pages.",
        "- If `results_count` is 0, the bulk endpoint is NOT a valid historical backfill path —",
        "  STOP and escalate to user before plan 02.1-06 proceeds.",
    ]
    PROBE_DOC.write_text("\n".join(lines) + "\n")
    print(f"Wrote findings to: {PROBE_DOC}")


async def main() -> int:
    parser = argparse.ArgumentParser(
        description="Probe API-Football /odds?league&season for historical coverage."
    )
    parser.add_argument("--league-id", type=int, default=39, help="Default: 39 (PL)")
    parser.add_argument("--season", type=int, default=2024, help="Default: 2024 (2024-2025)")
    args = parser.parse_args()

    settings = Settings()
    # T-02.1-01: never log the api key — pass directly into the httpx client header.
    report = await probe(args.league_id, args.season, settings.api_football_key)

    print(json.dumps(report, indent=2))
    write_findings(report)
    return 0 if report["results_count"] > 0 else 1


if __name__ == "__main__":
    import sys
    sys.exit(asyncio.run(main()))
