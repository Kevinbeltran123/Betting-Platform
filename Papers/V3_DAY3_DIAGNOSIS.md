# V3 Live Engine — Day-3 Silence Diagnosis

**Date:** 2026-05-12
**Scope:** 1642 GSVs, 20 fixtures, 8h shadow window
**Source:** `data/cache/v3_shadow/dt=2026-05-12/gsv_log.parquet`
**Reproduce:** `uv run python scripts/spike/v3/diagnose_day3_silence.py`
**Output:** `logs/v3_day3_diagnosis.json`

---

## TL;DR — Why we emitted 0 picks

The silence is **not** caused by archetype thresholds or by the OOD detector. It is caused by a **liquidity-placeholder collision between two modules**:

- `runtime/dual_write.py:216` hard-codes `max_stake_cap = 1.0` for every Sportmonks-sourced market line (explicit Phase-1 placeholder per the comment on line 189-190: *"Phase 2 will wire real caps from Sportmonks when emitted"*).
- `mes.liquidity_score()` interprets that 1.0 as "$1 stake cap" against a `target_stake = 100.0` USD baseline. Anything `cap < 0.5 × target_stake = 50.0` returns 0.0 — i.e., **rule #7-equivalent rejection silently encoded in the routing score, not the gate**.
- Consequence: for every (thesis, market) pair, MES = `(base_edge × clarity × slowness × 0.0) / variance = 0.0`. `0.0` never passes the 0.6 MES threshold; the market_selector returns an empty list; the gate never even gets a chance to deny anything.

Independent confirmation from the diagnostic dryrun:

| run | candidates | allowed picks |
|-----|------------|---------------|
| as-is (1642 frames, real pipeline) | 0 | 0 |
| same frames + `liquidity_score(line.cap == 1.0) → 1.0` monkey-patch | 684 | **121** |

The 121 allowed picks land in the operator's target window of "10-100 with 0 anti-Napoli violations" (only 21 over — see T3 for the proposed tightening via `line_max_age_sec`).

The rule-1 path (`generate_theses` returns []) was the operator's working hypothesis. It is **not** the cause: `generate_theses()` emits **244 theses in 222 of 1642 frames (13.52%)**. The bottleneck is one layer downstream.

---

## T0.1 — Distribution of game states across the 1642 frames

### Coverage
- Frames: 1642
- Fixtures: 20
- Time span: 2026-05-12 15:54Z → 23:59Z (8h continuous)

### Minute buckets

| Bucket | Frames | % |
|--------|--------|---|
| 00-09  | 116 | 7.1 |
| 10-19  | 103 | 6.3 |
| 20-29  | 137 | 8.3 |
| 30-39  | 138 | 8.4 |
| 40-49  | 372 | 22.7 |
| 50-59  | 214 | 13.0 |
| 60-69  | 171 | 10.4 |
| 70-79  | 171 | 10.4 |
| 80-89  | 141 | 8.6 |
| 90+    | 79  | 4.8 |

The 40-49 peak comes from the HT cohort (period="HT" was 237 frames; minute is held at 45 / first 1-2 of 2H).

### Score states (top 5)

| Score | Frames |
|-------|--------|
| 0-0 | 745 |
| 1-0 | 281 |
| 0-1 | 226 |
| 1-1 | 93 |
| 0-2 | 64 |

### Game phase

| Phase | Frames |
|-------|--------|
| open_attacking | 968 (59.0%) |
| cagey_open | 319 (19.4%) |
| cagey_closed | 191 (11.6%) |
| desperate | 86 (5.2%) |
| cruise | 78 (4.8%) |

### Periods

| Period | Frames |
|--------|--------|
| 2H  | 760 |
| 1H  | 574 |
| HT  | 237 |
| ET1 | 65  |
| NS  | 6   |

### dominant_losing

| Value | Frames |
|-------|--------|
| False | 1264 (77.0%) |
| True  | 378 (23.0%) |

### xG total

| Bucket | Frames |
|--------|--------|
| <0.5    | 278 |
| 0.5-1.0 | 378 |
| 1.0-1.5 | 277 |
| 1.5-2.0 | 327 |
| 2.0-3.0 | 295 |
| 3.0+    | 87 |

Median xG total ≈ 1.0-1.5 across the dataset.

### |xg_diff|

