"""Phase 02.1 Wave 0 stub — filled in by plan 02.1-05.

D-04: ParquetStore.write_results / read_results / write_odds / read_odds
with 3-level Hive partitioning (sport/league/season; NO matchday).
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.skip(
    reason="Phase 02.1 Wave 0 stub — plan 02.1-05 implements results/odds round-trip tests"
)


def test_round_trip_results():
    pass


def test_round_trip_odds():
    pass


def test_results_is_3_level_not_4_level():
    pass


def test_odds_is_3_level_not_4_level():
    pass
