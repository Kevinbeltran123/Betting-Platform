"""Assemble the full Match Intel for a fixture from all cached layers + render.

Demonstrates lossless fusion across mixed provenance (StatsBomb / ESPN /
Transfermarkt / scouting). Usage: ... 38_assemble_match_intel "Spain" "Norway"
"""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

from bip.evaluation.tournaments.team_style_profiler.advanced_metrics import AdvancedTeamProfile
from bip.evaluation.tournaments.team_style_profiler.intel import (
    Injury, assemble_intel, render_intel_markdown,
)
from bip.evaluation.tournaments.team_style_profiler.match_dossier import (
    DossierContext, generate_dossier,
)
from bip.evaluation.tournaments.team_style_profiler.player_advanced import PlayerAdvancedProfile
from bip.evaluation.tournaments.team_style_profiler.player_props import PlayerPropProfile
from bip.evaluation.tournaments.team_style_profiler.statsbomb_advanced import TeamStatsBombProfile
from bip.evaluation.tournaments.team_style_profiler.tactical_identity import tactical_identity_for
from bip.evaluation.tournaments.team_style_profiler.tsv_schema import DistributionStat, TeamStyleVector

P = Path(__file__).resolve().parents[3] / "data" / "cache" / "tsp"
OUT = P / "dossier_demos"


def _slug(n: str) -> str:
    return n.replace(" ", "_").replace("'", "").replace("ô", "o").lower()


def _ds(m) -> DistributionStat:
    m = float(m or 0.0)
    return DistributionStat(mean=m, ci_low=m, ci_high=m, n=8)


def _load(sub, slug):
    f = P / sub / f"{slug}.json"
    return json.loads(f.read_text()) if f.exists() else None


def _props(slug):
    d = _load("player_props", slug)
    if not d:
        return []
    src = d.get("source", "statsbomb")
    src = "espn" if "espn" in src else "statsbomb"
    out = []
    for i, p in enumerate(d["players"]):
        out.append(PlayerPropProfile(
            player_id=i, player_name=p["name"], team=d["team"], position=p.get("position", "?"),
            n_matches=p["n_matches"], minutes_total=p["n_matches"] * 90.0, confidence=p["confidence"],
            shots_per90=_ds(p.get("shots_per90")), shots_on_target_per90=_ds(p.get("sot_per90")),
            xg_per90=_ds(p.get("xg_per90")), goals_per90=_ds(p.get("goals_per90")),
            fouls_committed_per90=_ds(p.get("fouls_per90")),
            fouls_drawn_per90=_ds(p.get("fouls_drawn_per90")), yellow_cards_per90=_ds(p.get("yellows_per90")),
            key_passes_per90=_ds(0), assists_per90=_ds(p.get("assists_per90")),
            penalties_taken=p.get("penalties_taken", 0), source=src))
    return out


def _advanced(slug):
    d = _load("player_advanced", slug)
    if not d:
        return None
    out = []
    for i, p in enumerate(d["players"]):
        out.append(PlayerAdvancedProfile(
            player_id=i, player_name=p["name"], team=d["team"], position=p.get("position", "?"),
            n_matches=p["n_matches"], confidence=p["confidence"],
            prog_passes_per90=_ds(p.get("prog_passes_per90")), prog_carries_per90=_ds(p.get("prog_carries_per90")),
            sca_per90=_ds(p.get("sca_per90")), gca_per90=_ds(p.get("gca_per90")),
            tackles_per90=_ds(p.get("tackles_per90")), interceptions_per90=_ds(p.get("interceptions_per90")),
            clearances_per90=_ds(0), recoveries_per90=_ds(0),
            dribbled_past_per90=_ds(p.get("dribbled_past_per90")),
            aerial_won_per90=_ds(p.get("aerial_won_per90")),
            aerial_lost_per90=_ds(max(0.0, p.get("aerial_won_per90", 0) / max(p.get("aerial_win_rate", 0.5), 0.01) - p.get("aerial_won_per90", 0)))))
    return out


def _team_adv(slug, team):
    d = _load("advanced_metrics", slug)
    if not d:
        return None
    return AdvancedTeamProfile(
        team=team, n_matches=d["n_matches"], field_tilt=_ds(d["field_tilt"]),
        gk_goals_prevented_per_match=_ds(d["gk_goals_prevented_per_match"]),
        line_height=_ds(d.get("line_height")), directness=_ds(d.get("directness")),
        xg_share_leading=d["xg_share_leading"], xg_share_level=d["xg_share_level"],
        xg_share_trailing=d["xg_share_trailing"])


def _injuries(slug):
    d = _load("availability", slug)
    if not d:
        return []
    return [Injury(name=e["name"], injury=e.get("injury") or "lesión",
                   until=e.get("until"), ongoing=e.get("ongoing", False)) for e in d.get("injured", [])]


def _tsv(slug):
    f = P / "profiles" / f"{slug}_tsv.json"
    return TeamStyleVector.model_validate_json(f.read_text()) if f.exists() else None


def _tid(slug, name):
    f = P / "profiles_statsbomb" / f"{slug}_sb.json"
    prof = TeamStatsBombProfile.model_validate_json(f.read_text()) if f.exists() else None
    return tactical_identity_for(name, prof)


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    home, away = (sys.argv[1], sys.argv[2]) if len(sys.argv) >= 3 else ("Spain", "Norway")
    hs, as_ = _slug(home), _slug(away)
    ctx = DossierContext(home_team=home, away_team=away, home_tsv=_tsv(hs), away_tsv=_tsv(as_),
                         tournament_slug="world_cup_2026", fixture_date=date(2026, 6, 20),
                         home_tid=_tid(hs, home), away_tid=_tid(as_, away))
    intel = assemble_intel(
        generate_dossier(ctx),
        home_props=_props(hs), away_props=_props(as_),
        home_advanced=_advanced(hs), away_advanced=_advanced(as_),
        home_team_adv=_team_adv(hs, home), away_team_adv=_team_adv(as_, away),
        home_injuries=_injuries(hs), away_injuries=_injuries(as_))
    md = render_intel_markdown(intel)
    (OUT / f"{hs}_vs_{as_}_intel.md").write_text(md)
    print(md)
    return 0


if __name__ == "__main__":
    sys.exit(main())
