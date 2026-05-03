---
phase: 03-pick-engine-delivery-account-protection
verified: 2026-05-03T20:09:07Z
status: human_needed
score: 4/5 must-haves verified (1 deferred to user — CORNERS-01 Part A manual probe)
overrides_applied: 0
re_verification: false
human_verification:
  - test: "CORNERS-01 Part A — fill in `scripts/corners_gate_findings.md` after probing Betano"
    expected: "5-league table with markets/naming/odds-range/min-stake/screenshot per fixture; verdict (PASS|FAIL) on the gate decision block"
    why_human: "Live Betano UI requires a logged-in browser session and human-readable inspection of corner time-window markets — cannot be probed programmatically by the verifier"
  - test: "Run `scripts/smoke_e2e_pick.py` end-to-end with live Telegram + Anthropic + Supabase, then fill the runbook Sign-off block"
    expected: "Telegram channel receives one rendered pick; Supabase `picks` row inserted with claude_validation populated; Pinnacle event resolution succeeds (or skip-no-event log when offered fixture has no Pinnacle event); exit 0"
    why_human: "Live API keys, real Telegram channel admin, and Anthropic billing require user-controlled credentials and external delivery confirmation"
  - test: "Verify `idx_picks_sport_market_created` index exists on the live Supabase `picks` table"
    expected: "Either run `SUPABASE_DB_PASSWORD=... uv run python scripts/verify_migration_004.py` (exit 0) OR confirm via Supabase MCP execute_sql that all 4 migration-004 invariants hold"
    why_human: "Verifier does not have the SUPABASE_DB_PASSWORD; plan 03-01 SUMMARY confirmed via MCP but a periodic re-confirmation against the live DB belongs to the operator"
deferred:
  - truth: "CLV-03 alert (rolling 50-pick avg <+1% → Telegram warning)"
    addressed_in: "Phase 4"
    evidence: "Phase 4 success criterion #5: 'If rolling 50-pick average CLV drops below +1%, a Telegram warning is sent'. `compute_rolling_clv_average` exists in `bip/clv/recorder.py`; scheduler job wiring intentionally deferred (STATE.md Phase 3 closeout decisions)."
  - truth: "CLV-04 daily aggregator (PerformanceMetric upsert)"
    addressed_in: "Phase 4"
    evidence: "Phase 4 success criterion #4: 'Performance metrics (ROI, yield, average CLV, ...) are aggregated in performance_metrics table'. Repository + table exist; aggregator job intentionally deferred (STATE.md)."
  - truth: "Production caller of PickEngine (orchestrator instantiation in __main__/setup)"
    addressed_in: "Phase 4"
    evidence: "Phase 4 goal: 'The full pipeline runs autonomously on a VPS with scheduled jobs'. STATE.md Phase 3 closeout: 'Production caller of PickEngine does NOT yet exist — only tests instantiate it. Production wiring is a Phase 4 deployment concern.' Smoke runner (`scripts/smoke_e2e_pick.py`) wires the engine for manual verification."
  - truth: "_reconcile_clv real implementation (rolling-50 trend + back-fill)"
    addressed_in: "Phase 4"
    evidence: "Method body is `clv_reconciliation_deferred` warning per quick-260503-k8k decisions. Cron entry retained for ops visibility; full implementation is Phase 4."
  - truth: "Empirical PL smoke train (~1,520 API credits) for ML-02/ML-03 to flip from structural-PASS to empirical-PASS"
    addressed_in: "Phase 02.1 deferral, owner-accepted risk"
    evidence: "STATE.md Phase 02.1 P11/P12 — 'Premier League smoke train: real end-to-end exit check (D-16 one-shot) — DEFERRED'. Not a Phase 3 concern but worth tracking."
  - truth: "Per-channel Telegram (paid sub-feed) + connection pooling (Supavisor) + Plugin Registry decorator pattern (G-CODE-06, G-LOGIC-11, G-SCALE-01..04)"
    addressed_in: "Phase 7 / v2"
    evidence: "AUDIT-GAPS.md classifies these as Grave/Moderado scalability gaps. CORE-02 layout drift acknowledged in REQUIREMENTS.md row note; tennis scaffold (Phase 7) will force the refactor."
---

# Phase 3: Pick Engine + Delivery + Account Protection — Verification Report

**Phase Goal:** Qualified picks with genuine edge are delivered via Telegram with account longevity protections active from the first alert, and Claude Role C validates every pick against red flags before sending.

**Verified:** 2026-05-03T20:09:07Z
**Status:** human_needed
**Re-verification:** No — initial verification (Phase 3 was never previously verified per AUDIT-GAPS appendix)

**Test suite snapshot:** `uv run pytest -q` → **282 passed, 0 failed** (matches expected count from quick-260503-k8k SUMMARY).

---

## Goal Achievement

### Observable Truths

