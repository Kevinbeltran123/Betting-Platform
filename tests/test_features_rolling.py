"""Rolling form features — D-02 point-in-time correctness (DATA-02/05)."""


class TestRollingForm:
    """Rolling form features use only matches before fixture.kickoff_utc."""

    def test_no_future_match_leakage(self):
        """Rolling form for fixture F uses only matches before F.kickoff_utc."""
        # Will import: from bip.sports.football.features import FeatureEngineer
        assert False, "not yet implemented"

    def test_rolling_windows_3_5_10(self):
        """Rolling windows [3, 5, 10] produce 3 distinct aggregates per metric — D-02."""
        assert False, "not yet implemented"

    def test_home_away_split(self):
        """Rolling form computes separate home and away aggregates — D-02."""
        assert False, "not yet implemented"
