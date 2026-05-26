"""Re-run backtest with shrinkage λ × 0.85 + diagnostic isotonic on Euro24.

Two corrections evaluated:
  A) λ shrinkage: multiply both home and away λ's by 0.85 before bivariate
     grid. Addresses the observed bias of over-predicting goals (predicted
     O2.5 ≈58.8% vs real ≈37.9%).
  B) Isotonic calibration on Euro24 (n=24): IN-SAMPLE training, applied
     to all 29 fixtures. Diagnostic only — overfits on small n.

Reports comparison:
  - Original (no correction)
  - + shrinkage 0.85
  - + shrinkage 0.85 + isotonic Euro24

Output: data/cache/tsp/backtest_reports/calibration_diagnostic.md
"""
from __future__ import annotations

import json
import sys
from dataclasses import replace
from pathlib import Path

import numpy as np

from bip.evaluation.tournaments.team_style_profiler.backtest.isotonic_calibrator import (
    IsotonicCalibrator,
)
from bip.evaluation.tournaments.team_style_profiler.backtest.metrics import (
    MARKET_BRIER_GATES,
    BacktestMetrics,
    MarketMetrics,
    brier_score,
    expected_calibration_error,
    hit_rate,
    market_passes_brier_gate,
)
from bip.evaluation.tournaments.team_style_profiler.backtest.runner import (
    HistoricalFixture,
    _market_outcome,
)
from bip.evaluation.tournaments.team_style_profiler.bettable_profile import (
    BettableProfile,
    from_confederation_cohort,
    from_tsv,
)
from bip.evaluation.tournaments.team_style_profiler.coach_history import (
    get_current_coach,
)
from bip.evaluation.tournaments.team_style_profiler.confederation_cohort import (
    build_confederation_cohort,
)
from bip.evaluation.tournaments.team_style_profiler.cross_team_predictor import (
    MarketPredictions,
    MarketProb,
    derive_lambdas,
    predict_asian_handicap,
    predict_btts,
    predict_over_corners,
    predict_over_cards,
    predict_over_under_goals,
)
from bip.evaluation.tournaments.team_style_profiler.predictor_helpers import (
    bivariate_poisson_grid,
)
from bip.evaluation.tournaments.team_style_profiler.tsv_schema import (
    TeamStyleVector,
)


ROOT = Path(__file__).resolve().parents[3]
TEAM_IDS_PATH = ROOT / "data" / "cache" / "tsp" / "team_ids.json"
TOURNAMENTS_DIR = ROOT / "data" / "cache" / "tsp" / "tournaments"
PROFILES_BT_DIR = ROOT / "data" / "cache" / "tsp" / "profiles_backtest"
REPORTS_DIR = ROOT / "data" / "cache" / "tsp" / "backtest_reports"

TOURNAMENTS = ["AFCON_2023", "Copa_2024", "Euro_2024"]
SHRINKAGE = 0.85


def predict_markets_shrunk(
    home: BettableProfile,
    away: BettableProfile,
    lambda_scale: float = SHRINKAGE,
    rho: float = 0.0,
) -> MarketPredictions:
    """Same as predict_markets but applies lambda_scale to derived λ's."""
    lam_h, lam_a = derive_lambdas(home, away)
    lam_h *= lambda_scale
    lam_a *= lambda_scale
    grid = bivariate_poisson_grid(lam_h, lam_a, rho=rho)

    btts_yes, btts_no = predict_btts(home, away, grid)
    o25, u25 = predict_over_under_goals(home, away, grid, 2.5)
    o35, _ = predict_over_under_goals(home, away, grid, 3.5)

    return MarketPredictions(
        home_team=home.team_name, away_team=away.team_name,
        home_source=home.source, away_source=away.source,
        over_2_5=o25, over_3_5=o35, under_2_5=u25,
        btts_yes=btts_yes, btts_no=btts_no,
        corners_over_8_5=predict_over_corners(home, away, 8.5),
        corners_over_9_5=predict_over_corners(home, away, 9.5),
        corners_over_10_5=predict_over_corners(home, away, 10.5),
        cards_over_3_5=predict_over_cards(home, away, 3.5),
        cards_over_4_5=predict_over_cards(home, away, 4.5),
        cards_over_5_5=predict_over_cards(home, away, 5.5),
        ah_home_minus_0_5=predict_asian_handicap(home, away, grid, -0.5, "home"),
        ah_home_minus_1_5=predict_asian_handicap(home, away, grid, -1.5, "home"),
        ah_away_minus_0_5=predict_asian_handicap(home, away, grid, -0.5, "away"),
        ah_away_minus_1_5=predict_asian_handicap(home, away, grid, -1.5, "away"),
        lambda_home=lam_h, lambda_away=lam_a,
    )


