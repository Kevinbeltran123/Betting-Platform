"""Ola 1.C feasibility check — toy hierarchical Bayesian model with PyMC.

Goal: decide GO/NO-GO for the full Ola 2.C spike. Two acceptance criteria:

1. **Convergence**: NUTS sampling on a small hierarchical Dixon-Coles
   model with per-tournament partial pooling must produce:
   - max R-hat < 1.05 across all parameters
   - min ESS > 400
   - 0 divergent transitions
   on synthetic data (~3 tournaments × ~10 teams × ~50 matches each).
   Uses non-centered parameterisation to dodge Neal's funnel at the
   per-tournament σ groups (Gelman 2005, PyMC canonical diagnostic).

2. **Inference latency**: Posterior samples are written to NPZ on disk.
   Reading samples + computing predictive λ for 50 (home, away) pairs
   must complete with p95 < 500ms — the v3 production budget. NO MCMC
   at predict time; the production inference path is
       (read samples once) → (Numpy einsum on posterior means).

This script writes its verdict to ``Papers/WC2026_V3_C_FEASIBILITY.md``
and the posterior NPZ to ``data/cache/wc2026_v3/c_feasibility_toy_posterior.npz``.

Usage:

    uv run python scripts/spike/wc2026_v3/c_feasibility_toy.py \\
        --n-tournaments 3 --n-teams 10 --n-matches 50 \\
        --output-dir data/cache/wc2026_v3/

The script is intentionally synthetic — the goal is to verify the model
shape converges + the inference pattern is fast, BEFORE building the
full Ola 2.C module on real WC2018+Euro2020 calibration data. If the
toy fails either criterion, kill C and reallocate the 7 days to A
rigor + D polish per PLAN.md §"Wave 2".
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np


@dataclass
class FeasibilityVerdict:
    """Structured result of the feasibility check.

    Mirrors what gets written to Papers/WC2026_V3_C_FEASIBILITY.md so
    downstream agents (planner, executor) can branch on it.
    """

    go: bool
    max_rhat: float
    min_ess: float
    n_divergences: int
    p50_latency_ms: float
    p95_latency_ms: float
    p99_latency_ms: float
    n_pairs_timed: int
    sampling_seconds: float
    notes: str

    rhat_threshold: float = 1.05
    ess_threshold: float = 400.0
    latency_p95_budget_ms: float = 500.0


# ─────────────────────────────────────────────────────────────────
# Synthetic data generation
# ─────────────────────────────────────────────────────────────────


def generate_synthetic_corpus(
    n_tournaments: int,
    n_teams: int,
    n_matches_per_tournament: int,
    *,
    seed: int = 42,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, dict]:
    """Generate hierarchical-Poisson-distributed match data.

    Returns
    -------
    tournament_idx: (n_matches,) ints in [0, n_tournaments)
    home_idx, away_idx: (n_matches,) ints in [0, n_teams)
    home_goals, away_goals: (n_matches,) ints
    truth: dict of generating params (attack, defense, sigma_attack_t, etc.)
        For post-hoc recovery-error checks.
    """
    rng = np.random.default_rng(seed)

    # Hyper
    tau_attack = 0.35
    tau_defense = 0.35
    sigma_attack_t = rng.uniform(0.05, 0.20, size=n_tournaments)
    sigma_defense_t = rng.uniform(0.05, 0.20, size=n_tournaments)

    mu_attack_team = rng.normal(0, tau_attack, size=n_teams)
    mu_defense_team = rng.normal(0, tau_defense, size=n_teams)
    z_attack_tt = rng.normal(0, 1, size=(n_tournaments, n_teams))
    z_defense_tt = rng.normal(0, 1, size=(n_tournaments, n_teams))
    attack_tt = mu_attack_team[None, :] + sigma_attack_t[:, None] * z_attack_tt
    defense_tt = mu_defense_team[None, :] + sigma_defense_t[:, None] * z_defense_tt

    intercept = 0.10
    home_adv = 0.20

    n_total = n_tournaments * n_matches_per_tournament
    tournament_idx = np.repeat(np.arange(n_tournaments), n_matches_per_tournament)
    home_idx = rng.integers(0, n_teams, size=n_total)
    away_idx = rng.integers(0, n_teams, size=n_total)
    # Avoid degenerate self-matches
    mask = home_idx == away_idx
    away_idx[mask] = (away_idx[mask] + 1) % n_teams

    log_lam_h = (
        intercept
        + home_adv
        + attack_tt[tournament_idx, home_idx]
        + defense_tt[tournament_idx, away_idx]
    )
    log_lam_a = (
        intercept
        + attack_tt[tournament_idx, away_idx]
        + defense_tt[tournament_idx, home_idx]
    )
    home_goals = rng.poisson(np.exp(log_lam_h))
    away_goals = rng.poisson(np.exp(log_lam_a))

    truth = {
        "tau_attack": tau_attack,
        "tau_defense": tau_defense,
        "sigma_attack_t": sigma_attack_t,
        "sigma_defense_t": sigma_defense_t,
        "mu_attack_team": mu_attack_team,
        "mu_defense_team": mu_defense_team,
        "attack_tt": attack_tt,
        "defense_tt": defense_tt,
        "intercept": intercept,
        "home_adv": home_adv,
    }

    return tournament_idx, home_idx, away_idx, home_goals, away_goals, truth


# ─────────────────────────────────────────────────────────────────
# PyMC model + sampling
# ─────────────────────────────────────────────────────────────────


def fit_hierarchical(
    tournament_idx: np.ndarray,
    home_idx: np.ndarray,
    away_idx: np.ndarray,
    home_goals: np.ndarray,
    away_goals: np.ndarray,
    n_tournaments: int,
    n_teams: int,
    *,
    draws: int = 1000,
    tune: int = 1000,
    chains: int = 4,
    target_accept: float = 0.95,
    seed: int = 42,
) -> tuple["az.InferenceData", float]:  # type: ignore[name-defined]
    """Fit the hierarchical Dixon-Coles model with NUTS.

    Returns (idata, sampling_wall_seconds).
    """
    import pymc as pm

    coords = {
        "tournament": [f"T{i}" for i in range(n_tournaments)],
        "team": [f"team_{i}" for i in range(n_teams)],
    }

    with pm.Model(coords=coords):
        # Hyperpriors — global scale across teams
        tau_attack = pm.HalfNormal("tau_attack", sigma=1.0)
        tau_defense = pm.HalfNormal("tau_defense", sigma=1.0)

        # Per-tournament noise scale (controls partial pooling strength)
        sigma_attack_t = pm.HalfNormal(
            "sigma_attack_t", sigma=0.5, dims="tournament"
        )
        sigma_defense_t = pm.HalfNormal(
            "sigma_defense_t", sigma=0.5, dims="tournament"
        )

        # Per-team global means
        mu_attack_team = pm.Normal(
            "mu_attack_team", mu=0, sigma=tau_attack, dims="team"
        )
        mu_defense_team = pm.Normal(
            "mu_defense_team", mu=0, sigma=tau_defense, dims="team"
        )

        # Non-centered parameterisation — z * sigma + mu — to dodge
        # Neal's funnel at small per-group n.
        z_attack = pm.Normal("z_attack", mu=0, sigma=1, dims=("tournament", "team"))
        z_defense = pm.Normal("z_defense", mu=0, sigma=1, dims=("tournament", "team"))

        attack_tt = pm.Deterministic(
            "attack_tt",
            mu_attack_team[None, :] + sigma_attack_t[:, None] * z_attack,
            dims=("tournament", "team"),
        )
        defense_tt = pm.Deterministic(
            "defense_tt",
            mu_defense_team[None, :] + sigma_defense_t[:, None] * z_defense,
            dims=("tournament", "team"),
        )

        intercept = pm.Normal("intercept", mu=0, sigma=0.5)
        home_adv = pm.Normal("home_adv", mu=0.2, sigma=0.2)

        log_lam_h = (
            intercept
            + home_adv
            + attack_tt[tournament_idx, home_idx]
            + defense_tt[tournament_idx, away_idx]
        )
        log_lam_a = (
            intercept
            + attack_tt[tournament_idx, away_idx]
            + defense_tt[tournament_idx, home_idx]
        )

        pm.Poisson("obs_home_goals", mu=pm.math.exp(log_lam_h), observed=home_goals)
        pm.Poisson("obs_away_goals", mu=pm.math.exp(log_lam_a), observed=away_goals)

        t0 = time.perf_counter()
        idata = pm.sample(
            draws=draws,
            tune=tune,
            chains=chains,
            target_accept=target_accept,
            random_seed=seed,
            progressbar=False,
            return_inferencedata=True,
        )
        wall = time.perf_counter() - t0

    return idata, wall


# ─────────────────────────────────────────────────────────────────
# Convergence + latency checks
# ─────────────────────────────────────────────────────────────────


def evaluate_convergence(idata) -> tuple[float, float, int]:
    """Return (max_rhat, min_ess, n_divergences)."""
    import arviz as az

    summary = az.summary(idata, var_names=["~attack_tt", "~defense_tt"], filter_vars="like")
    max_rhat = float(summary["r_hat"].max())
    min_ess = float(summary["ess_bulk"].min())
    n_divergences = int(idata.sample_stats["diverging"].sum())
    return max_rhat, min_ess, n_divergences


def persist_posterior_npz(idata, n_tournaments: int, n_teams: int, path: Path) -> None:
    """Write posterior samples to NPZ in a layout the predictive-mean
    reader can consume without re-loading PyMC/ArviZ at predict time."""
    posterior = idata.posterior
    np.savez_compressed(
        path,
        attack_tt=posterior["attack_tt"].values,
        defense_tt=posterior["defense_tt"].values,
        intercept=posterior["intercept"].values,
        home_adv=posterior["home_adv"].values,
        n_tournaments=n_tournaments,
        n_teams=n_teams,
    )


def predictive_lambda(
    samples_npz_path: Path,
    tournament_idx: int,
    home_idx: int,
    away_idx: int,
) -> tuple[float, float]:
    """Compute predictive mean (λ_h, λ_a) from on-disk posterior samples.

    No PyMC / ArviZ. NumPy only — closed-form predictive mean = exp of
    posterior mean of the log-rate. This is the production inference
    path we're benchmarking; full posterior predictive draws would be
    too slow.
    """
    npz = np.load(samples_npz_path)
    attack = npz["attack_tt"].mean(axis=(0, 1))  # (n_tournaments, n_teams)
    defense = npz["defense_tt"].mean(axis=(0, 1))
    intercept = float(npz["intercept"].mean())
    home_adv = float(npz["home_adv"].mean())

    log_lam_h = (
        intercept
        + home_adv
        + attack[tournament_idx, home_idx]
        + defense[tournament_idx, away_idx]
    )
    log_lam_a = (
        intercept
        + attack[tournament_idx, away_idx]
        + defense[tournament_idx, home_idx]
    )
    return float(np.exp(log_lam_h)), float(np.exp(log_lam_a))


def measure_latency(
    samples_npz_path: Path,
    n_tournaments: int,
    n_teams: int,
    *,
    n_pairs: int = 50,
    seed: int = 7,
) -> tuple[float, float, float]:
    """Time ``n_pairs`` calls to predictive_lambda from a cold start.

    Returns (p50_ms, p95_ms, p99_ms). The current implementation
    re-reads the NPZ every call (worst-case I/O) — production can
    cache the loaded posterior in process memory, only paying the
    read once. This worst-case timing is the conservative budget check.
    """
    rng = np.random.default_rng(seed)
    timings_ms: list[float] = []
    for _ in range(n_pairs):
        t_idx = int(rng.integers(0, n_tournaments))
        h = int(rng.integers(0, n_teams))
        a = int(rng.integers(0, n_teams))
        if h == a:
            a = (a + 1) % n_teams
        t0 = time.perf_counter()
        predictive_lambda(samples_npz_path, t_idx, h, a)
        timings_ms.append((time.perf_counter() - t0) * 1000.0)
    timings = np.asarray(timings_ms)
    return (
        float(np.percentile(timings, 50)),
        float(np.percentile(timings, 95)),
        float(np.percentile(timings, 99)),
    )


# ─────────────────────────────────────────────────────────────────
# Verdict + report
# ─────────────────────────────────────────────────────────────────


def run_feasibility(
    output_dir: Path,
    *,
    n_tournaments: int = 3,
    n_teams: int = 10,
    n_matches_per_tournament: int = 50,
    draws: int = 1000,
    tune: int = 1000,
    chains: int = 4,
    seed: int = 42,
) -> FeasibilityVerdict:
    output_dir.mkdir(parents=True, exist_ok=True)
    npz_path = output_dir / "c_feasibility_toy_posterior.npz"

    print("Generating synthetic corpus...")
    t_idx, h_idx, a_idx, hg, ag, _truth = generate_synthetic_corpus(
        n_tournaments, n_teams, n_matches_per_tournament, seed=seed
    )

    print(
        f"Fitting hierarchical model: {n_tournaments} tournaments × "
        f"{n_teams} teams × {n_matches_per_tournament} matches ..."
    )
    idata, sampling_seconds = fit_hierarchical(
        t_idx, h_idx, a_idx, hg, ag,
        n_tournaments, n_teams,
        draws=draws, tune=tune, chains=chains, seed=seed,
    )
    print(f"  Sampling wall: {sampling_seconds:.1f}s")

    print("Evaluating convergence...")
    max_rhat, min_ess, n_div = evaluate_convergence(idata)
    print(f"  max_rhat={max_rhat:.3f}  min_ess={min_ess:.0f}  divergences={n_div}")

    print(f"Persisting posterior to {npz_path}...")
    persist_posterior_npz(idata, n_tournaments, n_teams, npz_path)

    print("Measuring inference latency from on-disk samples...")
    p50, p95, p99 = measure_latency(
        npz_path, n_tournaments, n_teams, n_pairs=50, seed=seed
    )
    print(f"  p50={p50:.2f}ms  p95={p95:.2f}ms  p99={p99:.2f}ms")

    notes = []
    convergence_ok = (
        max_rhat < 1.05 and min_ess >= 400 and n_div == 0
    )
    latency_ok = p95 < 500.0
    if not convergence_ok:
        notes.append(
            f"Convergence FAIL: rhat={max_rhat:.3f} ess={min_ess:.0f} div={n_div}"
        )
    if not latency_ok:
        notes.append(f"Latency FAIL: p95={p95:.2f}ms > 500ms")

    go = convergence_ok and latency_ok
    if go:
        notes.append("All criteria met. Proceed to Ola 2.C full spike.")

    return FeasibilityVerdict(
        go=go,
        max_rhat=max_rhat,
        min_ess=min_ess,
        n_divergences=n_div,
        p50_latency_ms=p50,
        p95_latency_ms=p95,
        p99_latency_ms=p99,
        n_pairs_timed=50,
        sampling_seconds=sampling_seconds,
        notes=" | ".join(notes),
    )


def write_verdict_doc(verdict: FeasibilityVerdict, doc_path: Path) -> None:
    """Write the 1-page Papers/WC2026_V3_C_FEASIBILITY.md verdict."""
    doc_path.parent.mkdir(parents=True, exist_ok=True)

    if verdict.go:
        verdict_block = "**GO** for Ola 2.C full spike."
    else:
        verdict_block = (
            "**NO-GO**. Reallocate 7-day Ola 2.C budget to A rigor + D "
            "polish per PLAN.md §\"Wave 2\" risk pad."
        )

    rhat_pass = "✓" if verdict.max_rhat < verdict.rhat_threshold else "✗"
    ess_pass = "✓" if verdict.min_ess >= verdict.ess_threshold else "✗"
    div_pass = "✓" if verdict.n_divergences == 0 else "✗"
    lat_pass = (
        "✓" if verdict.p95_latency_ms < verdict.latency_p95_budget_ms else "✗"
    )

    body = f"""# Ola 1.C Feasibility Verdict — Hierarchical Bayesian Pooling