| # | Truth (from ROADMAP.md Phase 3 Success Criteria) | Status | Evidence |
|---|---|---|---|
| 1 | A pick with edge ≥ per-market threshold triggers a Telegram alert showing fixture, market, selection, model probability, odds, edge%, stake, Claude validation status, and key reasoning bullets | VERIFIED | `PickEngine.evaluate` (engine.py:108) gates on per-market threshold via `LeagueRegistry.get(league).model_params.edge_threshold_<market>` (quick-260503-j74). YAML defines 1X2=0.08, BTTS=0.05, OU=0.05, AH=0.06, corners=0.07 (premier_league.yaml:25-29). `pick.html` template renders fixture/market/selection/best_odds/edge/suggested_stake/model_probability/bookmaker/claude_validation/up to 3 reasoning bullets (sender.py:_build_context + template). `TelegramSender.send_pick` flows the rendered HTML through `TelegramBot.send_html` (parse_mode=HTML). DateTrigger `send_pick_<fixture>_<market>` registered in `_schedule_send` (engine.py:245-260). |
| 2 | Quarter-Kelly stake sizing is applied with rounding to nearest 0.5 unit, and no more than 60% of weekly picks come from the same market (account longevity rotation enforced) | VERIFIED (rotation structurally dormant in 1X2-only Phase 3 — acknowledged in REQUIREMENTS.md PICK-03 + account_longevity.py:104-106) | `quarter_kelly_units(edge, odds, max_fraction=0.25)` clamps to `[0, 0.25]` (account_longevity.py:31-47). `round_to_nearest_half_unit` (line 50-56). `deterministic_jitter` ±10% via md5 (line 63-74). `exceeds_60pct_cap` rolling 168h drop-on-bind (line 95-125) wired into `PickEngine.evaluate` step 3 (engine.py:119-120). Spot-check: `quarter_kelly(0.05, 2.10) ≈ 0.0114`; jitter is reproducible across calls (`0.1` twice for fixture=12345). Settings.max_kelly_fraction default 0.25 (settings.py:32). |
| 3 | Claude Role C reads each pick against learnings/football-learnings.md and outputs CONFIRM/FLAG/REJECT — REJECT blocks the alert, FLAG sends with a warning tag | VERIFIED | `ClaudeValidator.validate` (validator.py:91-137) uses AsyncAnthropic + strict tool_use (`VALIDATE_PICK_TOOL`, additionalProperties=false) + forced tool_choice (Pitfall 3) + cache_control ephemeral on the learnings block. D-07 retry: 2 attempts × 60s sleep then returns None → engine maps to `filtered/claude_api_unavailable`. `engine.evaluate` step 4: `verdict.verdict == "REJECT"` → `_persist_rejected` (status=rejected, never sent); CONFIRM/FLAG → `_persist_pending` + `_schedule_send`. `pick.html` template branches on `pick.claude_validation == "FLAG"` and emits ⚠️ WARNING entity + `Claude flagged: <reason_code>` (D-14). Learnings file is real (~18KB Spanish corpus, restructured in commit 55f00be — placeholder fully replaced). git SHA stamped via `_git_sha` with sha256[:16] fallback (learnings_loader.py). |
| 4 | All picks (sent and filtered) are logged to Supabase `picks` table with status `pending` and updated to `won/lost/void` post-match | VERIFIED | Migration 004 (`20260502000000_add_claude_validation_to_picks.sql`) widens `picks_status_check` to include `filtered` and `rejected` and adds 4 `claude_*` columns + `picks_unique_prediction` UNIQUE on (fixture_id, market, prediction_id) + `idx_picks_sport_market_created`. `PickStatus` StrEnum has 7 members (types.py — pending/won/lost/void/push/filtered/rejected). Every branch in `engine.evaluate` calls `pick_repo.insert(pick)` (D-04 — `_persist_filtered`, `_persist_rejected`, `_persist_pending`). Reconciliation in `PipelineOrchestrator._reconcile_results` (orchestrator.py:441-524) handles all 16 API-Football status codes per Risk 9: SETTLED → won/lost, PEN → push (1X2), VOID/PST/CANC/ABD → void, IN_PLAY/NOT_STARTED → reschedule (max 4), Q3 RESOLVED → log abandon, unknown → log error and leave pending. Updates via `pick_repo.update_status_by_fixture` and `update_status` (repositories.py:186). |
| 5 | CORNERS-01 go/no-go gate is executed: Betano time-window corner markets verified and API-Football corner timing data confirmed for 5 leagues across 3+ seasons — result documented regardless of outcome | PARTIAL — Part B automated (FAIL as expected), Part A awaits human probe | **Part B (D-17b automated):** `scripts/corners_gate_coverage.py` runs end-to-end, exits 1 (FAIL) and writes `scripts/corners_gate_coverage.md` showing 0% coverage across all 5 leagues (`missing_cols=no_data`) — correct outcome per A5 (no historical corner data seeded yet; Phase 02.1 P09 omits corner columns). Result *is* documented. **Part A (D-17a manual):** `scripts/corners_gate_probe.md` (checklist) and `scripts/corners_gate_findings.md` (template) exist; the findings template is unfilled (`_(fill in)_` placeholders throughout — see `head -30` of findings file). Human action required. **Descope orchestrator (D-18):** `scripts/corners_gate_descope.py` ready to run when verdict is FAIL. |

