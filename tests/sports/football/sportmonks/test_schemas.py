"""Layer-1 tests: Pydantic schemas parse Sportmonks payloads correctly.

Uses fixture JSONs captured during the 2026-05-09 reconnaissance run
(stored in ``data/cache/sportmonks/recon/``). These are real responses
from the live API, so the tests exercise the schemas against realistic
data without requiring the API at test time.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from bip.sports.football.sportmonks.schemas import (
    Fixture,
    FixtureStatistic,
    Odd,
    Prediction,
    PressureMinute,
    Trend,
)
from bip.sports.football.sportmonks.types import (
    LIVE_PREDICTOR_STAT_IDS,
    PredictionType,
    StatType,
)

# Recon fixtures are an optional dependency for tests — when missing
# (clean checkout), tests are skipped. CI can run them by re-running
# the recon script.
RECON_DIR = Path(__file__).resolve().parent.parent.parent.parent.parent \
    / "data" / "cache" / "sportmonks" / "recon"


def _has_recon() -> bool:
    return RECON_DIR.exists() and (RECON_DIR / "21_live_high_value.json").exists()


pytestmark = pytest.mark.skipif(
    not _has_recon(),
    reason="Sportmonks recon fixtures missing — run reconnaissance script first.",
)


@pytest.fixture
def live_fixture_payload() -> dict:
    return json.loads((RECON_DIR / "21_live_high_value.json").read_text())["data"]


@pytest.fixture
def inplay_payload() -> dict:
    return json.loads((RECON_DIR / "03_livescores_inplay.json").read_text())


# ── Fixture parsing ──────────────────────────────────────────────────────────


class TestFixtureParsing:
    def test_top_level_fields(self, live_fixture_payload: dict):
        f = Fixture.model_validate(live_fixture_payload)
        assert f.id > 0
        assert f.league_id > 0
        assert f.season_id > 0

    def test_includes_attached(self, live_fixture_payload: dict):
        f = Fixture.model_validate(live_fixture_payload)
        # Recon hit a live fixture with these includes
        assert f.statistics is not None and len(f.statistics) > 0
        assert f.predictions is not None and len(f.predictions) > 0
        assert f.participants is not None and len(f.participants) == 2

    def test_is_live_detection(self, live_fixture_payload: dict):
        f = Fixture.model_validate(live_fixture_payload)
        # Recon fixture was 2nd half live
        if f.state and f.state.developer_name.startswith("INPLAY"):
            assert f.is_live() is True
        # Either way: function never raises
        assert isinstance(f.is_live(), bool)

    def test_extra_fields_ignored(self):
        # Sportmonks adds keys we don't model — must not raise.
        raw = {
            "id": 1,
            "sport_id": 1,
            "league_id": 1,
            "season_id": 1,
            "name": "Test",
            "future_field_we_dont_know": {"deep": True},
        }
        f = Fixture.model_validate(raw)
        assert f.id == 1


# ── FixtureStatistic ────────────────────────────────────────────────────────


class TestFixtureStatistic:
    def test_value_extraction(self):
        s = FixtureStatistic.model_validate({
            "id": 1, "fixture_id": 100, "type_id": StatType.SHOTS_TOTAL,
            "participant_id": 50, "data": {"value": 14},
        })
        assert s.value == 14.0

    def test_value_string_coerced(self):
        s = FixtureStatistic.model_validate({
            "id": 1, "fixture_id": 100, "type_id": StatType.BALL_POSSESSION,
            "participant_id": 50, "data": {"value": "62.5"},
        })
        assert s.value == 62.5

    def test_value_none_on_missing(self):
        s = FixtureStatistic.model_validate({
            "id": 1, "fixture_id": 100, "type_id": StatType.GOALS,
            "participant_id": 50, "data": {},
        })
        assert s.value is None


# ── Trend (minute-by-minute) ────────────────────────────────────────────────


class TestTrendParsing:
    def test_parses_minute_value(self, live_fixture_payload: dict):
        f = Fixture.model_validate(live_fixture_payload)
        assert f.trends is not None
        # Spot-check: every trend has a positive minute and a known type_id
        for t in f.trends[:50]:
            assert t.minute >= 0
            assert t.fixture_id == f.id

    def test_trends_cover_known_stat_types(self, live_fixture_payload: dict):
        f = Fixture.model_validate(live_fixture_payload)
        if not f.trends:
            pytest.skip("trends absent on this fixture")
        type_ids_seen = {t.type_id for t in f.trends}
        # Several known stats must appear in trends from the recon fixture
        assert any(tid in LIVE_PREDICTOR_STAT_IDS for tid in type_ids_seen)


# ── PressureMinute ──────────────────────────────────────────────────────────


class TestPressureParsing:
    def test_pressure_in_valid_range(self, live_fixture_payload: dict):
        f = Fixture.model_validate(live_fixture_payload)
        if not f.pressure:
            pytest.skip("pressure absent")
        for p in f.pressure[:20]:
            assert 0.0 <= p.pressure <= 100.0
            assert p.minute >= 0


# ── Prediction bodies ──────────────────────────────────────────────────────


class TestPredictionBodies:
    def test_first_half_winner_keys(self, live_fixture_payload: dict):
        f = Fixture.model_validate(live_fixture_payload)
        for p in f.predictions or []:
            if p.type_id == PredictionType.FIRST_HALF_WINNER_PROBABILITY:
                body = p.predictions
                assert {"home", "draw", "away"} <= set(body)
                # Probabilities should sum to ~100 (Sportmonks uses pct)
                total = sum(float(body[k]) for k in ("home", "draw", "away"))
                assert 99.0 <= total <= 101.0
                break
        else:
            pytest.skip("no FIRST_HALF_WINNER prediction in fixture")

    def test_btts_yes_no(self, live_fixture_payload: dict):
        f = Fixture.model_validate(live_fixture_payload)
        for p in f.predictions or []:
            if p.type_id == PredictionType.BTTS_PROBABILITY:
                assert {"yes", "no"} <= set(p.predictions)
                break

    def test_ou25_yes_no_sum_100(self, live_fixture_payload: dict):
        f = Fixture.model_validate(live_fixture_payload)
        for p in f.predictions or []:
            if p.type_id == PredictionType.OVER_UNDER_2_5_PROBABILITY:
                body = p.predictions
                total = float(body["yes"]) + float(body["no"])
                assert 99.0 <= total <= 101.0
                break

    def test_htft_grid_has_9_cells(self, live_fixture_payload: dict):
        f = Fixture.model_validate(live_fixture_payload)
        for p in f.predictions or []:
            if p.type_id == PredictionType.HTFT_PROBABILITY:
                # 3 HT outcomes × 3 FT outcomes = 9 cells
                expected = {
                    "home_home", "home_draw", "home_away",
                    "draw_home", "draw_draw", "draw_away",
                    "away_home", "away_draw", "away_away",
                }
                assert expected <= set(p.predictions)
                break


# ── Odd parsing ─────────────────────────────────────────────────────────────


class TestOddParsing:
    def test_decimal_odd_extracted(self):
        o = Odd.model_validate({
            "id": 1, "fixture_id": 100, "market_id": 1, "bookmaker_id": 2,
            "label": "1", "value": "2.50",
        })
        assert o.decimal_odd == 2.50
        assert o.implied_prob == pytest.approx(0.4, abs=1e-9)

    def test_implied_prob_invalid_odd(self):
        o = Odd.model_validate({
            "id": 1, "fixture_id": 100, "market_id": 1, "bookmaker_id": 2,
            "label": "1", "value": "1.00",
        })
        assert o.implied_prob is None  # odd <= 1.0 is invalid

    def test_suspended_flag(self):
        o = Odd.model_validate({
            "id": 1, "fixture_id": 100, "market_id": 1, "bookmaker_id": 2,
            "label": "1", "value": "2.50", "suspended": True, "stopped": True,
        })
        assert o.suspended is True
        assert o.stopped is True


# ── Recon-fixture sanity ─────────────────────────────────────────────────────


class TestReconFixtureSanity:
    def test_inplay_payload_at_least_one_fixture(self, inplay_payload: dict):
        assert len(inplay_payload["data"]) >= 1
        # Each entry should validate as a partial Fixture
        for rec in inplay_payload["data"]:
            f = Fixture.model_validate(rec)
            assert f.id > 0