**Date:** automated (this file is regenerated by
`scripts/spike/wc2026_v3/c_feasibility_toy.py`).

## Verdict

{verdict_block}

## Criteria

| Criterion | Threshold | Measured | Pass? |
|-----------|-----------|----------|-------|
| max R-hat | < {verdict.rhat_threshold} | {verdict.max_rhat:.4f} | {rhat_pass} |
| min ESS (bulk) | ≥ {verdict.ess_threshold:.0f} | {verdict.min_ess:.0f} | {ess_pass} |
| divergent transitions | 0 | {verdict.n_divergences} | {div_pass} |
| inference p95 latency | < {verdict.latency_p95_budget_ms:.0f}ms | {verdict.p95_latency_ms:.2f}ms | {lat_pass} |

## Performance

- Sampling wall: {verdict.sampling_seconds:.1f}s
  ({verdict.sampling_seconds / 60:.1f} min)
- Inference latency (cold-cache, NPZ re-read per call):
  p50={verdict.p50_latency_ms:.2f}ms / p95={verdict.p95_latency_ms:.2f}ms /
  p99={verdict.p99_latency_ms:.2f}ms
- Pairs timed: {verdict.n_pairs_timed}

## Notes

{verdict.notes}

## Reproducibility

```
uv run python scripts/spike/wc2026_v3/c_feasibility_toy.py \\
    --output-dir data/cache/wc2026_v3/
```