**Score:** 4/5 truths fully verified; 1 truth (CORNERS-01) is half-completed pending human Part A.

### Deferred Items

Items not yet met but explicitly addressed in later milestone phases (filtered against ROADMAP).

| # | Item | Addressed In | Evidence |
|---|------|-------------|----------|
| 1 | CLV-03 rolling-50-pick avg <+1% Telegram warning | Phase 4 | Phase 4 success criterion #5 in ROADMAP.md |
| 2 | CLV-04 daily PerformanceMetric aggregator job | Phase 4 | Phase 4 success criterion #4 in ROADMAP.md |
| 3 | Production caller of PickEngine (autonomous wiring) | Phase 4 | Phase 4 goal — "full pipeline runs autonomously on a VPS"; STATE.md Phase 3 closeout note |
| 4 | `_reconcile_clv` real implementation (rolling-50 + back-fill) | Phase 4 | quick-260503-k8k decision: body is explicit `clv_reconciliation_deferred` warning + comment |
| 5 | Empirical PL smoke train (ML-02/ML-03 → empirical PASS) | Phase 02.1 deferred | STATE.md — owner-accepted risk; ~1,520 API-Football Pro credits required |
| 6 | Per-channel Telegram, Supavisor pooling, PluginRegistry decorator | Phase 7 / v2 | AUDIT-GAPS.md G-SCALE-01..04 + G-LOGIC-11; Phase 7 (tennis scaffold) forces the refactor |

