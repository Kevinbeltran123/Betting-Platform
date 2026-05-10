"""Layer-1 tests for LiveMatchState.from_fixture()."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from bip.evaluation.live.match_state import LiveMatchState
from bip.sports.football.sportmonks.schemas import Fixture
from bip.sports.football.sportmonks.types import StatType

RECON_DIR = Path(__file__).resolve().parent.parent.parent.parent \
    / "data" / "cache" / "sportmonks" / "recon"


pytestmark = pytest.mark.skipif(
    not (RECON_DIR / "21_live_high_value.json").exists(),
    reason="Sportmonks recon fixture missing — run reconnaissance first.",
)


@pytest.fixture
def fixture() -> Fixture:
    raw = json.loads((RECON_DIR / "21_live_high_value.json").read_text())
    return Fixture.model_validate(raw["data"])


class TestStateConstruction:
    def test_basic_fields(self, fixture: Fixture):
        state = LiveMatchState.from_fixture(fixture)
        assert state.fixture_id == fixture.id
        assert state.home_team_id != state.away_team_id
        assert state.home_team_name and state.away_team_name

    def test_score_extraction(self, fixture: Fixture):
        state = LiveMatchState.from_fixture(fixture)
        assert state.home_goals >= 0
        assert state.away_goals >= 0

    def test_minute_in_valid_range(self, fixture: Fixture):
        state = LiveMatchState.from_fixture(fixture)
        assert 0 <= state.minute <= 130  # incl. extra time

    def test_stats_indexed_by_type_id(self, fixture: Fixture):
        state = LiveMatchState.from_fixture(fixture)
        # The recon fixture has 80 stats — both teams should have most types
        assert len(state.home_stats) > 10
        assert len(state.away_stats) > 10
        # Possession should be present
        assert StatType.BALL_POSSESSION in state.home_stats
        assert StatType.BALL_POSSESSION in state.away_stats

    def test_predictions_indexed(self, fixture: Fixture):
        state = LiveMatchState.from_fixture(fixture)
        # The recon fixture has 29 predictions; verify indexing works
        assert len(state.sportmonks_predictions) > 5


class TestDerivedSignals:
    def test_xg_proxy_non_negative(self, fixture: Fixture):
        state = LiveMatchState.from_fixture(fixture)
        assert state.home_shot_quality_xg_proxy >= 0
        assert state.away_shot_quality_xg_proxy >= 0

    def test_pressure_avg_in_range(self, fixture: Fixture):
        state = LiveMatchState.from_fixture(fixture)
        # Pressure 0-100 → avg should also be in that range
        assert 0 <= state.home_pressure_avg <= 100
        assert 0 <= state.away_pressure_avg <= 100

    def test_remaining_minutes_consistent(self, fixture: Fixture):
        state = LiveMatchState.from_fixture(fixture)
        if state.minute >= 90:
            assert state.remaining_minutes == 0
        else:
            assert state.remaining_minutes == 90 - state.minute

    def test_score_diff(self, fixture: Fixture):
        state = LiveMatchState.from_fixture(fixture)
        assert state.score_diff_home == state.home_goals - state.away_goals
