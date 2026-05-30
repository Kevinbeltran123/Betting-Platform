"""Collect current injuries / availability for WC2026 squads from Transfermarkt.

Transfermarkt serves real HTML to curl_cffi (no Cloudflare block). For each team
we scrape the squad page → each player's injury history → current status.
Output: data/cache/tsp/availability/{team}.json.

Team → kader path map is extensible; seeded with verified IDs. Full WC2026 run
is a batch job (fill TM_KADER for all 48). Be polite: ~0.3s between requests.
"""
from __future__ import annotations

import json
import sys
import time
from datetime import date
from pathlib import Path

from bip.evaluation.tournaments.team_style_profiler.transfermarkt_scrape import (
    current_injury_status,
    fetch_injuries_html,
    fetch_squad_html,
    parse_injuries,
    parse_squad,
    resolve_kader_path,
)

PROJECT = Path(__file__).resolve().parents[3]
OUT_DIR = PROJECT / "data" / "cache" / "tsp" / "availability"
TODAY = date(2026, 5, 30)

# Transfermarkt national-team kader paths (extensible — add the rest of WC2026).
TM_KADER = {
    "Norway": "/norwegen/kader/verein/3440",
}


def _slug(name: str) -> str:
    return name.replace(" ", "_").replace("'", "").lower()


def collect_team(name: str, kader_path: str) -> dict:
    squad = parse_squad(fetch_squad_html(kader_path))
    time.sleep(0.3)
    players = []
    injured = []
    for p in squad:
        try:
            recs = parse_injuries(fetch_injuries_html(p.profile_path))
        except Exception:
            recs = []
        time.sleep(0.3)
        st = current_injury_status(recs, TODAY)
        entry = {
            "name": p.name, "tm_id": p.tm_id, "injured": st.injured,
            "injury": st.injury, "ongoing": st.ongoing,
            "until": st.until.isoformat() if st.until else None,
            "n_injury_records": len(recs),
        }
        players.append(entry)
        if st.injured:
            injured.append(entry)
    return {
        "team": name, "as_of": TODAY.isoformat(), "n_squad": len(squad),
        "n_injured": len(injured), "injured": injured, "players": players,
    }


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    teams = sys.argv[1:] or list(TM_KADER)
    for name in teams:
        kader = TM_KADER.get(name) or resolve_kader_path(name)
        if not kader:
            print(f"  ✗ {name}: could not resolve Transfermarkt squad")
            continue
        rep = collect_team(name, kader)
        (OUT_DIR / f"{_slug(name)}.json").write_text(json.dumps(rep, indent=2, ensure_ascii=False))
        print(f"\n=== {name}: {rep['n_squad']} squad, {rep['n_injured']} currently OUT (as of {TODAY}) ===")
        for e in rep["injured"]:
            until = f"until {e['until']}" if e["until"] else "ongoing"
            print(f"  ⛔ {e['name']:24} {e['injury']} ({until})")
        if not rep["injured"]:
            print("  (squad fully available)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
