"""Replay a shadow-log day using the v3 engine AS COMMITTED — no monkey-patches.

Defaults to Day-4 (2026-05-13). The V3Pipeline runs end-to-end on each
historical GSV frame, so the T1 dedup filter applies and the headline
pick count reflects production behaviour going forward.

This is purely additive read-only against the existing shadow log; no
production code is touched, no new pkl written.
"""
from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import polars as pl  # noqa: E402

from bip.evaluation.live.engine_v3.archetypes import generate_theses  # noqa: E402
from bip.evaluation.live.engine_v3.conditional_predictor import (  # noqa: E402
    ConditionalPredictor,
)
from bip.evaluation.live.engine_v3.gsv import GameStateVector  # noqa: E402
from bip.evaluation.live.engine_v3.mispricing_window import (  # noqa: E402
    MispricingWindowConfig,
)
from bip.evaluation.live.engine_v3.ood_detector import OODDetector  # noqa: E402
from bip.evaluation.live.engine_v3.pipeline import V3Pipeline  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--src",
        type=Path,
        default=Path("data/cache/v3_shadow/dt=2026-05-13/gsv_log.parquet"),
    )
    parser.add_argument(
        "--ood",
        type=Path,
        default=Path("data/cache/ood_detector_v2_real.pkl"),
    )
    args = parser.parse_args()

    df = pl.read_parquet(args.src)
    gsvs = [GameStateVector.model_validate_json(s) for s in df["gsv_json"]]
    print(f"Loaded {len(gsvs)} GSVs from {len({g.fixture_id for g in gsvs})} fixtures")

    ood = OODDetector.load(args.ood) if args.ood.exists() else None
    if ood:
        print(f"OOD v2 loaded: n_train={ood.n_train} threshold={ood.threshold:.3f}")

    # Phase-2: load isotonic calibrator if present
    from bip.evaluation.live.engine_v3.calibrator import IsotonicCalibrator
    cal_path = Path("data/cache/isotonic_calibrator_v1.pkl")
    calibrator = None
    if cal_path.exists():
        calibrator = IsotonicCalibrator.load(cal_path)
        print(f"Calibrator loaded: {len(calibrator.per_cell)} cells, "
              f"{len(calibrator.per_family)} families")

    # Phase-2: warm-up drift monitor from v2 history
    from bip.evaluation.live.engine_v3.drift_monitor import (
        CalibrationDriftMonitor,
    )
    drift_monitor = CalibrationDriftMonitor()
    v2_picks_path = Path("reports/sportmonks_live/exports/picks_graded.parquet")
    if v2_picks_path.exists():
        n_seeded = drift_monitor.warm_up_from_v2_history(v2_picks_path)
        drifted = drift_monitor.drifted_cells()
        print(f"Drift monitor warmed: n_seeded={n_seeded}, drifted_cells={len(drifted)}")
        for s in drifted:
            print(f"  DRIFTED: {s.family}@{s.minute_bucket}  pred={s.expected_win_rate:.2f} "
                  f"actual={s.empirical_win_rate:.2f}  ks_p={s.ks_p_value:.4f}  n={s.n}")

    predictor = ConditionalPredictor.default(calibrator=calibrator)
    win_cfg = MispricingWindowConfig()
    pipeline = V3Pipeline(
        conditional_predictor=predictor,
        ood_detector=ood,
        drift_monitor=drift_monitor,
        mispricing_window_cfg=win_cfg,
    )

    total_candidates = 0
    total_allowed = 0
    total_deduped = 0
    per_archetype: Counter[str] = Counter()
    per_family: Counter[str] = Counter()
    deny_by_rule: Counter[str] = Counter()
    ood_skips = 0
    anti_napoli_violations: list[dict] = []
    fixtures_with_picks: set[int] = set()
    picks_per_fixture: Counter[int] = Counter()
    sample: list[dict] = []
    name_by_fid: dict[int, str] = {}

    # Sort by fixture_id + state_version so dedup state behaves like
    # production (sequential frame ordering per fixture).
    gsvs_sorted = sorted(gsvs, key=lambda g: (g.fixture_id, g.state_version))

    for g in gsvs_sorted:
        name_by_fid[g.fixture_id] = f"{g.home_team_name} vs {g.away_team_name}"
        out = pipeline.run_on_gsv(g)
        total_candidates += len(out.candidates)
        total_deduped += out.deduped_count
        if out.gate_results and all(
            not r.verdict.allowed and r.verdict.rule_number == 9
            for r in out.gate_results
        ):
            ood_skips += 1
        for r in out.gate_results:
            if not r.verdict.allowed:
                deny_by_rule[f"rule_{r.verdict.rule_number}"] += 1
        for pick in out.allowed_picks:
            total_allowed += 1
            fixtures_with_picks.add(g.fixture_id)
            picks_per_fixture[g.fixture_id] += 1
            arch = pick.candidate.thesis.archetype.value
            fam = pick.candidate.family.value
            per_archetype[arch] += 1
            per_family[fam] += 1
            direction = pick.candidate.thesis.prediction.direction
            if (
                g.score.dominant_losing
                and direction in ("under", "no")
                and arch != "cruise_mode"
            ):
                anti_napoli_violations.append(
                    {
                        "fixture_id": g.fixture_id,
                        "minute": g.time.minute,
                        "score": f"{g.score.home_goals}-{g.score.away_goals}",
                        "archetype": arch,
                        "market_id": pick.candidate.market_id,
                    }
                )
            if len(sample) < 30:
                sample.append(
                    {
                        "fid": g.fixture_id,
                        "match": f"{g.home_team_name} vs {g.away_team_name}",
                        "min": g.time.minute,
                        "score": f"{g.score.home_goals}-{g.score.away_goals}",
                        "dom_los": g.score.dominant_losing,
                        "arch": arch,
                        "market": pick.candidate.market_id,
                        "dir": direction,
                        "mes": round(pick.candidate.mes.score, 2),
                        "edge": round(pick.candidate.mes.base_edge, 3),
                        "fair_p": round(pick.candidate.fair_prob, 3),
                    }
                )

    print()
    print("=" * 80)
    print(f"REPLAY OF {args.src.parent.name} WITH COMMITTED FIXES — DEDUP'D")
    print("=" * 80)
    print(f"  total candidates produced:     {total_candidates}")
    print(f"  total ALLOWED picks (unique):  {total_allowed}")
    print(f"  deduped re-emissions:          {total_deduped}")
    print(f"  fixtures with at least 1 pick: {len(fixtures_with_picks)} / "
          f"{len({g.fixture_id for g in gsvs_sorted})}")
    print(f"  OOD short-circuit frames:      {ood_skips}")
    print(f"  anti-Napoli violations:        {len(anti_napoli_violations)}")
    print()
    print(f"Per-archetype:  {dict(per_archetype.most_common())}")
    print(f"Per-family:     {dict(per_family.most_common())}")
    print(f"Denied by rule: {dict(deny_by_rule)}")
    print()
    print("Picks per fixture (top 10):")
    for fid, n in picks_per_fixture.most_common(10):
        print(f"  {fid}  {name_by_fid.get(fid, '?'):<55}  {n} picks")
    print()
    print("First 30 picks:")
    for p in sample:
        match = (p["match"][:38] + "…") if len(p["match"]) > 39 else p["match"]
        print(
            f"  fid={p['fid']}  {match:<40}  "
            f"min={p['min']:>3}  {p['score']}  "
            f"{'(DOM_LOS)' if p['dom_los'] else '         '}  "
            f"{p['arch']:<28} {p['market'][:38]:<38}  "
            f"dir={p['dir']:<5}  mes={p['mes']:<6}  edge={p['edge']:<6}  fp={p['fair_p']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
