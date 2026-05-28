"""Empirical Bayes shrinkage spike — confederation × era pooling.

Question. Does shrinking team attack/defense rates toward their
confederation × era mean (Stein-style) improve Brier score on hold-out
vs unshrunken MLE baseline?

Theory (Egidi, Pauli & Torelli 2018, J Applied Stats; Efron-Morris 1977):
For team i with MLE rate r_i (n_i games) and group mean μ_g:
    r_i_shrunk = w_i * μ_g + (1 - w_i) * r_i
    w_i = τ² / (τ² + σ²_i / n_i)
where τ² = variance of true team effects within group (method-of-moments
estimator), σ² = sampling variance.

This is the FIXED-τ rescue path discussed in INTERNATIONAL_ANALYST_RESEARCH.md
§3.3 (Ola 1.C NO-GO follow-up). Pools hyperparameters; does NOT estimate
hyperparameters via MCMC. No identifiability issues at small n.

DESIGN.
- Train: WC18 + Euro20 + AFCON23 (≈167 matches).
- Hold-out: WC22 + Copa24 + Euro24 (≈147 matches).
- Goal model: λ_h = exp(α_atk_h - α_def_a + γ_home).
- MLE: solve attack/defense rates per team (single-era, all train data).
- EB shrinkage: per confederation cell, shrink toward cell mean.
- Predict: simulate (X_h, X_a) ~ independent Poisson via grid up to 6 goals.
- Brier: 3-way (W/D/L) over hold-out, paired delta.

RUN
    uv run python scripts/spike/eb_shrinkage_v3/01_fit_and_evaluate.py
"""
from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import polars as pl
from scipy.optimize import minimize
from scipy.stats import poisson

from bip.evaluation.tournaments.patterns_v2 import confederation_of


DATA_PATH = Path("data/cache/wc2026_v3/patterns_enriched.parquet")
OUTPUT_PATH = Path("data/cache/eb_shrinkage_v3/spike_results.json")
OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

TRAIN_TOURNAMENTS: frozenset[str] = frozenset(
    {"wc_2018", "euro_2020", "afcon_2023"}
)
HOLDOUT_TOURNAMENTS: frozenset[str] = frozenset(
    {"wc_2022", "copa_2024", "euro_2024"}
)

MAX_GOALS_GRID = 6  # P(score) computed over goals in {0,..,6}.
RNG_SEED = 260528


@dataclass
class FitResult:
    attack: dict[str, float]
    defense: dict[str, float]
    home_advantage: float


def load_data() -> pl.DataFrame:
    df = pl.read_parquet(DATA_PATH)
    df = df.filter(
        pl.col("home_goals").is_not_null() & pl.col("away_goals").is_not_null()
    )
    df = df.with_columns(
        [
            pl.col("home_goals").cast(pl.Int32),
            pl.col("away_goals").cast(pl.Int32),
            pl.col("home_team").alias("home"),
            pl.col("away_team").alias("away"),
        ]
    )
    return df


