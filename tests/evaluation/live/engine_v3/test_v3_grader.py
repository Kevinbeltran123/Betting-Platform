"""Tests for the v3 outcome grader.

The grader is the bridge between v3 shadow picks (with v3-specific
market_id strings + bookmaker_odd + activated_at_minute) and the
existing FinalOutcome / grade_pick infrastructure from grading.py.

Covers:
- grade_v3_pick maps each family correctly: goals, btts, corners,
  cards, 1X2, next_goal.
- _grade_next_goal handles "no more goals" + directional cases.
- profit_units_for / status_for produce correct accounting.
- Batch grading: end-to-end with a mock Sportmonks client returning
  a synthesized fixture, verifies the outcomes parquet round-trips.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import polars as pl
import pytest

from bip.evaluation.live.engine_v3.runtime.v3_grader import (
    GradeReport,
    GradedPick,
    _grade_next_goal,
    grade_picks_for_date,
    grade_v3_pick,
    profit_units_for,
    status_for,
    write_outcomes_parquet,
)
from bip.evaluation.live.grading import FinalOutcome


@pytest.fixture
def anyio_backend():
    return "asyncio"


HOME_ID, AWAY_ID = 100, 200


def _outcome(
    *,
    home_goals: int = 1,
    away_goals: int = 0,
    home_1h: int = 0,
    away_1h: int = 0,
    cards: int = 3,
    corners: int = 9,
    goal_events: tuple = (),
) -> FinalOutcome:
    return FinalOutcome(
        fixture_id=12345,
        league_id=564,
        home_goals=home_goals,
        away_goals=away_goals,
        home_goals_first_half=home_1h,
        away_goals_first_half=away_1h,
        total_cards=cards,
        total_corners=corners,
        is_finished=True,
        goal_events=goal_events,
        home_team_id=HOME_ID,
        away_team_id=AWAY_ID,
    )


def _pick_row(
    *,
    family: str,
    market_id: str,
    direction: str,
    line_value: float | None = None,
    activated_at_minute: int = 30,
    bookmaker_odd: float | None = 2.0,
) -> dict[str, Any]:
    return {
        "fixture_id": 12345,
        "timestamp_utc": datetime(2026, 5, 12, 17, 30, tzinfo=timezone.utc),
        "thesis_id": "test_thesis",
        "family": family,
        "market_id": market_id,
        "direction": direction,
        "line_value": line_value,
        "activated_at_minute": activated_at_minute,
        "bookmaker_odd": bookmaker_odd,
    }


# ──────────────────────────────────────────────────────────────────────
# Family routing
# ──────────────────────────────────────────────────────────────────────


def test_goals_over_won():
    out = _outcome(home_goals=2, away_goals=1)  # total = 3
    pick = _pick_row(family="goals", market_id="match_goals_over_2.5",
                     direction="over", line_value=2.5)
    reason, won = grade_v3_pick(pick, out)
    assert reason == "graded"
    assert won is True


def test_goals_under_lost_at_exact_line_with_off_by_one_audit():
    """Regression on the 2026-05-10 audit: under 2.5 with 3 goals must LOSE
    (not silently double-win like the previous code did with line+1)."""
    out = _outcome(home_goals=2, away_goals=1)  # total = 3
    pick = _pick_row(family="goals", market_id="match_goals_under_2.5",
                     direction="under", line_value=2.5)
    reason, won = grade_v3_pick(pick, out)
    assert reason == "graded"
    assert won is False  # 3 < 2.5 is False → under loses


def test_first_half_goals_over_won():
    out = _outcome(home_goals=3, away_goals=0, home_1h=2, away_1h=0)
    pick = _pick_row(family="goals", market_id="first_half_goals_over_1.5",
                     direction="over", line_value=1.5)
    _, won = grade_v3_pick(pick, out)
    assert won is True


def test_btts_yes_won():
    out = _outcome(home_goals=2, away_goals=1)
    pick = _pick_row(family="btts", market_id="btts_yes", direction="yes")
    _, won = grade_v3_pick(pick, out)
    assert won is True


def test_btts_no_lost_when_both_scored():
    out = _outcome(home_goals=1, away_goals=1)
    pick = _pick_row(family="btts", market_id="btts_no", direction="no")
    _, won = grade_v3_pick(pick, out)
    assert won is False


def test_corners_over_lost():
    out = _outcome(corners=8)
    pick = _pick_row(family="corners", market_id="match_corners_over_9.5",
                     direction="over", line_value=9.5)
    _, won = grade_v3_pick(pick, out)
    assert won is False


def test_cards_over_won():
    out = _outcome(cards=5)
    pick = _pick_row(family="cards", market_id="cards_over_4.5",
                     direction="over", line_value=4.5)
    _, won = grade_v3_pick(pick, out)
    assert won is True


def test_result_1x2_home_won():
    out = _outcome(home_goals=2, away_goals=1)
    pick = _pick_row(family="result_1x2", market_id="1x2_home", direction="home")
    _, won = grade_v3_pick(pick, out)
    assert won is True


def test_result_1x2_draw_lost_with_home_winning():
    out = _outcome(home_goals=1, away_goals=0)
    pick = _pick_row(family="result_1x2", market_id="1x2_draw", direction="draw")
    _, won = grade_v3_pick(pick, out)
    assert won is False


# ──────────────────────────────────────────────────────────────────────
# next_goal logic
# ──────────────────────────────────────────────────────────────────────


def test_next_goal_home_won_when_home_scores_after_pick():
    out = _outcome(goal_events=((20, AWAY_ID), (55, HOME_ID), (78, HOME_ID)))
    assert _grade_next_goal("home", pick_minute=30, outcome=out) is True


def test_next_goal_away_lost_when_home_scores_first_after_pick():
    out = _outcome(goal_events=((20, AWAY_ID), (55, HOME_ID), (78, AWAY_ID)))
    assert _grade_next_goal("away", pick_minute=30, outcome=out) is False


def test_next_goal_no_won_when_no_goals_after_pick():
    out = _outcome(goal_events=((20, AWAY_ID),))
    assert _grade_next_goal("no", pick_minute=30, outcome=out) is True


def test_next_goal_no_lost_when_goal_after_pick():
    out = _outcome(goal_events=((40, HOME_ID),))
    assert _grade_next_goal("no", pick_minute=30, outcome=out) is False


def test_next_goal_directional_lost_when_no_more_goals():
    """If pick was 'next goal home' but no more goals in match → lost,
    not void (the bet didn't win)."""
    out = _outcome(goal_events=((20, AWAY_ID),))
    assert _grade_next_goal("home", pick_minute=30, outcome=out) is False


def test_grade_v3_pick_next_goal_routing():
    out = _outcome(goal_events=((45, HOME_ID),))
    pick = _pick_row(family="next_goal", market_id="next_goal_home",
                     direction="home", activated_at_minute=40)
    reason, won = grade_v3_pick(pick, out)
    assert reason == "next_goal"
    assert won is True


# ──────────────────────────────────────────────────────────────────────
# Accounting helpers
# ──────────────────────────────────────────────────────────────────────


def test_profit_units_won_pays_odd_minus_one():
    assert profit_units_for(True, 2.10) == pytest.approx(1.10)


def test_profit_units_lost_returns_minus_one():
    assert profit_units_for(False, 2.10) == -1.0


def test_profit_units_void_returns_zero():
    assert profit_units_for(None, 2.10) == 0.0


def test_profit_units_missing_odd_returns_zero():
    assert profit_units_for(True, None) == 0.0


def test_status_for_mapping():
    assert status_for(True) == "won"
    assert status_for(False) == "lost"
    assert status_for(None) == "void"


# ──────────────────────────────────────────────────────────────────────
# Ungradable path
# ──────────────────────────────────────────────────────────────────────


def test_unknown_family_returns_ungradable():
    pick = _pick_row(family="props", market_id="player_shots_over_2.5",
                     direction="over", line_value=2.5)
    reason, won = grade_v3_pick(pick, _outcome())
    assert reason == "ungradable"
    assert won is None


def test_goals_without_line_returns_ungradable():
    pick = _pick_row(family="goals", market_id="match_goals",
                     direction="over", line_value=None)
    # market_id has no number; _parse_line returns None
    reason, _ = grade_v3_pick(pick, _outcome())
    assert reason == "ungradable"


# ──────────────────────────────────────────────────────────────────────
# Batch grading end-to-end with mock client
# ──────────────────────────────────────────────────────────────────────


class _MockClient:
    """Duck-typed Sportmonks client that returns a fabricated finished
    Fixture for the test fixture_id."""

    def __init__(self, fixture_factory):
        self._factory = fixture_factory
        self.calls: list[int] = []

    async def get_fixture(self, fixture_id, *, includes=None):
        self.calls.append(fixture_id)
        fx = self._factory(fixture_id)
        if fx is None:
            from bip.sports.football.sportmonks.client import SportmonksError
            raise SportmonksError(404, f"no fixture {fixture_id}")
        return fx


def _make_finished_fixture(fixture_id: int = 12345):
    """Construct a Sportmonks Fixture pydantic with FT state + 2-1 score."""
    from bip.sports.football.sportmonks.schemas import (
        Fixture, Participant, FixtureState, Period, Score, Event,
    )
    home = Participant(id=HOME_ID, name="Home FC")
    away = Participant(id=AWAY_ID, name="Away FC")
    state = FixtureState(id=5, state="FT", name="Full Time",
                        developer_name="FT")
    # Scores: type_id 1525 = CURRENT (full-time); periods include 1H and 2H
    # The from_fixture _extract_current_score reads type_id-filtered scores.
    scores = [
        Score.model_validate({
            "id": 1, "fixture_id": fixture_id, "type_id": 1525,
            "participant_id": HOME_ID, "score": {"goals": 2, "participant": "home"},
            "description": "CURRENT",
        }),
        Score.model_validate({
            "id": 2, "fixture_id": fixture_id, "type_id": 1525,
            "participant_id": AWAY_ID, "score": {"goals": 1, "participant": "away"},
            "description": "CURRENT",
        }),
        Score.model_validate({
            "id": 3, "fixture_id": fixture_id, "type_id": 1,
            "participant_id": HOME_ID, "score": {"goals": 1, "participant": "home"},
            "description": "1ST_HALF",
        }),
        Score.model_validate({
            "id": 4, "fixture_id": fixture_id, "type_id": 1,
            "participant_id": AWAY_ID, "score": {"goals": 1, "participant": "away"},
            "description": "1ST_HALF",
        }),
    ]
    # Goal events at minute 30 (away), 70 (home), 88 (home)
    events = [
        Event.model_validate({
            "id": 1, "fixture_id": fixture_id, "type_id": 14,
            "participant_id": AWAY_ID, "minute": 30,
        }),
        Event.model_validate({
            "id": 2, "fixture_id": fixture_id, "type_id": 14,
            "participant_id": HOME_ID, "minute": 70,
        }),
        Event.model_validate({
            "id": 3, "fixture_id": fixture_id, "type_id": 14,
            "participant_id": HOME_ID, "minute": 88,
        }),
    ]
    return Fixture(
        id=fixture_id, sport_id=1, league_id=564, season_id=1,
        starting_at=datetime(2026, 5, 12, 17, 0, tzinfo=timezone.utc),
        state_id=5, has_odds=True,
        participants=[home, away], state=state, periods=[],
        scores=scores, events=events,
    )


def _write_picks(tmp_path, day: int, rows: list[dict]) -> Path:
    part = tmp_path / f"dt=2026-05-{day:02d}"
    part.mkdir(parents=True, exist_ok=True)
    pl.DataFrame(rows).write_parquet(part / "picks.parquet")
    return part


@pytest.mark.anyio("asyncio")
async def test_grade_picks_for_date_empty_partition(tmp_path):
    client = _MockClient(lambda fid: None)
    graded, report = await grade_picks_for_date(
        "2026-05-12", shadow_root=tmp_path, client=client,
    )
    assert graded == []
    assert report.n_picks_input == 0
    assert client.calls == []


@pytest.mark.anyio("asyncio")
async def test_grade_picks_for_date_end_to_end(tmp_path):
    """Full path: write picks parquet, grade via mock client, verify
    statuses + outcomes parquet round-trip."""
    _write_picks(tmp_path, day=12, rows=[
        _pick_row(family="goals", market_id="match_goals_over_2.5",
                  direction="over", line_value=2.5),
        _pick_row(family="btts", market_id="btts_yes", direction="yes"),
        _pick_row(family="corners", market_id="match_corners_over_9.5",
                  direction="over", line_value=9.5, bookmaker_odd=1.85),
    ])
    client = _MockClient(_make_finished_fixture)
    graded, report = await grade_picks_for_date(
        "2026-05-12", shadow_root=tmp_path, client=client,
    )
    assert report.n_picks_input == 3
    assert report.n_fixtures == 1
    assert report.n_fixtures_finished == 1

    # goals over 2.5 with 3 total → won; profit = odd-1 = 1.0
    g_goals = next(g for g in graded if "goals" in g.market_id)
    assert g_goals.status == "won"
    assert g_goals.profit_units == pytest.approx(1.0)

    # btts yes with 2-1 → won
    g_btts = next(g for g in graded if "btts" in g.market_id)
    assert g_btts.status == "won"

    # corners over 9.5 with 9 corners (from _outcome default not used —
    # but we built a real fixture without corners stats so total_corners=0)
    # → over 9.5 with 0 corners → lost
    g_corners = next(g for g in graded if "corners" in g.market_id)
    assert g_corners.status == "lost"
    assert g_corners.profit_units == -1.0

    # Write + roundtrip
    out_path = write_outcomes_parquet(graded, tmp_path / "dt=2026-05-12")
    assert out_path.exists()
    df = pl.read_parquet(out_path)
    assert df.height == 3
    for col in ("fixture_id", "thesis_id", "market_id", "pick_timestamp_utc",
                "status", "profit_units", "bookmaker_odd", "settled_at"):
        assert col in df.columns


@pytest.mark.anyio("asyncio")
async def test_grade_picks_pending_when_fixture_fetch_fails(tmp_path):
    """If get_fixture raises, those picks get status='pending' and the
    grader continues with the rest."""
    _write_picks(tmp_path, day=12, rows=[
        _pick_row(family="goals", market_id="match_goals_over_2.5",
                  direction="over", line_value=2.5),
    ])
    client = _MockClient(lambda fid: None)  # always raises 404
    graded, report = await grade_picks_for_date(
        "2026-05-12", shadow_root=tmp_path, client=client,
    )
    assert report.n_pending == 1
    assert graded[0].status == "pending"
