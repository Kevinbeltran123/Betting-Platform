"""Confederation tilt — Iter 3 + Iter 4 findings.

EVIDENCE.
  Iter 3 (StatsBomb n=128 WC18+WC22): CONMEBOL ppm 1.74, UEFA 1.57, CAF 1.11,
    AFC 1.03, CONCACAF 0.83. CONMEBOL > UEFA at WC level.
  Iter 4 (martj42 n=192 modern WC >=2012): CONMEBOL ppm 1.80, UEFA 1.60,
    CONCACAF 1.00, CAF 0.98, AFC 0.84. Same ordering. Modern CONMEBOL vs UEFA
    head-to-head: 43.24% / 24.32% / 32.43% (CONMEBOL wins more).
  Time-stable hierarchy: ordering identical pre-2012 vs post-2012.

WHY. Lock_v1's strength prior over martj42 + StatsBomb blends decades of
matches. The Bradley-Terry equivalent under-weights CONMEBOL's recent
dominance in WC-specific matches. CONCACAF gets a slight over-rate
because (a) home-advantage in CONCACAF qualifying inflates ppm,
(b) USA/Mexico/Canada will host WC2026 and lock_v1 lacks host feature.

APPLICATION. Tilt the predictor-implied probability based on confederation
matchup. Magnitudes are calibrated to the observed empirical gap.

NOT a fixed delta — a multiplicative factor on the team's strength.
Caps applied to avoid runaway tilts on extreme matchups.
"""
from __future__ import annotations

from dataclasses import dataclass


# Empirical ppm per confederation in modern WC (>= 2012, martj42 n=192).
# Used as the relative scale for tilt magnitudes.
MODERN_WC_PPM: dict[str, float] = {
    "CONMEBOL": 1.797,
    "UEFA": 1.600,
    "CONCACAF": 1.000,
    "CAF": 0.981,
    "AFC": 0.837,
    "OFC": 0.500,  # very low n; effectively lowest
}

# Confederation tilt factor — multiplier on lock_v1's implied team-win
# probability. Calibrated such that:
#   - CONMEBOL gets a +5% lift (it's the dominant WC conf, under-priced by
#     UEFA-dominant priors)
#   - CONCACAF gets a -10% downgrade (combined with host-nation finding)
#   - AFC/CAF/OFC neutral-to-slight-downgrade
# The base value (UEFA = 1.00) is the reference.
CONF_TILT: dict[str, float] = {
    "CONMEBOL": 1.05,
    "UEFA": 1.00,
    "CAF": 0.97,
    "AFC": 0.95,
    "CONCACAF": 0.90,
    "OFC": 0.85,
    "UNK": 1.00,  # neutral when conf is missing
}

# Per-pair predictor reliability (Brier from walk-forward backtest n=199).
# Higher Brier => less reliable predictor => widen edge threshold.
# Brier_threshold * pair_uncertainty_factor = effective edge threshold.
PAIR_UNCERTAINTY: dict[frozenset[str], float] = {
    # Most reliable (Brier <= 0.15) — narrow threshold
    frozenset({"CONMEBOL", "UEFA"}): 1.00,
    frozenset({"CONMEBOL", "CAF"}): 1.00,
    # Moderate (0.15 < Brier <= 0.20)
    frozenset({"AFC", "UEFA"}): 1.10,
    # Worst (Brier > 0.20) — widen edge threshold materially
    frozenset({"CAF", "UEFA"}): 1.20,
    frozenset({"CONMEBOL", "AFC"}): 1.20,
    frozenset({"CONCACAF", "UEFA"}): 1.25,
    frozenset({"CAF", "AFC"}): 1.40,  # Brier 0.317 — worst observed
}


