"""Referee tendency table — discipline rates for international referees.

The highest-ROI new signal for the player-prop board: referee identity drives
the cards/fouls markets (the softest, least-modeled props) more than team
discipline does. Built 100% offline from StatsBomb match metadata (313/314
cached matches carry a `referee`), which is exactly the elite-international
referee pool that officiates the World Cup (Turpin, Oliver, Orsato, Marciniak…).

OPERATIONAL MODEL: FIFA assigns WC2026 referees per-round during the tournament.
When a referee is announced, look them up (`referee_for`) and apply their tilt
to the prop board's soft markets (`apply_referee_to_board`).

Thresholds are empirical terciles across the 29 referees with >=4 cached
matches (2026-05-30).
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Literal

import numpy as np

from bip.evaluation.tournaments.team_style_profiler.player_props import PropCandidate
from bip.evaluation.tournaments.team_style_profiler.tsv_schema import DistributionStat

# Empirical terciles of cards/match across international refs (n>=4), 2026-05-30.
CARDS_STRICT_MIN = 3.8     # p67: >=3.8 cards/match -> strict
CARDS_LENIENT_MAX = 3.2    # p33: <=3.2 cards/match -> lenient

N_GREEN_MIN = 8
N_YELLOW_MIN = 4

Strictness = Literal["strict", "average", "lenient"]
RefConfidence = Literal["green", "yellow", "red"]

_YELLOW_CARDS = {"Yellow Card", "Second Yellow"}
_RED_CARDS = {"Red Card", "Second Yellow"}


@dataclass(frozen=True)
class MatchDiscipline:
    """Both-teams discipline totals for a single match."""

    yellows: int
    reds: int
    fouls: int
    penalties: int


@dataclass(frozen=True)
class RefereeTendency:
    referee_name: str
    country: str
    n_matches: int
    confidence: RefConfidence
    strictness: Strictness

    cards_per_match: DistributionStat   # yellows + reds shown
    yellows_per_match: DistributionStat
    reds_per_match: DistributionStat
    fouls_per_match: DistributionStat
    penalties_per_match: DistributionStat


def parse_match_discipline(events: list[dict]) -> MatchDiscipline:
    yellows = reds = fouls = penalties = 0
    for e in events:
        t = (e.get("type") or {}).get("name")
        card = (
            ((e.get("foul_committed") or {}).get("card") or {}).get("name")
            or ((e.get("bad_behaviour") or {}).get("card") or {}).get("name")
        )
        if card in _YELLOW_CARDS:
            yellows += 1
        if card in _RED_CARDS:
            reds += 1
        if t == "Foul Committed":
            fouls += 1
        if t == "Shot" and (e.get("shot") or {}).get("type", {}).get("name") == "Penalty":
            penalties += 1
    return MatchDiscipline(yellows=yellows, reds=reds, fouls=fouls, penalties=penalties)


def _confidence_for(n: int) -> RefConfidence:
    if n >= N_GREEN_MIN:
        return "green"
    if n >= N_YELLOW_MIN:
        return "yellow"
    return "red"


def _strictness(cards_per_match: float) -> Strictness:
    if cards_per_match >= CARDS_STRICT_MIN:
        return "strict"
    if cards_per_match <= CARDS_LENIENT_MAX:
        return "lenient"
    return "average"


def _bootstrap_mean(values: list[float], n_boot: int = 2000, seed: int = 42) -> DistributionStat:
    n = len(values)
    if n == 0:
        return DistributionStat(mean=0.0, ci_low=0.0, ci_high=0.0, n=0)
    arr = np.array(values, dtype=float)
    rng = np.random.default_rng(seed)
    boots = arr[rng.integers(0, n, size=(n_boot, n))].mean(axis=1)
    return DistributionStat(
        mean=float(arr.mean()),
        ci_low=float(np.percentile(boots, 2.5)),
        ci_high=float(np.percentile(boots, 97.5)),
        n=n,
    )


def build_referee_tendencies(
    per_ref: dict[str, tuple[str, list[MatchDiscipline]]],
) -> dict[str, RefereeTendency]:
    """Aggregate per-referee match discipline into tendencies.

    per_ref maps referee_name -> (country, [MatchDiscipline, ...]).
    """
    out: dict[str, RefereeTendency] = {}
    for name, (country, matches) in per_ref.items():
        if not matches:
            continue
        cards = _bootstrap_mean([m.yellows + m.reds for m in matches])
        out[name] = RefereeTendency(
            referee_name=name,
            country=country,
            n_matches=len(matches),
            confidence=_confidence_for(len(matches)),
            strictness=_strictness(cards.mean),
            cards_per_match=cards,
            yellows_per_match=_bootstrap_mean([m.yellows for m in matches]),
            reds_per_match=_bootstrap_mean([float(m.reds) for m in matches]),
            fouls_per_match=_bootstrap_mean([float(m.fouls) for m in matches]),
            penalties_per_match=_bootstrap_mean([float(m.penalties) for m in matches]),
        )
    return out


def referee_for(
    name: str, table: dict[str, RefereeTendency]
) -> RefereeTendency | None:
    """Exact-name lookup (FIFA publishes referee names per round)."""
    return table.get(name)


def apply_referee_to_board(
    board: list[PropCandidate], ref: RefereeTendency | None
) -> list[PropCandidate]:
    """Annotate the soft (fouls/cards) prop candidates with referee context.

    This is the edge cross: a high-foul player under a STRICT referee is the
    bettable card/foul signal; under a LENIENT referee the same player's prop
    should be attenuated. Only touches softness==1 markets (fouls/cards).
    """
    if ref is None:
        return board
    if ref.strictness == "strict":
        tag = f"✓ árbitro estricto ({ref.referee_name}, {ref.cards_per_match.mean:.1f} tarj/p) — refuerza"
    elif ref.strictness == "lenient":
        tag = f"⚠ árbitro permisivo ({ref.referee_name}, {ref.cards_per_match.mean:.1f} tarj/p) — atenúa"
    else:
        tag = f"árbitro promedio ({ref.referee_name}, {ref.cards_per_match.mean:.1f} tarj/p)"
    import dataclasses
    out: list[PropCandidate] = []
    for c in board:
        if c.softness == 1:
            out.append(dataclasses.replace(c, stat=f"{c.stat} · {tag}"))
        else:
            out.append(c)
    return out
