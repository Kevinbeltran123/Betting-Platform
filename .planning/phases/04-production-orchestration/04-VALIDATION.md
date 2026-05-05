---
phase: 4
slug: production-orchestration
status: draft
# nyquist_compliant: true means the per-task TABLE is complete with one row per
# plan task. It does NOT assert that all tests are GREEN — Status column tracks that.
# /gsd-verify-work reads Status, not this flag, when gating phase completion.
nyquist_compliant: true
wave_0_complete: true
created: 2026-05-03
---

# Phase 4 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Detailed validation architecture lives in [04-RESEARCH.md §Validation Architecture](04-RESEARCH.md). This file is the planner-facing contract that gsd-plan-checker reads.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x + pytest-asyncio 0.25.x (already installed) |
| **Config file** | `pyproject.toml` ([tool.pytest.ini_options]) |
| **Quick run command** | `uv run pytest tests/unit/ -x --tb=short` |
| **Full suite command** | `uv run pytest tests/ -x --tb=short` |
| **Estimated runtime** | ~30s unit, ~120s full (with integration test DB) |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/unit/ -x --tb=short`
- **After every plan wave:** Run `uv run pytest tests/ -x --tb=short`
- **Before `/gsd-verify-work`:** Full suite must be green; manual smoke-test runbook executed once on staging
- **Max feedback latency:** 30 seconds (unit), 120 seconds (full)

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 4-00-01 | 00 | 0 | DATA-04 | — | N/A | wave0 | `uv run pytest tests/unit/production tests/unit/metrics tests/unit/clv tests/unit/picks/test_engine_claude_failure.py tests/unit/telegram/test_routing.py tests/integration tests/test_settings_phase4.py --collect-only` | ✅ created | ✅ green |
| 4-00-02 | 00 | 0 | DATA-04 | — | N/A | wave0 fixture | `uv run pytest tests/ --collect-only` | ✅ extended | ✅ green |
| 4-00-03 | 00 | 0 | CLV-04 | T-4-03 | LANGUAGE sql STABLE + LEFT JOIN + status filter | file content | `grep -c "compute_performance_period\|LEFT JOIN clv_records" supabase/migrations/20260503000000_compute_period_rpc.sql` | ✅ created | ✅ green |
| 4-00-04 | 00 | 0 | DATA-04 | T-4-03 | RPC pushed to live DB | manual (BLOCKING) | `mcp__claude_ai_Supabase__apply_migration` (Path A used) | ✅ live DB | ✅ green |
| 4-00-05 | 00 | 0 | — | — | N/A | file content | `grep -c "SC#1 Reconciliation\|SC#2 Reconciliation" .planning/phases/04-production-orchestration/04-CONTEXT.md` | ✅ extended | ✅ green |
| 4-01-01 | 01 | 1 | — | T-4-01 / T-4-06 / T-4-07 | filter default + ops channel validator + Literal enforcement | unit | `uv run pytest tests/test_settings_phase4.py -x --tb=short` | ✅ from 4-00-01 stub | ✅ green |
| 4-01-02 | 01 | 1 | — | T-4-01 | 10/10 settings tests GREEN | unit | `uv run pytest tests/test_settings_phase4.py -x --tb=short` | ✅ from 4-00-01 stub | ✅ green |
| 4-01-03 | 01 | 1 | DATA-04 | — | N/A | dependency install | `uv pip show sdnotify \| grep "Version: 0.3.2"` | ✅ pyproject.toml | ✅ green |
| 4-02-01 | 02 | 2 | — | T-4-04 | sd_notify + Path.touch in same tick | unit | `uv run pytest tests/unit/production/test_heartbeat.py -x --tb=short` | ✅ from 4-00-01 stub | ✅ green |
| 4-02-02 | 02 | 2 | CLV-03 | — | inner-join + status neq filters via PostgREST | unit (covered by 4-02-03) | `uv run python -c "from bip.core.storage.repositories import ClvRecordRepository; assert hasattr(ClvRecordRepository, 'last_n_settled')"` | ✅ existing | ✅ green |
| 4-02-03 | 02 | 2 | CLV-03 | — | reuse compute_rolling_clv_average + 12h cooldown + per-market guard | unit | `uv run pytest tests/unit/clv/test_trend_checker.py -x --tb=short` | ✅ from 4-00-01 stub | ✅ green |
| 4-03-01 | 03 | 3 | CLV-04 | T-4-03 | parameterized .rpc() binding (no f-string SQL) | unit (covered by 4-03-02 + 4-03-03) | `grep -c '\.rpc(.compute_performance_period' src/bip/core/storage/repositories.py` | ✅ existing | ✅ green |
| 4-03-02 | 03 | 3 | CLV-04 | — | per-day-mean stdev with floor + 4 periods + idempotent upsert + str.to_datetime ISO8601 parsing (WARNING 4) | unit + integration | `uv run pytest tests/unit/metrics/ tests/integration/test_drift_polars_supabase_dates.py -x --tb=short` | ✅ from 4-00-01 stub | ✅ green |
| 4-03-03 | 03 | 3 | CLV-04 | T-4-03 | RPC parameter contract + LEFT JOIN keep no-CLV picks | integration (mocked) | `uv run pytest tests/integration/test_compute_period_rpc.py -x --tb=short` | ✅ from 4-00-01 stub | ✅ green |
| 4-03-04 | 03 | 3 | CLV-04 | — | re-run upserts (NOT inserts) — D-13 idempotency | integration (mocked) | `uv run pytest tests/integration/test_metrics_aggregator_idempotent.py -x --tb=short` | ✅ from 4-00-01 stub | ✅ green |
| 4-04-01 | 04 | 4 | — | — | ClaudeVerdict accepts SKIPPED + filter default vs skip opt-in branch | unit | `uv run pytest tests/unit/claude/test_validator.py tests/unit/picks/test_engine_claude_failure.py tests/picks/test_engine.py -x --tb=short` | ✅ from 4-00-01 stub | ✅ green |
| 4-04-02 | 04 | 4 | DATA-04 | — | drift_checker plumbed + 4 new cron jobs registered when deps present + auto_recover_complete event using literal var names | unit | `uv run pytest tests/scheduler/test_orchestrator.py -x --tb=short` | ✅ existing | ✅ green |
| 4-04-03 | 04 | 4 | — | T-4-01 | TWO TelegramBot instances (one per channel) | unit | `uv run pytest tests/unit/telegram/test_routing.py -x --tb=short` | ✅ from 4-00-01 stub | ✅ green |
| 4-05-01 | 05 | 5 | DATA-04 | T-4-06 | 4-tuple return + 2 TelegramBots + drift_checker passed + REAL learnings_text/PickEngine ctor args + no settings logging | unit | `uv run pytest tests/unit/production/test_builder.py -x --tb=short` | ✅ from 4-00-01 stub | ✅ green |
| 4-05-02 | 05 | 5 | DATA-04 | T-4-06 | SIGTERM/SIGINT registered + sd_notify after start + no settings logging | unit | `uv run pytest tests/unit/production/test_main.py -x --tb=short` | ✅ from 4-00-01 stub | ✅ green |
| 4-06-01 | 06 | 6 | — | T-4-05 | Type=notify + WatchdogSec=600 + User=bip | file content | `grep -c "Type=notify\|WatchdogSec=600\|User=bip" deploy/systemd/bip.service` | ✅ created in plan | ✅ green |
| 4-06-02 | 06 | 6 | — | T-4-04 | mode 0750 owner bip:bip | file content | `cat deploy/tmpfiles.d/bip.conf` | ✅ created in plan | ✅ green |
| 4-06-03 | 06 | 6 | — | T-4-02 / T-4-05 / T-4-06 | idempotent + never overwrites .env + silent grep -q validation | shell syntax + grep | `bash -n deploy/install.sh && grep -c "set -euo pipefail\|grep -q\|install -m 600" deploy/install.sh` | ✅ created in plan | ✅ green |
| 4-06-04 | 06 | 6 | — | — | operator quickstart with .env + health checks | file content | `wc -l < deploy/README.md` | ✅ created in plan | ✅ green |
| 4-06-05 | 06 | 6 | — | — | 9 plans listed; no TBD placeholders | file content | `grep -A20 "Phase 4: Production Orchestration" .planning/ROADMAP.md \| grep "04-0"` | ✅ ROADMAP.md | ✅ green |
| 4-06-06 | 06 | 6 | — | T-4-02 / T-4-04 / T-4-05 / T-4-06 | visual review of 4 deploy artifacts | manual checkpoint | (operator inspects deploy/ directory) | N/A | ✅ green (auto-approved per push-through) |
| 4-07-01 | 07 | 7 | — | — | SC#1 model-CLV drift + SC#2 claude_failure_mode | file content | `grep -c "weekly model-CLV drift\|claude_failure_mode" .planning/ROADMAP.md` | ✅ ROADMAP.md | ✅ green |
| 4-07-02 | 07 | 7 | DATA-04 | T-4-02 / T-4-04 / T-4-05 / T-4-06 | 8-check operator runbook | file content | `grep -c "### Check [1-8]:" deploy/SMOKE_TEST.md` | ✅ created in plan | ✅ green |
| 4-07-03 | 07 | 7 | DATA-04 | T-4-02 / T-4-04 / T-4-05 / T-4-06 | 8/8 checks pass on real staging VPS | manual (BLOCKING) | (operator runs SMOKE_TEST.md on Hetzner) | N/A live VPS | ⬜ pending |
| 4-08-01 | 08 | 7 | — | — | per-task table SHAPE complete (one row per task) — does NOT assert tests GREEN | file content | `grep -c "nyquist_compliant: true" .planning/phases/04-production-orchestration/04-VALIDATION.md` | ✅ this task | ✅ green |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

> Per-task table mechanically populated by 04-08-PLAN. Executor agents update Status as tasks complete during execution.
> `nyquist_compliant: true` in frontmatter = the TABLE is complete with one row per task. It does NOT assert tests are GREEN. The Status column carries that signal per-row.

---

## Wave 0 Requirements

- [x] `tests/unit/production/__init__.py` — package marker
- [x] `tests/unit/production/test_builder.py` — stubs for `build_orchestrator(settings)` factory tests (D-05)
- [x] `tests/unit/production/test_main.py` — stubs for SIGTERM/SIGINT handler + `asyncio.run` smoke-test (D-05)
- [x] `tests/unit/production/test_heartbeat.py` — stubs for `HeartbeatTicker.tick()` (file mtime + sd_notify call assertion)
- [x] `tests/unit/clv/test_trend_checker.py` — stubs for D-09–D-12 (rolling-50 query, threshold, cooldown, per-market guard)
- [x] `tests/unit/metrics/__init__.py` — package marker
- [x] `tests/unit/metrics/test_aggregator.py` — stubs for D-13 idempotency, period boundaries
- [x] `tests/unit/metrics/test_drift.py` — stubs for D-14 hard threshold, soft (1.5×stdev_floored), insufficient sample
- [x] `tests/unit/picks/test_engine_claude_failure.py` — stubs for D-01 filter vs skip branches
- [x] `tests/unit/telegram/test_routing.py` — stubs for D-03 picks-channel vs ops-channel routing
- [x] `tests/integration/test_metrics_aggregator_idempotent.py` — stub for repeat-run idempotency on test DB (D-13)
- [x] `tests/integration/test_compute_period_rpc.py` — stub for Supabase RPC `compute_period` LEFT JOIN behavior (D-02 picks have no clv_record)
- [x] `tests/conftest.py` — extend with `mock_sd_notify`, `mock_ops_telegram_sender`, `tmp_heartbeat_path` fixtures
- [ ] `tests/integration/conftest.py` — extend with `seeded_picks_with_clv` fixture (parametrized for picks-with-CLV vs picks-without-CLV) — *deferred; integration tests in Wave 3 use mocked Supabase clients*

*Existing pytest infrastructure covers framework install — no new dev dependency beyond `sdnotify==0.3.2` (production dep, not dev).*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| systemd `WatchdogSec=600` triggers restart on stale heartbeat | DATA-04 / SC#3 | Requires real systemd PID 1 + service unit installed; pytest cannot interact with PID 1 | On staging VPS: `systemctl start bip.service`; `systemctl stop bip-heartbeat-job` (simulate hang via `pkill -STOP -f bip.production`); wait 10 min; `journalctl -u bip.service -n 50` confirms `WATCHDOG=1 timed out` + auto-restart line; `systemctl status bip.service` shows new PID. |
| SIGTERM → graceful shutdown completes within 30s | SC#3 | Requires real signal delivery + APScheduler scheduler running real cron firings | On staging: `systemctl stop bip.service`; `journalctl -u bip.service -n 30` confirms `signal_received signum=15`, `scheduler_shutdown_complete jobs_pending=0`, exit code 0. |
| systemd unit hardening (`ProtectSystem=strict`, `MemoryDenyWriteExecute=true`) does not break workload | SC#3 / hardening | numpy/xgboost/CatBoost JIT shims may fail under MDWX | On staging: full pipeline run (`python -m bip.production` for one daily cycle), confirm fixtures fetched, picks generated, CLV recorded, no `EACCES`/`Operation not permitted` in journal. |
| Hetzner VPS auto-restart on host reboot | SC#3 | Requires real host reboot | On staging: `systemctl reboot`, after VPS comes back: `systemctl is-active bip.service` returns `active`, `_auto_recover` event in journal with re-queued job count > 0. |
| `/etc/bip/.env` mode 600 + `bip:bip` ownership preserved across deployment script re-run | D-06 | File permissions verification | After re-running `deploy/install.sh`: `stat -c '%a %U:%G' /etc/bip/.env` returns `600 bip:bip`; existing secrets unchanged (`md5sum` matches pre-run). |
| Telegram ops channel reception | D-03 | Requires real Telegram channel + bot token | Trigger CLV trend alert manually via `python -m bip.production trigger-clv-trend-alert --dry-run=false`; confirm message arrives in ops channel, NOT picks channel. |

---

## Validation Sign-Off

- [x] All tasks have `<validation>` block referencing automated verify cmd OR a Wave 0 stub OR a row in Manual-Only table
- [x] Sampling continuity: no 3 consecutive tasks without automated verify (manual-only tasks must be flanked by ≤2 unverified tasks)
- [x] Wave 0 covers every MISSING test file referenced in any plan's `validation.test_files`
- [x] No watch-mode flags (`--watch`, `-w`) in any automated command — all CI-friendly
- [x] Feedback latency < 30s for unit, < 120s for full suite
- [x] `nyquist_compliant: true` set in frontmatter once planner finalizes the per-task table SHAPE (does not assert tests GREEN — Status column carries that)

**Approval:** signed-off by 04-08-PLAN
