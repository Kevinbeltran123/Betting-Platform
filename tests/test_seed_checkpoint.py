"""Seed script checkpoint resume — D-01 (historical data acquisition)."""


class TestSeedCheckpoint:
    """Seed script can resume after interruption via checkpoint file."""

    def test_checkpoint_resume(self, tmp_path):
        """Resume skips already-completed fixture IDs — D-01 constraint."""
        # Will import: from scripts.seed_historical import load_checkpoint, save_checkpoint
        assert False, "not yet implemented"

    def test_checkpoint_atomic_write(self, tmp_path):
        """save_checkpoint writes to .tmp then renames — D-01 durability."""
        assert False, "not yet implemented"
