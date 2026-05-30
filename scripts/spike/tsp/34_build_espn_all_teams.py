"""ESPN current-form player-prop layer for ALL WC2026 teams.

ESPN works for every team (not just the 8 underdogs) and adds what StatsBomb
lacks: RECENCY (2024-25 qualifiers + friendlies) vs StatsBomb's tournament-only
history. Complementary — StatsBomb has xG/depth, ESPN has breadth/recency.

Pulls each team's matches from its confederation WC-qualifier comp + friendlies
(+ Nations League for CONCACAF, which covers the auto-qualified hosts who played
no qualifiers). Output: data/cache/tsp/player_props_espn/{team}.json (kept apart
from player_props/ so StatsBomb's xG profiles are not overwritten).
"""
from __future__ import annotations

import json
import sys
import time
import unicodedata
from pathlib import Path

import requests

from bip.evaluation.tournaments.team_style_profiler.coach_history import CURRENT_COACHES
from bip.evaluation.tournaments.team_style_profiler.espn_ingest import match_player_counts
from bip.evaluation.tournaments.team_style_profiler.player_props import (
    build_player_profiles,
    prop_board,
)

PROJECT = Path(__file__).resolve().parents[3]
OUT_DIR = PROJECT / "data" / "cache" / "tsp" / "player_props_espn"
S = "https://site.api.espn.com/apis/site/v2/sports/soccer"
RECENT_MATCHES = 12  # most-recent completed matches per team (current form)

CONF_QUALIFIER = {
    "UEFA": "fifa.worldq.uefa", "CONMEBOL": "fifa.worldq.conmebol",
    "CAF": "fifa.worldq.caf", "AFC": "fifa.worldq.afc",
    "CONCACAF": "fifa.worldq.concacaf", "OFC": "fifa.worldq.ofc",
}
# coach_history name -> ESPN displayName, where they diverge.
ESPN_NAME = {
    "USA": "United States",
    "Côte d'Ivoire": "Ivory Coast", "Cape Verde": "Cape Verde Islands",
    "DR Congo": "Congo DR", "Curaçao": "Curacao",
    "Czech Republic": "Czechia", "Turkey": "Türkiye",
}


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return " ".join(t for t in s.lower().replace("-", " ").split() if t != "and")


def _slug(name: str) -> str:
    return _norm(name).replace(" ", "_")


def _get(url: str) -> dict:
    r = requests.get(url, timeout=20, headers={"User-Agent": "Mozilla/5.0"})
    r.raise_for_status()
    time.sleep(0.2)
    return r.json()


def _team_index(league: str) -> dict[str, str]:
    try:
        data = _get(f"{S}/{league}/teams")
    except Exception:
        return {}
    idx = {}
    for sp in data.get("sports", []):
        for lg in sp.get("leagues", []):
            for t in lg.get("teams", []):
                team = t.get("team", {})
                idx[_norm(team.get("displayName", ""))] = team.get("id")
    return idx


def resolve_id(name: str, *indexes: dict) -> str | None:
    target = _norm(ESPN_NAME.get(name, name))
    for idx in indexes:
        if target in idx:
            return idx[target]
        for k, v in idx.items():
            if target and (target in k or k in target):
                return v
    return None


def completed_event_ids(league: str, team_id: str) -> list[tuple[str, str]]:
    try:
        sch = _get(f"{S}/{league}/teams/{team_id}/schedule")
    except Exception:
        return []
    out = []
    for e in sch.get("events", []):
        comp = e.get("competitions", [{}])[0]
        if comp.get("status", {}).get("type", {}).get("completed"):
            out.append((e["id"], e.get("date", "")))
    return out


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    friendly_idx = _team_index("fifa.friendly")
    teams = sys.argv[1:] or sorted(CURRENT_COACHES)
    conf_idx_cache: dict[str, dict] = {}

    for name in teams:
        rec = CURRENT_COACHES.get(name)
        if rec is None:
            print(f"  ✗ {name}: not in CURRENT_COACHES")
            continue
        qual = CONF_QUALIFIER.get(rec.confederation)
        leagues = [lg for lg in (qual, "fifa.friendly") if lg]
        if rec.confederation == "CONCACAF":
            leagues.append("concacaf.nations.league")

        if qual and qual not in conf_idx_cache:
            conf_idx_cache[qual] = _team_index(qual)
        team_id = resolve_id(name, conf_idx_cache.get(qual, {}), friendly_idx)
        if not team_id:
            print(f"  ✗ {name}: ESPN id not resolved")
            continue

        seen: set[str] = set()
        dated: list[tuple[str, str]] = []
        for lg in leagues:
            for eid, dt in completed_event_ids(lg, team_id):
                if eid not in seen:
                    seen.add(eid)
                    dated.append((eid, dt, lg))
        dated.sort(key=lambda x: x[1], reverse=True)
        dated = dated[:RECENT_MATCHES]

        per_match = []
        for eid, _, lg in dated:
            try:
                cm = match_player_counts(_get(f"{S}/{lg}/summary?event={eid}"), team_id)
                if cm[0]:
                    per_match.append(cm)
            except Exception:
                continue
        profiles = sorted(build_player_profiles(per_match, source="espn"),
                          key=lambda p: -p.n_matches)
        board = prop_board(profiles)
        (OUT_DIR / f"{_slug(name)}.json").write_text(json.dumps({
            "team": name, "source": "espn-current-form", "n_matches": len(per_match),
            "n_players": len(profiles),
            "players": [{"name": p.player_name, "position": p.position, "n_matches": p.n_matches,
                         "confidence": p.confidence, "shots_per90": round(p.shots_per90.mean, 2),
                         "sot_per90": round(p.shots_on_target_per90.mean, 2),
                         "goals_per90": round(p.goals_per90.mean, 3),
                         "fouls_per90": round(p.fouls_committed_per90.mean, 2),
                         "yellows_per90": round(p.yellow_cards_per90.mean, 3),
                         "p_anytime_scorer": round(p.p_anytime_scorer, 3)} for p in profiles],
            "prop_board": [{"market": c.market, "player": c.player_name, "stat": c.stat,
                            "softness": c.softness, "confidence": c.confidence} for c in board],
        }, indent=2, ensure_ascii=False))
        print(f"  ✓ {name:24} {len(per_match):2} matches, {len(profiles):2} players"
              f"  | top: {board[0].player_name if board else '-'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
