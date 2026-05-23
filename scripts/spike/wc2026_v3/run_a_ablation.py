"""Ola 2.A — A (Transfermarkt) paired-ΔBrier ablation on n=199 hold-out.

Compares two predictor configurations on the IMMOVABLE 4-tournament hold-out
(WC2022 + AFCON2023 + Copa2024 + Euro2024 = 199 matches):

- ``baseline`` — v2's full pipeline WITHOUT market-value injection
- ``with_mv`` — v2's full pipeline WITH market-value offsets (Peeters 2018)

Both configurations share identical:
- strength prior (weighted-MLE on 49k martj42 minus hold-out tournaments)
- DIBP toggle (per ablation matrix; default ON to mirror v2 production)
- beta calibrators (per ablation matrix; default ON)
- match-importance weighting (per ablation matrix; default ON)
- bootstrap seed (42), n_resamples (2000)

The ONLY difference is whether market-value offsets are injected into
``CalibratedDIBPPredictor`` via the Wave 1.A.2 pipeline toggle.

Verdict per v2 PLAN.md quality gates (inherited verbatim):
- Gate 3: paired-ΔBrier ≥ +0.005 (i.e. baseline_brier − mv_brier ≥ 0.005)
  with bootstrap CI not crossing 0
- Gate 4: pass on ≥ 2 of 4 hold-out tournaments

Output:
- ``data/cache/wc2026_v3/a_ablation_report.json`` — structured numbers
  for downstream consumption (Ola 3.E ensemble integration + Ola 3.F
  lock_v3 audit metadata)
- ``Papers/WC2026_V3_A_ABLATION.md`` — human-readable verdict +
  per-tournament breakdown (gitignored — local working notes)

Usage:

    # Default β_mv = 0.10
    uv run python scripts/spike/wc2026_v3/run_a_ablation.py \\
        --market-values-path data/cache/transfermarkt/squad_values_current.parquet

    # Sweep over a β_mv grid (writes one JSON per beta)
    uv run python scripts/spike/wc2026_v3/run_a_ablation.py \\
        --market-values-path data/cache/transfermarkt/squad_values_current.parquet \\
        --beta-sweep 0.05 0.10 0.15 0.20

    # Faster: skip beta-calibration + DIBP (matches v2 'baseline' ablation
    # cell which already converged to no-effect per v2 spike)
    uv run python scripts/spike/wc2026_v3/run_a_ablation.py \\
        --market-values-path ... --no-dibp --no-beta-cal --no-match-importance

The beta-sweep mode is the principled way to PICK β_mv: run each on the
n=115 calibration corpus (NOT the n=199 hold-out — that would be
leakage). Lowest paired-ΔBrier on calibration wins; THAT β is then
locked for the hold-out evaluation. Default 0.10 is a heuristic guess
pending the sweep.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np

from bip.evaluation.tournaments.wc2026_v2.backtest import (
    bootstrap_ci,
    run_walk_forward_backtest,
)
from bip.evaluation.tournaments.wc2026_v2.corpus import build_split


@dataclass
class AblationReport:
    """Structured output for Ola 2.A's verdict."""

    beta_mv: float
    market_values_path: str

    n_heldout: int
    n_calibration: int
    n_train: int

    # Brier on lock convention (1X2 divided by K=3)
    baseline_brier_1x2_point: float
    baseline_brier_1x2_ci_lower: float
    baseline_brier_1x2_ci_upper: float
    baseline_ece_1x2: float

    with_mv_brier_1x2_point: float
    with_mv_brier_1x2_ci_lower: float
    with_mv_brier_1x2_ci_upper: float
    with_mv_ece_1x2: float

    # Paired delta = baseline - with_mv (positive = MV helps)
    delta_brier_1x2_point: float
    delta_brier_1x2_ci_lower: float
    delta_brier_1x2_ci_upper: float
    delta_significant: bool  # CI does NOT cross zero

    # Per-tournament breakdown (slug → point Brier)
    per_tournament_baseline: dict[str, float]
    per_tournament_with_mv: dict[str, float]
    per_tournament_delta: dict[str, float]
    n_tournaments_mv_better: int

    # Inherited from v2 PLAN.md quality gates
    gate_brier_ci_upper_max: float = 0.21
    gate_ece_max: float = 0.05
    gate_brier_improvement_min: float = 0.005
    gate_tournament_pass_count_min: int = 2

    # Derived gate verdicts
    @property
    def gate_1_brier_ci_upper(self) -> bool:
        return self.with_mv_brier_1x2_ci_upper < self.gate_brier_ci_upper_max

    @property
    def gate_2_ece(self) -> bool:
        return self.with_mv_ece_1x2 < self.gate_ece_max

    @property
    def gate_3_brier_improvement(self) -> bool:
        return (
            self.delta_brier_1x2_point >= self.gate_brier_improvement_min
            and self.delta_significant
        )

    @property
    def gate_4_tournament_pass(self) -> bool:
        return self.n_tournaments_mv_better >= self.gate_tournament_pass_count_min

    @property
    def verdict(self) -> str:
        if all(
            [
                self.gate_1_brier_ci_upper,
                self.gate_2_ece,
                self.gate_3_brier_improvement,
                self.gate_4_tournament_pass,
            ]
        ):
            return "PASS"
        if self.gate_3_brier_improvement:
            return "SHADOW-only"
        return "FAIL"


