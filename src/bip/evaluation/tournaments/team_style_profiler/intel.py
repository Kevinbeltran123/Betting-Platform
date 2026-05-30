"""Match Intel assembler — fuses every collected layer into one fixture view
WITHOUT losing anything relevant.

Design (operator directive 2026-05-30: integrate all info, lose NOTHING):
  - Additive & optional: each layer is a section; a missing layer degrades to a
    note, never a fabricated value.
  - Provenance travels: every section keeps its source + confidence.
  - Cross-source links ANNOTATE, never delete: an injured player's prop is
    flagged ⛔, not removed; the full injury list is always shown.
  - Conservative name matching: token-subset or surname+initial; ambiguous →
    abstain and record it (a false link loses more fidelity than no link).

Wraps the existing match_dossier (picks + planteamiento + patterns) untouched
and adds: availability, referee+injury-annotated prop boards, weak-links,
creators, advanced team shape.
"""
from __future__ import annotations

import dataclasses
import unicodedata
from dataclasses import dataclass, field

from bip.evaluation.tournaments.team_style_profiler.advanced_metrics import (
    AdvancedTeamProfile,
)
from bip.evaluation.tournaments.team_style_profiler.match_dossier import MatchDossier
from bip.evaluation.tournaments.team_style_profiler.player_advanced import (
    PlayerAdvancedProfile,
    weak_links,
)
from bip.evaluation.tournaments.team_style_profiler.player_props import (
    PlayerPropProfile,
    PropCandidate,
    prop_board,
)
from bip.evaluation.tournaments.team_style_profiler.referee_tendencies import (
    RefereeTendency,
    apply_referee_to_board,
)


# ── Conservative cross-source name matching (the "lose nothing" crux) ──


def normalize_name(s: str) -> list[str]:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return [t for t in s.lower().replace("-", " ").replace(".", " ").split() if t]


def match_name(target: str, candidates: list[str]) -> str | None:
    """Return the single candidate matching `target`, else None.

    Matches on token-subset (either direction) or surname+first-initial.
    If MORE THAN ONE candidate matches, returns None (abstain — never guess).
    """
    tt = normalize_name(target)
    if not tt:
        return None
    tset = set(tt)
    hits = []
    for c in candidates:
        ct = normalize_name(c)
        if not ct:
            continue
        cset = set(ct)
        subset = tset <= cset or cset <= tset
        surname_initial = tt[-1] == ct[-1] and tt[0][:1] == ct[0][:1]
        if subset or surname_initial:
            hits.append(c)
    return hits[0] if len(hits) == 1 else None


# ── Sections ──


@dataclass(frozen=True)
class Injury:
    name: str
    injury: str
    until: str | None
    ongoing: bool


@dataclass(frozen=True)
class WeakLinkNote:
    team: str
    player: str
    position: str
    reason: str
    kind: str


@dataclass(frozen=True)
class Creator:
    team: str
    player: str
    position: str
    sca_per90: float
    prog_passes_per90: float


@dataclass(frozen=True)
class AdvancedShape:
    team: str
    field_tilt: float
    line_height: float
    directness: float
    gk_goals_prevented: float
    game_state: str          # front-runner / chaser / game-manager / balanced
    read: str                # one-line analyst read


@dataclass(frozen=True)
class MatchIntel:
    dossier: MatchDossier                       # existing picks + planteamiento + patterns
    home_injuries: list[Injury]
    away_injuries: list[Injury]
    home_prop_board: list[PropCandidate]        # referee + injury annotated
    away_prop_board: list[PropCandidate]
    weak_links: list[WeakLinkNote]
    creators: list[Creator]
    home_shape: AdvancedShape | None
    away_shape: AdvancedShape | None
    provenance_notes: list[str] = field(default_factory=list)  # unmatched / missing layers


def _game_state_label(p: AdvancedTeamProfile) -> str:
    if p.xg_share_trailing >= 0.45:
        return "chaser (xG inflado yendo por detrás)"
    if p.xg_share_leading >= 0.38:
        return "front-runner (sigue creando con ventaja)"
    if p.xg_share_level >= 0.45:
        return "game-manager (vive en el empate)"
    return "equilibrado"


def _shape(p: AdvancedTeamProfile | None) -> AdvancedShape | None:
    if p is None:
        return None
    gs = _game_state_label(p)
    line = "línea alta" if p.line_height.mean >= 42 else "bloque profundo" if p.line_height.mean <= 33 else "línea media"
    direct = "directo" if p.directness.mean >= 0.25 else "posesión corta" if p.directness.mean <= 0.17 else "mixto"
    read = f"{line}, {direct}; {gs}"
    return AdvancedShape(
        team=p.team, field_tilt=p.field_tilt.mean, line_height=p.line_height.mean,
        directness=p.directness.mean, gk_goals_prevented=p.gk_goals_prevented_per_match.mean,
        game_state=gs, read=read)


def _annotated_board(
    props: list[PlayerPropProfile], team: str,
    referee: RefereeTendency | None, injuries: list[Injury],
) -> tuple[list[PropCandidate], list[str]]:
    """Build a team's prop board; annotate (never drop) referee + injuries."""
    board = [dataclasses.replace(c, team=team) for c in prop_board(props)]
    board = apply_referee_to_board(board, referee)   # preserves team/flag via replace
    inj_names = [i.name for i in injuries]
    out: list[PropCandidate] = []
    matched: set[str] = set()
    for c in board:
        m = match_name(c.player_name, inj_names)
        if m is not None:
            inj = next(i for i in injuries if i.name == m)
            until = f"hasta {inj.until}" if inj.until else "sin fecha de vuelta"
            out.append(dataclasses.replace(
                c, flag=f"⛔ LESIONADO: {inj.injury} ({until}) — NO apostar"))
            matched.add(m)
        else:
            out.append(c)
    notes = [f"{team}: lesionado {i.name} ({i.injury}) no está en el prop board "
             f"(sin perfil de stats) — revisar aparte"
             for i in injuries if i.name not in matched]
    return out, notes