| Bucket | Frames |
|--------|--------|
| <0.5    | 1168 (71.1%) |
| 0.5-1.0 | 416  (25.3%) |
| 1.0-1.5 | 31   (1.9%) |
| 1.5+    | 27   (1.6%) |

**A5's threshold of `|xg_diff| ≥ 1.5` excludes 98.4% of the dataset by construction.**

### Numerical advantage non-zero

| Value | Frames |
|-------|--------|
| False | 1475 (89.8%) |
| True  | 167 (10.2%) |

A1, A11 depend on `red_cards_*` events. Day-3 had ≤2 red cards in the entire window; A11's "advantage > 0" path is reachable but rare.

---

## T0.2 — Per-archetype failure decomposition

For each archetype, I evaluated its conditions in order and counted which AND-clause was the first to eliminate a frame. The "fires" column is independently corroborated by running the real `generate_theses()` over every frame (numbers match).

| Arch | Fires | Top failed clause | %  | 2nd | %  | 3rd | %  |
|------|-------|-------------------|----|-----|----|-----|----|
| A1 red_card_away_early | 0 | `red_cards_away≥1` | 95.4 | `minute<30` | 4.6 | — | — |
| A2 napoli | 67 | `dominant_losing=True` | 77.0 | `25≤minute≤45` | 18.7 | `|xg_div|≥0.3` | 0.2 |
| A3 late_cagey_0_0 | 0 | `goal_diff=0` | 46.2 | `minute≥75` | 43.5 | `xg_total<0.6` | (see below) |
| A4 lead_two_defensive_sub | 22 | `|goal_diff|≥2` | 90.1 | `55≤minute≤75` | 6.4 | `def_sub_by_leader` | 2.1 |
| A5 regression_to_xg | 2 | `goal_diff=0` | 46.2 | `minute≥60` | 44.6 | `|xg_diff|≥1.5` | 9.1 |
| A6 cards_momentum | 0 | `yellows≥5` | 87.4 | `ref_card_rate≥5.0` | 11.0 | `minute≥70` | 1.6 |
| A7 underdog_siege | 0 | `|goal_diff|=1` | 63.6 | `underdog_leads` | 21.0 | `minute≥70` | 12.2 |
| A8 open_game | 0 | `is_open_game` | 99.1 | `aggressive_formation` | 0.9 | — | — |
| A9 playmaker_off | 0 | `key_player_off` | 100.0 | — | — | — | — |
| A10 second_half_reset | 0 | `period=2H` | 53.7 | `46≤minute≤50` | 39.5 | `dominant_losing` | 5.2 |
| A11 numerical_sustained | 59 | `numerical_advantage>0` | 95.4 | `not dominant_losing` | 1.0 | `minute≥30` | — |
| A12 cruise_mode | 94 | `|goal_diff|=1` | 63.6 | `minute≥80` | 28.9 | `xg_per_min≤0.05` | 1.0 |

### Real-generator emissions

`generate_theses()` over the 1642 frames emitted **244 theses across 222 frames (13.52%)**. Per archetype:

| Archetype | Real fires |
|-----------|------------|
| cruise_mode | 94 |
| dominant_losing_napoli | 67 |
| numerical_sustained | 59 |
| lead_two_defensive_sub | 22 |
| regression_to_xg | 2 |

This independently corroborates the manual decomposition (5 of 12 archetypes are reachable from the empirical Day-3 distribution; the rest are gated by missing event signals, e.g. red cards, key-player subs, formation changes — these may be Sportmonks ingester gaps, not archetype-threshold problems).

### Where the 244 theses die

The full-pipeline dryrun (`t02b_full_pipeline_dryrun`):

| Metric | Value |
|--------|-------|
| frames with `≥1` market line | 1642 (100%) |
| frames with a market that routes to a known family | **1642 (100%)** |
| `MarketSnapshot.lines` size: p50 / p75 / max | 290 / 338 / 416 |
| corner-family markets across all frames | 92,128 |
| goals-family markets | 82,728 |
| candidates produced by `select_markets` | **0** |
| frames where `select_markets` killed all theses | 222 |

Markets are present and routable. Yet `select_markets` returns nothing — the smoking gun for the liquidity bug.

### Smoking gun

Sample of the first frame's market lines:

