"""Tests for confederation tilt (Iter 3 + Iter 4 findings)."""
from __future__ import annotations

from bip.evaluation.tournaments.patterns_v2 import (
    CONF_TILT,
    MODERN_WC_PPM,
    confederation_of,
    confederation_tilt_verdict,
)


class TestConfederationOf:
    def test_canonical_team_mapping(self) -> None:
        assert confederation_of("Brazil") == "CONMEBOL"
        assert confederation_of("Argentina") == "CONMEBOL"
        assert confederation_of("France") == "UEFA"
        assert confederation_of("Morocco") == "CAF"
        assert confederation_of("Japan") == "AFC"
        assert confederation_of("USA") == "CONCACAF"
        assert confederation_of("United States") == "CONCACAF"
        assert confederation_of("Côte d'Ivoire") == "CAF"
        assert confederation_of("Ivory Coast") == "CAF"
        assert confederation_of("New Zealand") == "OFC"

    def test_unknown_returns_unk(self) -> None:
        assert confederation_of("Atlantis") == "UNK"


class TestConfTiltHierarchy:
    def test_conmebol_highest(self) -> None:
        # CONMEBOL gets +5% (modern WC dominance)
        assert CONF_TILT["CONMEBOL"] > CONF_TILT["UEFA"]

    def test_concacaf_downgraded(self) -> None:
        # CONCACAF gets -10% (weakest WC conf + WC2026 host blind spot)
        assert CONF_TILT["CONCACAF"] < CONF_TILT["UEFA"]
        assert CONF_TILT["CONCACAF"] == 0.90

    def test_uefa_is_baseline(self) -> None:
        assert CONF_TILT["UEFA"] == 1.00

    def test_unknown_is_neutral(self) -> None:
        assert CONF_TILT["UNK"] == 1.00


class TestModernWcPpm:
    def test_ordering_matches_finding(self) -> None:
        # Hierarchy from iter 4 martj42 n=192 modern WC.
        assert MODERN_WC_PPM["CONMEBOL"] > MODERN_WC_PPM["UEFA"]
        assert MODERN_WC_PPM["UEFA"] > MODERN_WC_PPM["CONCACAF"]
        assert MODERN_WC_PPM["CONCACAF"] > MODERN_WC_PPM["CAF"]
        assert MODERN_WC_PPM["CAF"] > MODERN_WC_PPM["AFC"]


class TestConfederationTiltVerdict:
    def test_brazil_vs_usa_favors_brazil(self) -> None:
        v = confederation_tilt_verdict("Brazil", "USA")
        assert v.home_conf == "CONMEBOL"
        assert v.away_conf == "CONCACAF"
        assert v.home_tilt > v.away_tilt
        # CONMEBOL vs CONCACAF should have meaningful tilt gap
        assert v.home_tilt / v.away_tilt >= 1.10
        assert v.is_cross_conf is True

    def test_argentina_vs_germany_conmebol_lift(self) -> None:
        v = confederation_tilt_verdict("Argentina", "Germany")
        assert v.home_tilt > v.away_tilt  # CONMEBOL > UEFA
        assert v.is_cross_conf is True

    def test_france_vs_spain_same_conf_neutral(self) -> None:
        v = confederation_tilt_verdict("France", "Spain")
        assert v.home_tilt == v.away_tilt
        assert v.is_cross_conf is False
        assert v.edge_threshold_multiplier == 1.00

    def test_wc2026_hosts_get_downgrade(self) -> None:
        # USA at home vs UEFA opponent: USA gets CONCACAF downgrade.
        v = confederation_tilt_verdict("USA", "Spain")
        assert v.home_tilt == 0.90
        assert v.away_tilt == 1.00

    def test_caf_vs_afc_widens_edge_threshold(self) -> None:
        # Predictor's worst-Brier pair from iter 3 (0.317).
        v = confederation_tilt_verdict("Morocco", "Japan")
        assert v.edge_threshold_multiplier >= 1.40

    def test_rationale_cites_conf(self) -> None:
        v = confederation_tilt_verdict("Brazil", "Germany")
        assert "CONMEBOL" in v.rationale
        # UEFA tilt is 1.00 so it should NOT show up as tilt-change rationale
