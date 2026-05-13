"""Replay Day-3 (2026-05-12) using the v3 engine AS COMMITTED — no monkey-patches.

This isolates "what would the production watch loop have emitted today
if the fixes in commits 468d257 / 6ec9dbb / 3f7d821 were live"?

Runs ``V3Pipeline().run()`` (default constructor — picks up the new
``line_max_age_sec=300`` default, the patched ``liquidity_score``, the
relaxed A3/A5 thresholds), wired with the OOD v2 detector. Sources GSVs
from ``data/cache/v3_shadow/dt=2026-05-12/gsv_log.parquet``.

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
    make_fair_prob_provider,
)
from bip.evaluation.live.engine_v3.gsv import GameStateVector  # noqa: E402
from bip.evaluation.live.engine_v3.market_selector import select_markets  # noqa: E402
from bip.evaluation.live.engine_v3.mispricing_window import (  # noqa: E402
    MispricingWindowConfig,
)
from bip.evaluation.live.engine_v3.no_bet_gate import run_gate  # noqa: E402
from bip.evaluation.live.engine_v3.ood_detector import OODDetector  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--src",
        type=Path,
        default=Path("data/cache/v3_shadow/dt=2026-05-12/gsv_log.parquet"),
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

    predictor = ConditionalPredictor.default(calibrator=calibrator)
    provider = make_fair_prob_provider(predictor)
    win_cfg = MispricingWindowConfig()

    # NOTE: defaults come from the committed code — target_stake=100,
    # mes_threshold=0.6, line_max_age_sec=300 (just changed in 6ec9dbb).
    total_candidates = 0
    total_allowed = 0
    per_archetype: Counter[str] = Counter()
    per_family: Counter[str] = Counter()
    deny_by_rule: Counter[str] = Counter()
    ood_skips = 0
    anti_napoli_violations: list[dict] = []
    fixtures_with_picks: set[int] = set()
    picks_per_fixture: Counter[int] = Counter()
    sample: list[dict] = []
    name_by_fid: dict[int, str] = {}

    for g in gsvs:
        name_by_fid[g.fixture_id] = f"{g.home_team_name} vs {g.away_team_name}"
        theses = generate_theses(g)
        if not theses:
            continue
        candidates = select_markets(
            theses, g, provider, top_k=3, target_stake=100.0, mes_threshold=0.6
        )
        total_candidates += len(candidates)
        if not candidates:
            continue
        gate_results = run_gate(
            theses,
            candidates,
            g,
            mes_threshold=0.6,
            line_max_age_sec=300.0,
            commentary_required=False,
            uncertainty_band=0.08,
            ood_detector=ood,
            mispricing_window_cfg=win_cfg,
        )
        # OOD short-circuits → all denied with rule 9. Detect.
        if gate_results and all(
            not r.verdict.allowed and r.verdict.rule_number == 9 for r in gate_results
        ):
            ood_skips += 1
        for r in gate_results:
            if r.verdict.allowed:
                total_allowed += 1
                fixtures_with_picks.add(g.fixture_id)
                picks_per_fixture[g.fixture_id] += 1
                arch = r.candidate.thesis.archetype.value
                fam = r.candidate.family.value
                per_archetype[arch] += 1
                per_family[fam] += 1
                direction = r.candidate.thesis.prediction.direction
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
                            "market_id": r.candidate.market_id,
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
                            "market": r.candidate.market_id,
                            "dir": direction,
                            "mes": round(r.candidate.mes.score, 2),
                            "edge": round(r.candidate.mes.base_edge, 3),
                            "fair_p": round(r.candidate.fair_prob, 3),
                        }
                    )
            else:
                deny_by_rule[f"rule_{r.verdict.rule_number}"] += 1

    print()
    print("=" * 80)
    print(f"REPLAY OF 2026-05-12 WITH COMMITTED FIXES (no monkey-patches)")
    print("=" * 80)
    print(f"  total candidates produced:     {total_candidates}")
    print(f"  total ALLOWED picks:           {total_allowed}")
    print(f"  fixtures with at least 1 pick: {len(fixtures_with_picks)} / 20")
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
