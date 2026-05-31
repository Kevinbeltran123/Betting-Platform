"""Tests for the Match Intel assembler — conservative matching + lossless fusion."""
from __future__ import annotations

from datetime import date

from bip.evaluation.tournaments.team_style_profiler.intel import (
    DuelMatchup,
    Injury,
    WeakLinkNote,
    assemble_intel,
    duel_matchups,
    match_name,
)
from bip.evaluation.tournaments.team_style_profiler.match_dossier import (
    DossierContext,
    generate_dossier,
)
from bip.evaluation.tournaments.team_style_profiler.player_advanced import (
    PlayerAdvancedProfile,
)
from bip.evaluation.tournaments.team_style_profiler.player_props import PlayerPropProfile
from bip.evaluation.tournaments.team_style_profiler.tsv_schema import DistributionStat


# ── Name matcher (the lose-nothing crux) ──


def test_match_token_subset():
    # StatsBomb full name vs Transfermarkt short name
    assert match_name("Leandro Daniel Paredes", ["Leandro Paredes"]) == "Leandro Paredes"
    assert match_name("Lionel Andrés Messi Cuccittini", ["Lionel Messi"]) == "Lionel Messi"


def test_match_accents_normalized():
    assert match_name("Angel Di Maria", ["Ángel Di María"]) == "Ángel Di María"


def test_no_false_link_on_surname_collision():
    # same surname, different first initial → no match (must not wrong-link)
    assert match_name("Pablo Sarabia", ["Carlos Sarabia"]) is None


def test_ambiguous_abstains():
    # two plausible matches → abstain (None), never guess
    assert match_name("John Smith", ["John Smith", "Jack Smith"]) is None


def test_no_match_returns_none():
    assert match_name("Erling Haaland", ["Martin Odegaard"]) is None


# ── Assembler: lossless cross-links ──


def _ds(m: float) -> DistributionStat:
    return DistributionStat(mean=m, ci_low=m, ci_high=m, n=8)


def _prof(pid: int, name: str, team: str = "Argentina", fouls: float = 2.5,
          source: str = "statsbomb", fouls_drawn: float = 0.5) -> PlayerPropProfile:
    return PlayerPropProfile(
        player_id=pid, player_name=name, team=team, position="Center Midfield",
        n_matches=8, minutes_total=720.0, confidence="green",
        shots_per90=_ds(1.0), shots_on_target_per90=_ds(0.5), xg_per90=_ds(0.1),
        goals_per90=_ds(0.1), fouls_committed_per90=_ds(fouls), fouls_drawn_per90=_ds(fouls_drawn),
        yellow_cards_per90=_ds(0.4),
        key_passes_per90=_ds(0.5), assists_per90=_ds(0.1), penalties_taken=0,
        source=source)


def _adv(name: str, team: str, aerial_won: float = 0.0,
         conf: str = "green") -> PlayerAdvancedProfile:
    z = _ds(0.0)
    return PlayerAdvancedProfile(
        player_id=abs(hash(name)) % 10000, player_name=name, team=team,
        position="Center Forward", n_matches=8, confidence=conf,
        prog_passes_per90=z, prog_carries_per90=z, sca_per90=z, gca_per90=z,
        tackles_per90=z, interceptions_per90=z, clearances_per90=z, recoveries_per90=z,
        dribbled_past_per90=z, aerial_won_per90=_ds(aerial_won), aerial_lost_per90=z)


def _dossier(home="Argentina", away="Mexico"):
    ctx = DossierContext(home_team=home, away_team=away, home_tsv=None, away_tsv=None,
                         tournament_slug="world_cup_2026", fixture_date=date(2026, 6, 14))
    return generate_dossier(ctx)


def test_injured_player_flagged_not_removed():
    props = [_prof(1, "Leandro Daniel Paredes"), _prof(2, "Julián Álvarez", fouls=2.3)]
    injuries = [Injury("Leandro Paredes", "Knock", "2026-06-20", False)]
    intel = assemble_intel(_dossier(), home_props=props, home_injuries=injuries)
    board = intel.home_prop_board
    paredes = [c for c in board if "Paredes" in c.player_name]
    # still present (not dropped) AND flagged
    assert paredes, "injured player must remain on the board"
    assert all("LESIONADO" in c.flag for c in paredes)
    # a non-injured player is not flagged
    alvarez = [c for c in board if "Álvarez" in c.player_name]
    assert alvarez and all(c.flag == "" for c in alvarez)


def test_injured_player_absent_from_board_becomes_provenance_note():
    props = [_prof(1, "Leandro Daniel Paredes")]
    injuries = [Injury("Emiliano Martínez", "Hamstring", None, True)]  # GK, not in board
    intel = assemble_intel(_dossier(), home_props=props, home_injuries=injuries)
    assert any("Emiliano Martínez" in n for n in intel.provenance_notes)
    # injury still fully present in the section — nothing lost
    assert any(i.name == "Emiliano Martínez" for i in intel.home_injuries)


def test_missing_advanced_layer_noted_not_silent():
    intel = assemble_intel(_dossier(), home_props=[_prof(1, "X")], home_advanced=None)
    assert any("sin métricas avanzadas" in n for n in intel.provenance_notes)


def test_referee_unknown_noted():
    intel = assemble_intel(_dossier())
    assert any("rbitro no asignado" in n for n in intel.provenance_notes)


def test_existing_dossier_preserved():
    d = _dossier()
    intel = assemble_intel(d)
    assert intel.dossier is d                     # existing picks/planteamiento untouched


