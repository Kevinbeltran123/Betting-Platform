"""Tests for calibrator_drift CLI."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

from bip.evaluation.live.calibration import (
    IsotonicProbabilityCalibrator, PerMarketCalibrator,
)

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts" / "spike" / "sportmonks"))
import calibrator_drift as cd  # type: ignore  # noqa: E402


def _make_global(seed: int, tmp_path: Path, name: str) -> Path:
    rng = np.random.default_rng(seed)
    probs = np.linspace(0.1, 0.9, 200)
    outcomes = (rng.uniform(size=200) < probs).astype(float)
    cal = IsotonicProbabilityCalibrator.fit(probs, outcomes)
    path = tmp_path / name
    cal.save_json(path)
    return path


def _make_per_market(
    seed: int, tmp_path: Path, name: str, threshold: int = 25,
) -> Path:
    rng = np.random.default_rng(seed)
    a_probs = np.linspace(0.1, 0.9, 200)
    a_out = (rng.uniform(size=200) < a_probs).astype(float)
    b_probs = np.linspace(0.6, 0.95, 200)
    b_out = (rng.uniform(size=200) < 0.30).astype(float)
    probs = np.concatenate([a_probs, b_probs])
    outcomes = np.concatenate([a_out, b_out])
    markets = ["market_A"] * 200 + ["market_B"] * 200
    cal = PerMarketCalibrator.fit(
        probs, outcomes, markets, min_samples_per_market=threshold,
    )
    path = tmp_path / name
    cal.save_json(path)
    return path


class TestCompareGlobal:
    def test_stable_calibrators_no_alerts(self, tmp_path: Path, capsys):
        # Same seed → near-identical calibrators
        old = _make_global(0, tmp_path, "old.json")
        new = _make_global(0, tmp_path, "new.json")
        rc = cd.main(["--old", str(old), "--new", str(new),
                      "--kind", "global"])
        assert rc == 0  # no alerts
        out = capsys.readouterr().out
        assert "All shifts within" in out
        assert "✅" in out

    def test_drifted_calibrators_emit_alerts(self, tmp_path: Path, capsys):
        # Different seeds → calibrator curves differ
        old = _make_global(0, tmp_path, "old.json")
        new = _make_global(99, tmp_path, "new.json")
        # Use small alert_threshold to force alerts
        rc = cd.main(["--old", str(old), "--new", str(new),
                      "--kind", "global",
                      "--alert-threshold", "0.001"])
        # With seed shift + low threshold, expect alerts
        assert rc == 3
        out = capsys.readouterr().out
        assert "checkpoint(s) shifted" in out


class TestComparePerMarket:
    def test_runs_without_error(self, tmp_path: Path, capsys):
        old = _make_per_market(0, tmp_path, "old.json")
        new = _make_per_market(0, tmp_path, "new.json")
        rc = cd.main([
            "--old", str(old), "--new", str(new),
            "--kind", "per_market",
        ])
        # Either 0 or 3, depending on numeric stability of the fit
        assert rc in {0, 3}
        out = capsys.readouterr().out
        assert "PER-MARKET CALIBRATOR DRIFT" in out
        assert "Coverage change" in out

    def test_market_threshold_changes_show_added_removed(
        self, tmp_path: Path, capsys,
    ):
        # Old with high threshold → fewer markets get own fit
        old = _make_per_market(0, tmp_path, "old.json", threshold=300)
        # New with low threshold → more markets qualify
        new = _make_per_market(0, tmp_path, "new.json", threshold=50)
        cd.main([
            "--old", str(old), "--new", str(new),
            "--kind", "per_market",
        ])
        out = capsys.readouterr().out
        # Markets should have gained own fit (added section)
        assert "gaining own fit" in out


class TestKindDetection:
    def test_auto_detects_global(self, tmp_path: Path):
        path = _make_global(0, tmp_path, "g.json")
        assert cd._detect_kind(path) == "isotonic"

    def test_auto_detects_per_market(self, tmp_path: Path):
        path = _make_per_market(0, tmp_path, "pm.json")
        assert cd._detect_kind(path) == "per_market"

    def test_mismatched_types_error(self, tmp_path: Path, capsys):
        g = _make_global(0, tmp_path, "g.json")
        pm = _make_per_market(0, tmp_path, "pm.json")
        rc = cd.main(["--old", str(g), "--new", str(pm), "--kind", "auto"])
        assert rc == 2
        err = capsys.readouterr().err
        assert "different types" in err


class TestErrors:
    def test_missing_old_file(self, tmp_path: Path, capsys):
        new = _make_global(0, tmp_path, "new.json")
        rc = cd.main([
            "--old", str(tmp_path / "missing.json"),
            "--new", str(new),
        ])
        assert rc == 1
        err = capsys.readouterr().err
        assert "old file not found" in err

    def test_missing_new_file(self, tmp_path: Path, capsys):
        old = _make_global(0, tmp_path, "old.json")
        rc = cd.main([
            "--old", str(old),
            "--new", str(tmp_path / "missing.json"),
        ])
        assert rc == 1
