"""League strength multipliers for cross-league rate normalization.

Player per-90 rates are NOT directly comparable across leagues. A 0.5 SoT/90
in EPL implies different attacking quality than 0.5 SoT/90 in MLS — the
defenses being faced are different. The multiplier scales raw rates to an
EPL-equivalent baseline so the lineup blender (Phase 2.2) can sum rates
across teammates from heterogeneous leagues.

Reference league: Premier League (multiplier = 1.0).

Multipliers live in `configs/league_strength.yaml` and are operator-tuned.
Sources to seed from (in order of authority):
  1. Operator domain knowledge (preferred).
  2. Club Elo (clubelo.com) league-aggregate weighted average.
  3. UEFA coefficient ratios.

Lookup is cache-first; missing leagues default to FALLBACK_MULTIPLIER with
a warning logged.
"""

from __future__ import annotations

from pathlib import Path

import structlog
import yaml
from pydantic import BaseModel, ConfigDict, Field

from bip.core.errors import ConfigurationError

logger = structlog.get_logger(__name__)

_CONFIG_PATH = Path(__file__).resolve().parent.parent / "configs" / "league_strength.yaml"

# When a player's club_league_id is not in the multiplier table we fall back
# to this value (a moderately-strong-league assumption) and log a warning.
# Set deliberately conservative so unknown leagues don't inflate predictions.
FALLBACK_MULTIPLIER = 0.70


class LeagueStrength(BaseModel):
    """Multiplier entry for a single league."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    api_football_league_id: int
    name: str
    multiplier: float = Field(ge=0.1, le=1.5)
    confidence: str = Field(pattern=r"^(high|medium|low)$")


class LeagueStrengthTable:
    """In-memory lookup of league_id -> multiplier."""

    def __init__(self, entries: list[LeagueStrength]) -> None:
        self._by_id: dict[int, LeagueStrength] = {e.api_football_league_id: e for e in entries}

    def get(self, league_id: int | None) -> float:
        """Return the multiplier for a league, or FALLBACK_MULTIPLIER if missing."""
        if league_id is None:
            logger.warning("league_strength_missing", league_id=None, fallback=FALLBACK_MULTIPLIER)
            return FALLBACK_MULTIPLIER
        entry = self._by_id.get(league_id)
        if entry is None:
            logger.warning(
                "league_strength_missing",
                league_id=league_id,
                fallback=FALLBACK_MULTIPLIER,
            )
            return FALLBACK_MULTIPLIER
        return entry.multiplier

    def __len__(self) -> int:
        return len(self._by_id)

    def __contains__(self, league_id: int) -> bool:
        return league_id in self._by_id


def load_league_strength(path: Path | None = None) -> LeagueStrengthTable:
    """Load and validate the league_strength.yaml config."""
    target = path if path is not None else _CONFIG_PATH
    if not target.exists():
        raise ConfigurationError(
            f"League strength config not found: {target}. "
            "Run scripts/seed_league_strength.py or populate manually."
        )
    with target.open() as f:
        data = yaml.safe_load(f)

    entries = [LeagueStrength.model_validate(item) for item in data["leagues"]]
    if not any(e.multiplier == 1.0 for e in entries):
        logger.warning(
            "league_strength_no_reference",
            note="No league has multiplier=1.0; ratios are still valid but absolute scale is arbitrary.",
        )
    return LeagueStrengthTable(entries)