def load_profiles(tournament: str) -> dict[str, TeamStyleVector]:
    out = {}
    folder = PROFILES_BT_DIR / tournament
    if not folder.exists():
        return out
    for f in folder.glob("*_tsv.json"):
        tsv = TeamStyleVector.model_validate_json(f.read_text())
        out[tsv.team_name] = tsv
    return out


def conf_of(team_id: int, team_ids_by_id) -> str | None:
    n = team_ids_by_id.get(team_id)
    if not n:
        return None
    r = get_current_coach(n)
    return r.confederation if r else None


def get_profile(name, team_id, tsv_by_name, cohorts, team_ids_by_id):
    if name in tsv_by_name and tsv_by_name[name].flag in ("green", "yellow"):
        return from_tsv(tsv_by_name[name])
    conf = conf_of(team_id, team_ids_by_id)
    if conf and conf in cohorts:
        return cohorts[conf]
    return None


def build_fixtures(tournament: str, team_ids_by_id):
    tsv_by_name = load_profiles(tournament)
    all_tsvs = list(tsv_by_name.values())
    cohorts = {}
    for conf in {t.confederation for t in all_tsvs}:
        c = build_confederation_cohort(conf, all_tsvs)
        if c:
            cohorts[conf] = from_confederation_cohort(c)

    fixtures_data = json.loads((TOURNAMENTS_DIR / f"{tournament}_fixtures.json").read_text())
    fixtures = []
    for fx in fixtures_data:
        if not fx["is_finished"]:
            continue
        home_name = team_ids_by_id.get(fx["home_team_id"])
        away_name = team_ids_by_id.get(fx["away_team_id"])
        hp = get_profile(home_name, fx["home_team_id"], tsv_by_name, cohorts, team_ids_by_id)
        ap = get_profile(away_name, fx["away_team_id"], tsv_by_name, cohorts, team_ids_by_id)
        if hp is None or ap is None:
            continue
        fixtures.append(HistoricalFixture(
            fixture_id=fx["fixture_id"],
            home_profile=hp, away_profile=ap,
            home_goals=fx["home_goals"] or 0,
            away_goals=fx["away_goals"] or 0,
        ))
    return fixtures, tournament


def run_with_predictor(fixtures, predictor_fn) -> dict[str, tuple[list[float], list[int]]]:
    """Run predictions; return market -> (probs, outcomes)."""
    market_data: dict[str, tuple[list[float], list[int]]] = {}
    for fix in fixtures:
        preds = predictor_fn(fix.home_profile, fix.away_profile)
        for mp in preds.all_markets:
            out = _market_outcome(mp.market, fix)
            if out is None:
                continue
            market_data.setdefault(mp.market, ([], []))
            market_data[mp.market][0].append(mp.probability)
            market_data[mp.market][1].append(out)
    return market_data


def metrics_from_data(market_data) -> dict[str, MarketMetrics]:
    out = {}
    for market, (probs, outcomes) in market_data.items():
        p = np.asarray(probs, dtype=float)
        y = np.asarray(outcomes, dtype=float)
        b = brier_score(p, y)
        out[market] = MarketMetrics(
            market=market, n=len(p), brier=b,
            ece=expected_calibration_error(p, y),
            hit_rate=hit_rate(p, y),
            mean_predicted=float(p.mean()), mean_outcome=float(y.mean()),
            passes_brier_gate=market_passes_brier_gate(market, b),
        )
    return out


