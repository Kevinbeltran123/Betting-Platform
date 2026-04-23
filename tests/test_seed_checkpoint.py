"""Seed script checkpoint resume — D-01 (historical data acquisition)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def _load_seed_module():
    """Import scripts/seed_historical.py as a module (not in sys.path by default)."""
    root = Path(__file__).parent.parent
    spec = importlib.util.spec_from_file_location(
        "seed_historical", root / "scripts" / "seed_historical.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["seed_historical"] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class TestSeedCheckpoint:
    """Seed script can resume after interruption via checkpoint file."""

    def test_checkpoint_resume(self, tmp_path, monkeypatch):
        """Resume skips already-completed fixture IDs — D-01 constraint."""
        seed = _load_seed_module()
        cp = tmp_path / "seed_checkpoint.json"
        monkeypatch.setattr(seed, "CHECKPOINT_PATH", cp)

        # First save, then load — must round-trip
        seed.save_checkpoint({101, 102, 103})
        reloaded = seed.load_checkpoint()
        assert reloaded == {101, 102, 103}

    def test_checkpoint_atomic_write(self, tmp_path, monkeypatch):
        """save_checkpoint writes to .tmp then renames — D-01 durability."""
        seed = _load_seed_module()
        cp = tmp_path / "seed_checkpoint.json"
        monkeypatch.setattr(seed, "CHECKPOINT_PATH", cp)

        seed.save_checkpoint({200})

        # Final file exists; no stray .tmp left behind
        assert cp.exists()
        tmp_files = list(tmp_path.glob("*.tmp"))
        assert tmp_files == [], f"Unexpected .tmp files: {tmp_files}"

    def test_checkpoint_empty_when_missing(self, tmp_path, monkeypatch):
        """load_checkpoint returns empty set when file does not exist — D-01."""
        seed = _load_seed_module()
        cp = tmp_path / "does_not_exist.json"
        monkeypatch.setattr(seed, "CHECKPOINT_PATH", cp)

        assert seed.load_checkpoint() == set()
