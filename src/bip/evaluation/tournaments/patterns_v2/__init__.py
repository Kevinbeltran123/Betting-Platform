"""Patterns v2 — runtime modules derived from session-1 EDA findings.

See ``Papers/WC2026_HISTORICAL_PATTERNS_V2.md`` and
``Papers/INTERNATIONAL_ANALYST_RESEARCH.md`` for the empirical evidence
behind each module.

Modules:
- ``host_nation_filter`` — applies confidence downgrade when tournament host
  participates in a fixture (L5.6, p=0.0065, 3.32x worst-decile over-rep).
- ``ht_live_rules`` — empirical lookup table for live picks conditioned on
  HT scoreline and favorite identity (Lens 3 favorite-stratified matrix,
  n=255 fav-defined).
- ``regime_warning`` — flags fixtures that may exhibit the modern-vs-classic
  regime shift (L3.1, P(fav wins | HT 0-0) drops 62%->41% post-2022).
- ``confederation_tilt`` / ``team_transfer_filter`` — confederation and
  team-level transfer signals.
- ``venues_wc2026`` — WC2026 venue metadata (altitude, climate, timezone).
- ``heat_venue_filter`` — Mohr 2012 + Nature SR 2024; daytime kickoffs
  in Dallas / Houston / Monterrey trigger UNDER goals + UNDER corners tilt.
- ``altitude_verdict`` — FIFA 2010 + Apunts 2022; Guadalajara 1566m and
  Mexico City 2240m trigger home edge against unacclimatized visitors.
- ``travel_jetlag_verdict`` — Janse van Rensburg 2021 + Fowler 2014/2017;
  eastward travel ≥2 zones with <recovery flags affected side.
"""

from bip.evaluation.tournaments.patterns_v2.altitude_verdict import (
    ACCLIMATIZED_TEAMS,
    ALTITUDE_HOME_EDGE_GOALS_PER_1000M,
    ALTITUDE_THRESHOLD_M,
    AltitudeVerdict,
    altitude_verdict,
)
from bip.evaluation.tournaments.patterns_v2.confederation_tilt import (
    CONF_TILT,
    MODERN_WC_PPM,
    PAIR_UNCERTAINTY,
    ConfederationTiltVerdict,
    confederation_of,
    confederation_tilt_verdict,
)
from bip.evaluation.tournaments.patterns_v2.heat_venue_filter import (
    HEAT_KICKOFF_DAYTIME_END_H,
    HEAT_KICKOFF_DAYTIME_START_H,
    HEAT_TILT_HOT,
    HEAT_TILT_NONE,
    HEAT_TILT_VERY_HOT,
    HeatVenueVerdict,
    heat_venue_verdict,
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
from bip.evaluation.tournaments.patterns_v2.travel_jetlag_verdict import (
    EASTWARD_PENALTY_MULTIPLIER,
    JETLAG_DAYS_PER_ZONE,
    JETLAG_ZONE_THRESHOLD,
    TravelJetlagVerdict,
    travel_jetlag_verdict,
)
from bip.evaluation.tournaments.patterns_v2.venues_wc2026 import (
    HIGH_ALTITUDE_VENUES,
    HOT_VENUES,
    VENUES_WC2026,
    VERY_HOT_VENUES,
    Venue,
    venue_by_slug,
)

__all__ = [
    "ACCLIMATIZED_TEAMS",
    "ALTITUDE_HOME_EDGE_GOALS_PER_1000M",
    "ALTITUDE_THRESHOLD_M",
    "AltitudeVerdict",
    "CONF_TILT",
    "EASTWARD_PENALTY_MULTIPLIER",
    "HEAT_KICKOFF_DAYTIME_END_H",
    "HEAT_KICKOFF_DAYTIME_START_H",
    "HEAT_TILT_HOT",
    "HEAT_TILT_NONE",
    "HEAT_TILT_VERY_HOT",
    "HIGH_ALTITUDE_VENUES",
    "HOST_DOWNGRADE_FACTOR",
    "HOST_NATIONS",
    "HOT_VENUES",
    "HT_LIVE_TABLE",
    "HeatVenueVerdict",
    "JETLAG_DAYS_PER_ZONE",
    "JETLAG_ZONE_THRESHOLD",
    "MODERN_WC_PPM",
    "PAIR_UNCERTAINTY",
    "TEAM_TRANSFER_TILT",
    "TravelJetlagVerdict",
    "VENUES_WC2026",
    "VERY_HOT_VENUES",
    "Venue",
    "ConfederationTiltVerdict",
    "HostNationVerdict",
    "HTLiveVerdict",
    "RegimeWarning",
    "TeamTransferVerdict",
    "altitude_verdict",
    "confederation_of",
    "confederation_tilt_verdict",
    "heat_venue_verdict",
    "host_nation_in_fixture",
    "host_nation_verdict",
    "ht_live_lookup",
    "regime_warning_for_fixture",
    "team_transfer_verdict",
    "travel_jetlag_verdict",
    "venue_by_slug",
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