def fit_mle_poisson(
    df: pl.DataFrame,
) -> FitResult:
    """Fit independent Poisson with home advantage via L-BFGS-B.

    Parameterization: log λ_h = α_h - δ_a + γ; log λ_a = α_a - δ_h.
    Identifiability: pin sum(α) = 0, sum(δ) = 0.
    """
    teams = sorted(
        set(df["home"].to_list()) | set(df["away"].to_list())
    )
    team_idx = {t: i for i, t in enumerate(teams)}
    n = len(teams)

    rows = df.select(
        ["home", "away", "home_goals", "away_goals"]
    ).to_numpy()
    home_idx = np.array([team_idx[r[0]] for r in rows], dtype=int)
    away_idx = np.array([team_idx[r[1]] for r in rows], dtype=int)
    hg = np.array([r[2] for r in rows], dtype=int)
    ag = np.array([r[3] for r in rows], dtype=int)

    # Params: [α_0..α_{n-2}, δ_0..δ_{n-2}, γ]. Last team's α and δ derived
    # via sum-to-zero constraint.
    def unpack(theta: np.ndarray) -> tuple[np.ndarray, np.ndarray, float]:
        alpha_free = theta[: n - 1]
        delta_free = theta[n - 1 : 2 * (n - 1)]
        gamma = theta[2 * (n - 1)]
        alpha = np.concatenate([alpha_free, [-alpha_free.sum()]])
        delta = np.concatenate([delta_free, [-delta_free.sum()]])
        return alpha, delta, gamma

    def neg_log_lik(theta: np.ndarray) -> float:
        alpha, delta, gamma = unpack(theta)
        lam_h = np.exp(alpha[home_idx] - delta[away_idx] + gamma)
        lam_a = np.exp(alpha[away_idx] - delta[home_idx])
        # Poisson log-lik (ignoring log(k!) constant — irrelevant for MLE).
        ll = (
            (hg * np.log(lam_h + 1e-12) - lam_h).sum()
            + (ag * np.log(lam_a + 1e-12) - lam_a).sum()
        )
        return -ll

    theta0 = np.zeros(2 * (n - 1) + 1)
    theta0[-1] = 0.2  # mild home advantage init.
    res = minimize(
        neg_log_lik, theta0, method="L-BFGS-B",
        options={"maxiter": 500, "ftol": 1e-9},
    )
    alpha, delta, gamma = unpack(res.x)

    return FitResult(
        attack={t: float(alpha[team_idx[t]]) for t in teams},
        defense={t: float(delta[team_idx[t]]) for t in teams},
        home_advantage=float(gamma),
    )


def group_by_confederation(
    teams: list[str],
) -> dict[str, list[str]]:
    by_conf: dict[str, list[str]] = defaultdict(list)
    for t in teams:
        by_conf[confederation_of(t)].append(t)
    return dict(by_conf)


def stein_shrink(
    rates: dict[str, float],
    n_obs: dict[str, int],
    groups: dict[str, list[str]],
) -> tuple[dict[str, float], dict[str, dict]]:
    """Per-group Stein shrinkage of rates toward group mean.

    For group g with K teams and rates r_1..r_K (each from n_i obs):
        μ_g = mean(r_i)
        σ²_obs = mean(sample variance estimates) ≈ var(r_i) / (per-team n)
        τ² = max(0, var(r_i) - σ²_obs)  [method-of-moments, conservative]
        w_i = τ² / (τ² + σ²_obs / n_i)  [shrinkage weight on prior]
        r_i_shrunk = w_i * μ_g + (1 - w_i) * r_i

    Where group has K=1, no shrinkage (rate is its own group). Where K>=2,
    apply formula.

    Returns (shrunken_rates, audit_per_group).
    """
    shrunken = {}
    audit = {}
    for conf, members in groups.items():
        K = len(members)
        member_rates = np.array([rates[t] for t in members])
        member_n = np.array([n_obs[t] for t in members])
        mu_g = float(member_rates.mean())

        if K <= 1:
            for t in members:
                shrunken[t] = rates[t]
            audit[conf] = {
                "n_teams": K,
                "mu_g": mu_g,
                "tau_sq": None,
                "shrinkage_w_mean": 0.0,
                "reason": "single-team group, no shrinkage",
            }
            continue

        var_observed = float(member_rates.var(ddof=1))
        sigma_sq = var_observed / max(float(member_n.mean()), 1.0)
        tau_sq = max(0.0, var_observed - sigma_sq)

        weights = []
        for t, n_t in zip(members, member_n):
            if tau_sq <= 0:
                w = 1.0  # full shrinkage to prior (no true variation detected)
            else:
                w = tau_sq / (tau_sq + sigma_sq / max(n_t, 1))
            # NOTE: in standard Stein, w is on the SHRINKAGE FACTOR (toward
            # prior). Equivalent form: r_shrunk = mu + (1-w)*(r - mu).
            # We use w_shrink = sigma²/(sigma² + n*tau²) -> shrink-to-mu.
            w_shrink = (sigma_sq / max(n_t, 1)) / (
                sigma_sq / max(n_t, 1) + max(tau_sq, 1e-9)
            )
            weights.append(w_shrink)
            shrunken[t] = w_shrink * mu_g + (1 - w_shrink) * rates[t]

        audit[conf] = {
            "n_teams": K,
            "mu_g": mu_g,
            "tau_sq": tau_sq,
            "sigma_sq": sigma_sq,
            "shrinkage_w_mean": float(np.mean(weights)),
        }

    return shrunken, audit