def run_ablation(
    market_values_path: str,
    beta_mv: float,
    *,
    n_bootstrap: int = 2000,
    seed: int = 42,
    use_dibp: bool = True,
    use_beta_calibration: bool = True,
    use_match_importance: bool = True,
) -> AblationReport:
    """Run the paired-ΔBrier ablation and return a structured report."""

    split = build_split()
    n_heldout = split.heldout.height
    n_calibration = split.calibration.height
    n_train = split.train.height

    print(f"Corpus: train={n_train} | cal={n_calibration} | heldout={n_heldout}")
    print(
        f"Configs: use_dibp={use_dibp} use_beta_cal={use_beta_calibration} "
        f"use_match_importance={use_match_importance} β_mv={beta_mv}"
    )

    print("\n[1/2] baseline (no market-value)...")
    baseline = run_walk_forward_backtest(
        train=split.train,
        calibration=split.calibration,
        heldout=split.heldout,
        n_bootstrap=n_bootstrap,
        seed=seed,
        use_dibp=use_dibp,
        use_beta_calibration=use_beta_calibration,
        use_match_importance=use_match_importance,
        use_market_value=False,
    )
    print(f"  Brier 1X2: {baseline.overall_brier_1x2}")
    print(f"  ECE  1X2: {baseline.overall_ece_1x2:.4f}")

    print("\n[2/2] with market_value...")
    with_mv = run_walk_forward_backtest(
        train=split.train,
        calibration=split.calibration,
        heldout=split.heldout,
        n_bootstrap=n_bootstrap,
        seed=seed,
        use_dibp=use_dibp,
        use_beta_calibration=use_beta_calibration,
        use_match_importance=use_match_importance,
        use_market_value=True,
        market_values_path=market_values_path,
        market_value_beta=beta_mv,
    )
    print(f"  Brier 1X2: {with_mv.overall_brier_1x2}")
    print(f"  ECE  1X2: {with_mv.overall_ece_1x2:.4f}")

    # Paired-ΔBrier: baseline_per_fixture - with_mv_per_fixture
    # Positive = MV reduces Brier (helps).
    baseline_per_fixture = np.concatenate(
        [m.per_fixture_brier_1x2 for m in baseline.per_tournament.values()]
    )
    with_mv_per_fixture = np.concatenate(
        [m.per_fixture_brier_1x2 for m in with_mv.per_tournament.values()]
    )
    assert baseline_per_fixture.shape == with_mv_per_fixture.shape
    paired = baseline_per_fixture - with_mv_per_fixture
    delta_ci = bootstrap_ci(paired, n_resamples=n_bootstrap, seed=seed + 200)
    delta_significant = not (delta_ci.lower <= 0.0 <= delta_ci.upper)

    # Per-tournament breakdown
    per_baseline = {
        slug: m.brier_1x2.point for slug, m in baseline.per_tournament.items()
    }
    per_mv = {slug: m.brier_1x2.point for slug, m in with_mv.per_tournament.items()}
    per_delta = {slug: per_baseline[slug] - per_mv[slug] for slug in per_baseline}
    n_better = sum(1 for d in per_delta.values() if d > 0)

    return AblationReport(
        beta_mv=beta_mv,
        market_values_path=market_values_path,
        n_heldout=n_heldout,
        n_calibration=n_calibration,
        n_train=n_train,
        baseline_brier_1x2_point=baseline.overall_brier_1x2.point,
        baseline_brier_1x2_ci_lower=baseline.overall_brier_1x2.lower,
        baseline_brier_1x2_ci_upper=baseline.overall_brier_1x2.upper,
        baseline_ece_1x2=baseline.overall_ece_1x2,
        with_mv_brier_1x2_point=with_mv.overall_brier_1x2.point,
        with_mv_brier_1x2_ci_lower=with_mv.overall_brier_1x2.lower,
        with_mv_brier_1x2_ci_upper=with_mv.overall_brier_1x2.upper,
        with_mv_ece_1x2=with_mv.overall_ece_1x2,
        delta_brier_1x2_point=delta_ci.point,
        delta_brier_1x2_ci_lower=delta_ci.lower,
        delta_brier_1x2_ci_upper=delta_ci.upper,
        delta_significant=delta_significant,
        per_tournament_baseline=per_baseline,
        per_tournament_with_mv=per_mv,
        per_tournament_delta=per_delta,
        n_tournaments_mv_better=n_better,
    )