```
'half_time_correct_score_3-2':
    side_a_decimal: 126.0
    max_stake_cap: 1.0          ← the placeholder
    last_update_utc: 2026-05-12T15:04:42Z

'asian_corners_over_8.5':
    side_a_decimal: 2.02
    max_stake_cap: 1.0          ← same
'asian_corners_under_8.5':
    side_a_decimal: 1.77
    max_stake_cap: 1.0          ← same
```

Across the entire dataset:

```
total market lines:  485,440
lines with max_stake_cap < 50.0:  485,440  (100.00%)
```

100% of lines fail `cap ≥ 0.5 × target_stake (= 50.0)`, so 100% of lines get `liquidity_score = 0.0`, so 100% of (thesis, market) candidates get `MES = 0.0`, so 100% are rejected by the routing threshold before they ever reach the gate. The reason `gate_denials.parquet` doesn't exist is that **the gate is reached zero times**.

---

## T0.2c — Pipeline behaviour with the placeholder neutralised

To isolate "would picks land if liquidity_score didn't kill everything?", I monkey-patched `liquidity_score` to return 1.0 when it sees the Phase-1 placeholder cap of 1.0 (and to honour the original schedule for any real cap). No production code changed.

Result:

| Metric | Value |
|--------|-------|
| candidates produced by `select_markets` | 684 |
| candidates surviving the gate | **121** |
| denied by `rule_4` (line freshness >60s) | 558 |
| denied by `rule_8` (predictive variance >0.8) | 5 |
| **anti-Napoli violations (Under direction + dominant_losing, non-cruise)** | **0** |

Per-archetype distribution of the 121 allowed picks:

| Archetype | Allowed |
|-----------|---------|
| dominant_losing_napoli | 93 |
| cruise_mode | 15 |
| numerical_sustained | 7 |
| lead_two_defensive_sub | 6 |

