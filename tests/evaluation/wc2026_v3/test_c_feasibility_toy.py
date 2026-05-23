"""Tests for the C feasibility script (Ola 1.C).

Skips the actual MCMC sample (too slow for CI; ~2 min); locks in the
helper functions that the verdict depends on:
  - generate_synthetic_corpus shape + Poisson reproducibility
  - persist_posterior_npz + predictive_lambda round-trip
  - measure_latency returns ascending p50 < p95 < p99
  - write_verdict_doc formats GO vs NO-GO branches correctly
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest


_SCRIPT_DIR = Path(__file__).resolve().parents[3] / "scripts" / "spike" / "wc2026_v3"
sys.path.insert(0, str(_SCRIPT_DIR))
import c_feasibility_toy as cf  # noqa: E402


# ─────────────────────────────────────────────────────────────────
# Synthetic corpus
# ─────────────────────────────────────────────────────────────────


def test_generate_synthetic_corpus_shapes() -> None:
    t, h, a, hg, ag, truth = cf.generate_synthetic_corpus(
        n_tournaments=3, n_teams=10, n_matches_per_tournament=20, seed=7
    )
    n_total = 3 * 20
    assert t.shape == (n_total,)
    assert h.shape == (n_total,)
    assert a.shape == (n_total,)
    assert hg.shape == (n_total,)
    assert ag.shape == (n_total,)
    # Each tournament represented exactly n_matches_per_tournament times
    counts = np.bincount(t, minlength=3)
    assert np.all(counts == 20)


def test_synthetic_no_self_matches() -> None:
    _, h, a, _, _, _ = cf.generate_synthetic_corpus(3, 10, 50, seed=11)
    assert not np.any(h == a)


def test_synthetic_reproducible_with_seed() -> None:
    r1 = cf.generate_synthetic_corpus(3, 10, 50, seed=42)
    r2 = cf.generate_synthetic_corpus(3, 10, 50, seed=42)
    assert np.array_equal(r1[0], r2[0])
    assert np.array_equal(r1[3], r2[3])
    assert np.array_equal(r1[4], r2[4])


def test_synthetic_truth_has_expected_keys() -> None:
    _, _, _, _, _, truth = cf.generate_synthetic_corpus(2, 5, 10, seed=1)
    expected = {
        "tau_attack",
        "tau_defense",
        "sigma_attack_t",
        "sigma_defense_t",
        "mu_attack_team",
        "mu_defense_team",
        "attack_tt",
        "defense_tt",
        "intercept",
        "home_adv",
    }
    assert expected <= set(truth.keys())


# ─────────────────────────────────────────────────────────────────
# NPZ persist + predictive_lambda round-trip
# ─────────────────────────────────────────────────────────────────


def _write_fake_posterior(path: Path, n_tournaments: int = 3, n_teams: int = 8) -> None:
    """Synthetic NPZ matching the layout persist_posterior_npz produces."""
    rng = np.random.default_rng(0)
    n_chains, n_draws = 4, 100
    np.savez_compressed(
        path,
        attack_tt=rng.normal(0, 0.1, size=(n_chains, n_draws, n_tournaments, n_teams)),
        defense_tt=rng.normal(0, 0.1, size=(n_chains, n_draws, n_tournaments, n_teams)),
        intercept=np.full((n_chains, n_draws), 0.10),
        home_adv=np.full((n_chains, n_draws), 0.20),
        n_tournaments=n_tournaments,
        n_teams=n_teams,
    )


def test_predictive_lambda_returns_positive_finite(tmp_path: Path) -> None:
    npz = tmp_path / "post.npz"
    _write_fake_posterior(npz)
    lam_h, lam_a = cf.predictive_lambda(npz, tournament_idx=0, home_idx=0, away_idx=1)
    assert np.isfinite(lam_h) and lam_h > 0
    assert np.isfinite(lam_a) and lam_a > 0


def test_predictive_lambda_home_advantage_makes_home_larger(tmp_path: Path) -> None:
    """With attack/defense ≈ 0 and home_adv=0.20, λ_h must exceed λ_a."""
    npz = tmp_path / "post.npz"
    _write_fake_posterior(npz, n_tournaments=2, n_teams=4)
    # Average over many random pairs to wash out the random attack/defense noise
    home_wins = 0
    for h in range(4):
        for a in range(4):
            if h == a:
                continue
            lam_h, lam_a = cf.predictive_lambda(npz, 0, h, a)
            if lam_h > lam_a:
                home_wins += 1
    # Out of 12 pairs, expect >=8 to favor home with 0.20 advantage.
    assert home_wins >= 8, f"home advantage broken: only {home_wins}/12 favor home"


# ─────────────────────────────────────────────────────────────────
# measure_latency
# ─────────────────────────────────────────────────────────────────


def test_measure_latency_returns_ascending_percentiles(tmp_path: Path) -> None:
    npz = tmp_path / "post.npz"
    _write_fake_posterior(npz, n_tournaments=3, n_teams=10)
    p50, p95, p99 = cf.measure_latency(npz, 3, 10, n_pairs=20, seed=3)
    assert p50 <= p95 <= p99
    # All percentiles must be measurable (finite, non-zero — np.percentile
    # returns 0 if all timings are 0 which would be suspicious).
    assert p50 > 0


# ─────────────────────────────────────────────────────────────────
# Verdict markdown
# ─────────────────────────────────────────────────────────────────


def test_write_verdict_doc_go_branch(tmp_path: Path) -> None:
    verdict = cf.FeasibilityVerdict(
        go=True,
        max_rhat=1.01,
        min_ess=800,
        n_divergences=0,
        p50_latency_ms=2.0,
        p95_latency_ms=5.0,
        p99_latency_ms=10.0,
        n_pairs_timed=50,
        sampling_seconds=120.0,
        notes="All criteria met. Proceed to Ola 2.C full spike.",
    )
    doc = tmp_path / "verdict.md"
    cf.write_verdict_doc(verdict, doc)
    body = doc.read_text()
    assert "**GO**" in body
    assert "Proceed to Ola 2.C" in body
    assert "1.01" in body  # rhat
    assert "800" in body  # ess


def test_write_verdict_doc_no_go_branch(tmp_path: Path) -> None:
    verdict = cf.FeasibilityVerdict(
        go=False,
        max_rhat=1.20,
        min_ess=50,
        n_divergences=42,
        p50_latency_ms=900.0,
        p95_latency_ms=2000.0,
        p99_latency_ms=5000.0,
        n_pairs_timed=50,
        sampling_seconds=600.0,
        notes="Convergence FAIL: rhat=1.200 ess=50 div=42 | Latency FAIL: p95=2000ms > 500ms",
    )
    doc = tmp_path / "verdict.md"
    cf.write_verdict_doc(verdict, doc)
    body = doc.read_text()
    assert "**NO-GO**" in body
    assert "Reallocate" in body
    assert "1.2" in body
    assert "2000" in body


# ─────────────────────────────────────────────────────────────────
# Full pipeline smoke (skipped — requires MCMC)
# ─────────────────────────────────────────────────────────────────


@pytest.mark.slow
def test_run_feasibility_smoke(tmp_path: Path) -> None:
    """End-to-end on the smallest possible config. Takes ~30s.

    Marked slow so default CI excludes it. Operator runs explicitly
    via ``pytest -m slow`` to validate the toy actually converges.
    """
    verdict = cf.run_feasibility(
        tmp_path,
        n_tournaments=2,
        n_teams=5,
        n_matches_per_tournament=15,
        draws=200,
        tune=200,
        chains=2,
    )
    # Just check it ran end-to-end and produced finite numbers.
    assert np.isfinite(verdict.max_rhat)
    assert np.isfinite(verdict.min_ess)
    assert verdict.n_divergences >= 0
    assert verdict.p95_latency_ms > 0
    assert (tmp_path / "c_feasibility_toy_posterior.npz").exists()
