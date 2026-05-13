"""V3 Day-3 silence diagnosis — T0 of the V3_DAY3_DIAGNOSIS spike.

Loads the 1642 GSVs persisted at data/cache/v3_shadow/dt=2026-05-12/gsv_log.parquet,
deserialises each row back into a Pydantic GameStateVector, and computes:

    T0.1 — Distribution of game states across the day
    T0.2 — For each of the 12 archetypes: how many frames it would have
           fired on vs failed on, and which AND-clause failed most often
    T0.3 — Cross-check vs v2 picks_graded.parquet for Day-3 (was v2 silent too?)
    T0.4 — Synthetic edge case: build an A2-target GSV and run V3Pipeline

Output: ``logs/v3_day3_diagnosis.json`` consumed by the markdown writer.

This is read-only: no model files touched, no production code modified.
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import polars as pl

from bip.evaluation.live.engine_v3.archetypes import generate_theses
from bip.evaluation.live.engine_v3.gsv import GameStateVector


# ──────────────────────────────────────────────────────────────────────
# Loading
# ──────────────────────────────────────────────────────────────────────


def load_gsvs(path: Path) -> list[GameStateVector]:
    df = pl.read_parquet(path)
    out: list[GameStateVector] = []
    for s in df["gsv_json"]:
        out.append(GameStateVector.model_validate_json(s))
    return out


# ──────────────────────────────────────────────────────────────────────
# T0.1 — distributions
# ──────────────────────────────────────────────────────────────────────


def _bucket_minute(m: int) -> str:
    if m < 0:
        return "pre"
    if m >= 90:
        return "90+"
    lo = (m // 10) * 10
    return f"{lo:02d}-{lo + 9:02d}"


def _bucket_total(x: float) -> str:
    if x < 0.5:
        return "<0.5"
    if x < 1.0:
        return "0.5-1.0"
    if x < 1.5:
        return "1.0-1.5"
    if x < 2.0:
        return "1.5-2.0"
    if x < 3.0:
        return "2.0-3.0"
    return "3.0+"


def _bucket_abs_xg_diff(x: float) -> str:
    x = abs(x)
    if x < 0.5:
        return "<0.5"
    if x < 1.0:
        return "0.5-1.0"
    if x < 1.5:
        return "1.0-1.5"
    return "1.5+"


def t01_distributions(gsvs: list[GameStateVector]) -> dict[str, Any]:
    minute_bucket = Counter(_bucket_minute(g.time.minute) for g in gsvs)
    score_state = Counter(f"{g.score.home_goals}-{g.score.away_goals}" for g in gsvs)
    game_phase = Counter(g.tactical.game_phase for g in gsvs)
    dom_losing = Counter(g.score.dominant_losing for g in gsvs)
    xg_total_bucket = Counter(
        _bucket_total(g.xg.home_xg_total + g.xg.away_xg_total) for g in gsvs
    )
    abs_xg_diff_bucket = Counter(_bucket_abs_xg_diff(g.xg.xg_diff) for g in gsvs)
    has_num_adv = Counter(g.numerical.numerical_advantage != 0 for g in gsvs)
    period = Counter(g.time.period for g in gsvs)
    fixture_count = len({g.fixture_id for g in gsvs})

    return {
        "n_frames": len(gsvs),
        "n_fixtures": fixture_count,
        "minute_bucket": dict(minute_bucket.most_common()),
        "score_state_top10": dict(score_state.most_common(10)),
        "game_phase": dict(game_phase.most_common()),
        "period": dict(period.most_common()),
        "dominant_losing": {str(k): v for k, v in dom_losing.items()},
        "xg_total_bucket": dict(xg_total_bucket.most_common()),
        "abs_xg_diff_bucket": dict(abs_xg_diff_bucket.most_common()),
        "numerical_advantage_nonzero": {str(k): v for k, v in has_num_adv.items()},
    }


# ──────────────────────────────────────────────────────────────────────
# T0.2 — archetype-by-archetype failure decomposition
#
# For each archetype we evaluate the conditions IN THE ORDER the detector
# checks them and track which clause first eliminates the frame. The
# clause names below mirror the early-return checks in archetypes.py so
# the counts are interpretable.
# ──────────────────────────────────────────────────────────────────────


ArchetypeEval = dict[str, Any]


def _eval_a1_red_card_away(g: GameStateVector) -> ArchetypeEval:
    chain = [
        ("red_cards_away>=1", g.numerical.red_cards_away >= 1),
        ("minute<30", g.time.minute < 30),
        ("xg_diff>=-0.4", g.xg.xg_diff >= -0.4),
    ]
    return _eval_chain("A1_red_card_away_early", chain, g)


def _eval_a2_napoli(g: GameStateVector) -> ArchetypeEval:
    chain = [
        ("dominant_losing=True", g.score.dominant_losing),
        ("25<=minute<=45", 25 <= g.time.minute <= 45),
        ("|xg_vs_score_div|>=0.3", abs(g.xg.xg_vs_score_divergence) >= 0.3),
    ]
    return _eval_chain("A2_napoli", chain, g)


def _eval_a3_late_cagey(g: GameStateVector) -> ArchetypeEval:
    chain = [
        ("goal_diff==0", g.score.goal_diff == 0),
        ("home_goals==0", g.score.home_goals == 0),
        ("minute>=75", g.time.minute >= 75),
        ("xg_total<0.6", (g.xg.home_xg_total + g.xg.away_xg_total) < 0.6),
        ("game_phase==cagey_closed", g.tactical.game_phase == "cagey_closed"),
    ]
    return _eval_chain("A3_late_cagey_zero_zero", chain, g)


def _eval_a4_lead_two(g: GameStateVector) -> ArchetypeEval:
    leader_is_home = g.score.goal_diff >= 2
    defensive_subs = [
        s
        for s in g.roster.recent_subs_5min
        if s.role_signal == "defensive"
        and (
            (leader_is_home and s.team_id == g.home_team_id)
            or (not leader_is_home and s.team_id == g.away_team_id)
        )
    ]
    chain = [
        ("|goal_diff|>=2", abs(g.score.goal_diff) >= 2),
        ("55<=minute<=75", 55 <= g.time.minute <= 75),
        ("defensive_sub_by_leader", bool(defensive_subs)),
    ]
    return _eval_chain("A4_lead_two_defensive_sub", chain, g)


def _eval_a5_regression_xg(g: GameStateVector) -> ArchetypeEval:
    chain = [
        ("goal_diff==0", g.score.goal_diff == 0),
        ("minute>=60", g.time.minute >= 60),
        ("|xg_diff|>=1.5", abs(g.xg.xg_diff) >= 1.5),
    ]
    return _eval_chain("A5_regression_to_xg", chain, g)


def _eval_a6_cards(g: GameStateVector) -> ArchetypeEval:
    total_y = g.cards.yellows[0] + g.cards.yellows[1]
    chain = [
        ("yellows_total>=5", total_y >= 5),
        ("minute>=70", g.time.minute >= 70),
        ("ref_card_rate_prior>=5.0", g.cards.ref_card_rate_prior >= 5.0),
    ]
    return _eval_chain("A6_cards_momentum_strict_ref", chain, g)


def _eval_a7_underdog_siege(g: GameStateVector) -> ArchetypeEval:
    if g.score.dominant_team_id is None or abs(g.score.goal_diff) != 1:
        # we still want to count the gate
        chain = [
            ("dominant_team_id_known", g.score.dominant_team_id is not None),
            ("|goal_diff|==1", abs(g.score.goal_diff) == 1),
            ("underdog_leads", False),
            ("minute>=70", g.time.minute >= 70),
            ("underdog_phase_in_park/collapse", False),
        ]
        return _eval_chain("A7_underdog_leads_siege", chain, g)
    leader_is_home = g.score.goal_diff == 1
    leader_id = g.home_team_id if leader_is_home else g.away_team_id
    underdog_phase = g.tactical.home_phase if leader_is_home else g.tactical.away_phase
    chain = [
        ("dominant_team_id_known", True),
        ("|goal_diff|==1", True),
        ("underdog_leads", leader_id != g.score.dominant_team_id),
        ("minute>=70", g.time.minute >= 70),
        (
            "underdog_phase_in_park/collapse",
            underdog_phase in ("parking_bus", "collapsing"),
        ),
    ]
    return _eval_chain("A7_underdog_leads_siege", chain, g)


def _eval_a8_open_game(g: GameStateVector) -> ArchetypeEval:
    is_open = g.is_open_game
    aggressive = {"4-3-3", "3-4-3", "4-2-4", "3-3-4"}
    chain = [
        (
            "is_open_game (>=3 goals AND minute<=60)",
            is_open,
        ),
        (
            "aggressive_formation_either_side",
            g.roster.formation_home in aggressive
            or g.roster.formation_away in aggressive,
        ),
    ]
    return _eval_chain("A8_open_game_formations", chain, g)


def _eval_a9_playmaker_off(g: GameStateVector) -> ArchetypeEval:
    home_off, away_off = g.roster.key_player_off
    if not (home_off or away_off):
        chain = [("key_player_off_either_side", False)]
        return _eval_chain("A9_key_playmaker_off", chain, g)
    chain = [
        ("key_player_off_either_side", True),
        (
            "lost_team_is_dominant",
            (home_off and g.score.dominant_team_id == g.home_team_id)
            or (away_off and g.score.dominant_team_id == g.away_team_id),
        ),
    ]
    return _eval_chain("A9_key_playmaker_off", chain, g)


def _eval_a10_second_half_reset(g: GameStateVector) -> ArchetypeEval:
    chain = [
        ("period==2H", g.time.period == "2H"),
        ("46<=minute<=50", 46 <= g.time.minute <= 50),
        ("dominant_losing=True", g.score.dominant_losing),
        (
            "formation_change_by_dominant",
            bool(
                [
                    c
                    for c in g.roster.formation_changes
                    if c.team_id == g.score.dominant_team_id
                ]
            ),
        ),
    ]
    return _eval_chain("A10_second_half_reset", chain, g)


def _eval_a11_numerical_sustained(g: GameStateVector) -> ArchetypeEval:
    chain = [
        ("numerical_advantage>0", g.numerical.numerical_advantage > 0),
        ("minute>=30", g.time.minute >= 30),
        ("not dominant_losing", not g.score.dominant_losing),
    ]
    return _eval_chain("A11_numerical_sustained", chain, g)


def _eval_a12_cruise(g: GameStateVector) -> ArchetypeEval:
    leader_is_home = g.score.goal_diff == 1
    leader_phase = g.tactical.home_phase if leader_is_home else g.tactical.away_phase
    recent_total = g.xg.xg_per_min_home_last_15 + g.xg.xg_per_min_away_last_15
    chain = [
        ("|goal_diff|==1", abs(g.score.goal_diff) == 1),
        ("minute>=80", g.time.minute >= 80),
        (
            "leader_phase_in_control/park",
            leader_phase in ("controlling", "parking_bus"),
        ),
        ("recent_xg_per_min_sum<=0.05", recent_total <= 0.05),
    ]
    return _eval_chain("A12_cruise_mode", chain, g)


def _eval_chain(
    name: str, chain: list[tuple[str, bool]], g: GameStateVector
) -> ArchetypeEval:
    fired = all(passed for _, passed in chain)
    first_fail = None if fired else next(c for c, p in chain if not p)
    return {
        "archetype": name,
        "fired": fired,
        "first_fail": first_fail,
        "fixture_id": g.fixture_id,
        "minute": g.time.minute,
        "score": f"{g.score.home_goals}-{g.score.away_goals}",
        "dominant_losing": g.score.dominant_losing,
        "xg_total": round(g.xg.home_xg_total + g.xg.away_xg_total, 3),
        "xg_diff": round(g.xg.xg_diff, 3),
        "xg_div": round(g.xg.xg_vs_score_divergence, 3),
        "game_phase": g.tactical.game_phase,
    }


_EVALS = (
    _eval_a1_red_card_away,
    _eval_a2_napoli,
    _eval_a3_late_cagey,
    _eval_a4_lead_two,
    _eval_a5_regression_xg,
    _eval_a6_cards,
    _eval_a7_underdog_siege,
    _eval_a8_open_game,
    _eval_a9_playmaker_off,
    _eval_a10_second_half_reset,
    _eval_a11_numerical_sustained,
    _eval_a12_cruise,
)


def t02_archetype_failures(gsvs: list[GameStateVector]) -> dict[str, Any]:
    """For each archetype: count fires, count failures per first-failing clause,
    and surface up to 5 'near-miss' frames (failed exactly one final clause)."""
    summary: dict[str, dict[str, Any]] = {}
    near_misses: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for fn in _EVALS:
        archetype_name = None
        fired = 0
        fail_counts: Counter[str] = Counter()
        per_frame_evals: list[ArchetypeEval] = []
        for g in gsvs:
            ev = fn(g)
            archetype_name = ev["archetype"]
            per_frame_evals.append(ev)
            if ev["fired"]:
                fired += 1
            else:
                fail_counts[ev["first_fail"]] += 1

        # Near-miss: frame that passed all but the LAST clause in the chain.
        # We approximate this as frames where the first_fail is the LAST clause name.
        last_clause = None
        if per_frame_evals:
            chain_names = []
            sample = per_frame_evals[0]
            for ev in per_frame_evals:
                if ev["fired"]:
                    continue
            # Use the most-common ordered set of clauses across non-fired evals.
            # In practice each archetype has a fixed clause list — pull from one eval.

        # Re-derive the clause set for this archetype from the first eval that failed,
        # by running the eval again on a synthetic always-passing GSV.
        # Simpler: list of clause names per archetype is fixed; expose via a hand
        # mapping.
        clause_order = _CLAUSE_ORDER.get(archetype_name, [])
        last = clause_order[-1] if clause_order else None
        if last is not None:
            for ev in per_frame_evals:
                if ev["fired"]:
                    continue
                if ev["first_fail"] == last and len(near_misses[archetype_name]) < 5:
                    near_misses[archetype_name].append(ev)

        # Convert fail_counts to sorted dict
        fail_table = [
            {"clause": k, "count": v, "pct": round(100 * v / len(gsvs), 2)}
            for k, v in fail_counts.most_common()
        ]
        summary[archetype_name] = {
            "fired": fired,
            "fired_pct": round(100 * fired / max(len(gsvs), 1), 4),
            "failure_table_top3": fail_table[:3],
            "failure_table_full": fail_table,
            "near_miss_examples": near_misses.get(archetype_name, []),
        }
    return summary


_CLAUSE_ORDER: dict[str, list[str]] = {
    "A1_red_card_away_early": [
        "red_cards_away>=1",
        "minute<30",
        "xg_diff>=-0.4",
    ],
    "A2_napoli": [
        "dominant_losing=True",
        "25<=minute<=45",
        "|xg_vs_score_div|>=0.3",
    ],
    "A3_late_cagey_zero_zero": [
        "goal_diff==0",
        "home_goals==0",
        "minute>=75",
        "xg_total<0.6",
        "game_phase==cagey_closed",
    ],
    "A4_lead_two_defensive_sub": [
        "|goal_diff|>=2",
        "55<=minute<=75",
        "defensive_sub_by_leader",
    ],
    "A5_regression_to_xg": [
        "goal_diff==0",
        "minute>=60",
        "|xg_diff|>=1.5",
    ],
    "A6_cards_momentum_strict_ref": [
        "yellows_total>=5",
        "minute>=70",
        "ref_card_rate_prior>=5.0",
    ],
    "A7_underdog_leads_siege": [
        "dominant_team_id_known",
        "|goal_diff|==1",
        "underdog_leads",
        "minute>=70",
        "underdog_phase_in_park/collapse",
    ],
    "A8_open_game_formations": [
        "is_open_game (>=3 goals AND minute<=60)",
        "aggressive_formation_either_side",
    ],
    "A9_key_playmaker_off": [
        "key_player_off_either_side",
        "lost_team_is_dominant",
    ],
    "A10_second_half_reset": [
        "period==2H",
        "46<=minute<=50",
        "dominant_losing=True",
        "formation_change_by_dominant",
    ],
    "A11_numerical_sustained": [
        "numerical_advantage>0",
        "minute>=30",
        "not dominant_losing",
    ],
    "A12_cruise_mode": [
        "|goal_diff|==1",
        "minute>=80",
        "leader_phase_in_control/park",
        "recent_xg_per_min_sum<=0.05",
    ],
}


# ──────────────────────────────────────────────────────────────────────
# Validate by also running the REAL generate_theses() over each frame.
# This confirms the eval-chain decomposition is faithful (0 fires from
# manual eval ⟺ 0 theses from generate_theses on that frame).
# ──────────────────────────────────────────────────────────────────────


def t02c_pipeline_with_liquidity_fix(gsvs: list[GameStateVector]) -> dict[str, Any]:
    """Re-run the pipeline with the liquidity-score bug worked around.

    Workaround: monkey-patch ``liquidity_score`` to treat the placeholder
    ``max_stake_cap == 1.0`` as full liquidity (1.0). This isolates the
    "what would the system produce if the cap placeholder didn't kill MES"
    question. No production code is changed by this dryrun — only the
    in-memory function reference for the duration of the run.
    """
    from bip.evaluation.live.engine_v3 import mes as mes_module
    from bip.evaluation.live.engine_v3.market_selector import select_markets
    from bip.evaluation.live.engine_v3.conditional_predictor import (
        ConditionalPredictor,
        make_fair_prob_provider,
    )
    from bip.evaluation.live.engine_v3.no_bet_gate import run_gate

    original_liq = mes_module.liquidity_score

    def patched_liq(line, target_stake):
        # If the cap is the Phase-1 placeholder (1.0), assume full liquidity.
        # Otherwise honour the original schedule.
        if line.max_stake_cap == 1.0:
            return 1.0
        return original_liq(line, target_stake)

    mes_module.liquidity_score = patched_liq

    try:
        predictor = ConditionalPredictor.default()
        provider = make_fair_prob_provider(predictor)
        total_candidates = 0
        total_allowed = 0
        denied_by_rule: Counter[str] = Counter()
        allowed_per_archetype: Counter[str] = Counter()
        anti_napoli_violations = 0  # under-direction picks when dominant_losing
        sample_picks: list[dict[str, Any]] = []
        for g in gsvs:
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
                line_max_age_sec=60.0,
                commentary_required=False,
                uncertainty_band=0.08,
                ood_detector=None,
            )
            for r in gate_results:
                if r.verdict.allowed:
                    total_allowed += 1
                    allowed_per_archetype[r.candidate.thesis.archetype.value] += 1
                    direction = r.candidate.thesis.prediction.direction
                    if (
                        g.score.dominant_losing
                        and direction in ("under", "no")
                        and r.candidate.thesis.archetype.value != "cruise_mode"
                    ):
                        anti_napoli_violations += 1
                    if len(sample_picks) < 30:
                        sample_picks.append(
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
                    denied_by_rule[f"rule_{r.verdict.rule_number}"] += 1
        return {
            "total_candidates": total_candidates,
            "total_allowed_picks": total_allowed,
            "denied_by_rule": dict(denied_by_rule),
            "allowed_per_archetype": dict(allowed_per_archetype.most_common()),
            "anti_napoli_violations": anti_napoli_violations,
            "sample_picks_first_30": sample_picks,
        }
    finally:
        mes_module.liquidity_score = original_liq


def t02b_full_pipeline_dryrun(gsvs: list[GameStateVector]) -> dict[str, Any]:
    """Run the COMPLETE pipeline (theses → market_selector → no_bet_gate) over
    every frame. Aggregate: candidate counts, gate-denial reasons, market-family
    availability per frame, allowed-pick counts.

    This is the smoking-gun probe — generate_theses() emits 244 theses, but
    if select_markets + run_gate kill them all, we have explained the silence.
    """
    from bip.evaluation.live.engine_v3.conditional_predictor import (
        ConditionalPredictor,
        make_fair_prob_provider,
    )
    from bip.evaluation.live.engine_v3.market_selector import (
        family_for_market_id,
        select_markets,
    )
    from bip.evaluation.live.engine_v3.no_bet_gate import run_gate

    predictor = ConditionalPredictor.default()
    provider = make_fair_prob_provider(predictor)

    market_family_counter: Counter[str] = Counter()
    market_id_counter: Counter[str] = Counter()
    frames_with_market_ids: list[int] = []
    frames_with_routable_market: int = 0
    total_candidates = 0
    total_allowed = 0
    deny_reasons: Counter[str] = Counter()
    deny_examples: defaultdict[int, list[dict[str, Any]]] = defaultdict(list)
    frames_with_theses_no_candidates: int = 0

    for g in gsvs:
        # Market availability per frame
        lines = g.markets.lines or {}
        frames_with_market_ids.append(len(lines))
        has_routable = False
        for mid in lines:
            market_id_counter[mid] += 1
            fam = family_for_market_id(mid)
            if fam is not None:
                market_family_counter[fam.value] += 1
                has_routable = True
        if has_routable:
            frames_with_routable_market += 1

        theses = generate_theses(g)
        if not theses:
            continue
        candidates = select_markets(
            theses, g, provider, top_k=3, target_stake=100.0, mes_threshold=0.6
        )
        total_candidates += len(candidates)
        if not candidates:
            frames_with_theses_no_candidates += 1
            continue
        gate_results = run_gate(
            theses,
            candidates,
            g,
            mes_threshold=0.6,
            line_max_age_sec=60.0,
            commentary_required=False,
            uncertainty_band=0.08,
            ood_detector=None,
        )
        for r in gate_results:
            if r.verdict.allowed:
                total_allowed += 1
            else:
                rule = r.verdict.rule_number
                deny_reasons[f"rule_{rule}"] += 1
                if len(deny_examples[rule]) < 3:
                    deny_examples[rule].append(
                        {
                            "fixture_id": g.fixture_id,
                            "minute": g.time.minute,
                            "score": f"{g.score.home_goals}-{g.score.away_goals}",
                            "dominant_losing": g.score.dominant_losing,
                            "archetype": r.candidate.thesis.archetype.value,
                            "market_id": r.candidate.market_id,
                            "reason": r.verdict.reason,
                        }
                    )

    return {
        "frames_with_market_ids_distribution": {
            "min": int(min(frames_with_market_ids) if frames_with_market_ids else 0),
            "p25": int(np.percentile(frames_with_market_ids, 25)) if frames_with_market_ids else 0,
            "p50": int(np.percentile(frames_with_market_ids, 50)) if frames_with_market_ids else 0,
            "p75": int(np.percentile(frames_with_market_ids, 75)) if frames_with_market_ids else 0,
            "max": int(max(frames_with_market_ids) if frames_with_market_ids else 0),
        },
        "frames_with_routable_market": frames_with_routable_market,
        "frames_with_routable_market_pct": round(
            100 * frames_with_routable_market / max(len(gsvs), 1), 2
        ),
        "market_family_counts": dict(market_family_counter.most_common()),
        "market_id_top20": dict(market_id_counter.most_common(20)),
        "total_candidates": total_candidates,
        "frames_with_theses_no_candidates": frames_with_theses_no_candidates,
        "total_allowed_picks": total_allowed,
        "deny_reasons": dict(deny_reasons),
        "deny_examples_by_rule": {k: v for k, v in deny_examples.items()},
    }


def t02_validate_with_real_generator(
    gsvs: list[GameStateVector],
) -> dict[str, Any]:
    real_fire_counts: Counter[str] = Counter()
    total_thesis_emissions = 0
    frames_with_any_thesis = 0
    for g in gsvs:
        theses = generate_theses(g)
        if theses:
            frames_with_any_thesis += 1
        total_thesis_emissions += len(theses)
        for t in theses:
            real_fire_counts[t.archetype.value] += 1
    return {
        "total_thesis_emissions_over_dataset": total_thesis_emissions,
        "frames_with_any_thesis": frames_with_any_thesis,
        "per_archetype_real_fires": dict(real_fire_counts.most_common()),
    }


# ──────────────────────────────────────────────────────────────────────
# T0.3 — v2 picks during Day-3 window
# ──────────────────────────────────────────────────────────────────────


def t03_v2_emission_check(gsvs: list[GameStateVector]) -> dict[str, Any]:
    path = Path("reports/sportmonks_live/exports/picks_graded.parquet")
    if not path.exists():
        return {"available": False, "note": "picks_graded.parquet missing"}
    df = pl.read_parquet(path)
    day3_fids = {g.fixture_id for g in gsvs}
    day3_min_ts = min(g.timestamp_utc for g in gsvs)
    day3_max_ts = max(g.timestamp_utc for g in gsvs)
    # Filter rows whose fixture overlaps the Day-3 cohort.
    f = df.filter(pl.col("fixture_id").is_in(list(day3_fids)))
    total_day3 = f.height
    # Some schemas have created_at / kickoff_utc — show what we have.
    cols = df.columns
    summary: dict[str, Any] = {
        "available": True,
        "day3_fixture_count": len(day3_fids),
        "day3_min_ts": day3_min_ts.isoformat() if day3_min_ts else None,
        "day3_max_ts": day3_max_ts.isoformat() if day3_max_ts else None,
        "v2_picks_total_rows": df.height,
        "v2_picks_in_day3_fixtures": total_day3,
        "v2_picks_columns": cols,
    }
    # If 'graded_at' or 'created_at' exists, count picks created during 2026-05-12.
    for ts_col in ("created_at", "captured_at", "pick_time_utc", "ts_utc"):
        if ts_col in cols:
            try:
                fday = df.filter(
                    pl.col(ts_col).cast(pl.Datetime).dt.date()
                    == datetime(2026, 5, 12).date()
                )
                summary[f"v2_picks_dated_2026_05_12_via_{ts_col}"] = fday.height
                break
            except Exception:
                pass
    return summary


# ──────────────────────────────────────────────────────────────────────
# T0.4 — synthetic A2-target pipeline test
# ──────────────────────────────────────────────────────────────────────


def t04_synthetic_a2_test() -> dict[str, Any]:
    """Build a frame that should activate A2 (Napoli) and run V3Pipeline."""
    from bip.evaluation.live.match_state import LiveMatchState
    from bip.evaluation.live.engine_v3.gsv import (
        MarketLine,
        MarketSnapshot,
        PreMatchPriors,
    )
    from bip.evaluation.live.engine_v3.gsv_builder import GSVBuilder
    from bip.evaluation.live.engine_v3.pipeline import V3Pipeline

    # Construct a synthetic state via LiveMatchState — Day-3 frames give us
    # a template. We hand-roll the minimal fields the GSV builder needs.
    # If LiveMatchState construction is too coupled, run generate_theses
    # against a hand-built GSV instead.
    from bip.evaluation.live.engine_v3.gsv import (
        CardsState,
        CornerState,
        FlowState,
        NumericalState,
        RosterState,
        ScoreState,
        TacticalState,
        TimeState,
        XGState,
    )

    now = datetime.now(timezone.utc)
    gsv = GameStateVector(
        fixture_id=999_999,
        state_version=1,
        timestamp_utc=now,
        home_team_id=100,
        away_team_id=200,
        home_team_name="Synthetic Napoli",
        away_team_name="Synthetic Underdog",
        score=ScoreState(
            home_goals=0,
            away_goals=1,
            goal_diff=-1,
            dominant_team_id=100,
            dominant_losing=True,
            last_goal_minute=20,
            last_goal_team_id=200,
            minutes_since_last_goal=15.0,
        ),
        time=TimeState(
            minute=35,
            period="1H",
            added_time_estimate=0.0,
            time_remaining_half=10.0,
            time_remaining_match=55.0,
        ),
        numerical=NumericalState(
            home_players=11,
            away_players=11,
            numerical_advantage=0,
            red_cards_home=0,
            red_cards_away=0,
        ),
        xg=XGState(
            home_xg_total=1.8,
            away_xg_total=0.4,
            xg_diff=1.4,
            xg_per_min_home_last_15=0.08,
            xg_per_min_away_last_15=0.01,
            xg_vs_score_divergence=0.5,
            shots_total=(14, 4),
            shots_on_target=(7, 1),
            shots_in_box=(5, 1),
            big_chances=(3, 0),
        ),
        flow=FlowState(
            possession_home_5min=65.0,
            possession_home_match=62.0,
            attacks_last_10min=(18, 6),
            dangerous_attacks_last_10min=(10, 2),
            pressing_intensity="high",
        ),
        corners=CornerState(
            corners_home=6,
            corners_away=2,
            corner_rate_last_15min=0.4,
            corners_pending=0,
        ),
        cards=CardsState(
            yellows=(2, 1),
            reds=(0, 0),
            card_rate_last_15min=0.2,
            players_on_yellow=[],
            ref_card_rate_prior=4.0,
        ),
        roster=RosterState(
            formation_home="4-3-3",
            formation_away="5-4-1",
            formation_changes=[],
            subs_used=(1, 0),
            subs_remaining=(4, 5),
            recent_subs_5min=[],
            injuries_live=[],
            key_player_off=(False, False),
        ),
        tactical=TacticalState(
            home_phase="controlling",
            away_phase="parking_bus",
            game_phase="open_attacking",
            tempo="high",
        ),
        priors=PreMatchPriors(
            lambda_home_prematch=1.9,
            lambda_away_prematch=0.9,
            expected_corners_total=10.4,
            expected_cards_total=3.9,
            elo_diff=200.0,
            h2h_btts_rate=0.6,
            h2h_over25_rate=0.55,
            h2h_over_corners_95=0.55,
            bookmaker_consensus_close={},
        ),
        markets=MarketSnapshot(
            lines={
                "next_goal_home": MarketLine(
                    market_id="next_goal_home",
                    side_a_decimal=1.95,
                    side_b_decimal=2.05,
                    line_value=None,
                    last_update_utc=now,
                    max_stake_cap=1_000.0,
                ),
                "match_goals_over_25": MarketLine(
                    market_id="match_goals_over_25",
                    side_a_decimal=2.10,
                    side_b_decimal=1.80,
                    line_value=2.5,
                    last_update_utc=now,
                    max_stake_cap=1_000.0,
                ),
                "match_corners_over_9_5": MarketLine(
                    market_id="match_corners_over_9_5",
                    side_a_decimal=1.95,
                    side_b_decimal=1.95,
                    line_value=9.5,
                    last_update_utc=now,
                    max_stake_cap=1_000.0,
                ),
            }
        ),
        last_critical_event=None,
        last_critical_event_age_sec=999.0,
    )

    theses = generate_theses(gsv)
    rule_layer_summary = {
        "thesis_count": len(theses),
        "archetypes": [t.archetype.value for t in theses],
        "directions": [t.prediction.direction for t in theses],
    }

    # Run pipeline end-to-end using a from-scratch V3Pipeline (no detector wired)
    # We bypass GSVBuilder since we already have a GSV; we call the inner stages
    # directly to confirm a pick lands.
    from bip.evaluation.live.engine_v3.conditional_predictor import (
        ConditionalPredictor,
        make_fair_prob_provider,
    )
    from bip.evaluation.live.engine_v3.market_selector import select_markets
    from bip.evaluation.live.engine_v3.no_bet_gate import run_gate

    predictor = ConditionalPredictor.default()
    provider = make_fair_prob_provider(predictor)
    candidates = select_markets(
        theses, gsv, provider, top_k=3, target_stake=100.0, mes_threshold=0.6
    )
    gate_results = run_gate(
        theses,
        candidates,
        gsv,
        mes_threshold=0.6,
        line_max_age_sec=60.0,
        commentary_required=False,
        uncertainty_band=0.08,
        ood_detector=None,
    )
    candidate_summary = [
        {
            "archetype": c.thesis.archetype.value,
            "market_id": c.market_id,
            "direction": c.thesis.prediction.direction,
            "mes": round(c.mes.score, 3),
            "base_edge": round(c.mes.base_edge, 3),
            "liquidity_score": round(c.mes.liquidity_score, 3),
            "conditional_variance": round(c.mes.conditional_variance, 3),
        }
        for c in candidates
    ]
    gate_summary = [
        {
            "archetype": r.candidate.thesis.archetype.value,
            "market_id": r.candidate.market_id,
            "allowed": r.verdict.allowed,
            "rule": r.verdict.rule_number,
            "reason": r.verdict.reason,
        }
        for r in gate_results
    ]
    return {
        "rule_layer_summary": rule_layer_summary,
        "candidates": candidate_summary,
        "gate_results": gate_summary,
        "n_allowed": sum(1 for r in gate_results if r.verdict.allowed),
    }


# ──────────────────────────────────────────────────────────────────────
# Main entry
# ──────────────────────────────────────────────────────────────────────


def main() -> None:
    src = Path("data/cache/v3_shadow/dt=2026-05-12/gsv_log.parquet")
    print(f"Loading {src}…")
    gsvs = load_gsvs(src)
    print(f"Loaded {len(gsvs)} GSVs covering {len({g.fixture_id for g in gsvs})} fixtures.")

    print("T0.1 — distributions")
    t01 = t01_distributions(gsvs)
    print("T0.2 — archetype failure decomposition")
    t02 = t02_archetype_failures(gsvs)
    t02_real = t02_validate_with_real_generator(gsvs)
    print("T0.2b — full-pipeline dryrun over 1642 frames")
    t02b = t02b_full_pipeline_dryrun(gsvs)
    print("T0.2c — pipeline dryrun with liquidity placeholder fix")
    t02c = t02c_pipeline_with_liquidity_fix(gsvs)
    print("T0.3 — v2 emission check")
    t03 = t03_v2_emission_check(gsvs)
    print("T0.4 — synthetic A2 pipeline test")
    t04 = t04_synthetic_a2_test()

    out_path = Path("logs/v3_day3_diagnosis.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(
            {
                "t01_distributions": t01,
                "t02_archetype_failures": t02,
                "t02_real_generator_check": t02_real,
                "t02b_full_pipeline_dryrun": t02b,
                "t02c_pipeline_with_liquidity_fix": t02c,
                "t03_v2_emission_check": t03,
                "t04_synthetic_a2": t04,
            },
            indent=2,
            default=str,
        )
    )
    print(f"Wrote {out_path}")

    # Brief on-stdout summary
    real_total = t02_real["total_thesis_emissions_over_dataset"]
    real_frames = t02_real["frames_with_any_thesis"]
    print(
        f"\n>>> generate_theses() emitted {real_total} theses across "
        f"{real_frames} of {len(gsvs)} frames "
        f"({100*real_frames/max(len(gsvs),1):.2f}% non-empty)."
    )
    if t04["n_allowed"] > 0:
        print(f">>> T0.4 synthetic A2 produced {t04['n_allowed']} allowed picks (pipeline reachable).")
    else:
        print(f">>> T0.4 synthetic A2 produced 0 allowed picks — pipeline BLOCKED.")


if __name__ == "__main__":
    main()
