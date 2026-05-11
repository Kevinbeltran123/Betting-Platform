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


class TestScoreExtractionOrderInvariance:
    """Regression for bug 2026-05-11: Sportmonks scores array can be
    non-chronological. Prior _extract_current_score walked all entries
    and overwrote based on iteration order, returning 1ST_HALF score
    even at FT. 66% of Day-1+2 fixtures affected (Randers vs Odense
    stored 0-1 vs real 2-2). Fix filters by type_id, preferring
    CURRENT (1525)."""

    @staticmethod
    def _make_fixture(scores_payload: list[dict]) -> Fixture:
        return Fixture.model_validate({
            "id": 999999, "sport_id": 1, "league_id": 271, "season_id": 1,
            "state": {"id": 5, "state": "FT", "name": "Full Time",
                      "short_name": "FT", "developer_name": "FT"},
            "participants": [
                {"id": 100, "name": "Home FC", "meta": {"location": "home"}},
                {"id": 200, "name": "Away SC", "meta": {"location": "away"}},
            ],
            "scores": scores_payload,
        })

    @staticmethod
    def _s(type_id: int, goals: int, side: str) -> dict:
        return {"id": 1, "fixture_id": 999999, "type_id": type_id,
                "score": {"goals": goals, "participant": side},
                "participant_id": 100 if side == "home" else 200}

    def test_randers_odense_non_chronological_at_ft(self):
        """Real-world Day-2 fixture: 1ST_HALF appears AFTER CURRENT
        in the scores array. Pre-fix returned 0-1 (half-time score).
        Post-fix must return 2-2 (final score, CURRENT type_id=1525)."""
        s = self._s
        fixture = self._make_fixture([
            s(2, 2, "home"),       # 2ND_HALF home
            s(48996, 2, "home"),   # 2ND_HALF_ONLY home
            s(1525, 2, "home"),    # CURRENT home
            s(1, 1, "away"),       # 1ST_HALF away
            s(2, 2, "away"),       # 2ND_HALF away
            s(1, 0, "home"),       # 1ST_HALF home  ← overwrote in old code
            s(1525, 2, "away"),    # CURRENT away
            s(48996, 1, "away"),   # 2ND_HALF_ONLY away ← overwrote in old code
        ])
        state = LiveMatchState.from_fixture(fixture)
        assert (state.home_goals, state.away_goals) == (2, 2)

    def test_current_wins_when_1h_appears_later(self):
        s = self._s
        fixture = self._make_fixture([
            s(1525, 4, "home"), s(1525, 2, "away"),
            s(1, 1, "home"), s(1, 0, "away"),
        ])
        state = LiveMatchState.from_fixture(fixture)
        assert (state.home_goals, state.away_goals) == (4, 2)

    def test_fallback_to_2nd_half_when_no_current(self):
        s = self._s
        fixture = self._make_fixture([
            s(1, 1, "home"), s(1, 0, "away"),
            s(2, 3, "home"), s(2, 2, "away"),
        ])
        state = LiveMatchState.from_fixture(fixture)
        assert (state.home_goals, state.away_goals) == (3, 2)

    def test_fallback_to_1st_half_at_half_time(self):
        s = self._s
        fixture = self._make_fixture([
            s(1, 1, "home"), s(1, 2, "away"),
        ])
        state = LiveMatchState.from_fixture(fixture)
        assert (state.home_goals, state.away_goals) == (1, 2)

    def test_empty_scores_returns_zero(self):
        fixture = self._make_fixture([])
        state = LiveMatchState.from_fixture(fixture)
        assert (state.home_goals, state.away_goals) == (0, 0)
