"""Model registry + metadata schema — ML-04."""


class TestModelMetadata:
    """ML-04: metadata.json schema validates via ModelMetadata Pydantic model."""

    def test_metadata_schema(self):
        """ModelMetadata has all required fields (training_date, feature_set_hash, ...)."""
        # Will import: from bip.train.metadata import ModelMetadata
        assert False, "not yet implemented"

    def test_feature_set_hash(self):
        """feature_set_hash = sha256(sorted(feature_names))[:16] — deterministic."""
        # Will import: from bip.train.metadata import feature_set_hash
        assert False, "not yet implemented"

    def test_feature_set_hash_detects_addition(self):
        """Adding a feature changes the hash — ML-04."""
        assert False, "not yet implemented"


class TestModelRegistry:
    """ML-04: ModelRegistry read/write/promote of registry.json."""

    def test_promote_atomic(self, tmp_model_dir):
        """promote() writes via .tmp then renames — ML-04 durability."""
        # Will import: from bip.train.registry import ModelRegistry
        assert False, "not yet implemented"

    def test_promote_updates_production(self, tmp_model_dir):
        """promote(league, version) sets leagues[league]['production'] = version."""
        assert False, "not yet implemented"

    def test_history_appended(self, tmp_model_dir):
        """promote() appends version to leagues[league]['history']."""
        assert False, "not yet implemented"
