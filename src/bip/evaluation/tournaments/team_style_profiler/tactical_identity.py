"""Tactical Identity (planteamiento) — codifies a national team's playing
philosophy from StatsBomb tactical proxies + curated qualitative anchors.

PHILOSOPHY (operator directive 2026-05-30):
  "Quiero que aprendas a identificar el planteamiento de juego."

This is a sidecar to the TSV, analogous to coach_history. It does NOT predict
markets and does NOT touch lock_v1. It turns the tactical proxies already
computed in `statsbomb_advanced.TeamStatsBombProfile` into a *labeled* read of
HOW a team plays, so the match_dossier can reason about the game-plan, not just
the goal rates.

Three dimensions are derived mechanically from data (thresholds below are the
empirical terciles measured across 40 WC2026 teams, 2026-05-30):

  press_intensity   <- PPDA            (LOW ppda = HIGH press)
  set_piece_reliance <- set_piece_xg_share
  finishing_profile <- conversion_rate (goals / xG)

A fourth layer — `archetype` — is the SYNTHESIS of those dimensions into a named
game-plan. That synthesis is football judgment, so it lives in
`synthesize_archetype()` below for the operator to define.

Qualitative anchors (press triggers, build-up shape — things metrics can't see)
are curated per team in PHILOSOPHY_ANCHORS, sourced from
Papers/INTERNATIONAL_ANALYST_RESEARCH.md.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from bip.evaluation.tournaments.team_style_profiler.statsbomb_advanced import (
    TeamStatsBombProfile,
)

# --- Empirical terciles across 40 WC2026 teams (StatsBomb cache, 2026-05-30) ---
# PPDA: passes per defensive action in opp third. LOW = presses hard/high.
PPDA_HIGH_PRESS_MAX = 11.0   # p33: <=11.0 -> high-press
PPDA_LOW_BLOCK_MIN = 13.5    # p67: >=13.5 -> passive / low-block

# set_piece_xg_share: fraction of total xG from set pieces + penalties.
SP_RELIANT_MIN = 0.21        # p67: >=0.21 -> set-piece reliant
SP_OPEN_PLAY_MAX = 0.09      # p33: <=0.09 -> open-play dominant

# conversion_rate: goals / xG. >1 clinical, <1 wasteful.
CONV_CLINICAL_MIN = 1.10
CONV_WASTEFUL_MAX = 0.90

# Sample-size confidence, mirrors TSV flag policy.
N_GREEN_MIN = 10
N_YELLOW_MIN = 5

PressIntensity = Literal["high_press", "balanced_press", "low_block"]
SetPieceReliance = Literal["set_piece_reliant", "mixed", "open_play"]
FinishingProfile = Literal["clinical", "neutral", "wasteful"]
Confidence = Literal["green", "yellow", "red"]


@dataclass(frozen=True)
class PhilosophyAnchor:
    """Curated qualitative read that metrics cannot capture.

    Sourced from Papers/INTERNATIONAL_ANALYST_RESEARCH.md. These are the
    'philosophy over formation' notes: press triggers, build-up shape,
    weak-link, simplified principles a national team can install in 10 days.
    """

    press_trigger: str       # e.g. "6-second rule after loss" / "deep, springs on turnover"
    build_up: str            # e.g. "vertical through thirds" / "long to target then second balls"
    weak_link: str           # the #1 structural vulnerability to attack
    note: str = ""


@dataclass(frozen=True)
class TacticalIdentity:
    """Structured planteamiento for one national team."""

    team_name: str
    n_matches: int
    confidence: Confidence

    # Mechanical, data-derived dimensions
    press_intensity: PressIntensity
    set_piece_reliance: SetPieceReliance
    finishing_profile: FinishingProfile

    # Raw values kept for the dossier to quote
    ppda: float
    set_piece_xg_share: float
    conversion_rate: float

    # Synthesis (operator-defined) + curated qualitative layer
    archetype: str
    anchor: PhilosophyAnchor | None


def _confidence_for(n: int) -> Confidence:
    if n >= N_GREEN_MIN:
        return "green"
    if n >= N_YELLOW_MIN:
        return "yellow"
    return "red"


def _press_intensity(ppda: float) -> PressIntensity:
    if ppda <= PPDA_HIGH_PRESS_MAX:
        return "high_press"
    if ppda >= PPDA_LOW_BLOCK_MIN:
        return "low_block"
    return "balanced_press"


def _set_piece_reliance(share: float) -> SetPieceReliance:
    if share >= SP_RELIANT_MIN:
        return "set_piece_reliant"
    if share <= SP_OPEN_PLAY_MAX:
        return "open_play"
    return "mixed"


def _finishing_profile(conv: float) -> FinishingProfile:
    if conv >= CONV_CLINICAL_MIN:
        return "clinical"
    if conv <= CONV_WASTEFUL_MAX:
        return "wasteful"
    return "neutral"


# --- Curated qualitative anchors (philosophy over formation) ---
# The 16 set-piece-catalog teams, grounded in Papers/SET_PIECE_CATALOG_WC2026.md
# (weak_link <- each team's "Weakness #1 explotable") +
# Papers/INTERNATIONAL_ANALYST_RESEARCH.md (philosophy over formation) + the
# data-derived archetype. Key = TSV canonical team name. Extend as opposition
# reports are written.
PHILOSOPHY_ANCHORS: dict[str, PhilosophyAnchor] = {
    "Spain": PhilosophyAnchor(
        press_trigger="6-second counter-press after loss (De la Fuente continuity of Luis Enrique principle); PPDA 6.1, hardest presser of the field",
        build_up="possession as control, vertical when the third opens; 34% short corners, Carvajal blind-side flick signature",
        weak_link="pure-zonal corner defense → runner to the far post (the classic way to beat 3-compressed-near-post); pace in behind the high line",
    ),
    "Morocco": PhilosophyAnchor(
        press_trigger="deep, compact block; springs on turnover (WC22 SF identity), PPDA 16.4",
        build_up="reactive — absorb then counter through wide runners; set-piece offense historically under-developed",
        weak_link="creating vs a parked bus; reliant on transition moments",
        note="Regragui deposed Mar 2026 — Ouahbi <3mo; WC22/AFCON legacy NOT predictive, re-baseline on friendlies.",
    ),
    "Argentina": PhilosophyAnchor(
        press_trigger="high mid-block, selective press (PPDA 9.8); Scaloni squad-cohesion > tactical innovation",
        build_up="patient then vertical to forwards; near-post flick → far-post finish corner signature, 26% set-piece xG",
        weak_link="slow short-corner defending (Colombia exploited, Copa24 final); aging spine depends on key individuals fit",
    ),
    "Brazil": PhilosophyAnchor(
        press_trigger="high press under Ancelotti (PPDA 9.9), aggressive on opponent build-up but structure still settling",
        build_up="wide overloads + Vinicius/Raphinha 1v1; inswing corners to stacked far post",
        weak_link="wasteful finishing (conv ~0.88) — dominates without killing games; zonal→man transition leaves near post free",
        note="Ancelotti since May 2025; new defensive system not yet consolidated.",
    ),
    "France": PhilosophyAnchor(
        press_trigger="reactive mid-low block (Deschamps pragmatism, PPDA 15.1); cedes the ball, springs on transition",
        build_up="vertical to Mbappé in transition; Griezmann inswing set-pieces a primary route when the game closes",
        weak_link="pure-zonal corners overload near post → second post free (Spain exploited EURO24 SF); blunt in open play vs a parked side",
    ),
    "England": PhilosophyAnchor(
        press_trigger="balanced, situational press under Tuchel (PPDA 11.1), no extreme block height",
        build_up="possession through Bellingham/Foden; inswinger corners, Barry deception routines + long throws",
        weak_link="no elite direct-FK threat after the Trent snub; zonal corner defense leaves the second post",
    ),
    "Germany": PhilosophyAnchor(
        press_trigger="high, aggressive press (PPDA 7.9); hunts the ball high",
        build_up="positional via Kimmich/Wirtz; elite codified set-pieces (Buttgereit double-investment, Mittelstädt→Kimmich→Wirtz routine)",
        weak_link="wasteful finishing (conv ~0.79) — volume without conversion; no clear penalty hierarchy post-Kroos; tall CBs vulnerable to low-cross delivery",
    ),
    "Portugal": PhilosophyAnchor(
        press_trigger="balanced press; controls midfield through Vitinha/João Neves",
        build_up="Bruno Fernandes creation + heavy set-piece reliance (29% of xG); MacPhee upgrade, Bruno direct-FK #1",
        weak_link="slow defensive recovery on second balls (lost to FRA EURO24 QF); Ronaldo as #1 penalty despite measurable decline",
    ),
    "Netherlands": PhilosophyAnchor(
        press_trigger="low-medium block (PPDA 15), not a high-pressing side under Koeman",
        build_up="clinical in transition (conv 1.81) + Van Dijk aerial target on inswing corners",
        weak_link="deep-zonal corners cede first contact (2 corner goals conceded EURO24); unresolved Gakpo/Memphis penalty order; Verbruggen weakest top-UEFA shootout keeper",
        note="Most dead-ball-exploitable of the top-UEFA sides.",
    ),
    "Belgium": PhilosophyAnchor(
        press_trigger="low-medium block (PPDA 14.8); aging spine, slow second-ball recovery",
        build_up="De Bruyne creation + Lukaku near-post flicks; clinical on the counter",
        weak_link="aging CB pair + Courtois punching over catching; chained counter-corners exploitable; KDB delivery erratic when not fully fit",
    ),
    "Croatia": PhilosophyAnchor(
        press_trigger="high press built on Modrić/Kovačić midfield control (PPDA 10.8)",
        build_up="midfield possession + Modrić set-piece delivery (22% set-piece xG), far-post header-back routine",
        weak_link="absolute Modrić dependency at 40 — if subbed/injured ~60% of SP threat gone; slow post-corner transition",
        note="SP threat collapses late once Modrić is off → live UNDER goals signal.",
    ),
    "Uruguay": PhilosophyAnchor(
        press_trigger="high, intense man-oriented press (Bielsa, PPDA 10.9)",
        build_up="build through play (Bielsa philosophy), NOT set-pieces — elite aerial talent infra-utilized",
        weak_link="Bielsa man-marking on defensive corners exposed to blocks/picks (known vs Leeds/Athletic); SP offense under-developed vs Araújo/Giménez/Núñez talent",
        note="Bielsa broke Uruguay's set-piece tradition → UNDER corner-goals URU has EV.",
    ),
    "Mexico": PhilosophyAnchor(
        press_trigger="high press under Aguirre (PPDA 11.0)",
        build_up="set-piece-driven early goals (Aguirre cites SP); inswing near→far, Raúl Jiménez target",
        weak_link="very wasteful finishing (conv 0.38); aerial vulnerability vs physical European sides on second balls",
        note="conv 0.38 is a small, poor-xG Copa24 sample — treat with caution.",
    ),
    "USA": PhilosophyAnchor(
        press_trigger="balanced press under Pochettino; backline pace a concern if Robinson absent",
        build_up="Pulisic-led; ELITE Vio set-piece architecture — every corner is code-designed (stack-and-shed)",
        weak_link="wasteful finishing in open play (conv 0.72); second balls post-corner-clear (WC22 NED pattern); CB pace",
        note="Gianni Vio retained — corner markets vs softer CONCACAF backlines are the #1 catalog edge.",
    ),
    "Japan": PhilosophyAnchor(
        press_trigger="low-medium block (PPDA 15.7), disciplined zonal shape (J-League/Bundesliga influence)",
        build_up="clinical transition (conv 1.19) + codified far-post inswinger corners; Kubo direct FK",
        weak_link="small CB pair bullied aerially by physical sides (Iran, Asian Cup); zonal vulnerable to designed near-post traffic blocks",
    ),
    "Senegal": PhilosophyAnchor(
        press_trigger="higher press + verticality under Pape Thiaw (shift from Cissé)",
        build_up="aerial-dominance-driven and vertical; Mané high-leverage set-piece delivery",
        weak_link="aging spine + uncertain CB pairing — if Koulibaly out, the back-post inswinger loses its primary target",
    ),
}


def synthesize_archetype(
    press: PressIntensity,
    set_piece: SetPieceReliance,
    finishing: FinishingProfile,
) -> str:
    """Combine the three data-derived dimensions into a named game-plan.

    Cascade reflects how an analyst reads a team: press_intensity sets the
    control<->react axis, then finishing (the betting-critical efficiency
    signal) and set-piece danger-source refine it. Each label is recognizable
    and maps to a market lean exploited in `read_matchup`.
    """
    if press == "high_press":
        # Proactive teams that dominate territory.
        if finishing == "wasteful":
            # Creates volume, doesn't convert -> opponent-Under / fade their AH.
            return "dominador estéril"
        if set_piece == "set_piece_reliant":
            return "presión + pizarra"
        if finishing == "clinical":
            return "posesión-presión letal"
        return "dominador de posesión"

    if press == "low_block":
        # Reactive teams that cede territory and spring forward.
        if set_piece == "set_piece_reliant":
            return "especialista a balón parado"
        if finishing == "clinical":
            return "contragolpe letal"
        return "muro reactivo"

    # balanced_press: pragmatic, situational.
    if set_piece == "set_piece_reliant":
        return "equilibrado con balón parado"
    if finishing == "wasteful":
        return "equilibrado sin pegada"
    return "pragmático flexible"


@dataclass(frozen=True)
class MatchupRead:
    """Game-plan read of a fixture from two tactical identities.

    This is the bridge from 'how each team plays' to 'which event is most
    likely' — the analyst output, NOT a probability. The dossier turns these
    leans into picks once odds are attached.
    """

    home: TacticalIdentity
    away: TacticalIdentity
    tempo: str               # who dictates territory
    game_shape: str          # open / cagey / territorial
    market_leans: list[str]  # "MARKET — DIRECTION: rationale"
    caveats: list[str]


def _proactivity(press: PressIntensity) -> int:
    return {"high_press": 1, "balanced_press": 0, "low_block": -1}[press]


def read_matchup(home: TacticalIdentity, away: TacticalIdentity) -> MatchupRead:
    """Cross two planteamientos into a game-plan read with market leans."""
    ph, pa = _proactivity(home.press_intensity), _proactivity(away.press_intensity)
    both_high = home.press_intensity == "high_press" and away.press_intensity == "high_press"
    both_low = home.press_intensity == "low_block" and away.press_intensity == "low_block"
    leans: list[str] = []

    # --- Tempo + game shape ---
    if both_high:
        tempo = "ambos presionan: partido de ida y vuelta, nadie cede territorio"
        shape = "abierto"
        leans.append("Over 2.5 — dos presiones altas chocando abren espacios")
        if home.finishing_profile == "clinical" and away.finishing_profile == "clinical":
            leans.append("BTTS Sí — ambos clínicos en juego abierto")
    elif both_low:
        tempo = "ambos esperan: nadie quiere el balón, partido trabado"
        shape = "cerrado"
        leans.append("Under 2.5 — dos bloques bajos, pocas ocasiones claras")
        leans.append("Córners Under — poca presión sostenida")
        leans.append("BTTS No — ambos priorizan no encajar")
    elif ph != pa:
        presser, blocker = (home, away) if ph > pa else (away, home)
        side = "local" if ph > pa else "visitante"
        tempo = f"{presser.team_name} ({side}) dicta el tempo; {blocker.team_name} cede balón y espera la transición"
        shape = "territorial"
        # Sustained pressure forces corners for the presser.
        leans.append(f"Córners {presser.team_name} Over — presión sostenida vs bloque que cede campo")
        if presser.finishing_profile == "wasteful":
            leans.append(f"Under 2.5 — {presser.team_name} domina pero no concreta (dominador estéril)")
            leans.append(f"Cuidado con el AH -1.5 de {presser.team_name}: genera, no mata partidos")
        elif presser.finishing_profile == "clinical":
            leans.append(f"AH -0.5/-1 {presser.team_name} — dominio + pegada vs bloque pasivo")
        if blocker.finishing_profile == "clinical":
            leans.append(f"{blocker.team_name} vivo al contragolpe — no fiar BTTS No a ciegas")
    else:
        tempo = "dos planteamientos flexibles: el contexto (resultado, expulsiones) mandará"
        shape = "equilibrado"

    # --- Set-piece danger source (independent of tempo) ---
    for t, opp in ((home, away), (away, home)):
        if t.set_piece_reliance == "set_piece_reliant":
            extra = " — y será su vía principal si el rival cierra el juego abierto" if opp.press_intensity == "low_block" else ""
            leans.append(f"Balón parado {t.team_name}: amenaza real ({t.set_piece_xg_share:.0%} de su xG){extra}")

    # --- Caveats from confidence + qualitative anchors ---
    caveats: list[str] = []
    for t in (home, away):
        if t.confidence == "red":
            caveats.append(f"{t.team_name}: muestra muy pequeña (n={t.n_matches}) — identidad poco fiable")
        elif t.confidence == "yellow":
            caveats.append(f"{t.team_name}: muestra limitada (n={t.n_matches})")
        if t.anchor and t.anchor.note:
            caveats.append(f"{t.team_name}: {t.anchor.note}")

    return MatchupRead(
        home=home, away=away, tempo=tempo, game_shape=shape,
        market_leans=leans, caveats=caveats,
    )


def derive_tactical_identity(profile: TeamStatsBombProfile) -> TacticalIdentity:
    """Build the full planteamiento for one team from its StatsBomb profile."""
    press = _press_intensity(profile.ppda.mean)
    set_piece = _set_piece_reliance(profile.set_piece_xg_share.mean)
    finishing = _finishing_profile(profile.conversion_rate.mean)
    return TacticalIdentity(
        team_name=profile.team_name,
        n_matches=profile.n_matches,
        confidence=_confidence_for(profile.n_matches),
        press_intensity=press,
        set_piece_reliance=set_piece,
        finishing_profile=finishing,
        ppda=profile.ppda.mean,
        set_piece_xg_share=profile.set_piece_xg_share.mean,
        conversion_rate=profile.conversion_rate.mean,
        archetype=synthesize_archetype(press, set_piece, finishing),
        anchor=PHILOSOPHY_ANCHORS.get(profile.team_name),
    )