def assemble_intel(
    dossier: MatchDossier,
    *,
    home_props: list[PlayerPropProfile] | None = None,
    away_props: list[PlayerPropProfile] | None = None,
    home_advanced: list[PlayerAdvancedProfile] | None = None,
    away_advanced: list[PlayerAdvancedProfile] | None = None,
    home_team_adv: AdvancedTeamProfile | None = None,
    away_team_adv: AdvancedTeamProfile | None = None,
    home_injuries: list[Injury] | None = None,
    away_injuries: list[Injury] | None = None,
    referee: RefereeTendency | None = None,
) -> MatchIntel:
    ctx = dossier.context
    home_props = home_props or []
    away_props = away_props or []
    home_injuries = home_injuries or []
    away_injuries = away_injuries or []
    notes: list[str] = []

    hb, hn = _annotated_board(home_props, ctx.home_team, referee, home_injuries)
    ab, an = _annotated_board(away_props, ctx.away_team, referee, away_injuries)
    notes.extend(hn)
    notes.extend(an)

    wl: list[WeakLinkNote] = []
    creators: list[Creator] = []
    for team, adv in ((ctx.home_team, home_advanced), (ctx.away_team, away_advanced)):
        if not adv:
            notes.append(f"{team}: sin métricas avanzadas de jugador (no en StatsBomb)")
            continue
        for w in weak_links(adv):
            wl.append(WeakLinkNote(team=team, player=w["player"], position=w["position"],
                                   reason=w["reason"], kind=w["kind"]))
        for p in sorted([x for x in adv if x.confidence in ("green", "yellow")],
                        key=lambda x: -x.sca_per90.mean)[:3]:
            creators.append(Creator(team=team, player=p.player_name, position=p.position,
                                    sca_per90=p.sca_per90.mean,
                                    prog_passes_per90=p.prog_passes_per90.mean))

    if referee is None:
        notes.append("Árbitro no asignado (FIFA designa por ronda) — board sin tilt de tarjetas")

    return MatchIntel(
        dossier=dossier, home_injuries=home_injuries, away_injuries=away_injuries,
        home_prop_board=hb, away_prop_board=ab, weak_links=wl, creators=creators,
        home_shape=_shape(home_team_adv), away_shape=_shape(away_team_adv),
        provenance_notes=notes,
    )


# ── Render: existing dossier + the fused intel sections ──


def _shape_lines(s: AdvancedShape | None, name: str) -> list[str]:
    if s is None:
        return [f"- **{name}:** *sin forma avanzada (no en StatsBomb)*"]
    return [
        f"- **{name}:** {s.read}",
        f"  - field tilt {s.field_tilt:.0%} · línea x={s.line_height:.0f} · "
        f"{s.directness:.0%} pases largos · GK {s.gk_goals_prevented:+.2f}/p",
    ]


def render_intel_markdown(intel: MatchIntel) -> str:
    from bip.evaluation.tournaments.team_style_profiler.dossier_renderer import (
        render_markdown,
    )

    out = [render_markdown(intel.dossier), "", "---", "", "## §4. Disponibilidad (Transfermarkt)", ""]
    ctx = intel.dossier.context
    for name, inj in ((ctx.home_team, intel.home_injuries), (ctx.away_team, intel.away_injuries)):
        if inj:
            out.append(f"**{name} — {len(inj)} baja(s):**")
            for i in inj:
                until = f"hasta {i.until}" if i.until else "sin fecha de vuelta"
                out.append(f"- ⛔ {i.name}: {i.injury} ({until})")
        else:
            out.append(f"**{name}:** sin bajas reportadas / no recolectado")
        out.append("")

    out += ["---", "", "## §5. Forma avanzada de equipo (StatsBomb)", ""]
    out += _shape_lines(intel.home_shape, ctx.home_team)
    out += _shape_lines(intel.away_shape, ctx.away_team)

    out += ["", "---", "", "## §6. Inteligencia de jugador", "", "### Prop board (softest-first)"]
    for name, board in ((ctx.home_team, intel.home_prop_board), (ctx.away_team, intel.away_prop_board)):
        out.append(f"\n**{name}:**")
        if not board:
            out.append("- *(sin perfil de props)*")
        for c in board:
            soft = {1: "SOFT", 2: "med", 3: "hard"}.get(c.softness, "?")
            flag = f"  {c.flag}" if c.flag else ""
            out.append(f"- [{soft}] {c.market} — {c.player_name}: {c.stat}{flag}")

    if intel.weak_links:
        out += ["", "### Eslabones débiles (a atacar)"]
        for w in intel.weak_links:
            out.append(f"- {w.team}: **{w.player}** ({w.position}) — {w.reason}")
    if intel.creators:
        out += ["", "### Creadores (SCA/90)"]
        for c in intel.creators:
            out.append(f"- {c.team}: **{c.player}** {c.sca_per90:.1f} SCA, {c.prog_passes_per90:.0f} prog-pass")

    if intel.provenance_notes:
        out += ["", "---", "", "## §7. Procedencia / cobertura", ""]
        for n in intel.provenance_notes:
            out.append(f"- {n}")

    return "\n".join(out)