def write_report_md(report: AblationReport, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    g1 = "✓" if report.gate_1_brier_ci_upper else "✗"
    g2 = "✓" if report.gate_2_ece else "✗"
    g3 = "✓" if report.gate_3_brier_improvement else "✗"
    g4 = "✓" if report.gate_4_tournament_pass else "✗"

    rows = []
    for slug in sorted(report.per_tournament_baseline):
        b = report.per_tournament_baseline[slug]
        m = report.per_tournament_with_mv[slug]
        d = report.per_tournament_delta[slug]
        rows.append(f"| {slug} | {b:.4f} | {m:.4f} | {d:+.4f} |")
    per_tournament_table = "\n".join(rows)

    body = f"""# Ola 2.A — Transfermarkt Market-Value Ablation

**Automated.** Regenerated by
`scripts/spike/wc2026_v3/run_a_ablation.py`.

## Verdict

**{report.verdict}** at β_mv = {report.beta_mv}.

## Headline (lock convention — 1X2 Brier ÷ K=3)

| | baseline | with_mv | Δ (baseline − mv) |
|---|---|---|---|
| Brier point | {report.baseline_brier_1x2_point:.4f} | {report.with_mv_brier_1x2_point:.4f} | {report.delta_brier_1x2_point:+.4f} |
| Brier CI lower | {report.baseline_brier_1x2_ci_lower:.4f} | {report.with_mv_brier_1x2_ci_lower:.4f} | {report.delta_brier_1x2_ci_lower:+.4f} |
| Brier CI upper | {report.baseline_brier_1x2_ci_upper:.4f} | {report.with_mv_brier_1x2_ci_upper:.4f} | {report.delta_brier_1x2_ci_upper:+.4f} |
| ECE | {report.baseline_ece_1x2:.4f} | {report.with_mv_ece_1x2:.4f} | — |

Paired-ΔBrier CI {"DOES NOT cross zero" if report.delta_significant else "CROSSES zero"} → {"statistically significant" if report.delta_significant else "NOT significant at the 95% level"}.

## v2 Quality Gates (inherited verbatim)

| Gate | Threshold | Measured | Pass? |
|------|-----------|----------|-------|
| 1. Brier CI upper < 0.21 | with_mv | {report.with_mv_brier_1x2_ci_upper:.4f} | {g1} |
| 2. ECE < 0.05 | with_mv | {report.with_mv_ece_1x2:.4f} | {g2} |
| 3. ΔBrier ≥ 0.005 with CI not crossing 0 | delta | {report.delta_brier_1x2_point:+.4f} [{report.delta_brier_1x2_ci_lower:+.4f}, {report.delta_brier_1x2_ci_upper:+.4f}] | {g3} |
| 4. Pass on ≥ 2 of 4 tournaments | per-tournament | {report.n_tournaments_mv_better} of 4 | {g4} |

PASS requires all 4. SHADOW-only requires Gate 3 only.

## Per-tournament 1X2 Brier (lock convention)

| Tournament | baseline | with_mv | Δ |
|---|---|---|---|
{per_tournament_table}

## Reproducibility

- n_train = {report.n_train}
- n_calibration = {report.n_calibration}
- n_heldout = {report.n_heldout}
- β_mv = {report.beta_mv}
- market_values_path = `{report.market_values_path}`
- bootstrap n_resamples = 2000, seed = 42
"""
    path.write_text(body)


def write_report_json(report: AblationReport, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = asdict(report)
    # Decorate with derived gate verdicts so downstream consumers don't
    # need to re-implement the gate logic.
    payload["gate_1_brier_ci_upper"] = report.gate_1_brier_ci_upper
    payload["gate_2_ece"] = report.gate_2_ece
    payload["gate_3_brier_improvement"] = report.gate_3_brier_improvement
    payload["gate_4_tournament_pass"] = report.gate_4_tournament_pass
    payload["verdict"] = report.verdict
    path.write_text(json.dumps(payload, indent=2, sort_keys=True))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--market-values-path",
        type=str,
        default="data/cache/transfermarkt/squad_values_current.parquet",
        help="Parquet with team_name + market_value_eur columns.",
    )
    parser.add_argument(
        "--beta-mv", type=float, default=0.10, help="β_mv (default 0.10)."
    )
    parser.add_argument(
        "--beta-sweep",
        type=float,
        nargs="+",
        default=None,
        help="Run a sweep over these β values (overrides --beta-mv).",
    )
    parser.add_argument(
        "--n-bootstrap", type=int, default=2000, help="Bootstrap resamples."
    )
    parser.add_argument(
        "--seed", type=int, default=42, help="Bootstrap seed."
    )
    parser.add_argument("--no-dibp", action="store_true", help="Disable DIBP.")
    parser.add_argument(
        "--no-beta-cal", action="store_true", help="Disable beta calibration."
    )
    parser.add_argument(
        "--no-match-importance", action="store_true", help="Disable K-weighting."
    )
    parser.add_argument(
        "--output-json",
        type=Path,
        default=Path("data/cache/wc2026_v3/a_ablation_report.json"),
    )
    parser.add_argument(
        "--output-md",
        type=Path,
        default=Path("Papers/WC2026_V3_A_ABLATION.md"),
    )
    args = parser.parse_args(argv)

    use_dibp = not args.no_dibp
    use_beta_calibration = not args.no_beta_cal
    use_match_importance = not args.no_match_importance

    betas = args.beta_sweep if args.beta_sweep else [args.beta_mv]
    last_report: AblationReport | None = None
    for beta in betas:
        print(f"\n{'='*60}\nβ_mv = {beta}\n{'='*60}")
        report = run_ablation(
            market_values_path=args.market_values_path,
            beta_mv=beta,
            n_bootstrap=args.n_bootstrap,
            seed=args.seed,
            use_dibp=use_dibp,
            use_beta_calibration=use_beta_calibration,
            use_match_importance=use_match_importance,
        )
        # Per-beta filenames when sweeping
        if len(betas) > 1:
            out_json = args.output_json.with_stem(
                f"{args.output_json.stem}_beta{int(beta*100):03d}"
            )
            out_md = args.output_md.with_stem(
                f"{args.output_md.stem}_beta{int(beta*100):03d}"
            )
        else:
            out_json = args.output_json
            out_md = args.output_md
        write_report_json(report, out_json)
        write_report_md(report, out_md)
        print(f"\nβ_mv={beta} → verdict {report.verdict}")
        print(f"  ΔBrier = {report.delta_brier_1x2_point:+.4f} "
              f"[{report.delta_brier_1x2_ci_lower:+.4f}, "
              f"{report.delta_brier_1x2_ci_upper:+.4f}] "
              f"{'(significant)' if report.delta_significant else '(NS)'}")
        print(f"  Tournaments where MV helps: {report.n_tournaments_mv_better}/4")
        print(f"  JSON → {out_json}")
        print(f"  Report → {out_md}")
        last_report = report

    # Exit non-zero on FAIL so CI can branch on it.
    if last_report is None:
        return 1
    return 0 if last_report.verdict in {"PASS", "SHADOW-only"} else 2


if __name__ == "__main__":
    sys.exit(main())
