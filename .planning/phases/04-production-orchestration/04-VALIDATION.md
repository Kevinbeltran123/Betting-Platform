---
phase: 4
slug: production-orchestration
status: draft
nyquist_compliant: false
wave_0_complete: false
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

> Populated by gsd-planner. Each PLAN.md task gets a row here keyed by `{phase}-{plan}-{task}` ID. Planner attaches `<validation>` blocks to tasks; this table aggregates them.

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 4-00-01 | 00 | 0 | DATA-04 | — | N/A | wave0 | `uv run pytest tests/unit/production/ tests/unit/metrics/ tests/unit/clv/test_trend_checker.py --collect-only` | ❌ W0 | ⬜ pending |
| 4-XX-YY | XX | 1+ | REQ-{XX} | T-4-{N} / — | {expected secure behavior or "N/A"} | unit/integration/manual | `{command}` | ✅ / ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

> Planner MUST extend this table with one row per task before exiting. Mapping is mechanical — copy task IDs from PLAN.md frontmatter.

---

## Wave 0 Requirements

- [ ] `tests/unit/production/__init__.py` — package marker
- [ ] `tests/unit/production/test_builder.py` — stubs for `build_orchestrator(settings)` factory tests (D-05)
- [ ] `tests/unit/production/test_main.py` — stubs for SIGTERM/SIGINT handler + `asyncio.run` smoke-test (D-05)
- [ ] `tests/unit/production/test_heartbeat.py` — stubs for `HeartbeatTicker.tick()` (file mtime + sd_notify call assertion)
- [ ] `tests/unit/clv/test_trend_checker.py` — stubs for D-09–D-12 (rolling-50 query, threshold, cooldown, per-market guard)
- [ ] `tests/unit/metrics/__init__.py` — package marker
- [ ] `tests/unit/metrics/test_aggregator.py` — stubs for D-13 idempotency, period boundaries
- [ ] `tests/unit/metrics/test_drift.py` — stubs for D-14 hard threshold, soft (1.5×stdev_floored), insufficient sample
- [ ] `tests/unit/picks/test_engine_claude_failure.py` — stubs for D-01 filter vs skip branches
- [ ] `tests/unit/telegram/test_routing.py` — stubs for D-03 picks-channel vs ops-channel routing
- [ ] `tests/integration/test_metrics_aggregator_idempotent.py` — stub for repeat-run idempotency on test DB (D-13)
- [ ] `tests/integration/test_compute_period_rpc.py` — stub for Supabase RPC `compute_period` LEFT JOIN behavior (D-02 picks have no clv_record)
- [ ] `tests/conftest.py` — extend with `mock_sd_notify`, `mock_ops_telegram_sender`, `tmp_heartbeat_path` fixtures
- [ ] `tests/integration/conftest.py` — extend with `seeded_picks_with_clv` fixture (parametrized for picks-with-CLV vs picks-without-CLV)

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

- [ ] All tasks have `<validation>` block referencing automated verify cmd OR a Wave 0 stub OR a row in Manual-Only table
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify (manual-only tasks must be flanked by ≤2 unverified tasks)
- [ ] Wave 0 covers every MISSING test file referenced in any plan's `validation.test_files`
- [ ] No watch-mode flags (`--watch`, `-w`) in any automated command — all CI-friendly
- [ ] Feedback latency < 30s for unit, < 120s for full suite
- [ ] `nyquist_compliant: true` set in frontmatter once planner finalizes the per-task table

**Approval:** pending
