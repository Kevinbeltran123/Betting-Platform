"""ELO rating features — D-02 penaltyblog.ratings.Elo usage with temporal snapshot."""


class TestEloFeatures:
    """ELO ratings snapshot before fixture.computed_at — D-02 / RESEARCH Pitfall 5."""

    def test_elo_temporal_snapshot(self):
        """ELO for fixture F uses only matches ending before F.computed_at."""
        # Will import: from bip.sports.football.features import FeatureEngineer
        assert False, "not yet implemented"

    def test_uses_penaltyblog_elo(self):
        """ELO feature extraction calls penaltyblog.ratings.Elo (do not hand-roll)."""
        assert False, "not yet implemented"

    def test_home_field_advantage_applied(self):
        """Elo instantiated with home_field_advantage > 0 — D-02."""
        assert False, "not yet implemented"