Synthetic corpus: 3 tournaments × 10 teams × 50 matches each
(default). Seed 42.
"""
    doc_path.write_text(body)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--n-tournaments", type=int, default=3, help="Synthetic tournament count."
    )
    parser.add_argument(
        "--n-teams", type=int, default=10, help="Synthetic per-tournament team count."
    )
    parser.add_argument(
        "--n-matches", type=int, default=50, help="Synthetic matches per tournament."
    )
    parser.add_argument(
        "--draws", type=int, default=1000, help="NUTS draws per chain."
    )
    parser.add_argument(
        "--tune", type=int, default=1000, help="NUTS tuning steps per chain."
    )
    parser.add_argument(
        "--chains", type=int, default=4, help="NUTS chains."
    )
    parser.add_argument(
        "--seed", type=int, default=42, help="RNG seed."
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/cache/wc2026_v3"),
        help="Where to write posterior NPZ.",
    )
    parser.add_argument(
        "--doc-path",
        type=Path,
        default=Path("Papers/WC2026_V3_C_FEASIBILITY.md"),
        help="Where to write the verdict markdown (gitignored — Papers/).",
    )
    parser.add_argument(
        "--json-only",
        action="store_true",
        help="Print JSON verdict and skip writing markdown report.",
    )
    args = parser.parse_args(argv)

    verdict = run_feasibility(
        args.output_dir,
        n_tournaments=args.n_tournaments,
        n_teams=args.n_teams,
        n_matches_per_tournament=args.n_matches,
        draws=args.draws,
        tune=args.tune,
        chains=args.chains,
        seed=args.seed,
    )

    if args.json_only:
        print(json.dumps(asdict(verdict), indent=2))
    else:
        write_verdict_doc(verdict, args.doc_path)
        print(f"\nVerdict written to {args.doc_path}")
        print(f"GO={verdict.go}")

    return 0 if verdict.go else 1


if __name__ == "__main__":
    sys.exit(main())