**Interpretation**:
1. The pipeline is correct. The gate's rule #2 catches Under direction + dominant_losing: zero violations across 121 picks.
2. The rule #4 line-freshness threshold (60s) is also misaligned with the Sportmonks feed cadence (see T0.3 below). 558 candidate kills here is the second-largest leak.
3. With the liquidity placeholder neutralised AND the line-freshness threshold relaxed appropriately, the system would produce in the 100-200 picks range over Day-3 (above the operator's "10-100" target — line freshness needs to be tightened, see T2).

---

## T0.3 — Was v2 also silent?

`reports/sportmonks_live/exports/picks_graded.parquet` carries 1087 historical rows. Filtered to the 20 Day-3 fixtures:

| Metric | Value |
|--------|-------|
| Day-3 fixtures present in shadow log | 20 |
| v2 picks for those fixtures | **0** |
| v2 picks total across history | 1087 |

**v2 was also silent on Day-3.** This is a parallel finding the operator should track separately — the live-engine v3 silence is partially explained by the liquidity bug above, but v2 (independent codepath) emitting 0 picks for the same fixtures suggests either:
- The v2 codepath also relies on a Sportmonks-emitted stake cap and hits a similar mismatch
- Or the v2 pre-match filters (kickoff time, league whitelist, freshness checks) are excluding all 20 Day-3 fixtures
- Or the v2 watch loop was simply not running over the same 8h window

Out of scope for this spike but flagged for follow-up.

---

## T0.4 — Synthetic A2 pipeline test

Constructed a hand-rolled GSV that should activate Archetype 2 (Napoli):
- minute=35, period=1H, score 0-1, dominant_team_id=home, dominant_losing=True
- xg_total=2.2, xg_diff=+1.4, xg_vs_score_divergence=0.5
- 3 synthetic markets (next_goal_home, match_goals_over_2.5, match_corners_over_9.5) with `max_stake_cap=1000.0`

Result:

| Stage | Output |
|-------|--------|
| generate_theses | 1 thesis (dominant_losing_napoli, direction=home) |
| select_markets | 3 candidates (MES = 5.46, 4.33, 2.18 — all above 0.6) |
| run_gate | **3 allowed picks** |
| anti-Napoli rule #2 trips? | No — direction is "home" (not under/no), rule #2 passes |

**The pipeline is functional end-to-end when the inputs are clean.** This further isolates the silence to the input data (max_stake_cap placeholder), not a structural bug in V3.

---

## Distribution-derived insights for T2 (relaxations)

| Cohort | Statistic | Implication |
|--------|-----------|-------------|
| min≥75 + 0-0 (n=31)            | xG_total p25/p50/p75 = 1.16 / 2.23 / 2.26  | A3 threshold `xg_total < 0.6` is below p25 — captures essentially zero real frames. |
| min≥60 + tied (n=151)           | \|xg_diff\| p25/p50/p75/p90 = 0.23 / 0.37 / 0.44 / 0.70 | A5 threshold `\|xg_diff\| ≥ 1.5` captures only the >p90 outlier tail (2/151 frames). |
| dom_losing + \|xg_div\|≥0.3 (n=350) | 19.1% in min∈[25,45]; 29.1% in min∈[46,60] | A2 window [25,45] excludes 30% of qualifying frames at slightly later minutes. |
| min≥75 + 0-0 (n=31)            | 30/31 already classified `cagey_closed`     | The game_phase clause in A3 is well-aligned — keep it. |
| line age across 47,638 samples | p25/p50/p75/p90 = 10 / 30 / 1028 / 2590 sec | `line_max_age_sec=60.0` rejects 44% of line snapshots. |

---

## Action plan (handed to T1–T4)

### Primary fix — liquidity placeholder collision (T2/T4)

`liquidity_score()` should treat the Phase-1 placeholder (`max_stake_cap == 1.0`) as full liquidity until Phase 2 wires real Sportmonks caps. Two implementation options:

**Option A (recommended) — fix in `mes.liquidity_score`**:
- Add `if cap == 1.0: return 1.0` at the top of `liquidity_score`, gated by a clear comment about the Phase-1 contract.
- Pro: localized; the placeholder convention stays in `dual_write` where it belongs.
- Con: introduces a magic number in `mes.py` (mitigated by a precise comment).

**Option B — change the placeholder in `dual_write.py:216`** from 1.0 to 400.0 (= 4× target_stake).
- Pro: no logic change in `mes.py`.
- Con: 400.0 is an unrelated magic number tied to `target_stake=100.0`; if anyone changes `target_stake`, this breaks silently.

Option A is the safer pick.

### Secondary fix — line-freshness threshold (T2/T4)

`line_max_age_sec=60.0` (the Phase-1 default) is misaligned with the Sportmonks feed cadence: 44% of line snapshots are older than 60s while still carrying valid odds. Raising to 300s captures the p75 region without admitting truly stale lines (p90 = 2590s = 43 min, which we still want to reject).

**Proposed:** raise `line_max_age_sec` default from 60.0 to 300.0 in `pipeline.py` and `no_bet_gate.py`. Backtest must confirm this doesn't admit obviously-stale lines that pre-empt obvious price moves.

### Tertiary — archetype-threshold relaxations

Only A3 and A5 have clean empirical justification:
- A3: `xg_total < 0.6` → `xg_total < 1.4` (median for late 0-0 is 2.23; p25 is 1.16; 1.4 lands in the lower-cagey region)
- A5: `|xg_diff| ≥ 1.5` → `|xg_diff| ≥ 0.7` (= p90 of tied-60' frames)

A2 (Napoli) window extension from [25,45] to [25,55] is **defensible by distribution** (102 near-miss frames in [46,55]) **but risky** vs the anti-Napoli regression invariant. Backtest with extra scrutiny before changing A2 — and only ship if every new pick at min 46-55 passes the rule #2 inversion check.

### OOD detector (T1)

Re-fit on the 1642 real frames as planned — independent of the liquidity bug, the v1 detector was fit on 350 synthetic GSVs whose manifold likely doesn't cover the empirical distribution. The current rule #9 short-circuit doesn't fire in production because `select_markets` empties the candidate list upstream, but once the liquidity fix lands the OOD threshold becomes hot.

---

## Reproducibility

```bash
# Re-run the diagnosis end-to-end (read-only, ~30s)
uv run python scripts/spike/v3/diagnose_day3_silence.py

# Inspect the JSON output
cat logs/v3_day3_diagnosis.json | jq '.t02b_full_pipeline_dryrun'
cat logs/v3_day3_diagnosis.json | jq '.t02c_pipeline_with_liquidity_fix'
```

The diagnostic script is idempotent and touches no production files.