def predict_outcome_probs(
    fit: FitResult,
    home: str,
    away: str,
) -> tuple[float, float, float]:
    """Return (P_home_win, P_draw, P_away_win) via grid over Poisson PMFs."""
    a_h = fit.attack.get(home, 0.0)
    a_a = fit.attack.get(away, 0.0)
    d_h = fit.defense.get(home, 0.0)
    d_a = fit.defense.get(away, 0.0)
    lam_h = float(np.exp(a_h - d_a + fit.home_advantage))
    lam_a = float(np.exp(a_a - d_h))

    grid = np.arange(0, MAX_GOALS_GRID + 1)
    p_h = poisson.pmf(grid, lam_h)
    p_a = poisson.pmf(grid, lam_a)
    p_h /= p_h.sum()  # normalize truncation tail.
    p_a /= p_a.sum()

    joint = np.outer(p_h, p_a)  # joint[i,j] = P(home=i, away=j)
    p_home = float(np.triu(joint, k=1).sum())  # i > j
    p_draw = float(np.diag(joint).sum())
    p_away = float(np.tril(joint, k=-1).sum())
    return p_home, p_draw, p_away


def brier_3way(
    outcome: str, p_home: float, p_draw: float, p_away: float
) -> float:
    """3-class Brier score for outcome in {H, D, A}."""
    target = {
        "H": (1.0, 0.0, 0.0),
        "D": (0.0, 1.0, 0.0),
        "A": (0.0, 0.0, 1.0),
    }[outcome]
    return (
        (p_home - target[0]) ** 2
        + (p_draw - target[1]) ** 2
        + (p_away - target[2]) ** 2
    )


def outcome_from_goals(hg: int, ag: int) -> str:
    if hg > ag:
        return "H"
    if hg == ag:
        return "D"
    return "A"


def evaluate(
    fit: FitResult, holdout_df: pl.DataFrame
) -> tuple[float, list[float]]:
    briers = []
    for row in holdout_df.iter_rows(named=True):
        p_h, p_d, p_a = predict_outcome_probs(
            fit, row["home"], row["away"]
        )
        outcome = outcome_from_goals(row["home_goals"], row["away_goals"])
        briers.append(brier_3way(outcome, p_h, p_d, p_a))
    return float(np.mean(briers)), briers


def bootstrap_paired_delta_ci(
    briers_a: list[float],
    briers_b: list[float],
    n_boot: int = 5_000,
    rng_seed: int = RNG_SEED,
) -> tuple[float, float, float]:
    """Bootstrap CI for mean(A - B). Returns (mean_delta, low_95, high_95)."""
    rng = np.random.default_rng(rng_seed)
    a = np.array(briers_a)
    b = np.array(briers_b)
    deltas = a - b
    mean_delta = float(deltas.mean())
    n = len(deltas)
    boots = np.array(
        [deltas[rng.integers(0, n, n)].mean() for _ in range(n_boot)]
    )
    return mean_delta, float(np.percentile(boots, 2.5)), float(np.percentile(boots, 97.5))


