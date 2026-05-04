---
phase: 04
plan: 01
status: complete
completed: 2026-05-04
tasks_total: 3
tasks_done: 3
tests_added: 10
files_modified: 3
---

# Plan 04-01 — Settings extension (9 Phase 4 knobs)

## What was built

Settings has 9 new flat fields covering D-01 (claude_failure_mode), D-03 (telegram_ops_channel_id + validator), D-07 (heartbeat_file_path), D-09/D-11 (CLV trend), D-14 (drift gates), and RESEARCH §3 (drift_stdev_floor_pp). All defaults match CONTEXT.md decisions; ops channel validator mirrors Phase 3's pattern. sdnotify==0.3.2 pinned in pyproject.toml + lockfile.

## Tasks

| # | Task | Outcome |
|---|------|---------|
| 1 | Settings extension + ops channel validator | 9 fields + Literal typing; flat (no subclass per drift risk #3); `_validate_ops_channel_id` rejects malformed IDs; ruff-clean on new code |
| 2 | Convert test_settings_phase4.py from skip→GREEN | 10 tests passing in 0.08s (extra prefix-rejection split out from short-id case) |
| 3 | Pin sdnotify==0.3.2 in pyproject.toml | Locked, synced, importable; silent no-op on macOS |

## Key fields

```python
claude_failure_mode: Literal["filter", "skip"] = "filter"   # D-01
telegram_ops_channel_id: str = ""                           # D-03 + validator
heartbeat_file_path: str = "/var/run/bip/heartbeat"         # D-07
clv_trend_alert_threshold: float = 1.0                      # D-09
clv_trend_cooldown_hours: int = 12                          # D-11
drift_check_min_picks_per_window: int = 30                  # D-14
drift_absolute_threshold_pp: float = 2.0                    # D-14 hard
drift_stdev_multiplier: float = 1.5                         # D-14 soft
drift_stdev_floor_pp: float = 1.0                           # RESEARCH §3 (NEW)
```

## Verification

```
$ uv run pytest tests/test_settings_phase4.py -x --tb=short
============================== 10 passed in 0.08s ==============================

$ uv pip show sdnotify | head -2
Name: sdnotify
Version: 0.3.2
```

## Deviations

- **Comment placement on Phase 4 fields** moved above each field (one line per comment) instead of inline, to keep the new code under ruff's 100-char line limit. Pre-existing Phase 2/3 inline-comment lines (model_dir, telegram_channel_id, reconcile_max_retries) still exceed the limit — left untouched per "no surrounding cleanup" rule.
- **Extra prefix-rejection test** (`test_telegram_ops_channel_id_validator_rejects_no_minus100_prefix`) split out so the validator's two failure paths (short vs. wrong prefix) are individually verifiable. Total ended at 10 GREEN, not 9 — plan acceptance line `grep -c "def test_" returns 10` matches.

## Wires

- 04-02 will inject `Settings` into `HeartbeatTicker` (reads `heartbeat_file_path`) and `ClvTrendChecker` (reads `clv_trend_alert_threshold`, `clv_trend_cooldown_hours`).
- 04-03 will read `drift_*` fields in the drift compute path.
- 04-04 will branch on `claude_failure_mode` in `PickEngine.evaluate`.
- 04-05 will instantiate two `TelegramSender`s from `telegram_channel_id` + `telegram_ops_channel_id`.

## Self-Check: PASSED

- [x] All 3 tasks executed
- [x] Each task committed individually (3 commits this plan)
- [x] 10/10 settings tests GREEN
- [x] sdnotify installed + importable
- [x] ruff-clean on new code (3 pre-existing E501s preserved)
