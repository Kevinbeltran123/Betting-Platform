"""ModelLoader round-trip + feature-hash gate — ML-04."""


class TestModelLoader:
    """ML-04: model save/load round-trip with feature-hash verification."""

    def test_save_load_roundtrip(self, tmp_model_dir, synthetic_training_data):
        """Saved ensemble reloaded produces identical predictions — ML-04."""
        # Will import: from bip.train.loader import ModelLoader
        assert False, "not yet implemented"

    def test_feature_hash_mismatch_raises(self, tmp_model_dir):
        """Loader raises StorageError when current feature hash differs from metadata.json."""
        assert False, "not yet implemented"

    def test_load_rejects_path_outside_model_dir(self, tmp_model_dir):
        """Security: loader refuses paths resolved outside settings.model_dir — T-reg-01."""
        assert False, "not yet implemented"
