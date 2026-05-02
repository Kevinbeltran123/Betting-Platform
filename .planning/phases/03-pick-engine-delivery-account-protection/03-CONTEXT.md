# Phase 3: Pick Engine + Delivery + Account Protection - Context

**Gathered:** 2026-05-02
**Status:** Ready for planning

<domain>
## Phase Boundary

Phase 3 receives `ProbabilityMap` outputs from `FootballPlugin.predict()` (Phase 2), applies the EV/Kelly/account-longevity filter chain, validates each qualifying pick via Claude Role C against `learnings/football-learnings.md`, sends qualified picks to a private Telegram channel, and persists every pick (sent and filtered) to Supabase. CORNERS-01 verification gate ships this phase; gate failure auto-descopes Phase 6.

**In scope:** pick engine in `core/`, Claude Role C validator wiring, Telegram delivery, account-longevity protections (60% market cap, stake jitter, send-time variance), migration 004 (claude_* columns on picks), pick-result reconciliation, CORNERS-01 gate execution + documentation.

**Out of scope:** APScheduler production wiring + systemd + health monitoring (Phase 4); Claude Role B confidence modifier (Phase 5); corners model implementation (Phase 6, conditional on this gate).

</domain>

<decisions>
## Implementation Decisions

### Pick Selection & Re-prediction Handling

- **D-01:** T-2h is the primary send moment. T-30min runs a re-prediction; it only sends to Telegram if the T-2h pick was REJECTed by Claude (and T-30min recovers it via lineup-adjusted features) OR if T-2h had no qualifying edge (>=5%) and T-30min now does. Sent picks are never retracted, never edited.
  - Rationale: maximises CLV against Pinnacle closing lines (early send) while letting confirmed-lineup data rescue borderline picks.
- **D-02:** Phase 3 markets = 1X2 only (carries forward from D-12 Phase 02.1). `simulate_pick()` from `bip.train.backtest` is reused as the single edge-filter implementation -- pick engine imports `EDGE_THRESHOLD_PCT` and `simulate_pick` directly; no parallel implementation.

### Pick Persistence

- **D-03:** `PickStatus` enum (in `bip.core.types`) extended with two new values:
  - `filtered` -- pick did not clear the 5% edge threshold; never reached Claude or Telegram.
  - `rejected` -- Claude Role C returned REJECT; never sent to Telegram.

  Existing values (`pending`, `won`, `lost`, `void`, `push`) unchanged. Migration 004 widens the CHECK constraint on `picks.status` to accept the two new values.

- **D-04:** All picks (sent, filtered, rejected) persist to the `picks` table per PICK-05. The post-match results pipeline only updates rows with status `pending` to `won`/`lost`/`void`/`push`. Filtered/rejected rows are terminal at write time.

### Claude Role C Validator

- **D-05:** Validator prompt receives:
  - (a) the pick row (fixture, market, selection, model_probability, opening odds, edge, suggested stake);
  - (b) full `learnings/football-learnings.md` verbatim -- kept in Spanish (the Kevin-authored corrections retain their voice and pattern-matching context);
  - (c) curated feature signals only -- recent form (last 5 games), H2H last 3, motivation flags, key injuries from confirmed lineups. NOT the full ~50-feature row.

- **D-06:** Tool_use schema for the Anthropic SDK call (all output fields English):
  ```python
  {
    "verdict": Literal["CONFIRM", "FLAG", "REJECT"],
    "reason_code": str,          # e.g., "aggregate_stat_seduction", "h2h_too_old", "two_starting_cbs_out"
    "reasoning": str,            # English, max ~300 words
    "summary": str,              # English, max 120 chars (Telegram bullets source)
  }
  ```
  The Spanish learnings.md content remains in the prompt input; Claude reasons across it but emits English. Tool_use enforces schema; no JSON-mode / regex parsing fallback.

- **D-07:** Anthropic API failure handling -- conservative default:
  - On initial error: pick is held with status `pending` (NOT sent to Telegram, NOT marked filtered/rejected), retried once after 60 s.
  - After two consecutive failures: pick marked `filtered` with `reason_code='claude_api_unavailable'` for that prediction cycle.
  - Phase 4 wires a degraded `claude_validation='SKIPPED'` fall-through behind a feature flag (REQUIREMENTS.md Phase 4 spec); Phase 3 default stays conservative -- account longevity > uptime.

