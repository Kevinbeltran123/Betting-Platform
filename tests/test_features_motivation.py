"""Motivation context features — D-02 table-state temporal correctness."""


class TestMotivationFeatures:
    """Motivation uses only league-table state before fixture.kickoff_utc."""

    def test_motivation_temporal(self):
        """Motivation (top-4, relegation) uses only pre-kickoff table state."""
        assert False, "not yet implemented"

    def test_dead_rubber_classification(self):
        """Motivation emits dead_rubber flag near season end — D-02."""
        assert False, "not yet implemented"
