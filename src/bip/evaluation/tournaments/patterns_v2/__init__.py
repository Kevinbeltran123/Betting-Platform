"""Patterns v2 — runtime modules derived from session-1 EDA findings.

See ``Papers/WC2026_HISTORICAL_PATTERNS_V2.md`` for the empirical evidence
behind each module.

Modules:
- ``host_nation_filter`` — applies confidence downgrade when tournament host
  participates in a fixture (L5.6, p=0.0065, 3.32x worst-decile over-rep).
- ``ht_live_rules`` — empirical lookup table for live picks conditioned on
  HT scoreline and favorite identity (Lens 3 favorite-stratified matrix,
  n=255 fav-defined).
- ``regime_warning`` — flags fixtures that may exhibit the modern-vs-classic
  regime shift (L3.1, P(fav wins | HT 0-0) drops 62%->41% post-2022).
"""

from bip.evaluation.tournaments.patterns_v2.confederation_tilt import (
    CONF_TILT,
    MODERN_WC_PPM,
    PAIR_UNCERTAINTY,
    ConfederationTiltVerdict,
    confederation_of,
    confederation_tilt_verdict,
)
from bip.evaluation.tournaments.patterns_v2.host_nation_filter import (
    HOST_DOWNGRADE_FACTOR,
    HostNationVerdict,
    host_nation_in_fixture,
    host_nation_verdict,
)
from bip.evaluation.tournaments.patterns_v2.ht_live_rules import (
    HT_LIVE_TABLE,
    HTLiveVerdict,
    ht_live_lookup,
)
from bip.evaluation.tournaments.patterns_v2.regime_warning import (
    RegimeWarning,
    regime_warning_for_fixture,
)
from bip.evaluation.tournaments.patterns_v2.team_transfer_filter import (
    TEAM_TRANSFER_TILT,
    TeamTransferVerdict,
    team_transfer_verdict,
)

__all__ = [
    "CONF_TILT",
    "HOST_DOWNGRADE_FACTOR",
    "HOST_NATIONS",
    "HT_LIVE_TABLE",
    "MODERN_WC_PPM",
    "PAIR_UNCERTAINTY",
    "TEAM_TRANSFER_TILT",
    "ConfederationTiltVerdict",
    "HostNationVerdict",
    "HTLiveVerdict",
    "RegimeWarning",
    "TeamTransferVerdict",
    "confederation_of",
    "confederation_tilt_verdict",
    "host_nation_in_fixture",
    "host_nation_verdict",
    "ht_live_lookup",
    "regime_warning_for_fixture",
    "team_transfer_verdict",
]

# Tournament -> set of host nation team names (canonical English names).
# Sourced from FIFA / CAF / UEFA / CONMEBOL official records.
# WC 2026 is the operational target — USA / Mexico / Canada host.
HOST_NATIONS: dict[str, frozenset[str]] = {
    "wc_2018": frozenset({"Russia"}),
    "euro_2020": frozenset(),  # 11-city distributed, no single host
    "wc_2022": frozenset({"Qatar"}),
    "afcon_2023": frozenset({"Côte d'Ivoire", "Ivory Coast"}),
    "copa_2024": frozenset(),  # USA hosted but Copa-style — non-FIFA-host context
    "euro_2024": frozenset({"Germany"}),
    "world_cup_2026": frozenset({"USA", "United States", "Mexico", "Canada"}),
}
