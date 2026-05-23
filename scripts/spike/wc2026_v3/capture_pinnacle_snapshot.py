"""Capture a Pinnacle closing-line snapshot for one WC2026 fixture (Wave 2.D).

Per the PLAN, the v3 CLV-capture workflow is:
1. Scheduler fires T-5min before kickoff (operator's APScheduler, separate)
2. Calls this script with --event-id <id> --output <path>
3. Script fetches Pinnacle + Betfair Exchange 1X2 + AH from The Odds API
4. Writes a JSON snapshot to <path>
5. Downstream: v3 CLV sink consumes the snapshot (NOT WIRED in v3 sprint
   — engine_v3 freeze applies; integration deferred to operator)

The script is idempotent: same output path, same fetch → identical
content (modulo the Pinnacle source's own line movements). Suitable
for running offline against a list of fixtures, or live via scheduler.

API key handling: reads from OPTIMAL_ODDS_API_KEY env var by default,
or --api-key flag override. The script does NOT log the key.

Coverage verification (FREE — operator runs ONCE before subscribing):

    uv run python scripts/spike/wc2026_v3/capture_pinnacle_snapshot.py \\
        --verify-coverage --sport soccer_fifa_world_cup

This hits /sports endpoint (free across all tiers) to confirm the sport
is listed. Catches the "Pinnacle dropped WC2026 coverage" failure mode
BEFORE the operator subscribes.

Live snapshot (requires paid tier):

    OPTIMAL_ODDS_API_KEY=xxx uv run python \\
        scripts/spike/wc2026_v3/capture_pinnacle_snapshot.py \\
        --sport soccer_fifa_world_cup --event-id abc123 \\
        --output data/cache/odds_api/pinnacle/abc123.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from bip.integrations.odds_api_client import (
    BETFAIR_EX_EU_KEY,
    H2H_MARKET,
    PINNACLE_KEY,
    SOCCER_WC_2026,
    SPREADS_MARKET,
    OddsApiClient,
    OddsApiError,
    extract_pinnacle_h2h,
    shin_devig_h2h,
)


def _api_key_from_env_or_arg(arg_key: str | None) -> str:
    """Resolve API key from --api-key arg or env. Env: OPTIMAL_ODDS_API_KEY."""
    key = arg_key or os.environ.get("OPTIMAL_ODDS_API_KEY")
    if not key:
        raise SystemExit(
            "API key required: set OPTIMAL_ODDS_API_KEY or pass --api-key"
        )
    return key


def verify_coverage(client: OddsApiClient, sport_key: str) -> dict:
    """Free-tier coverage ping. Returns the matching sport entry or raises."""
    resp = client.get_sports(all_sports=True)
    sports = resp.data
    assert isinstance(sports, list)
    matches = [s for s in sports if s.get("key") == sport_key]
    if not matches:
        raise SystemExit(
            f"Sport {sport_key!r} NOT FOUND in /sports response. "
            "Operator should DEFER subscription — coverage missing."
        )
    return matches[0]


def capture_snapshot(
    client: OddsApiClient,
    sport_key: str,
    event_id: str,
    output_path: Path,
    *,
    bookmakers: tuple[str, ...] = (PINNACLE_KEY, BETFAIR_EX_EU_KEY),
    markets: tuple[str, ...] = (H2H_MARKET, SPREADS_MARKET),
) -> dict:
    """Fetch + write one event's snapshot. Returns the snapshot dict."""
    resp = client.get_event_odds(
        sport_key, event_id, bookmakers=bookmakers, markets=markets
    )
    payload = resp.data
    assert isinstance(payload, dict)

    # Convenience extraction — operator-facing CLV consumer can read
    # this directly without re-implementing the Pinnacle-parsing path.
    pinnacle_h2h = extract_pinnacle_h2h(payload)
    pinnacle_devig = (
        shin_devig_h2h(pinnacle_h2h) if pinnacle_h2h is not None else None
    )

    snapshot = {
        "captured_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "sport_key": sport_key,
        "event_id": event_id,
        "raw_payload": payload,
        "pinnacle_h2h_decimal": pinnacle_h2h,
        "pinnacle_h2h_devig_probs": pinnacle_devig,
        "rate_limit": {
            "requests_used": resp.rate_limit.requests_used,
            "requests_remaining": resp.rate_limit.requests_remaining,
            "last_request_cost": resp.rate_limit.last_request_cost,
        },
        "bookmakers_requested": list(bookmakers),
        "markets_requested": list(markets),
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(snapshot, indent=2, sort_keys=True))
    return snapshot


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--api-key",
        default=None,
        help="Override OPTIMAL_ODDS_API_KEY env.",
    )
    parser.add_argument(
        "--sport",
        default=SOCCER_WC_2026,
        help=f"Sport key (default: {SOCCER_WC_2026}).",
    )
    parser.add_argument(
        "--verify-coverage",
        action="store_true",
        help="FREE coverage ping (no event capture). Operator runs ONCE pre-subscription.",
    )
    parser.add_argument(
        "--event-id",
        default=None,
        help="Event ID to capture (required without --verify-coverage).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output JSON path (default: data/cache/odds_api/pinnacle/<event_id>.json).",
    )
    args = parser.parse_args(argv)

    api_key = _api_key_from_env_or_arg(args.api_key)

    with OddsApiClient(api_key=api_key) as client:
        if args.verify_coverage:
            sport = verify_coverage(client, args.sport)
            print(f"OK: {args.sport} listed in /sports response")
            print(json.dumps(sport, indent=2, sort_keys=True))
            return 0

        if not args.event_id:
            parser.error("--event-id is required unless --verify-coverage")

        output = args.output or Path(
            f"data/cache/odds_api/pinnacle/{args.event_id}.json"
        )
        try:
            snap = capture_snapshot(client, args.sport, args.event_id, output)
        except OddsApiError as e:
            print(f"OddsApiError: {e}", file=sys.stderr)
            return 1

        print(f"Wrote {output}")
        if snap["pinnacle_h2h_devig_probs"]:
            p = snap["pinnacle_h2h_devig_probs"]
            print(
                f"Pinnacle de-vig: home={p['home']:.4f} "
                f"draw={p['draw']:.4f} away={p['away']:.4f}"
            )
        else:
            print("WARNING: Pinnacle h2h not present in payload")
        rl = snap["rate_limit"]
        if rl["requests_remaining"] is not None:
            print(f"Rate limit: {rl['requests_remaining']} requests remaining")
        return 0


if __name__ == "__main__":
    sys.exit(main())
