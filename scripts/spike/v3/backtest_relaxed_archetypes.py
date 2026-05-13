"""T3 — Backtest of the proposed Day-3 fixes over the 1642 real GSVs.

What this measures
==================
Given the diagnosis in `Papers/V3_DAY3_DIAGNOSIS.md`, four fixes are proposed
for live engine v3:

  Fix 1 (primary)  : liquidity_score treats max_stake_cap==1.0 (Phase-1
                     placeholder) as full liquidity (1.0). Unblocks MES.
  Fix 2 (secondary): line_max_age_sec lifted from 60s to 300s — Sportmonks
                     line update cadence has p75 ≈ 1028s; 60s admits less
                     than half of valid lines.
  Fix 3 (archetype): A3 (late_cagey_zero_zero) xG-total threshold lifted
                     from 0.6 to 1.4 — the empirical p25 of late-game 0-0
                     frames is 1.16 and median is 2.23.
  Fix 4 (archetype): A5 (regression_to_xg) |xg_diff| threshold lowered
                     from 1.5 to 0.7 — the p90 of tied-60' frames is 0.70,
                     so 1.5 captures only outliers.

Anti-Napoli (A2) window is NOT extended in this round. The risk vs reward
is unfavourable.

The script runs the pipeline twice per frame:
  - "baseline" config (mes.py and archetypes.py as currently shipped)
  - "proposed" config (monkey-patched to apply Fix 1-4)

It compares: total candidates, total allowed picks, distribution per
archetype, anti-Napoli violations (rule #2 must catch every Under +
dominant_losing case not on the allow-list).

Output:
  - `Papers/V3_RELAXATION_BACKTEST_REPORT.md` (human-readable summary)
  - `logs/v3_day3_backtest.json` (machine-readable raw output)

This script is RE-RUNNABLE. The operator can invoke it after every Day-N
to re-verify the fixes against the latest distribution.

Usage:
    uv run python scripts/spike/v3/backtest_relaxed_archetypes.py
    uv run python scripts/spike/v3/backtest_relaxed_archetypes.py --src data/cache/v3_shadow/dt=2026-05-13/gsv_log.parquet
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import polars as pl  # noqa: E402

from bip.evaluation.live.engine_v3 import mes as mes_module  # noqa: E402
from bip.evaluation.live.engine_v3 import archetypes as arch_module  # noqa: E402
from bip.evaluation.live.engine_v3.archetypes import generate_theses  # noqa: E402
from bip.evaluation.live.engine_v3.conditional_predictor import (  # noqa: E402
    ConditionalPredictor,
    make_fair_prob_provider,
)
from bip.evaluation.live.engine_v3.gsv import GameStateVector  # noqa: E402
from bip.evaluation.live.engine_v3.market_selector import select_markets  # noqa: E402
from bip.evaluation.live.engine_v3.no_bet_gate import run_gate  # noqa: E402
from bip.evaluation.live.engine_v3.ood_detector import OODDetector  # noqa: E402


# ──────────────────────────────────────────────────────────────────────
# Loading
# ──────────────────────────────────────────────────────────────────────


def load_gsvs(path: Path) -> list[GameStateVector]:
    df = pl.read_parquet(path)
    return [GameStateVector.model_validate_json(s) for s in df["gsv_json"]]


# ──────────────────────────────────────────────────────────────────────
# Monkey-patches
# ──────────────────────────────────────────────────────────────────────


def patched_liquidity_score(line, target_stake):
    """Treat the Phase-1 placeholder (max_stake_cap == 1.0) as full liquidity.

    Reasoning: dual_write.market_snapshot_from_odds hard-codes
    max_stake_cap=1.0 for every Sportmonks line because Sportmonks does
    not emit stake caps. This placeholder collides with liquidity_score's
    "cap in USD vs target_stake in USD" comparison and zeros every MES.
    Until Phase 2 wires real caps, we treat the placeholder as full
    liquidity (1.0). Genuine cap values (anything ≠ 1.0) go through the
    original schedule.
    """
    if line.max_stake_cap == 1.0:
        return 1.0
    cap = max(0.0, line.max_stake_cap)
    if cap < 0.5 * target_stake:
        return 0.0
    if cap >= 4.0 * target_stake:
        return 1.0
    return min(1.0, (cap / target_stake - 0.5) / 3.5)


_ORIGINAL_A3 = arch_module.detect_late_cagey_zero_zero
_ORIGINAL_A5 = arch_module.detect_regression_to_xg


def patched_a3(gsv: GameStateVector):
    """Relaxed A3: xg_total threshold lifted 0.6 → 1.4."""
    from bip.evaluation.live.engine_v3.archetypes import (
        CausalStep,
        GSVPredicate,
        InvalidationTrigger,
        MarketFamily,
        ThesisArchetype,
        _mk_thesis,
    )

    if (
        not (
            gsv.score.goal_diff == 0
            and gsv.score.home_goals == 0
            and gsv.time.minute >= 75
            and (gsv.xg.home_xg_total + gsv.xg.away_xg_total) < 1.4
            and gsv.tactical.game_phase == "cagey_closed"
        )
    ):
        return None
    return _mk_thesis(
        arch=ThesisArchetype.LATE_CAGEY_ZERO_ZERO,
        rule_id="A3",
        minute=gsv.time.minute,
        premise=[
            GSVPredicate(path="score.home_goals", op="eq", value=0),
            GSVPredicate(path="score.away_goals", op="eq", value=0),
            GSVPredicate(path="time.minute", op="ge", value=75),
            GSVPredicate(path="tactical.game_phase", op="eq", value="cagey_closed"),
        ],
        chain=[
            CausalStep(
                cause="both_sides_play_for_point",
                effect="match_likely_ends_no_goal",
                mechanism="commentary + xG confirm low-intent territory game",
            ),
        ],
        family=MarketFamily.GOALS,
        direction="under",
        magnitude_pp=0.07,
        horizon_label="rest_of_match",
        invalidations=[
            InvalidationTrigger(
                kind="any_goal",
                description="0-0 broken → thesis dies trivially",
            ),
            InvalidationTrigger(
                kind="red_card_dominant",
                description="red card cracks the equilibrium",
            ),
            InvalidationTrigger(
                kind="red_card_underdog",
                description="red card cracks the equilibrium",
            ),
        ],
        confidence_prior=0.64,
    )


def patched_a5(gsv: GameStateVector):
    """Relaxed A5: |xg_diff| threshold lowered 1.5 → 0.7."""
    from bip.evaluation.live.engine_v3.archetypes import (
        CausalStep,
        GSVPredicate,
        InvalidationTrigger,
        MarketFamily,
        ThesisArchetype,
        _mk_thesis,
    )

    if gsv.score.goal_diff != 0 or gsv.time.minute < 60:
        return None
    if abs(gsv.xg.xg_diff) < 0.7:
        return None
    high_xg_home = gsv.xg.xg_diff > 0
    return _mk_thesis(
        arch=ThesisArchetype.REGRESSION_TO_XG,
        rule_id="A5",
        minute=gsv.time.minute,
        premise=[
            GSVPredicate(path="score.goal_diff", op="eq", value=0),
            GSVPredicate(path="time.minute", op="ge", value=60),
            GSVPredicate(
                path="xg.xg_diff",
                op="gt" if high_xg_home else "lt",
                value=0.7 if high_xg_home else -0.7,
            ),
        ],
        chain=[
            CausalStep(
                cause="high_xg_team_underconverted",
                effect="regression_to_mean",
                mechanism="finishing variance reverts over remaining minutes",
            ),
        ],
        family=MarketFamily.NEXT_GOAL,
        direction="home" if high_xg_home else "away",
        magnitude_pp=0.07,
        horizon_label="rest_of_match",
        invalidations=[
            InvalidationTrigger(
                kind="goal_for_underdog",
                description="opposite team scores → thesis dies",
            ),
            InvalidationTrigger(
                kind="red_card_dominant",
                description="numerical loss erodes the push",
            ),
        ],
        confidence_prior=0.55,
    )


# ──────────────────────────────────────────────────────────────────────
# Run one configuration over the dataset
# ──────────────────────────────────────────────────────────────────────


def run_config(
    gsvs: list[GameStateVector],
    *,
    target_stake: float = 100.0,
    mes_threshold: float = 0.6,
    line_max_age_sec: float = 60.0,
    ood_detector: OODDetector | None = None,
    label: str = "config",
) -> dict[str, Any]:
    """Run the pipeline over every frame under the active config.

    Caller is responsible for installing/removing patches in mes_module
    and arch_module before/after calling.
    """
    predictor = ConditionalPredictor.default()
    provider = make_fair_prob_provider(predictor)
    total_candidates = 0
    total_allowed = 0
    deny_by_rule: Counter[str] = Counter()
    allowed_per_archetype: Counter[str] = Counter()
    allowed_per_market_family: Counter[str] = Counter()
    sample_allowed: list[dict[str, Any]] = []
    anti_napoli_violations: list[dict[str, Any]] = []
    frames_with_theses = 0
    frames_with_allowed = 0

    for g in gsvs:
        theses = generate_theses(g)
        if not theses:
            continue
        frames_with_theses += 1
        candidates = select_markets(
            theses,
            g,
            provider,
            top_k=3,
            target_stake=target_stake,
            mes_threshold=mes_threshold,
        )
        total_candidates += len(candidates)
        if not candidates:
            continue
        gate_results = run_gate(
            theses,
            candidates,
            g,
            mes_threshold=mes_threshold,
            line_max_age_sec=line_max_age_sec,
            commentary_required=False,
            uncertainty_band=0.08,
            ood_detector=ood_detector,
        )
        had_allowed = False
        for r in gate_results:
            if r.verdict.allowed:
                total_allowed += 1
                had_allowed = True
                allowed_per_archetype[r.candidate.thesis.archetype.value] += 1
                allowed_per_market_family[r.candidate.family.value] += 1
                direction = r.candidate.thesis.prediction.direction
                if (
                    g.score.dominant_losing
                    and direction in ("under", "no")
                    and r.candidate.thesis.archetype.value != "cruise_mode"
                ):
                    anti_napoli_violations.append(
                        {
                            "fixture_id": g.fixture_id,
                            "minute": g.time.minute,
                            "score": f"{g.score.home_goals}-{g.score.away_goals}",
                            "archetype": r.candidate.thesis.archetype.value,
                            "market_id": r.candidate.market_id,
                            "direction": direction,
                        }
                    )
                if len(sample_allowed) < 50:
                    sample_allowed.append(
                        {
                            "fixture_id": g.fixture_id,
                            "minute": g.time.minute,
                            "score": f"{g.score.home_goals}-{g.score.away_goals}",
                            "dominant_losing": g.score.dominant_losing,
                            "archetype": r.candidate.thesis.archetype.value,
                            "market_id": r.candidate.market_id,
                            "direction": direction,
                            "mes": round(r.candidate.mes.score, 3),
                            "fair_prob": round(r.candidate.fair_prob, 3),
                            "base_edge": round(r.candidate.mes.base_edge, 3),
                        }
                    )
            else:
                deny_by_rule[f"rule_{r.verdict.rule_number}"] += 1
        if had_allowed:
            frames_with_allowed += 1

    return {
        "label": label,
        "config": {
            "target_stake": target_stake,
            "mes_threshold": mes_threshold,
            "line_max_age_sec": line_max_age_sec,
            "ood_active": ood_detector is not None and ood_detector.is_fitted,
            "ood_n_train": ood_detector.n_train if ood_detector else None,
            "ood_threshold": ood_detector.threshold if ood_detector else None,
        },
        "frames_with_theses": frames_with_theses,
        "frames_with_allowed": frames_with_allowed,
        "total_candidates": total_candidates,
        "total_allowed_picks": total_allowed,
        "denied_by_rule": dict(deny_by_rule),
        "allowed_per_archetype": dict(allowed_per_archetype.most_common()),
        "allowed_per_market_family": dict(allowed_per_market_family.most_common()),
        "anti_napoli_violation_count": len(anti_napoli_violations),
        "anti_napoli_violations": anti_napoli_violations[:20],
        "sample_allowed_first_50": sample_allowed,
    }


# ──────────────────────────────────────────────────────────────────────
# Driver
# ──────────────────────────────────────────────────────────────────────


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--src",
        type=Path,
        default=Path("data/cache/v3_shadow/dt=2026-05-12/gsv_log.parquet"),
    )
    parser.add_argument(
        "--ood-v2",
        type=Path,
        default=Path("data/cache/ood_detector_v2_real.pkl"),
    )
    parser.add_argument(
        "--out-json",
        type=Path,
        default=Path("logs/v3_day3_backtest.json"),
    )
    parser.add_argument(
        "--out-report",
        type=Path,
        default=Path("Papers/V3_RELAXATION_BACKTEST_REPORT.md"),
    )
    args = parser.parse_args()

    print(f"Loading GSVs from {args.src}…")
    gsvs = load_gsvs(args.src)
    print(f"Loaded {len(gsvs)} GSVs from {len({g.fixture_id for g in gsvs})} fixtures.")

    ood_v2 = None
    if args.ood_v2.exists():
        ood_v2 = OODDetector.load(args.ood_v2)
        print(f"Loaded OOD v2: n_train={ood_v2.n_train} threshold={ood_v2.threshold:.3f}")
    else:
        print(f"WARNING: ood v2 absent at {args.ood_v2}; running with ood_detector=None")

    # 1. Baseline (no patches, no OOD)
    print("\nRun 1/3: baseline (no patches, no OOD)…")
    baseline = run_config(gsvs, label="baseline_unfixed")

    # 2. Liquidity fix only (no threshold relaxations, no OOD)
    print("\nRun 2/3: liquidity-fix only (Fix 1)…")
    orig_liq = mes_module.liquidity_score
    mes_module.liquidity_score = patched_liquidity_score
    try:
        liq_only = run_config(gsvs, label="liquidity_fix_only")
    finally:
        mes_module.liquidity_score = orig_liq

    # 3. All fixes (liquidity + line freshness + A3 + A5 + OOD v2)
    print("\nRun 3/3: full proposal (Fix 1+2+3+4 + OOD v2)…")
    mes_module.liquidity_score = patched_liquidity_score
    arch_module.detect_late_cagey_zero_zero = patched_a3
    arch_module.detect_regression_to_xg = patched_a5
    # Re-build the detector tuple so generate_theses picks up the patches.
    arch_module._ARCHETYPE_DETECTORS = (
        arch_module.detect_red_card_away_early,
        arch_module.detect_dominant_losing_napoli,
        arch_module.detect_late_cagey_zero_zero,
        arch_module.detect_lead_two_defensive_sub,
        arch_module.detect_regression_to_xg,
        arch_module.detect_cards_momentum_strict_ref,
        arch_module.detect_underdog_leads_siege,
        arch_module.detect_open_game,
        arch_module.detect_key_playmaker_off,
        arch_module.detect_second_half_reset,
        arch_module.detect_numerical_sustained,
        arch_module.detect_cruise_mode,
    )
    try:
        proposed = run_config(
            gsvs,
            line_max_age_sec=300.0,
            ood_detector=ood_v2,
            label="proposed_full",
        )
    finally:
        mes_module.liquidity_score = orig_liq
        arch_module.detect_late_cagey_zero_zero = _ORIGINAL_A3
        arch_module.detect_regression_to_xg = _ORIGINAL_A5
        arch_module._ARCHETYPE_DETECTORS = (
            arch_module.detect_red_card_away_early,
            arch_module.detect_dominant_losing_napoli,
            arch_module.detect_late_cagey_zero_zero,
            arch_module.detect_lead_two_defensive_sub,
            arch_module.detect_regression_to_xg,
            arch_module.detect_cards_momentum_strict_ref,
            arch_module.detect_underdog_leads_siege,
            arch_module.detect_open_game,
            arch_module.detect_key_playmaker_off,
            arch_module.detect_second_half_reset,
            arch_module.detect_numerical_sustained,
            arch_module.detect_cruise_mode,
        )

    # ── Persist JSON ──────────────────────────────────────────────────
    args.out_json.parent.mkdir(parents=True, exist_ok=True)
    args.out_json.write_text(
        json.dumps(
            {
                "baseline": baseline,
                "liquidity_fix_only": liq_only,
                "proposed_full": proposed,
            },
            indent=2,
            default=str,
        )
    )
    print(f"\nWrote {args.out_json}")

    # ── Decision gate ────────────────────────────────────────────────
    print("\n=== DECISION GATE ===")
    n_new = proposed["total_allowed_picks"]
    anti = proposed["anti_napoli_violation_count"]
    archs = proposed["allowed_per_archetype"]
    diversity = len(archs)
    print(f"  total allowed picks (proposed): {n_new}")
    print(f"  anti-Napoli violations:         {anti}")
    print(f"  archetype diversity:            {diversity}")
    print(f"  per-archetype distribution:     {archs}")
    decision = "PASS"
    reasons = []
    if n_new < 5:
        decision = "FAIL"
        reasons.append(f"only {n_new} new picks (<5 threshold)")
    if n_new > 500:
        decision = "FAIL"
        reasons.append(f"{n_new} new picks (>500 overflow)")
    if anti > 0:
        decision = "FAIL"
        reasons.append(f"{anti} anti-Napoli violations (>0)")
    if diversity < 2:
        decision = "FAIL"
        reasons.append(f"diversity {diversity} (<2)")
    print(f"  decision: {decision}")
    if reasons:
        for r in reasons:
            print(f"    - {r}")

    # ── Report ───────────────────────────────────────────────────────
    args.out_report.parent.mkdir(parents=True, exist_ok=True)
    args.out_report.write_text(_render_report(baseline, liq_only, proposed, decision, reasons))
    print(f"Wrote {args.out_report}")

    return 0 if decision == "PASS" else 2


def _render_report(baseline, liq_only, proposed, decision, reasons) -> str:
    def _fmt(d: dict, max_items: int = 10) -> str:
        if not d:
            return "_(empty)_"
        lines = []
        for k, v in list(d.items())[:max_items]:
            lines.append(f"  - {k}: {v}")
        return "\n".join(lines)

    lines: list[str] = []
    lines.append("# V3 Day-3 Relaxation Backtest Report")
    lines.append("")
    lines.append(f"**Decision:** **{decision}**")
    if reasons:
        for r in reasons:
            lines.append(f"  - blocker: {r}")
    lines.append("")
    lines.append("## Summary table")
    lines.append("")
    lines.append("| Metric | Baseline (current) | Fix 1 (liquidity only) | Fix 1+2+3+4 + OOD v2 |")
    lines.append("|--------|--------------------|------------------------|----------------------|")
    lines.append(
        f"| total candidates    | {baseline['total_candidates']} "
        f"| {liq_only['total_candidates']} | {proposed['total_candidates']} |"
    )
    lines.append(
        f"| allowed picks       | {baseline['total_allowed_picks']} "
        f"| {liq_only['total_allowed_picks']} | {proposed['total_allowed_picks']} |"
    )
    lines.append(
        f"| frames with allowed | {baseline['frames_with_allowed']} "
        f"| {liq_only['frames_with_allowed']} | {proposed['frames_with_allowed']} |"
    )
    lines.append(
        f"| anti-Napoli violations | {baseline['anti_napoli_violation_count']} "
        f"| {liq_only['anti_napoli_violation_count']} | {proposed['anti_napoli_violation_count']} |"
    )
    lines.append(
        f"| archetype diversity | {len(baseline['allowed_per_archetype'])} "
        f"| {len(liq_only['allowed_per_archetype'])} | {len(proposed['allowed_per_archetype'])} |"
    )
    lines.append("")
    lines.append("## Proposed config: per-archetype distribution")
    lines.append("")
    lines.append(_fmt(proposed["allowed_per_archetype"]))
    lines.append("")
    lines.append("## Proposed config: per-market-family distribution")
    lines.append("")
    lines.append(_fmt(proposed["allowed_per_market_family"]))
    lines.append("")
    lines.append("## Proposed config: gate denial reasons (downstream of MES routing)")
    lines.append("")
    lines.append(_fmt(proposed["denied_by_rule"]))
    lines.append("")
    lines.append("## Sample of first 50 proposed picks")
    lines.append("")
    lines.append("| fid | min | score | dom_los | archetype | market | dir | MES | base_edge | fair_prob |")
    lines.append("|-----|-----|-------|---------|-----------|--------|-----|-----|-----------|-----------|")
    for p in proposed["sample_allowed_first_50"]:
        lines.append(
            f"| {p['fixture_id']} | {p['minute']} | {p['score']} | "
            f"{p['dominant_losing']} | {p['archetype']} | "
            f"{p['market_id'][:40]} | {p['direction']} | "
            f"{p['mes']} | {p['base_edge']} | {p['fair_prob']} |"
        )
    lines.append("")
    lines.append("## Per-configuration details")
    lines.append("")
    for cfg_name, cfg in (("baseline", baseline), ("liquidity_fix_only", liq_only), ("proposed_full", proposed)):
        lines.append(f"### {cfg_name}")
        lines.append("")
        lines.append(f"```json\n{json.dumps(cfg['config'], indent=2)}\n```")
        lines.append("")
    lines.append("## Reproduce")
    lines.append("")
    lines.append("```bash")
    lines.append("uv run python scripts/spike/v3/backtest_relaxed_archetypes.py")
    lines.append("```")
    lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