CONFEDERATION_BY_TEAM: dict[str, str] = {
    # Same canonical list as iter 3 — single source of truth.
    "France": "UEFA", "Germany": "UEFA", "England": "UEFA", "Spain": "UEFA",
    "Italy": "UEFA", "Portugal": "UEFA", "Netherlands": "UEFA",
    "Belgium": "UEFA", "Croatia": "UEFA", "Switzerland": "UEFA",
    "Denmark": "UEFA", "Sweden": "UEFA", "Poland": "UEFA",
    "Russia": "UEFA", "Wales": "UEFA", "Iceland": "UEFA",
    "Serbia": "UEFA", "Ukraine": "UEFA", "Austria": "UEFA",
    "Czech Republic": "UEFA", "Slovakia": "UEFA", "Romania": "UEFA",
    "Republic of Ireland": "UEFA", "Northern Ireland": "UEFA",
    "Hungary": "UEFA", "Turkey": "UEFA", "Greece": "UEFA",
    "Scotland": "UEFA", "Albania": "UEFA", "Finland": "UEFA",
    "North Macedonia": "UEFA", "Norway": "UEFA", "Slovenia": "UEFA",
    "Georgia": "UEFA",
    "Brazil": "CONMEBOL", "Argentina": "CONMEBOL", "Uruguay": "CONMEBOL",
    "Colombia": "CONMEBOL", "Chile": "CONMEBOL", "Peru": "CONMEBOL",
    "Ecuador": "CONMEBOL", "Paraguay": "CONMEBOL", "Bolivia": "CONMEBOL",
    "Venezuela": "CONMEBOL",
    "Morocco": "CAF", "Senegal": "CAF", "Egypt": "CAF", "Algeria": "CAF",
    "Tunisia": "CAF", "Ghana": "CAF", "Nigeria": "CAF",
    "Côte d'Ivoire": "CAF", "Ivory Coast": "CAF",
    "Cameroon": "CAF", "South Africa": "CAF", "Mali": "CAF",
    "Burkina Faso": "CAF", "DR Congo": "CAF", "Cape Verde": "CAF",
    "Equatorial Guinea": "CAF", "Gabon": "CAF",
    "Japan": "AFC", "South Korea": "AFC", "Korea Republic": "AFC",
    "Saudi Arabia": "AFC", "Iran": "AFC", "Australia": "AFC", "Qatar": "AFC",
    "USA": "CONCACAF", "United States": "CONCACAF", "Mexico": "CONCACAF",
    "Canada": "CONCACAF", "Costa Rica": "CONCACAF", "Panama": "CONCACAF",
    "Honduras": "CONCACAF", "Jamaica": "CONCACAF",
    "New Zealand": "OFC",
}


def confederation_of(team: str) -> str:
    return CONFEDERATION_BY_TEAM.get(team, "UNK")


@dataclass(frozen=True)
class ConfederationTiltVerdict:
    home_team: str
    away_team: str
    home_conf: str
    away_conf: str
    home_tilt: float
    """Multiplier on home team's implied win prob."""
    away_tilt: float
    is_cross_conf: bool
    edge_threshold_multiplier: float
    """Multiplier on the configured edge threshold."""
    rationale: str


def confederation_tilt_verdict(
    home_team: str, away_team: str
) -> ConfederationTiltVerdict:
    """Returns confederation-based tilts and edge-threshold widening.

    Use case:
      - Multiply each team's lock_v1 implied probability by its tilt.
      - Multiply the operator-configured edge threshold by the pair
        uncertainty factor before checking edge >= threshold.

    >>> v = confederation_tilt_verdict("Brazil", "USA")
    >>> v.home_tilt > v.away_tilt
    True
    >>> v.is_cross_conf
    True
    """
    h_conf = confederation_of(home_team)
    a_conf = confederation_of(away_team)
    h_tilt = CONF_TILT.get(h_conf, 1.0)
    a_tilt = CONF_TILT.get(a_conf, 1.0)
    is_cross = h_conf != a_conf and h_conf != "UNK" and a_conf != "UNK"
    pair_key = frozenset({h_conf, a_conf})
    edge_mult = PAIR_UNCERTAINTY.get(pair_key, 1.05 if is_cross else 1.00)

    rationale_parts = []
    if h_tilt != 1.0:
        delta_pct = (h_tilt - 1.0) * 100
        rationale_parts.append(
            f"home {h_conf} {delta_pct:+.0f}% tilt (modern WC ppm = "
            f"{MODERN_WC_PPM.get(h_conf, '?')})"
        )
    if a_tilt != 1.0:
        delta_pct = (a_tilt - 1.0) * 100
        rationale_parts.append(
            f"away {a_conf} {delta_pct:+.0f}% tilt (modern WC ppm = "
            f"{MODERN_WC_PPM.get(a_conf, '?')})"
        )
    if edge_mult > 1.0:
        rationale_parts.append(
            f"pair {h_conf}x{a_conf} requires {edge_mult:.2f}x edge "
            f"(predictor Brier-based reliability)"
        )

    return ConfederationTiltVerdict(
        home_team=home_team,
        away_team=away_team,
        home_conf=h_conf,
        away_conf=a_conf,
        home_tilt=h_tilt,
        away_tilt=a_tilt,
        is_cross_conf=is_cross,
        edge_threshold_multiplier=edge_mult,
        rationale="; ".join(rationale_parts) if rationale_parts else "neutral",
    )