def main() -> None:
    df = load_data()
    train_df = df.filter(pl.col("tournament_slug").is_in(list(TRAIN_TOURNAMENTS)))
    holdout_df = df.filter(
        pl.col("tournament_slug").is_in(list(HOLDOUT_TOURNAMENTS))
    )
    # Hold-out teams must appear in train (else attack/defense undefined for EB).
    train_teams = set(train_df["home"].to_list()) | set(train_df["away"].to_list())
    holdout_filtered = holdout_df.filter(
        pl.col("home").is_in(list(train_teams))
        & pl.col("away").is_in(list(train_teams))
    )

    print(f"Train matches: {len(train_df)}")
    print(f"Hold-out matches (raw): {len(holdout_df)}")
    print(f"Hold-out matches (both teams in train): {len(holdout_filtered)}")

    # 1. Baseline: MLE Poisson on train.
    print("\n[1] Fitting baseline Poisson MLE...")
    baseline_fit = fit_mle_poisson(train_df)
    print(f"    home_advantage γ = {baseline_fit.home_advantage:.4f}")

    baseline_brier, baseline_briers = evaluate(baseline_fit, holdout_filtered)
    print(f"    Hold-out Brier (baseline) = {baseline_brier:.4f}")

    # 2. Compute team observation counts (for shrinkage weight).
    n_obs: dict[str, int] = defaultdict(int)
    for r in train_df.iter_rows(named=True):
        n_obs[r["home"]] += 1
        n_obs[r["away"]] += 1

    # 3. EB shrinkage.
    print("\n[2] Computing confederation × era groups + Stein shrinkage...")
    groups = group_by_confederation(list(baseline_fit.attack.keys()))
    for conf, members in groups.items():
        print(f"    {conf}: {len(members)} teams")

    shrunk_attack, attack_audit = stein_shrink(
        baseline_fit.attack, n_obs, groups
    )
    shrunk_defense, defense_audit = stein_shrink(
        baseline_fit.defense, n_obs, groups
    )

    eb_fit = FitResult(
        attack=shrunk_attack,
        defense=shrunk_defense,
        home_advantage=baseline_fit.home_advantage,
    )

    eb_brier, eb_briers = evaluate(eb_fit, holdout_filtered)
    print(f"    Hold-out Brier (EB shrunken) = {eb_brier:.4f}")

    # 4. Paired delta + bootstrap CI.
    print("\n[3] Paired delta Brier + bootstrap 95% CI...")
    delta = baseline_brier - eb_brier
    print(f"    Delta (baseline - EB) = {delta:+.4f}")
    print(f"    EB beats baseline if positive.")

    mean_delta, lo, hi = bootstrap_paired_delta_ci(baseline_briers, eb_briers)
    print(f"    Bootstrap mean delta = {mean_delta:+.4f}")
    print(f"    95% CI: [{lo:+.4f}, {hi:+.4f}]")
    sig = (lo > 0) or (hi < 0)
    print(f"    Significant (CI excludes 0)? {sig}")

    # 5. Audit summary.
    print("\n[4] Shrinkage audit per confederation × era cell:")
    for conf, info in attack_audit.items():
        w_mean = info.get("shrinkage_w_mean", 0.0)
        print(
            f"    {conf}: K={info['n_teams']} teams, "
            f"mean shrinkage w = {w_mean:.3f}"
        )

    # 6. Persist results.
    results = {
        "spike_id": "eb_shrinkage_v3_01",
        "n_train_matches": len(train_df),
        "n_holdout_matches": len(holdout_filtered),
        "baseline_brier": baseline_brier,
        "eb_brier": eb_brier,
        "delta_baseline_minus_eb": delta,
        "bootstrap_mean_delta": mean_delta,
        "bootstrap_ci_95": [lo, hi],
        "significant_at_95": sig,
        "home_advantage": baseline_fit.home_advantage,
        "attack_shrinkage_audit": {
            conf: {k: v for k, v in info.items() if k != "tau_sq" or v is not None}
            for conf, info in attack_audit.items()
        },
        "defense_shrinkage_audit": {
            conf: {k: v for k, v in info.items() if k != "tau_sq" or v is not None}
            for conf, info in defense_audit.items()
        },
    }
    OUTPUT_PATH.write_text(json.dumps(results, indent=2))
    print(f"\nResults written: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
