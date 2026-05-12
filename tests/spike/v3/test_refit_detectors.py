"""Tests for ``scripts.spike.v3.refit_detectors``.

T3 invariants:
- ``next_version`` returns 1 when no pkls exist; increments past the
  highest existing version (parses ``_vN.pkl`` correctly).
- ``promote_symlink`` swaps an existing symlink atomically.
- ``refit_ood`` with insufficient real samples does NOT auto-promote
  even if the synthetic-blended fit is clean.
- ``refit_ood`` with sufficient real samples + zero anti-Napoli FPR
  auto-promotes.
- ``refit_ood`` with anti-Napoli FPR > 0 does NOT promote even with
  enough real samples.
- ``write_report`` produces a markdown with the expected sections and
  table rows.
- ``--dry-run`` skips all writes.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import patch

from scripts.spike.v3.refit_detectors import (
    RefitResult,
    latest_symlink_path,
    next_version,
    promote_symlink,
    refit_ood,
    write_report,
)

# ──────────────────────────────────────────────────────────────────────
# Versioning
# ──────────────────────────────────────────────────────────────────────


def test_next_version_empty_dir_returns_1(tmp_path):
    assert next_version(tmp_path, "ood_detector") == 1


def test_next_version_increments_past_highest(tmp_path):
    (tmp_path / "ood_detector_v1.pkl").touch()
    (tmp_path / "ood_detector_v3.pkl").touch()
    (tmp_path / "ood_detector_v2.pkl").touch()
    assert next_version(tmp_path, "ood_detector") == 4


def test_next_version_ignores_other_families(tmp_path):
    (tmp_path / "ood_detector_v5.pkl").touch()
    assert next_version(tmp_path, "pattern_layer") == 1


def test_next_version_ignores_non_versioned_files(tmp_path):
    (tmp_path / "ood_detector_latest.pkl").touch()
    (tmp_path / "ood_detector.pkl").touch()
    (tmp_path / "ood_detector_v_typo.pkl").touch()
    assert next_version(tmp_path, "ood_detector") == 1


# ──────────────────────────────────────────────────────────────────────
# Symlink promotion
# ──────────────────────────────────────────────────────────────────────


def test_promote_symlink_creates_new(tmp_path):
    target = tmp_path / "ood_detector_v1.pkl"
    target.touch()
    sym = tmp_path / "ood_detector_latest.pkl"
    promote_symlink(sym, target)
    assert sym.is_symlink()
    assert sym.resolve() == target.resolve()


def test_promote_symlink_replaces_existing(tmp_path):
    v1 = tmp_path / "ood_detector_v1.pkl"
    v1.touch()
    v2 = tmp_path / "ood_detector_v2.pkl"
    v2.touch()
    sym = tmp_path / "ood_detector_latest.pkl"
    promote_symlink(sym, v1)
    promote_symlink(sym, v2)
    assert sym.resolve() == v2.resolve()


# ──────────────────────────────────────────────────────────────────────
# Promotion policy (refit_ood)
# ──────────────────────────────────────────────────────────────────────


def test_refit_ood_insufficient_real_samples_does_not_promote(tmp_path):
    """Empty real GSV list → fit on synthetic only → no promotion."""
    result = refit_ood(
        real_gsvs=[],
        min_real_samples=100,
        out_dir=tmp_path,
        dry_run=False,
        blend_synthetic_n=50,
        seed=42,
        threshold_percentile=99.0,
    )
    assert result.promoted is False
    assert "n_real=0 < min=100" in result.promote_reason
    # Pkl IS written (preserved for inspection) even when not promoted
    assert result.pkl_path.exists()
    # The _latest symlink should NOT exist (no promotion)
    sym = latest_symlink_path(tmp_path, "ood_detector")
    assert not sym.exists() and not sym.is_symlink()


def test_refit_ood_with_zero_real_no_synthetic_blend_fails_gracefully(tmp_path):
    """If both real and synthetic blend are zero, fit raises — we should
    NOT crash the outer script; the refit_ood function passes through
    the exception so the caller can decide. For now, just exercise the
    happy path with synthetic blending."""
    # Smoke: zero real, default synthetic = 50 → fits OK
    result = refit_ood(
        real_gsvs=[],
        min_real_samples=100,
        out_dir=tmp_path,
        dry_run=False,
        blend_synthetic_n=50,
        seed=42,
        threshold_percentile=99.0,
    )
    assert result.version == 1
    assert result.n_synthetic > 0


def test_refit_ood_dry_run_does_not_write(tmp_path):
    result = refit_ood(
        real_gsvs=[],
        min_real_samples=100,
        out_dir=tmp_path,
        dry_run=True,
        blend_synthetic_n=20,
        seed=42,
        threshold_percentile=99.0,
    )
    assert not result.pkl_path.exists()
    sym = latest_symlink_path(tmp_path, "ood_detector")
    assert not sym.exists()


def test_refit_ood_promotes_when_real_samples_and_no_anti_napoli_fp(tmp_path):
    """Mock anti_napoli_fpr to 0 and provide enough fake real samples."""
    # The "real" GSVs here are just synthetic ones; we patch the
    # anti-Napoli check to control the FPR outcome.
    from scripts.spike.v3.fit_ood_detector import _generate_realistic_gsvs

    real = _generate_realistic_gsvs(150, seed=7)
    with patch(
        "scripts.spike.v3.refit_detectors.anti_napoli_false_positive_rate",
        return_value=0.0,
    ):
        result = refit_ood(
            real_gsvs=real,
            min_real_samples=100,
            out_dir=tmp_path,
            dry_run=False,
            blend_synthetic_n=20,
            seed=42,
            threshold_percentile=99.0,
        )
    assert result.promoted is True
    assert result.anti_napoli_fpr == 0.0
    sym = latest_symlink_path(tmp_path, "ood_detector")
    assert sym.is_symlink()
    assert sym.resolve() == result.pkl_path.resolve()


def test_refit_ood_blocks_promote_when_anti_napoli_fp_positive(tmp_path):
    """Even with enough real samples, FPR > 0 blocks promotion."""
    from scripts.spike.v3.fit_ood_detector import _generate_realistic_gsvs

    real = _generate_realistic_gsvs(150, seed=7)
    with patch(
        "scripts.spike.v3.refit_detectors.anti_napoli_false_positive_rate",
        return_value=0.04,  # 2/50 false positives
    ):
        result = refit_ood(
            real_gsvs=real,
            min_real_samples=100,
            out_dir=tmp_path,
            dry_run=False,
            blend_synthetic_n=20,
            seed=42,
            threshold_percentile=99.0,
        )
    assert result.promoted is False
    assert "anti-Napoli FPR=4.0%" in result.promote_reason
    sym = latest_symlink_path(tmp_path, "ood_detector")
    assert not sym.exists()


# ──────────────────────────────────────────────────────────────────────
# Report writing
# ──────────────────────────────────────────────────────────────────────


def test_write_report_produces_markdown_with_expected_sections(tmp_path):
    results = [
        RefitResult(
            family="ood_detector",
            version=2,
            n_real=120,
            n_synthetic=50,
            pkl_path=tmp_path / "ood_detector_v2.pkl",
            promoted=True,
            promote_reason="policy ok",
            threshold=3.5,
            anti_napoli_fpr=0.0,
        ),
        RefitResult(
            family="pattern_layer",
            version=2,
            n_real=120,
            n_synthetic=250,
            pkl_path=tmp_path / "pattern_layer_v2.pkl",
            promoted=False,
            promote_reason="n_real=80 < min=100",
        ),
    ]
    today = datetime(2026, 5, 11, tzinfo=UTC)
    report = write_report(results, tmp_path / "reports", window_days=30, today=today)
    body = report.read_text(encoding="utf-8")
    assert "# v3 detector refit — 2026-05-11" in body
    assert "ood_detector | v2" in body
    assert "pattern_layer | v2" in body
    assert "0.0%" in body  # anti-Napoli FPR formatted
    assert "Promotion policy" in body
    # Failure reason is preserved
    assert "n_real=80 < min=100" in body