- **D-08:** Migration 004 adds four columns to the `picks` table:
  - `claude_validation VARCHAR(10)` -- one of `CONFIRM` / `FLAG` / `REJECT` / `SKIPPED` / NULL
  - `claude_reasoning TEXT` -- full English reasoning paragraph
  - `claude_summary VARCHAR(120)` -- short summary used in Telegram alert
  - `claude_validated_at TIMESTAMPTZ`

  Plus widens the `status` CHECK constraint per D-03. The existing `predictions.claude_*` fields stay reserved for Role B (Phase 5, CLAUDE-03).

### Account Longevity Protections (PICK-03)

- **D-09:** 60% market-cap window = rolling trailing 168 hours from each pick attempt. If sending this pick would push the dominant market past 60% of all sent picks in the window, the pick is logged with status `filtered` (`reason_code='market_cap'`) and never reaches Telegram. Drop-on-bind, not defer.
  - Phase 3 note: with 1X2-only markets the cap is structurally dormant. The mechanism is built now so Phase 6 corners and future BTTS / Over-Under plug in cleanly.

- **D-10:** Stake jitter is **deterministic** from `fixture_id`:
  ```python
  jitter_pct = (md5_int(f"{fixture_id}-{market}") % 21 - 10) / 100   # -10% .. +10%
  raw_stake = quarter_kelly_units(edge, odds)                         # PICK-02
  stake = round_to_nearest_half_unit(raw_stake * (1 + jitter_pct))
  ```
  Reproducible (re-running the same fixture yields the same stake -- critical for backtest replay and incident postmortems), bounded +-10% of Kelly, breaks fingerprinting. No hidden RNG state. Use `hashlib.md5` (NOT Python's `hash()` -- salted by PYTHONHASHSEED).

- **D-11:** Send-time variance: `send_at = prediction_completed_at + random.Random(fixture_id).randint(0, 1800)`. APScheduler `add_job(trigger=DateTrigger(run_date=send_at))` queues the actual Telegram dispatch. Deterministic-from-seed for replay. Spreads send times across a 30-min window without measurably hurting CLV.

### Telegram Delivery (PICK-04)

- **D-12:** `parse_mode='HTML'` for all alerts. One Telegram message per qualifying pick -- never batched per matchday. One-message-per-pick respects the stake/timing variance from D-10/D-11 and keeps each alert independently reactable.

- **D-13:** Single private Telegram channel for v1 (Kevin is sole recipient). Channel ID stored as `TELEGRAM_CHANNEL_ID` in `.env` via pydantic-settings. Channel (not DM) keeps the door open to a paid sub-feed in v2 without DB or delivery-layer rewrites.

- **D-14:** FLAG picks render with a leading `WARNING` emoji on the headline plus a `Claude flagged: <reason_code>` line directly under it. CONFIRM picks render clean. REJECT picks never reach Telegram (consistent with D-03 status semantics).

- **D-15:** Reasoning bullets in the alert are sourced directly from `claude_summary` (D-08). The summary is split on ` * ` separators or rendered as a `<ul>` with up to 3 bullets per PICK-04. No SHAP / feature-attribution pipeline this phase.

### Pick Result Reconciliation (Claude's Discretion -- sane default)

- **D-16:** Recommended default (open to revision during planning): an APScheduler `DateTrigger` job at `kickoff + 150min` per fixture, registered alongside the T-2h / T-30min jobs by the daily orchestrator (Phase 1 D-03a pattern). The job reads the API-Football `/fixtures` payload, derives `won/lost/void/push` from `goals.home`, `goals.away`, and `status` (`FT`, `AET`, `PEN`, `PST`, `CANC`, `ABD`, `AWD`, `WO`), and updates `picks.status` for all `pending` picks of that fixture.
  - Postponed/abandoned/cancelled fixtures (`PST` / `ABD` / `CANC`) -> `void`.
  - Penalty-shootout finishes (`PEN`) -> resolve on regulation+ET score per Betano's standard 1X2 settlement rules (1X2 settles on 90+ET, not pens).

### CORNERS-01 Gate (CORNERS-01)

- **D-17:** Two-part gate, both parts must pass before Phase 6 is greenlit:
  - **Part (a) -- Betano time-window markets:** Manual probe documented in `scripts/corners_gate_probe.md` (a checklist Kevin executes, not an automated script). Steps: log in to Betano live, for 3-5 upcoming fixtures across all 5 leagues, screenshot the corner-window markets available (0-15, 15-30, 30-45, 45-60, 60-75, 75-90 -- or whatever Betano actually offers, e.g., "Total Corners 1H/2H"), record typical odds range, minimum stake, exact market naming convention. Findings written to `scripts/corners_gate_findings.md` (versioned in repo).
  - **Part (b) -- API-Football coverage:** `scripts/corners_gate_coverage.py` runs a Polars query over the existing 02.1 seed Parquet stores (features/, results/, odds/) -- counts fixtures with non-null corner-timing data per league per season; asserts every league has >=3 seasons with >=95% coverage. Output `scripts/corners_gate_coverage.md` (auto-generated). No additional API-Football calls -- the data is already on disk from 02.1.

- **D-18:** Gate-fail behaviour: if EITHER part fails, the gate-runner script produces:
  - (a) a `ROADMAP.md` edit moving Phase 6 from `Conditional` to `v2-deferred` (block of lines specified, applied via `gsd-sdk query roadmap.move-phase`),
  - (b) a `STATE.md` Blockers/Concerns entry,
  - (c) a single git commit `docs(03): CORNERS-01 gate failed -- Phase 6 descoped`.

  Phase 6 does not auto-execute; Kevin reviews the descope commit before any Phase 6 plan-phase runs. If both parts pass, the gate produces `corners_gate_pass.md` and Phase 6 stays on the roadmap.

### Claude's Discretion

- Internal API of the pick engine (single `PickEngine` class vs free functions in `core/picks/`). Recommend a `PickEngine` class with `evaluate(prediction: Prediction) -> Pick | None` for testability.
- Telegram template implementation -- Jinja2 vs `string.Template` vs f-string. Template lives in `core/telegram/templates/pick.html`; Claude picks the renderer.
- Exact SQL for the rolling-7d market-cap query (Polars over `picks` Parquet snapshot vs Supabase `SELECT WHERE created_at > now() - interval '7 days'`). Recommend the Supabase query -- picks table is the source of truth, no read-from-warm-cache surprises.
- Schema of the `corners_gate_*.md` artifact files (markdown with structured headers vs front-matter YAML).
- Whether the Telegram bot runs as part of the main scheduler process (shared event loop) or as a separate `python-telegram-bot` polling worker. Recommend in-process via `AsyncIOScheduler` event loop -- simpler ops, single process, no IPC.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Requirements (locked)
- `.planning/REQUIREMENTS.md` §PICK-01 through PICK-05 -- Pick engine and account-longevity requirements
- `.planning/REQUIREMENTS.md` §CLAUDE-01 -- Role C validator spec (CONFIRM/FLAG/REJECT)
- `.planning/REQUIREMENTS.md` §CORNERS-01 -- Two-part go/no-go gate; gate failure descopes Phase 6
- `.planning/REQUIREMENTS.md` §ML-04 -- Model versioning and `models/{sport}/{league}/{version}/metadata.json` (referenced for production-model selection in pick engine)

### Prior Phase Decisions (locked contracts)
- `.planning/phases/01-foundation-data-pipeline-clv/01-CONTEXT.md` D-02 -- `SportPlugin` ABC + `ProbabilityMap` shape (sport-agnostic); D-03 -- APScheduler job model (T-2h, T-30min, T+105min CLV); D-04 -- CLV snapshot timing
- `.planning/phases/02-ml-core-football/02-CONTEXT.md` D-05 -- Manual model promotion via CLI; pick engine reads `models/football/registry.json` for production-model selection
- `.planning/phases/02.1-close-phase-2-verification-gaps-clv-end-to-end-test-logloss-/02.1-CONTEXT.md` D-09, D-10 -- `EDGE_THRESHOLD_PCT = 0.05` and `simulate_pick()` are the SINGLE source of truth for edge filtering; D-12 -- Phase 3 = 1X2 only

### Source files to extend / create
- `src/bip/core/types.py` -- extend `PickStatus` enum with `filtered`, `rejected` (D-03)
- `src/bip/core/storage/models.py` `Pick` model -- add fields per migration 004 (D-08)
- `src/bip/core/picks/` (new) -- `engine.py` (PickEngine), `account_longevity.py` (60% cap, jitter, timing), `__init__.py`
- `src/bip/core/telegram/` (new) -- `bot.py`, `templates/pick.html`
- `src/bip/core/claude/` (new) -- `validator.py` (Role C), `learnings_loader.py`
- `src/bip/train/backtest.py` -- imported by pick engine (already provides `EDGE_THRESHOLD_PCT` + `simulate_pick`)
- `scripts/corners_gate_probe.md` (new, manual checklist)
- `scripts/corners_gate_coverage.py` (new, Polars query)
- `supabase/migrations/20260502000000_add_claude_validation_to_picks.sql` (new -- migration 004; column adds + status CHECK widen)

### Reference assets to port
- `/Users/kevin_beltran/ProyectosPersonales/Sports_Betting/Claude_Sport_Betting/learnings/football-learnings.md` -- port verbatim into the repo (recommend `src/bip/core/claude/prompts/football-learnings.md`); loaded into Role C prompt. Spanish content preserved.
- `/Users/kevin_beltran/ProyectosPersonales/Sports_Betting/Claude_Sport_Betting/sports-betting-analysis/scripts/ev_calculator.py` -- reference for EV math (mostly covered by `simulate_pick`; consult for edge-case handling and Kelly clamping).
- `/Users/kevin_beltran/ProyectosPersonales/Sports_Betting/Claude_Sport_Betting/playbooks/football.md` -- reference for analytical structure (informs Claude prompt scaffolding for D-05).

### Tech Stack Constraints
- `CLAUDE.md` §Technology Stack -- `python-telegram-bot 22.7` (HTML parse_mode), Anthropic SDK with tool_use, APScheduler 3.x (NOT 4.x), structlog for all logging.

### External APIs
- Anthropic Messages API tool_use spec -- https://docs.anthropic.com/en/docs/build-with-claude/tool-use (referenced for D-06 schema)
- API-Football v3 `/fixtures` `status` field codes (FT, AET, PEN, PST, CANC, ABD, AWD, WO) -- https://www.api-football.com/documentation-v3#tag/Fixtures
- Telegram Bot API -- HTML parse mode reference: https://core.telegram.org/bots/api#html-style

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `src/bip/train/backtest.py:12,29` -- `EDGE_THRESHOLD_PCT` constant + `simulate_pick(model_probs, opening_odds)` already exist; pick engine imports both, no duplication.
- `src/bip/core/storage/models.py:46` `Pick` model -- already has `edge`, `model_probability`, `implied_probability`, `kelly_fraction`, `suggested_stake`, `bookmaker`, `status`. Migration 004 only ADDs claude_* columns.
- `src/bip/core/storage/repositories.py` -- `PickRepository` follows the same `@dataclass(client: Client)` pattern as `PredictionRepository`; pick-engine writes flow through it.
- `src/bip/sports/football/plugin.py` -- `FootballPlugin.predict()` already returns `ProbabilityMap` and writes `Prediction` rows (with `is_shadow` flag). Pick engine consumes ONLY `is_shadow=False` predictions.
- `src/bip/scheduler/orchestrator.py` `PipelineOrchestrator` -- already wires T-2h, T-30min, T+105min jobs per fixture. Phase 3 adds two more job kinds: pick-send DateTrigger (D-11) and result-reconcile DateTrigger (D-16).
- `src/bip/clv/recorder.py` `ClvRecorder` -- already records `clv_records`. Phase 3 ensures every sent pick has a `pick_id` so the existing CLV recorder finds it post-match.
- `src/bip/core/storage/parquet_store.py` -- `read_results()` / `read_odds()` from 02.1 are reused by `corners_gate_coverage.py` (D-17b). No new ingestion code needed for the gate.

### Established Patterns
- pydantic-settings + `.env` for config -- extend `Settings` with `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHANNEL_ID`, `ANTHROPIC_API_KEY`, `CLAUDE_MODEL` (default `claude-sonnet-4-6`), `MAX_KELLY_FRACTION=0.25`. `EDGE_THRESHOLD_PCT` is read from `bip.train.backtest`, not duplicated in settings.
- structlog keyword logging -- every pick-engine event uses `logger.info("pick_evaluated", fixture_id=..., edge=..., decision="filtered|sent|rejected")`.
- `to_supabase_dict()` on every storage model -- extend `Pick.to_supabase_dict()` to serialize the new claude_* columns.
- `@dataclass` + `client: Client` for repositories -- same pattern for any new repository.
- Atomic writes (`.tmp` + `Path.replace()`) for any new artifact files (corners_gate_findings.md, corners_gate_coverage.md, etc.).

### Integration Points
- `FootballPlugin.predict()` writes `Prediction` rows; the daily orchestrator queues a pick-engine evaluate job per prediction. PickEngine reads `Prediction.probabilities`, applies edge filter via `simulate_pick`, applies Kelly + jitter (D-10), checks 60% cap (D-09), invokes Claude Role C, queues Telegram send (D-11).
- Telegram bot runs in the same `AsyncIOScheduler` event loop as the orchestrator -- no separate process.
- Claude Role C validator wraps an `anthropic.AsyncAnthropic` client; lives in `core/claude/` to stay sport-agnostic.
- CORNERS-01 gate is a one-shot artifact production job, not a scheduled job. Run manually (or as a Phase 3 Wave 1 plan) before any Phase 6 work.
- Migration 004 is applied via the same Supabase MCP path as migration 003 in 02.1 (D-15) -- exit criterion: `information_schema.columns` query confirms claude_* columns exist on `picks`.

</code_context>

<specifics>
## Specific Ideas

- The Telegram template (D-12, D-15) should structure the alert as: headline (`WARNING` if FLAG, fixture, market, selection, edge%) -> odds + stake line -> up to 3 reasoning bullets from `claude_summary` -> footer with model version + Claude verdict tag. Keep total length under ~600 chars so the alert renders without truncation in mobile Telegram.
- The PickEngine's `evaluate()` method should be IDEMPOTENT on `(fixture_id, market, prediction_id)` -- running it twice for the same prediction (e.g., post-restart re-run of T-2h) must produce the same `Pick` row, never a duplicate. Use a unique constraint on `(fixture_id, market, prediction_id)` in migration 004 OR an `INSERT ... ON CONFLICT DO NOTHING` pattern in `PickRepository.save()`.
- For deterministic stake jitter (D-10), use `hashlib.md5(f"{fixture_id}-{market}".encode()).digest()[0]` (or first 4 bytes as int) -- NOT Python's built-in `hash()` (salted per process by PYTHONHASHSEED, breaks reproducibility across restarts). Document this in `account_longevity.py`.
- For send-time variance (D-11), `random.Random(seed=fixture_id).randint(0, 1800)` is reproducible without leaking state into the global RNG. Each call constructs a fresh Random instance.
- learnings.md is small (~178 lines, ~3-4k tokens). Loading it verbatim every Role C call is fine; no chunking needed. Stamp the file's git SHA into the prompt + into `claude_reasoning` metadata so audit traces can pin which version of learnings the validator saw.
- `corners_gate_coverage.py` should NOT count fixtures with `status: PST/CANC/ABD` as missing-coverage -- those legitimately don't have corner data. Filter on `status='FT'` first, then check coverage.
- Anthropic SDK calls should pass `extra_headers={"anthropic-beta": "..."}` only if a feature requires it -- otherwise stick to defaults to avoid prompt-cache invalidation. tool_use is GA so no beta header needed.

</specifics>

<deferred>
## Deferred Ideas

- **Result reconciliation gray area** (covered as Claude's Discretion in D-16) -- revisit during planning if Claude's default proves insufficient.
- **Telegram bot user commands** (e.g., `/status`, `/clv_today`, `/pause`) -- out of scope; Telegram is one-way alerts in v1.
- **Multi-recipient channels** (paid sub-feed) -- D-13 keeps the door open via channel architecture; full implementation deferred to v2.
- **SHAP-based feature attribution in alerts** -- D-15 chose Claude's narrative; SHAP pipeline can be a future v2 enhancement.
- **Phase 6 (corners) implementation** -- conditional on D-17 gate passing; if descoped per D-18 it moves to v2-deferred.
- **Auto-promotion of model registry on CLV improvement** (Phase 2 D-05 deferred this; remains deferred -- Phase 4 scope).
- **Pinnacle /historical backfill** (Phase 02.1 deferred this) -- Phase 3 inherits the deferral; CLV recording continues using the API-Football last-snapshot proxy.
- **Bot-token rotation / .env secrets management hardening** -- ops-level concern for Phase 4 production deployment.
- **Telegram message localisation (Spanish vs English)** -- Phase 3 emits English (matches D-06 tool_use output); Spanish localisation deferred until explicitly requested.

</deferred>

---

*Phase: 03-pick-engine-delivery-account-protection*
*Context gathered: 2026-05-02*