# ── Corrections: blind spots + set-piece intel + demoted picks ──


def test_set_piece_intel_curated_and_lookup():
    from bip.evaluation.tournaments.team_style_profiler.set_piece_intel import set_piece_for
    assert set_piece_for("Spain") is not None
    assert set_piece_for("Atlantis") is None
    intel = assemble_intel(_dossier(home="Spain", away="Atlantis"))
    assert intel.home_set_piece is not None and intel.away_set_piece is None


def test_blind_spots_surface_what_data_misses():
    # Spain in set-piece catalog; ESPN-source props → no-xG caveat
    props = [_prof(1, "Someone", team="Spain", source="espn")]
    intel = assemble_intel(_dossier(home="Spain", away="Mexico"), home_props=props)
    bs = " ".join(intel.blind_spots)
    assert "CONFIRMAR XI" in bs                    # lineup always
    assert "balón parado" in bs                    # set-piece prompt (Spain + Mexico in catalog)
    assert "sin xG" in bs                          # ESPN no-xG caveat


def test_render_demotes_picks_to_evidence():
    md = render_intel_markdown_safe(_dossier(home="Spain", away="Mexico"))
    assert "§0. Investigar" in md                  # human dig-list first
    assert "evidencia" in md
    # the auto-verdict is gone
    assert "STRONG" not in md and "**Score**" not in md and "Ranked Picks" not in md


def render_intel_markdown_safe(dossier):
    from bip.evaluation.tournaments.team_style_profiler.intel import render_intel_markdown
    return render_intel_markdown(assemble_intel(dossier))


def test_confirmed_lineup_marks_starters_and_bench():
    props = [_prof(1, "Leandro Daniel Paredes"), _prof(2, "Banco Suplente", fouls=2.0)]
    intel = assemble_intel(_dossier(), home_props=props,
                           home_lineup=["Leandro Paredes", "Otro Titular"])
    board = intel.home_prop_board
    paredes = [c for c in board if "Paredes" in c.player_name]
    assert paredes and all("titular" in c.flag for c in paredes)
    bench = [c for c in board if "Suplente" in c.player_name]
    assert bench and all("banquillo" in c.flag for c in bench)


def test_both_lineups_resolve_the_lineup_blind_spot():
    intel = assemble_intel(_dossier(), home_lineup=["A"], away_lineup=["B"])
    assert any("XI CONFIRMADO" in s for s in intel.blind_spots)
    assert not any("CONFIRMAR XI a" in s for s in intel.blind_spots)


def test_injury_beats_starter_flag():
    props = [_prof(1, "Leandro Daniel Paredes")]
    intel = assemble_intel(_dossier(), home_props=props,
                           home_lineup=["Leandro Paredes"],
                           home_injuries=[Injury("Leandro Paredes", "Knock", None, True)])
    paredes = [c for c in intel.home_prop_board if "Paredes" in c.player_name]
    assert paredes and all("LESIONADO" in c.flag for c in paredes)  # injury priority


def test_recent_form_board_built_and_labeled():
    recent = [_prof(1, "Erling Haaland", team="Norway", source="espn")]
    intel = assemble_intel(_dossier(home="Spain", away="Norway"), away_props_recent=recent)
    assert intel.away_recent_board, "ESPN current-form board should be built"
    from bip.evaluation.tournaments.team_style_profiler.intel import render_intel_markdown
    out = render_intel_markdown(intel)
    assert "Forma actual (ESPN" in out          # labeled separately, provenance kept


# ── Duel matchups (threat × weak-link cross) ──


def test_duel_pace_pairs_foul_drawer_with_beaten_defender():
    # Mexico (away) has a defender beaten 1v1; Argentina (home) foul-drawer punishes it.
    weak = [WeakLinkNote(team="Mexico", player="Slow CB", position="Right Back",
                         reason="beaten 2.0×/90 1v1", kind="pace/1v1")]
    duels = duel_matchups(
        weak, "Argentina", "Mexico",
        home_props=[_prof(1, "Messi", fouls_drawn=2.4)], away_props=[],
        home_advanced=None, away_advanced=None)
    assert len(duels) == 1
    d = duels[0]
    assert d.attacker == "Messi" and d.attacker_team == "Argentina"
    assert d.defender == "Slow CB" and d.defender_team == "Mexico"
    assert d.market == "faltas/tarjetas/penal"


def test_duel_aerial_pairs_aerial_winner_with_weak_header():
    # Argentina (home) weak in the air; Mexico (away) aerial threat punishes it.
    weak = [WeakLinkNote(team="Argentina", player="Small CB", position="Center Back",
                         reason="aerial win rate 30%", kind="aerial")]
    duels = duel_matchups(
        weak, "Argentina", "Mexico",
        home_props=[], away_props=[],
        home_advanced=None, away_advanced=[_adv("Big Striker", "Mexico", aerial_won=3.0)])
    assert len(duels) == 1
    d = duels[0]
    assert d.attacker == "Big Striker" and d.attacker_team == "Mexico"
    assert d.market == "cabeza/córner"


def test_duel_not_fabricated_without_threat():
    # weak-link present but no foul-drawer on the attacking side → no duel.
    weak = [WeakLinkNote(team="Mexico", player="Slow CB", position="Right Back",
                         reason="beaten 2.0×/90 1v1", kind="pace/1v1")]
    duels = duel_matchups(
        weak, "Argentina", "Mexico",
        home_props=[_prof(1, "NoFouls", fouls_drawn=0.0)], away_props=[],
        home_advanced=None, away_advanced=None)
    assert duels == []
