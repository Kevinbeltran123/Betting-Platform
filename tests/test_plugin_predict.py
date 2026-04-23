"""FootballPlugin.predict() E2E — ML-01 + ML-05."""


class TestFootballPluginPredict:
    """ML-01: predict() returns calibrated ProbabilityMap with registry-sourced model_version."""

    async def test_predict_returns_probability_map(self, settings, tmp_model_dir):
        """FootballPlugin.predict() returns ProbabilityMap with probabilities summing to 1 — ML-01."""
        assert False, "not yet implemented"

    async def test_predict_uses_model_version_from_registry(self, settings, tmp_model_dir):
        """ProbabilityMap.model_version matches registry production version — ML-04."""
        assert False, "not yet implemented"

    async def test_shadow_and_production_paths(self, settings, tmp_model_dir):
        """When registry has both production and shadow, predict writes both — ML-05."""
        assert False, "not yet implemented"