---

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `src/bip/core/picks/engine.py` | PickEngine.evaluate orchestration heart (PICK-01..05, CLAUDE-01) | VERIFIED | 264 lines, 5-step filter chain, all paths persist (D-04), DateTrigger send job idempotent on (fixture_id, market, prediction_id), per-market threshold via LeagueRegistry |
| `src/bip/core/picks/account_longevity.py` | quarter_kelly + round_half + md5 jitter + deterministic_send_at + 60% market cap | VERIFIED | 125 lines, 5 pure functions; spot-checks confirm determinism + correct numerics |
| `src/bip/core/picks/__init__.py` | Re-exports PickEngine | VERIFIED | `from bip.core.picks.engine import PickEngine` + `__all__` |
| `src/bip/core/claude/validator.py` | ClaudeValidator with AsyncAnthropic + strict tool_use + cache_control + D-07 hand-rolled 2-attempt retry | VERIFIED | 137 lines, VALIDATE_PICK_TOOL strict=True, forced _TOOL_CHOICE constant (Pitfall 3), 60s sleep between attempts, returns None on exhaustion |
| `src/bip/core/claude/learnings_loader.py` | load_learnings() with git SHA stamp + sha256 fallback + module cache | VERIFIED | 83 lines, _CACHE singleton, subprocess git log, sha256[:16] fallback |
| `src/bip/core/claude/prompts/football-learnings.md` | Verbatim Spanish learnings corpus | VERIFIED | ~18KB, real Spanish content (R-001..R-014 rules), placeholder replaced in commit `20bfd51`, restructured in `55f00be` |
| `src/bip/core/telegram/bot.py` | TelegramBot with AIORateLimiter, send-only (no polling), HTML parse_mode | VERIFIED | 59 lines, ApplicationBuilder + AIORateLimiter(max_retries=3), `send_html` calls `bot.send_message(parse_mode=ParseMode.HTML)` |
| `src/bip/core/telegram/sender.py` | TelegramSender + render_pick (Jinja2, bullet cap 3) | VERIFIED | 81 lines, Jinja2 PackageLoader + autoescape(["html"]), claude_summary split on " * " capped at 3 |
| `src/bip/core/telegram/templates/pick.html` | FLAG branch + CONFIRM branch, Telegram HTML tags only | VERIFIED | 16 lines, `{% if pick.claude_validation == "FLAG" %}` → ⚠️ WARNING + `Claude flagged:`; `{% else %}` clean header |
| `src/bip/scheduler/orchestrator.py` | _run_pipeline → engine.evaluate; _record_clv (kickoff-1m); _reconcile_results (kickoff+150m, all 16 codes); _auto_recover Pitfall 6 | VERIFIED | 531 lines; 9 optional kwargs (pick_engine, pick_repo, telegram_bot, api_football_client, odds_api_client, clv_recorder, league_registry); D-01 dup-alert guard (lines 241-255); Strategy 2 Prediction construction (lines 268-279) |
| `src/bip/clv/odds_math.py` | remove_vig pure function (proportional method) | VERIFIED | 49 lines, key-agnostic, raises ValueError on empty/odd≤1.0; spot-check: fair_probs sum to 1.0 exactly |
| `src/bip/clv/recorder.py` | calculate_clv_percentage uses vig-removed math, ClvRecorder.record persists raw + fair | VERIFIED | 190 lines, dict+selection signature; spot-check: CLV(2.10 vs {1:1.95,X:3.40,2:4.20}, "1") = 3.05% (vs raw ~7.69% — 4.6pp downward correction) |
| `src/bip/clv/client.py` | OddsApiClient.find_event_by_fixture + fetch_pinnacle_closing_odds | VERIFIED | 237 lines; find_event uses /v4/sports/{sport_key}/events with team-name (case-insensitive contains) + ±2h kickoff window; same retry decorator |
| `src/bip/sports/__init__.py` | SportPlugin ABC with 6 abstract methods incl. get_opening_odds | VERIFIED | 88 lines, abstract method `get_opening_odds(fixture_id) -> dict[str, float]`; FeatureMatrix carries kickoff_utc/home_team/away_team |
| `src/bip/sports/football/plugin.py` | get_opening_odds parses Betano "Match Winner" market | VERIFIED | Lines 290-334: walks response[].bookmakers[?name=="Betano"].bets[?name=="Match Winner"].values; returns {} on coverage gap; raises on network errors |
| `src/bip/core/types.py` | PickStatus.filtered + PickStatus.rejected (7 total members) | VERIFIED | StrEnum with all 7 members |
| `src/bip/core/storage/models.py` | Pick has 4 claude_* fields with ISO serialization | VERIFIED | claude_validation/reasoning/summary/validated_at all `None`-defaulted; `to_supabase_dict` emits ISO string for datetime |
| `src/bip/core/settings.py` | telegram_channel_id (-100 validator) + anthropic_api_key + claude_model + max_kelly_fraction | VERIFIED | All 4 fields + @field_validator on telegram_channel_id rejecting non-`-100*` values |
| `src/bip/core/errors.py` | PickError + ClaudeError + TelegramError | VERIFIED | All 3 appended at end of file |
| `src/bip/core/storage/repositories.py` (PickRepository extensions) | get_window_picks, get_pending_for_fixture, update_status_by_fixture, query_pending_sends | VERIFIED | 4 methods at lines 146, 169, 186, 205 |
| `supabase/migrations/20260502000000_add_claude_validation_to_picks.sql` | 4 claude_* columns + status widening + idx_picks_sport_market_created + picks_unique_prediction UNIQUE + claude_validation CHECK | VERIFIED | All 5 schema changes present in SQL; Plan 03-01 SUMMARY confirms applied via Supabase MCP |
| `scripts/verify_migration_004.py` | psycopg verification of all 4 invariants | VERIFIED (script body present; live re-run requires SUPABASE_DB_PASSWORD — see Human Verification #3) | Replaced Wave-0 stub with 4 parameterized queries via psycopg |
| `scripts/corners_gate_probe.md` | Manual probe checklist (5 leagues × 3-5 fixtures) | VERIFIED | Plain Markdown checklist file, ready for Kevin to execute |
| `scripts/corners_gate_findings.md` | Hand-fillable findings template | VERIFIED structurally; UNFILLED by design | Template with `_(fill in)_` placeholders throughout — Part A awaits human probe (see Human Verification #1) |
| `scripts/corners_gate_coverage.py` | Polars coverage script (D-17b) | VERIFIED | Runs end-to-end, exits 1 (FAIL), writes `scripts/corners_gate_coverage.md` per spot-check |
| `scripts/corners_gate_descope.py` | D-18 conditional descope orchestrator | VERIFIED | 3-artifact FAIL flow (ROADMAP edit + STATE entry + git commit); --pass marker path |
| `scripts/smoke_e2e_pick.py` | Manual e2e smoke runner (live Telegram + Anthropic + Supabase) | VERIFIED structurally; live execution awaits human (Human Verification #2) | Imports clean (`uv run python -c "import scripts.smoke_e2e_pick"` succeeds); SimpleNamespace synthetic Prediction; --fixture-id required arg |
| `scripts/smoke_e2e_runbook.md` | Pre-flight + invocation + 4 verify touchpoints + sign-off | VERIFIED | Markdown runbook present |

---

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `PickEngine.evaluate` | `simulate_pick` (per-market threshold) | `bip.train.backtest.simulate_pick(threshold=...)` | WIRED | engine.py:108 — threshold resolved from `LeagueRegistry.get(league).model_params.edge_threshold_<market>` |
| `PickEngine.evaluate` | `quarter_kelly_units` + `deterministic_jitter` + `round_to_nearest_half_unit` | direct call | WIRED | engine.py:114-117 |
| `PickEngine.evaluate` | `exceeds_60pct_cap` (market cap) | `pick_repo.get_window_picks(sport, hours=168)` | WIRED | engine.py:119-120; account_longevity.py:121 |
| `PickEngine.evaluate` | `ClaudeValidator.validate` | async call | WIRED | engine.py:124; None → filtered, REJECT → rejected, CONFIRM/FLAG → pending |
| `PickEngine` (CONFIRM/FLAG path) | DateTrigger send job | `scheduler.add_job(self._sender.send_pick, ...)` with `replace_existing=True`, `misfire_grace_time=300` | WIRED | engine.py:245-260 |
| `TelegramSender.send_pick` | `TelegramBot.send_html` | direct await | WIRED | sender.py:73 |
| `TelegramBot.send_html` | Telegram API | `self.bot.send_message(parse_mode=HTML)` via AIORateLimiter | WIRED | bot.py:51-58 |
| `ClaudeValidator` | `learnings_text` + `learnings_sha` | constructor injection from `load_learnings()` | WIRED | validator.py:69-79; system prompt block 2 carries cache_control ephemeral + `<!-- learnings_sha=... -->` marker |
| `PipelineOrchestrator._run_pipeline` | `plugin.build_features` → `plugin.predict` → `plugin.get_opening_odds` → build `Prediction` → `pick_engine.evaluate` | Strategy 2 wiring | WIRED | orchestrator.py:235-282; `pick_engine.evaluate(prediction, opening_odds)` is the only entry into the Pick lifecycle |
| `PipelineOrchestrator._run_pipeline` (T-30min) | D-01 dup-alert guard | `pick_repo.get_pending_for_fixture(fixture_id)` (sync, list[dict]) | WIRED | orchestrator.py:241-255 — checks `p.get("market") == "1X2"` AND `p.get("status") == PickStatus.pending.value` |
| `PipelineOrchestrator._record_clv` (T-1min) | `OddsApiClient.find_event_by_fixture` → `fetch_pinnacle_closing_odds` → `ClvRecorder.record` | full chain at orchestrator.py:293-429 | WIRED | One ClvRecord per pending 1X2 pick; sport_key from LeagueRegistry (fallback `soccer_epl`); incomplete-market path logs `clv_skip_incomplete_market` |
| `PipelineOrchestrator._reconcile_results` (T+150min) | `api_football_client.get_fixture` → `pick_repo.update_status_by_fixture` / `update_status` | direct | WIRED | orchestrator.py:441-524; all 16 status codes covered by tests/scheduler/test_reconcile.py |
| `PipelineOrchestrator._auto_recover` | `pick_repo.query_pending_sends(sport, max_age_minutes=30)` → `_send_recovered_pick` | DateTrigger(now) re-queue | WIRED | orchestrator.py:108-135; Pitfall 6 mitigation |
| `FootballPlugin.get_opening_odds` | API-Football `/odds?fixture` (Betano "Match Winner") | `ApiFootballClient.get_odds(fixture_id, bookmaker="Betano")` | WIRED | plugin.py:290-334; returns `{}` gracefully on coverage gap |
| `LeagueRegistry.get(league).api_mappings.odds_api_sport_key` | Pinnacle event resolution | `OddsApiClient.find_event_by_fixture(sport_key=...)` | WIRED | orchestrator.py:333-343 — fallback to `"soccer_epl"` if registry/lookup fails (logged) |

All 15 critical links verified WIRED.

---

### Data-Flow Trace (Level 4)

| Artifact | Data variable | Source | Produces real data | Status |
|----------|---------------|--------|--------------------|--------|
| `PickEngine.evaluate` | `prediction.probabilities`, `opening_odds` | Orchestrator constructs `Prediction(...)` from `plugin.predict(features)` (real ML model output) + `plugin.get_opening_odds(fixture_id)` (real API-Football Betano odds) | YES — full chain wired through real plugin methods | FLOWING |
| `ClaudeValidator.validate` | `pick_summary`, `curated_signals` | Built by `PickEngine._build_pick_summary` + `_build_curated_signals` from the typed `Prediction` (real teams/league/probs/kickoff) | YES — no static returns; system prompt carries real ~18KB Spanish learnings + git SHA | FLOWING |
| `TelegramSender.send_pick` | `pick`, `home_team`, `away_team`, `model_version` | Passed from `PickEngine._schedule_send` (engine.py:248-256) — kwargs sourced from real Prediction + Pick | YES — `claude_validation` populated from verdict; bullets from `claude_summary.split(" * ")[:3]` | FLOWING |
| `pick.html` template | All fields via `_build_context` | Real Pick model + render kwargs | YES — no hardcoded empty defaults; `pick.suggested_stake or 0.0` only as a render-safety fallback | FLOWING |
| `_record_clv` ClvRecord persistence | `closing` dict | `OddsApiClient.fetch_pinnacle_closing_odds(...)` real Pinnacle h2h response, projected to {"1","X","2"} via team-name match | YES; partial markets are logged + skipped, not persisted as zero | FLOWING |
| `_reconcile_results` status updates | `status`, `home`, `away` | `api_football_client.get_fixture(fixture_id)` real API-Football response; missing goals logged + skipped | YES — `won/lost/void/push` derived from real response | FLOWING |

No HOLLOW or STATIC paths detected in the implemented chain. (One acknowledged gap: `_reconcile_clv` body is the deferred Phase-4 warning — but its placeholder status is intentional and logged; not a data-flow regression.)

---

### Behavioral Spot-Checks

| # | Behavior | Command | Result | Status |
|---|----------|---------|--------|--------|
| 1 | Full test suite passes | `uv run pytest -q` | 282 passed, 0 failed in 78.57s | PASS |
| 2 | Phase 3 test slice passes | `uv run pytest tests/picks/ tests/claude/ tests/telegram/ tests/scheduler/ tests/scripts/ tests/test_clv_recorder.py tests/test_clv_client.py tests/sports/ -q` | 144 passed in 7.90s | PASS |
| 3 | Phase 3 modules import cleanly | `uv run python -c "from bip.core.picks.engine import PickEngine; ..."` | `all imports OK` | PASS |
| 4 | Vig removal numerics correct | `uv run python -c "from bip.clv.odds_math import remove_vig; ..."` | fair_probs sum=1.0; CLV(2.10 vs 1.95) = 3.05% (vs raw 7.69%) | PASS |
| 5 | Account longevity functions deterministic | `uv run python -c "from bip.core.picks.account_longevity import ..."` | jitter(12345,'1X2') = 0.1 reproducibly; deterministic_send_at returns same datetime on repeat | PASS |
| 6 | Smoke runner imports cleanly | `uv run python -c "import scripts.smoke_e2e_pick"` | exit 0 (no errors) | PASS |
| 7 | CORNERS-01 Part B coverage script runs end-to-end | `uv run python scripts/corners_gate_coverage.py; echo $?` | exit 1 (FAIL — expected per A5: no corner data seeded); writes `scripts/corners_gate_coverage.md` with all-FAIL rows | PASS (gate ran, FAIL is documented per spec) |
| 8 | Per-market threshold YAML present | `grep edge_threshold_ src/bip/sports/football/config/leagues/premier_league.yaml` | 5 hits: 1x2=0.08, btts=0.05, ah=0.06, ou=0.05, corners=0.07 | PASS |
| 9 | Migration 004 SQL contains all 5 schema invariants | `grep claude_validation/picks_status_check/idx_picks_sport_market_created/picks_unique_prediction supabase/migrations/...sql` | All 5 invariants present | PASS |
| 10 | TelegramBot uses HTML parse_mode + no polling + AIORateLimiter wired | `grep ParseMode.HTML / AIORateLimiter / polling src/bip/core/telegram/bot.py` | `parse_mode=ParseMode.HTML` line 55; `AIORateLimiter(max_retries=3)` line 33; no `start_polling` / `Updater` references | PASS |
| 11 | TODO/FIXME/PLACEHOLDER scan on Phase 3 source | `grep -rn "TODO\|FIXME\|XXX\|HACK" src/bip/core/picks src/bip/core/claude src/bip/core/telegram src/bip/clv src/bip/scheduler/orchestrator.py` | Only matches are `Entry-XXX`/`R-NNN` template entries inside `football-learnings.md` (intentional placeholder for future learning entries — not a code stub) | PASS |
| 12 | PickStatus enum has 7 members incl. filtered + rejected | `grep -E "filtered\|rejected" src/bip/core/types.py` | both present | PASS |

All 12 spot-checks pass. Live-service checks (real Telegram delivery, real Anthropic call, real Supabase insert, real Pinnacle event resolution) routed to Human Verification #2.

---

### Requirements Coverage

| Requirement | Source plan(s) | Description | Status | Evidence |
|-------------|----------------|-------------|--------|----------|
| **PICK-01** | 03-00, 03-02, 03-07, 03-11; quick-260503-j74 | EV filter — per-market edge threshold from YAML; sub-threshold picks logged as `filtered` | SATISFIED | engine.py:108 + LeagueRegistry lookup; `_persist_filtered("no_edge")` path covers sub-threshold |
| **PICK-02** | 03-00, 03-03, 03-07, 03-11 | Quarter-Kelly sizing × 0.25 + 0.5-unit rounding + ±10% deterministic md5 jitter | SATISFIED | account_longevity.py:31-74; spot-check #5 confirms numerics + determinism |
| **PICK-03** | 03-00, 03-03, 03-07, 03-11 | Account longevity: 60% market rotation cap + deterministic send-time variance + quarter-Kelly clamping | SATISFIED (rotation structurally dormant 1X2-only — flagged in REQUIREMENTS.md and account_longevity.py:104-106; mechanism is built and tested for second-market plug-in) | account_longevity.py:81-125; engine.py:119-120 |
| **PICK-04** | 03-00, 03-06, 03-07, 03-11 | Telegram alert format (HTML, all required fields, ≤3 bullets, FLAG marker) | SATISFIED | sender.py + pick.html template + bot.py; spot-check #10 |
| **PICK-05** | 03-00, 03-01, 03-02, 03-07, 03-08, 03-11 | All picks logged to `picks` table with extended status enum; reconciliation updates won/lost/void/push | SATISFIED | Migration 004 widens CHECK; `_reconcile_results` handles all 16 status codes |
| **CLAUDE-01** | 03-00, 03-04, 03-05, 03-07, 03-11 | Role C validator with strict tool_use; REJECT blocks, FLAG sends with warning, API failure → `filtered/claude_api_unavailable` (D-07 conservative) | SATISFIED | validator.py + engine.py step 4; pick.html FLAG branch; learnings_loader.py SHA stamping |
| **CORNERS-01** | 03-09, 03-10 | Go/no-go gate: (a) Betano markets manually verified, (b) API-Football corner timing data confirmed for 5 leagues × 3+ seasons | NEEDS HUMAN — Part B PASS (script runs, FAIL documented as expected); Part A awaits human probe | Part A: probe.md + findings.md exist (template unfilled). Part B: coverage script executes + writes report (verdict FAIL per A5). |

No orphaned requirements detected. Phase 3 plans `requirements_addressed` frontmatter cleanly maps to ROADMAP/REQUIREMENTS Phase 3 set (PICK-01..05, CLAUDE-01, CORNERS-01).

---

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| (none in Phase 3 production code) | — | — | — | — |

The only `XXX` matches in Phase 3 source come from `football-learnings.md` Entry-XXX template instructions (lines 288-333) — these are intentional placeholders for future learnings entries, not code stubs.

`_reconcile_clv` at `orchestrator.py:431-439` is documented as a Phase-4 deferral (`clv_reconciliation_deferred` warning + comment); the cron entry is intentional for ops visibility. Not classified as an anti-pattern because its placeholder status is explicitly logged and traced through STATE.md + AUDIT-GAPS.md.

The `# type: ignore[attr-defined]` markers at orchestrator.py:174-175 + 301 + 348-350 + 379-380 + 447 are deliberate (fixture is `object`-typed for plugin abstraction, but field access is contractually safe per `FixtureData` schema). Not a stub.

---

### Human Verification Required

#### 1. CORNERS-01 Part A — Manual Betano probe

**Test:** Open Betano in a logged-in browser, navigate to a current fixture in each of the 5 leagues (Premier League, La Liga, Bundesliga, Serie A, Ligue 1). For each fixture, open `scripts/corners_gate_probe.md` as a checklist and capture the per-fixture data (markets seen, naming convention, odds range, min stake, screenshot) into `scripts/corners_gate_findings.md`. Fill in the Part A Gate Decision block at the top with PASS/FAIL.

**Expected:** All 5 league tables in `findings.md` populated with concrete entries (no `_(fill)_` placeholders); Verdict line set to PASS or FAIL with one-line rationale; screenshots saved under `scripts/corners_evidence/` (or note alternate location).

**Why human:** Live Betano UI requires authenticated browser session and human-readable inspection of corner time-window markets — cannot be probed by an automated agent.

**On verdict:**
- PASS → corners gate clears for Phase 6 engineering; run `scripts/corners_gate_coverage.py` again post-data-seeding (Phase 02.1 D-12 follow-up) to confirm Part B then also passes.
- FAIL → run `scripts/corners_gate_descope.py --reason "<one-line>"` to descope Phase 6 in ROADMAP, append STATE Blockers entry, and commit.

#### 2. End-to-end smoke runner against live services

**Test:**
```bash
# Pre-flight per scripts/smoke_e2e_runbook.md (5 env vars + bot is channel admin)
uv run python scripts/smoke_e2e_pick.py --fixture-id 99999 \
  --probs '{"1":0.55,"X":0.25,"2":0.20}' --odds '{"1":2.10,"X":3.40,"2":4.50}'
```

**Expected:**
- Console reports: `pick_persisted_pending` with verdict (CONFIRM or FLAG), or `pick_filtered`/`pick_rejected` with reason_code.
- Telegram channel receives one rendered pick within ~30 minutes (D-11 send-time variance window).
- Supabase `picks` row appears with `claude_validation` populated and `claude_validated_at` non-null.
- Sign-off block in `scripts/smoke_e2e_runbook.md` filled by Kevin.

**Why human:** Requires live `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHANNEL_ID` (with bot set as channel admin), `ANTHROPIC_API_KEY` with billing, and Supabase service role key — all user-controlled secrets that the verifier cannot supply. External delivery to Telegram requires human-side confirmation.

#### 3. Live re-confirmation of migration 004 invariants

**Test:**
```bash
SUPABASE_DB_PASSWORD=<password> uv run python scripts/verify_migration_004.py
```
or, alternatively, via Supabase MCP `execute_sql`:
```sql
SELECT column_name FROM information_schema.columns WHERE table_name='picks' AND column_name LIKE 'claude_%';
SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conname='picks_status_check';
SELECT indexname FROM pg_indexes WHERE tablename='picks' AND indexname='idx_picks_sport_market_created';
SELECT conname FROM pg_constraint WHERE conname='picks_unique_prediction';
```

**Expected:** Script exits 0; all 4 invariants confirmed (4 claude_* columns, widened status CHECK, market-cap index, unique-prediction constraint).

**Why human:** Verifier does not have `SUPABASE_DB_PASSWORD`. Plan 03-01 SUMMARY already verified once via Supabase MCP; this is a re-confirmation step before live picks start landing in production.

---

### Gaps Summary

**No structural gaps.** Phase 3 implementation is functionally complete and the closeout quick-task series (260503-iql/j74/jkf/k8k) closed the four critical AUDIT-GAPS.md findings:

- **G-LOGIC-02 (Pitfall 7 — vig removal)** → closed by quick-260503-iql; CLV math now compares against vig-removed fair lines (proportional method); spot-check confirms 4.6pp downward correction vs the previous biased calc.
- **G-MAINT-01 (per-market thresholds)** → closed by quick-260503-j74; PickEngine now reads `edge_threshold_<market>` from LeagueRegistry per pick, with `EDGE_THRESHOLD_PCT` retained as fallback.
- **G-CODE-01 / G-CODE-02 / G-CODE-03 / G-MAINT-04 / G-MAINT-08 / G-MAINT-11 (orchestrator wiring)** → closed by quick-260503-jkf (Strategy 2). Orchestrator builds a typed `Prediction` before calling `engine.evaluate`; `get_opening_odds` is now an ABC method on `SportPlugin` (and contract-tested); `pick_repo.get_pending_for_fixture` correctly treated as sync returning list[dict]; AsyncMock patches replaced with `spec=SportPlugin`/`spec=PickRepository` mocks.
- **G-MAINT-06 / G-LOGIC-03 (CLV recorder wiring + closing-line timing)** → closed by quick-260503-k8k; `_record_clv` now does the full Pinnacle event resolution → fetch closing odds → project to {1,X,2} → persist via `ClvRecorder.record` chain at `kickoff - 1m` (was `kickoff + 105m`); `OddsApiClient.find_event_by_fixture` added with team-name + ±2h commence_time match; `find_event` and `fetch_pinnacle_closing_odds` reuse the same retry decorator.

**One success criterion is half-completed:** CORNERS-01 Part A awaits Kevin's manual probe (template + checklist exist, both files structurally verified by `tests/scripts/test_corners_gate_artifacts.py`). Part B is automated and runs cleanly today, producing the expected FAIL report given that historical corner data has not yet been seeded — a Phase 02.1 P09 follow-up that is itself acknowledged as deferred.

**Six items are Phase-4 / Phase-7 / 02.1-deferred and explicitly out of Phase 3 scope** per STATE.md Phase 3 closeout decisions. They appear in the `deferred:` frontmatter section above and do not affect the Phase 3 status determination:

1. CLV-03 alert wiring (rolling 50-pick avg → Telegram) — Phase 4 success criterion #5.
2. CLV-04 daily aggregator — Phase 4 success criterion #4.
3. Production caller of PickEngine in `__main__.py` — Phase 4 deployment.
4. `_reconcile_clv` real implementation — Phase 4.
5. Empirical PL smoke train (~1,520 API credits) for ML-02/ML-03 → empirical PASS — Phase 02.1 deferral.
6. Plugin Registry decorator + Supavisor connection pooling + per-channel Telegram refactor — Phase 7 / v2 (forced by tennis scaffold).

**Status decision:** `human_needed` (NOT `passed`) because the human-verification section above lists three items requiring manual action (CORNERS-01 Part A probe, live e2e smoke run, live migration 004 re-confirmation). The automated chain is GREEN end-to-end (282 tests pass; all 15 critical wires verified; spot-checks all pass) but cannot, by definition, replace external/UI/credentialed verification.

---

_Verified: 2026-05-03T20:09:07Z_
_Verifier: Claude (gsd-verifier, Opus 4.7 / 1M context)_
