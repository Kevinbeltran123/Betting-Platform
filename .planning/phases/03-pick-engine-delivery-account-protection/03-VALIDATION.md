---
phase: 3
slug: pick-engine-delivery-account-protection
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-05-02
---

# Phase 3 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Source: 03-RESEARCH.md `## Validation Architecture` section.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.x + pytest-asyncio 1.3.x (already in `[project.optional-dependencies] dev`) |
| **Config file** | `pyproject.toml [tool.pytest.ini_options]` — `asyncio_mode = "auto"`, `slow` marker registered |
| **Quick run command** | `uv run pytest tests/ -x -m "not slow"` |
| **Full suite command** | `uv run pytest tests/ -v` |
| **Estimated runtime** | ~30s quick / ~2 min full |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/ -x -m "not slow"` (≤30s — all unit tests)
- **After every plan wave:** Run `uv run pytest tests/ -v` (≤2 min — adds reconcile + bot init integration)
- **Before `/gsd-verify-work`:** Full suite green + manual end-to-end (1 real fixture → 1 real Telegram alert → 1 real reconciliation against live Telegram + Anthropic + Supabase)
- **Max feedback latency:** 30 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 03-01-XX | 01 | 1 | Migration 004 | T-3-DDL | Idempotent CHECK widening | manual+verify | `uv run python scripts/verify_migration_004.py` | ❌ W0 | ⬜ pending |
| 03-02-XX | 02 | 1 | PICK-01 | — | edge < 5% filtered | unit | `pytest tests/train/test_backtest.py::test_simulate_pick_edge_threshold -x` | ✅ (Phase 02.1) — REUSED | ⬜ pending |
| 03-03-XX | 03 | 2 | PICK-02 | — | quarter_kelly math | unit | `pytest tests/picks/test_account_longevity.py::test_quarter_kelly -x` | ❌ W0 | ⬜ pending |
| 03-03-XX | 03 | 2 | PICK-02 | — | round to 0.5 unit | unit | `pytest tests/picks/test_account_longevity.py::test_round_half_unit -x` | ❌ W0 | ⬜ pending |
| 03-03-XX | 03 | 2 | PICK-03 (D-09) | T-3-CAP | 60% market-cap drop | unit | `pytest tests/picks/test_account_longevity.py::test_market_cap_drop -x` | ❌ W0 | ⬜ pending |
| 03-03-XX | 03 | 2 | PICK-03 (D-10) | T-3-DETERM | jitter stable across processes | unit | `pytest tests/picks/test_account_longevity.py::test_jitter_stable_across_processes -x` | ❌ W0 | ⬜ pending |
| 03-03-XX | 03 | 2 | PICK-03 (D-11) | T-3-DETERM | send_at stable for fixture_id | unit | `pytest tests/picks/test_account_longevity.py::test_send_at_stable -x` | ❌ W0 | ⬜ pending |
| 03-04-XX | 04 | 2 | CLAUDE-01 (cache) | T-3-PROMPT | learnings SHA stamp + cache block | unit | `pytest tests/claude/test_learnings_loader.py::test_sha_stamp_and_cache_block -x` | ❌ W0 | ⬜ pending |
| 03-05-XX | 05 | 3 | CLAUDE-01 (D-06) | T-3-INJECT | strict tool_use schema | unit | `pytest tests/claude/test_validator.py::test_tool_schema_strict -x` | ❌ W0 | ⬜ pending |
| 03-05-XX | 05 | 3 | CLAUDE-01 (D-07) | T-3-RETRY | failure → exactly 2 attempts, 60s sleep | unit (mocked) | `pytest tests/claude/test_validator.py::test_failure_double_retry -x` | ❌ W0 | ⬜ pending |
| 03-05-XX | 05 | 3 | CLAUDE-01 (D-07) | — | None verdict → filtered/claude_api_unavailable | integration | `pytest tests/picks/test_engine.py::test_claude_unavailable_filters -x` | ❌ W0 | ⬜ pending |
| 03-06-XX | 06 | 3 | PICK-04 (D-12) | T-3-XSS | HTML escapes &<> in team names | unit | `pytest tests/telegram/test_sender.py::test_render_escapes_special_chars -x` | ❌ W0 | ⬜ pending |
| 03-06-XX | 06 | 3 | PICK-04 (D-14) | — | FLAG → WARNING + reason_code | unit | `pytest tests/telegram/test_sender.py::test_flag_warning_marker -x` | ❌ W0 | ⬜ pending |
| 03-06-XX | 06 | 3 | PICK-04 (D-15) | — | bullets split on ` * `, max 3 | unit | `pytest tests/telegram/test_sender.py::test_summary_bullets_max_3 -x` | ❌ W0 | ⬜ pending |
| 03-06-XX | 06 | 3 | PICK-04 init | — | Application init no-polling, AIORateLimiter attached | unit | `pytest tests/telegram/test_bot.py::test_init_no_polling -x` | ❌ W0 | ⬜ pending |
| 03-07-XX | 07 | 4 | PICK-05 (D-04) | T-3-IDEMP | all paths persist (filtered/rejected/pending/sent) | integration | `pytest tests/picks/test_engine.py::test_all_paths_persist -x` | ❌ W0 | ⬜ pending |
| 03-08-XX | 08 | 4 | PICK-05 (D-16) | — | FT→won/lost; PST/CANC/ABD→void; PEN→regulation+ET | unit | `pytest tests/scheduler/test_reconcile.py::test_status_to_settlement -x` | ❌ W0 | ⬜ pending |
| 03-08-XX | 08 | 4 | PICK-05 (D-16) | — | reschedule on 2H/ET/SUSP | unit | `pytest tests/scheduler/test_reconcile.py::test_reschedule_on_in_play -x` | ❌ W0 | ⬜ pending |
| 03-08-XX | 08 | 4 | PICK-05 (recover) | T-3-MEMSTORE | re-queue pending picks on startup | integration | `pytest tests/scheduler/test_orchestrator.py::test_recover_pending_sends -x` | ❌ W0 | ⬜ pending |
| 03-08-XX | 08 | 4 | PICK-05 (D-01) | T-3-DUP-ALERT | T-30min skipped when T-2h pending | unit | `pytest tests/scheduler/test_orchestrator.py::test_t30_skipped_when_t2h_pending -x` | ❌ W0 | ⬜ pending |
| 03-08-XX | 08 | 4 | PICK-05 (D-01) | T-3-DUP-ALERT | T-30min PROCEEDS when T-2h was REJECTed | unit | `pytest tests/scheduler/test_orchestrator.py::test_t30_proceeds_when_t2h_rejected -x` | ❌ W0 | ⬜ pending |
| 03-08-XX | 08 | 4 | PICK-05 (D-01) | T-3-DUP-ALERT | T-30min PROCEEDS when T-2h was filtered (no edge) | unit | `pytest tests/scheduler/test_orchestrator.py::test_t30_proceeds_when_t2h_filtered -x` | ❌ W0 | ⬜ pending |
| 03-08-XX | 08 | 4 | PICK-05 (RESEARCH Q3) | T-3-RECONCILE-ABANDONED | reconcile abandons after 4 retries → ERROR log, status stays pending | unit | `pytest tests/scheduler/test_reconcile.py::test_reconcile_abandoned_after_4_retries -x` | ❌ W0 | ⬜ pending |
| 03-09-XX | 09 | 1 | CORNERS-01 (D-17a) | — | manual checklist file structure | structural | `pytest tests/scripts/test_corners_gate_artifacts.py::test_probe_md_structure -x` | ❌ W0 | ⬜ pending |
| 03-10-XX | 10 | 1 | CORNERS-01 (D-17b) | — | ≥95%, ≥3 seasons, FT-only | unit | `pytest tests/scripts/test_corners_gate_coverage.py::test_threshold_logic -x` | ❌ W0 | ⬜ pending |
| 03-10-XX | 10 | 1 | CORNERS-01 (D-18) | — | gate-fail → 3 artifacts (ROADMAP edit + STATE entry + commit) | integration | `pytest tests/scripts/test_corners_gate_descope.py::test_descope_three_artifacts -x` | ❌ W0 | ⬜ pending |
| 03-11-XX | 11 | 5 | E2E smoke | — | 1 fixture → 1 alert → 1 reconciliation (live) | manual | runbook in plan 11 | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/picks/__init__.py`, `tests/picks/test_account_longevity.py` — covers PICK-02, PICK-03 (D-09, D-10, D-11)
- [ ] `tests/picks/test_engine.py` — covers PICK-05 (all-paths persist), claude_unavailable_filters
- [ ] `tests/claude/__init__.py`, `tests/claude/test_validator.py` — covers CLAUDE-01 (D-06, D-07)
- [ ] `tests/claude/test_learnings_loader.py` — covers SHA stamp + cache block presence
- [ ] `tests/telegram/__init__.py`, `tests/telegram/test_bot.py` — covers init/no-polling/AIORateLimiter
- [ ] `tests/telegram/test_sender.py` — covers PICK-04 (D-12, D-14, D-15)
- [ ] `tests/scheduler/test_reconcile.py` — covers D-16 (status mapping, reschedule, settlement)
- [ ] `tests/scheduler/test_orchestrator.py` — extends with `test_recover_pending_sends` (Pitfall 6) + `test_t30_skipped_when_t2h_pending` (D-01 dup-alert guard)
- [ ] `tests/scripts/__init__.py`, `tests/scripts/test_corners_gate_artifacts.py`, `tests/scripts/test_corners_gate_coverage.py`, `tests/scripts/test_corners_gate_descope.py` — covers CORNERS-01 (D-17, D-18)
- [ ] `tests/conftest.py` — extend with `mock_anthropic_client` fixture (returns canned ClaudeVerdict), `mock_telegram_bot` fixture (records send_message calls)
- [ ] `scripts/verify_migration_004.py` — read-only `information_schema` + `pg_constraint` query mirroring 02.1's verify_migration_003.py pattern

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Telegram channel receives one alert per qualifying pick | PICK-04 | Real network egress to Telegram, real channel | Run `python scripts/smoke_send_pick.py --fixture <id>` against live channel; visually confirm one message with HTML-rendered headline + bullets + footer |
| Anthropic Role C returns CONFIRM/FLAG/REJECT for representative pick | CLAUDE-01 | Real Anthropic API call, non-deterministic content | Run `python scripts/smoke_validate_pick.py --pick <id>`; confirm tool_use response parses to `ClaudeVerdict` and `verdict` ∈ {CONFIRM, FLAG, REJECT} |
| CORNERS-01 Part (a) — Betano time-window market probe | CORNERS-01 (D-17a) | Bookmaker live UI, requires login | Kevin executes checklist in `scripts/corners_gate_probe.md`; writes findings to `scripts/corners_gate_findings.md` |
| Migration 004 applied to live Supabase | Migration 004 | Production-grade DDL via Supabase MCP path | Apply via Supabase MCP `apply_migration` (mirrors 02.1 D-15); verify via `uv run python scripts/verify_migration_004.py` (4 columns + widened CHECK constraint + idx_picks_sport_market_created index + picks_unique_prediction unique constraint) |
| `learnings.md` SHA stamp visible in `claude_reasoning` audit field | CLAUDE-01 (audit) | Requires actual DB row inspection | After smoke pick: `select claude_reasoning ->> 'learnings_sha' from picks where id = <id>` returns 40-char hex |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 30s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
