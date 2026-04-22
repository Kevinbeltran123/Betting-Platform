"""CLV recorder tests — CLV-02 (calculation), CLV-03 (rolling average)."""

import pytest
from datetime import datetime, timezone
from unittest.mock import MagicMock


class TestClvCalculation:
    """CLV-02: clv_percentage = (odds_at_pick / closing_odds - 1) * 100."""

    def test_clv_percentage_formula(self):
        """CLV formula: (2.10 / 2.00 - 1) * 100 = +5.0."""
        from bip.clv.recorder import calculate_clv_percentage
        result = calculate_clv_percentage(odds_at_pick=2.10, closing_odds=2.00)
        assert result == pytest.approx(5.0, abs=0.01)

    def test_clv_negative_when_odds_worse_than_closing(self):
        """CLV is negative when we got worse odds than closing line."""
        from bip.clv.recorder import calculate_clv_percentage
        result = calculate_clv_percentage(odds_at_pick=1.90, closing_odds=2.00)
        assert result == pytest.approx(-5.0, abs=0.01)

    def test_clv_zero_when_odds_equal_closing(self):
        """CLV is 0.0 when odds at pick == closing odds."""
        from bip.clv.recorder import calculate_clv_percentage
        result = calculate_clv_percentage(odds_at_pick=2.00, closing_odds=2.00)
        assert result == pytest.approx(0.0, abs=0.001)

    def test_clv_record_stored_with_odds_fetched_at(self, mock_client):
        """ClvRecord.odds_fetched_at is set when recording CLV — D-04c."""
        from bip.clv.recorder import ClvRecorder
        from bip.core.storage.models import ClvRecord
        from tests.conftest import setup_mock_chain

        setup_mock_chain(mock_client, data=[{"id": 1}])
        recorder = ClvRecorder(client=mock_client)
        clv = recorder.record(
            pick_id=1,
            fixture_id=12345,
            sport="football",
            market="onextwo",
            odds_at_pick=2.10,
            pinnacle_closing_odds=2.00,
            odds_fetched_at=datetime(2026, 4, 22, 17, 45, 0, tzinfo=timezone.utc),
        )
        assert clv.clv_percentage == pytest.approx(5.0, abs=0.01)
        assert clv.odds_fetched_at is not None


class TestRollingAverage:
    """CLV-03: Rolling 50-pick average CLV drops below +1% triggers alert flag."""

    def test_rolling_average_above_threshold(self):
        """No alert when rolling 50-pick average CLV >= +1%."""
        from bip.clv.recorder import compute_rolling_clv_average
        clv_values = [3.0] * 50  # all +3% — healthy
        avg = compute_rolling_clv_average(clv_values)
        assert avg == pytest.approx(3.0)
        assert avg >= 1.0

    def test_rolling_average_below_threshold(self):
        """Rolling average below +1% must return value < 1.0 (caller decides alert)."""
        from bip.clv.recorder import compute_rolling_clv_average
        clv_values = [-2.0] * 30 + [1.0] * 20  # average negative
        avg = compute_rolling_clv_average(clv_values)
        assert avg < 1.0

    def test_rolling_average_uses_last_50(self):
        """compute_rolling_clv_average uses only the last 50 values."""
        from bip.clv.recorder import compute_rolling_clv_average
        # 100 values: first 50 bad, last 50 good
        clv_values = [-5.0] * 50 + [4.0] * 50
        avg = compute_rolling_clv_average(clv_values)
        assert avg == pytest.approx(4.0, abs=0.01)

    def test_fewer_than_50_picks_uses_all(self):
        """With fewer than 50 picks, average all available values."""
        from bip.clv.recorder import compute_rolling_clv_average
        clv_values = [2.0, 3.0, 4.0]
        avg = compute_rolling_clv_average(clv_values)
        assert avg == pytest.approx(3.0, abs=0.01)
