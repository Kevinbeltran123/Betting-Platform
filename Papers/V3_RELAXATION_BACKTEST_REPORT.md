# V3 Day-3 Relaxation Backtest Report

**Decision:** **PASS**

## Summary table

| Metric | Baseline (current) | Fix 1 (liquidity only) | Fix 1+2+3+4 + OOD v2 |
|--------|--------------------|------------------------|----------------------|
| total candidates    | 0 | 684 | 756 |
| allowed picks       | 0 | 121 | 169 |
| frames with allowed | 0 | 89 | 115 |
| anti-Napoli violations | 0 | 0 | 0 |
| archetype diversity | 0 | 4 | 5 |

## Proposed config: per-archetype distribution

  - dominant_losing_napoli: 101
  - cruise_mode: 34
  - regression_to_xg: 16
  - numerical_sustained: 10
  - lead_two_defensive_sub: 8

## Proposed config: per-market-family distribution

  - goals: 102
  - btts: 64
  - corners: 2
  - next_corner: 1

## Proposed config: gate denial reasons (downstream of MES routing)

  - rule_4: 566
  - rule_8: 18
  - rule_9: 3

## Sample of first 50 proposed picks

| fid | min | score | dom_los | archetype | market | dir | MES | base_edge | fair_prob |
|-----|-----|-------|---------|-----------|--------|-----|-----|-----------|-----------|
| 19441858 | 67 | 0-3 | True | lead_two_defensive_sub | alternative_match_goals_over_5.5 | over | 10.159 | 0.882 | 1.0 |
| 19441858 | 68 | 0-3 | True | lead_two_defensive_sub | alternative_match_goals_over_5.5 | over | 10.699 | 0.889 | 1.0 |
| 19441858 | 69 | 0-3 | True | lead_two_defensive_sub | alternative_match_goals_over_5.5 | over | 11.209 | 0.889 | 1.0 |
| 19441858 | 70 | 0-3 | True | lead_two_defensive_sub | alternative_match_goals_over_5.5 | over | 11.769 | 0.889 | 1.0 |
| 19441858 | 71 | 0-3 | True | lead_two_defensive_sub | alternative_match_goals_over_5.5 | over | 12.544 | 0.9 | 1.0 |
| 19695411 | 34 | 0-1 | True | dominant_losing_napoli | 1st_half_goal_line_(0-1)_over_1.5 | home | 4.962 | 0.354 | 0.688 |
| 19695411 | 35 | 0-1 | True | dominant_losing_napoli | 1st_half_goal_line_(0-1)_over_1.5 | home | 5.294 | 0.378 | 0.681 |
| 19695411 | 36 | 0-1 | True | dominant_losing_napoli | 1st_half_goal_line_(0-1)_over_1.5 | home | 5.201 | 0.371 | 0.675 |
| 19695411 | 37 | 0-1 | True | dominant_losing_napoli | 1st_half_goal_line_(0-1)_over_1.5 | home | 5.105 | 0.365 | 0.668 |
| 19695411 | 38 | 0-1 | True | dominant_losing_napoli | 1st_half_goal_line_(0-1)_over_1.5 | home | 5.192 | 0.371 | 0.661 |
| 19695411 | 39 | 0-1 | True | dominant_losing_napoli | 1st_half_goal_line_(0-1)_over_1.5 | home | 5.56 | 0.397 | 0.654 |
| 19695411 | 40 | 0-1 | True | dominant_losing_napoli | 1st_half_goal_line_(0-1)_over_1.5 | home | 5.754 | 0.411 | 0.646 |
| 19695411 | 41 | 0-1 | True | dominant_losing_napoli | 1st_half_goal_line_(0-1)_over_1.5 | home | 6.144 | 0.439 | 0.639 |
| 19695411 | 42 | 0-1 | True | dominant_losing_napoli | 1st_half_goal_line_(0-1)_over_1.5 | home | 6.403 | 0.457 | 0.631 |
| 19695411 | 43 | 0-1 | True | dominant_losing_napoli | 1st_half_goal_line_(0-1)_over_1.5 | home | 6.489 | 0.464 | 0.624 |
| 19695411 | 44 | 0-1 | True | dominant_losing_napoli | 1st_half_goal_line_(0-1)_over_1.5 | home | 6.56 | 0.469 | 0.616 |
| 19695411 | 74 | 0-3 | True | lead_two_defensive_sub | match_corners_under_10.0 | over | 12.413 | 0.9 | 1.0 |
| 19695410 | 80 | 0-1 | True | cruise_mode | alternative_match_goals_over_3.5 | under | 19.225 | 0.961 | 1.0 |
| 19695412 | 80 | 1-0 | False | cruise_mode | alternative_match_goals_over_3.5 | under | 19.224 | 0.961 | 1.0 |
| 19695410 | 81 | 0-1 | True | cruise_mode | alternative_match_goals_over_3.5 | under | 19.227 | 0.961 | 1.0 |
| 19699661 | 30 | 0-2 | True | dominant_losing_napoli | result___both_teams_to_score_grasshopper | home | 11.613 | 0.683 | 0.801 |
| 19699661 | 30 | 0-2 | True | dominant_losing_napoli | result___both_teams_to_score_draw_/_yes | home | 10.522 | 0.619 | 0.801 |
| 19699661 | 31 | 0-2 | True | dominant_losing_napoli | result___both_teams_to_score_grasshopper | home | 11.521 | 0.678 | 0.795 |
| 19699661 | 31 | 0-2 | True | dominant_losing_napoli | result___both_teams_to_score_draw_/_yes | home | 10.43 | 0.614 | 0.795 |
| 19699661 | 32 | 0-2 | True | dominant_losing_napoli | result___both_teams_to_score_grasshopper | home | 11.426 | 0.672 | 0.79 |
| 19699661 | 32 | 0-2 | True | dominant_losing_napoli | result___both_teams_to_score_draw_/_yes | home | 10.335 | 0.608 | 0.79 |
| 19699661 | 33 | 0-2 | True | dominant_losing_napoli | result___both_teams_to_score_grasshopper | home | 11.329 | 0.666 | 0.784 |
| 19699661 | 33 | 0-2 | True | dominant_losing_napoli | alternative_match_goals_over_7.5 | home | 10.24 | 0.731 | 0.784 |
| 19699661 | 34 | 0-2 | True | dominant_losing_napoli | result___both_teams_to_score_grasshopper | home | 11.34 | 0.667 | 0.778 |
| 19699661 | 34 | 0-2 | True | dominant_losing_napoli | alternative_match_goals_over_7.5 | home | 10.157 | 0.726 | 0.778 |
| 19699661 | 35 | 0-2 | True | dominant_losing_napoli | result___both_teams_to_score_grasshopper | home | 11.237 | 0.661 | 0.772 |
| 19699661 | 35 | 0-2 | True | dominant_losing_napoli | alternative_match_goals_over_7.5 | home | 10.073 | 0.719 | 0.772 |
| 19699661 | 36 | 0-2 | True | dominant_losing_napoli | result___both_teams_to_score_grasshopper | home | 11.131 | 0.655 | 0.766 |
| 19699661 | 36 | 0-2 | True | dominant_losing_napoli | alternative_match_goals_over_7.5 | home | 10.056 | 0.718 | 0.766 |
| 19699661 | 37 | 0-2 | True | dominant_losing_napoli | result___both_teams_to_score_grasshopper | home | 11.023 | 0.648 | 0.76 |
| 19699661 | 37 | 0-2 | True | dominant_losing_napoli | alternative_match_goals_over_7.5 | home | 9.967 | 0.712 | 0.76 |
| 19699661 | 38 | 0-2 | True | dominant_losing_napoli | result___both_teams_to_score_grasshopper | home | 10.911 | 0.642 | 0.753 |
| 19699661 | 38 | 0-2 | True | dominant_losing_napoli | alternative_match_goals_over_7.5 | home | 9.933 | 0.709 | 0.753 |
| 19699661 | 39 | 0-2 | True | dominant_losing_napoli | result___both_teams_to_score_grasshopper | home | 10.896 | 0.641 | 0.746 |
| 19699661 | 39 | 0-2 | True | dominant_losing_napoli | result___both_teams_to_score_draw_/_yes | home | 9.852 | 0.58 | 0.746 |
| 19699661 | 40 | 0-2 | True | dominant_losing_napoli | result___both_teams_to_score_grasshopper | home | 10.779 | 0.634 | 0.739 |
| 19699661 | 40 | 0-2 | True | dominant_losing_napoli | alternative_match_goals_over_7.5 | home | 9.742 | 0.696 | 0.739 |
| 19439606 | 61 | 1-1 | False | numerical_sustained | alternative_match_goals_over_5.5 | over | 8.259 | 0.871 | 0.938 |
| 19439606 | 62 | 1-1 | False | numerical_sustained | alternative_match_goals_over_5.5 | over | 8.47 | 0.863 | 0.929 |
| 19705549 | 25 | 0-1 | True | dominant_losing_napoli | alternative_match_goals_over_6.5 | home | 8.839 | 0.676 | 0.714 |
| 19705549 | 25 | 0-1 | True | dominant_losing_napoli | result___both_teams_to_score_southampton | home | 8.456 | 0.532 | 0.714 |
| 19439606 | 63 | 1-1 | False | numerical_sustained | alternative_match_goals_over_5.5 | over | 8.766 | 0.861 | 0.92 |
| 19700213 | 42 | 0-1 | True | dominant_losing_napoli | both_teams_to_score_in_1st_half_yes | home | 10.167 | 0.598 | 0.689 |
| 19700213 | 42 | 0-1 | True | dominant_losing_napoli | alternative_match_goals_over_5.5 | home | 9.107 | 0.651 | 0.689 |
| 19705549 | 26 | 0-1 | True | dominant_losing_napoli | alternative_match_goals_over_6.5 | home | 9.159 | 0.665 | 0.709 |

## Per-configuration details

### baseline

```json
{
  "target_stake": 100.0,
  "mes_threshold": 0.6,
  "line_max_age_sec": 60.0,
  "ood_active": false,
  "ood_n_train": null,
  "ood_threshold": null
}
```

### liquidity_fix_only

```json
{
  "target_stake": 100.0,
  "mes_threshold": 0.6,
  "line_max_age_sec": 60.0,
  "ood_active": false,
  "ood_n_train": null,
  "ood_threshold": null
}
```

### proposed_full

```json
{
  "target_stake": 100.0,
  "mes_threshold": 0.6,
  "line_max_age_sec": 300.0,
  "ood_active": true,
  "ood_n_train": 1692,
  "ood_threshold": 5.0433916464495345
}
```

## Reproduce

```bash
uv run python scripts/spike/v3/backtest_relaxed_archetypes.py
```