def main() -> int:
    team_ids = json.loads(TEAM_IDS_PATH.read_text())
    team_ids_by_id = {rec["id"]: name for name, rec in team_ids.items() if rec.get("id")}

    # Collect all fixtures (each tournament + combined)
    all_fixtures: list[HistoricalFixture] = []
    by_tournament: dict[str, list[HistoricalFixture]] = {}
    for t in TOURNAMENTS:
        fxs, _ = build_fixtures(t, team_ids_by_id)
        by_tournament[t] = fxs
        all_fixtures.extend(fxs)

    print(f"Total fixtures scoreable: {len(all_fixtures)}")
    print(f"  AFCON23={len(by_tournament['AFCON_2023'])}, "
          f"Copa24={len(by_tournament['Copa_2024'])}, "
          f"Euro24={len(by_tournament['Euro_2024'])}")

    # Baseline (no correction)
    from bip.evaluation.tournaments.team_style_profiler.cross_team_predictor import predict_markets
    print("\n=== Baseline (no shrinkage) ===")
    baseline_data = run_with_predictor(all_fixtures, lambda h, a: predict_markets(h, a))
    baseline_metrics = metrics_from_data(baseline_data)
    for m, mm in sorted(baseline_metrics.items()):
        status = "PASS" if mm.passes_brier_gate else "FAIL"
        print(f"  {m:18}: Brier={mm.brier:.4f} (gate {MARKET_BRIER_GATES.get(m, '?')}) "
              f"E[p]={mm.mean_predicted:.3f} E[y]={mm.mean_outcome:.3f} → {status}")

    # Shrinkage 0.85
    print(f"\n=== Shrinkage λ × {SHRINKAGE} ===")
    shrunk_data = run_with_predictor(all_fixtures, lambda h, a: predict_markets_shrunk(h, a, lambda_scale=SHRINKAGE))
    shrunk_metrics = metrics_from_data(shrunk_data)
    for m, mm in sorted(shrunk_metrics.items()):
        status = "PASS" if mm.passes_brier_gate else "FAIL"
        delta = mm.brier - baseline_metrics[m].brier
        sign = "↓" if delta < 0 else "↑"
        print(f"  {m:18}: Brier={mm.brier:.4f} {sign}{abs(delta):.4f} "
              f"E[p]={mm.mean_predicted:.3f} E[y]={mm.mean_outcome:.3f} → {status}")

    # Isotonic in-sample on Euro24 → apply globally (warning: leakage)
    print(f"\n=== Shrinkage + Isotonic (fit on Euro24, IN-SAMPLE) ===")
    euro_data_shrunk = run_with_predictor(
        by_tournament["Euro_2024"],
        lambda h, a: predict_markets_shrunk(h, a, lambda_scale=SHRINKAGE),
    )
    cal = IsotonicCalibrator()
    for market in ["BTTS_yes", "BTTS_no", "O2.5", "U2.5", "O3.5"]:
        if market in euro_data_shrunk and len(euro_data_shrunk[market][0]) >= 10:
            cal.fit(market, np.asarray(euro_data_shrunk[market][0]),
                    np.asarray(euro_data_shrunk[market][1]))

    # Apply calibration to ALL fixtures
    cal_data: dict[str, tuple[list[float], list[int]]] = {}
    for fix in all_fixtures:
        preds = predict_markets_shrunk(fix.home_profile, fix.away_profile, lambda_scale=SHRINKAGE)
        for mp in preds.all_markets:
            out = _market_outcome(mp.market, fix)
            if out is None:
                continue
            p_cal = cal.calibrate(mp.market, mp.probability)
            cal_data.setdefault(mp.market, ([], []))
            cal_data[mp.market][0].append(p_cal)
            cal_data[mp.market][1].append(out)
    cal_metrics = metrics_from_data(cal_data)
    for m, mm in sorted(cal_metrics.items()):
        status = "PASS" if mm.passes_brier_gate else "FAIL"
        delta = mm.brier - baseline_metrics[m].brier
        sign = "↓" if delta < 0 else "↑"
        print(f"  {m:18}: Brier={mm.brier:.4f} {sign}{abs(delta):.4f} "
              f"E[p]={mm.mean_predicted:.3f} E[y]={mm.mean_outcome:.3f} → {status}")

    # Summary table
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    summary_lines = [
        "# TSP Backtest — Calibration Diagnostic",
        "",
        f"Fixtures: {len(all_fixtures)} (n=29: AFCON 1, Copa 4, Euro 24)",
        f"Shrinkage tested: λ × {SHRINKAGE}",
        "",
        "## Per-market Brier comparison",
        "",
        "| Market | Gate | Baseline | + Shrinkage | + Iso(Euro IS) |",
        "|--------|------|----------|-------------|----------------|",
    ]
    for m in sorted(baseline_metrics.keys()):
        gate = MARKET_BRIER_GATES.get(m, "?")
        b = baseline_metrics[m].brier
        s = shrunk_metrics[m].brier if m in shrunk_metrics else "?"
        c = cal_metrics[m].brier if m in cal_metrics else "?"
        summary_lines.append(
            f"| {m} | {gate} | {b:.4f} | "
            f"{s:.4f}{' ✓' if shrunk_metrics[m].passes_brier_gate else ''} | "
            f"{c:.4f}{' ✓' if cal_metrics[m].passes_brier_gate else ''} |"
        )
    out_path = REPORTS_DIR / "calibration_diagnostic.md"
    out_path.write_text("\n".join(summary_lines))
    print(f"\nSaved: {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
