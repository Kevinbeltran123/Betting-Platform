# Phase 4: Production Orchestration - Context

**Gathered:** 2026-05-03
**Status:** Ready for planning

<domain>
## Phase Boundary

Phase 4 wires the working pipeline (data → predict → pick → Claude → Telegram, all built in Phases 1-3) into an autonomous deployment on Hetzner VPS. It adds the missing scheduled jobs (CLV trend alert, performance metrics aggregator, weekly model-CLV drift check, heartbeat), adds the production entrypoint that instantiates and runs `PipelineOrchestrator`, defines graceful-degradation semantics for Claude / Odds API outages, and ships the systemd unit that keeps it alive.

**In scope:**
- Production entrypoint (`src/bip/production/__main__.py`) wiring Settings → all clients → PipelineOrchestrator
- systemd unit + EnvironmentFile + dedicated `bip` system user
- Heartbeat job (touch file every 5 min) integrated with systemd `WatchdogSec`
- CLV trend alert scheduler job (CLV-03) — hourly cron, global + per-market dimension, 12h cooldown
- Performance metrics aggregator (CLV-04) — daily 23:00 UTC, all periods, upsert pattern
- Weekly model-CLV drift check — Monday cron, 4-week-vs-prior-4-week comparison
- Graceful degradation: Claude API feature flag (`claude_failure_mode`), Odds API skip-on-failure
- Separate ops alert channel (`TELEGRAM_OPS_CHANNEL_ID`) for system-health messages
- Settings extension for the new knobs (heartbeat path, drift thresholds, ops channel)

**Out of scope (explicitly deferred):**
- Web admin dashboard / breakdown UI (v2; CLAUDE.md "do not use FastAPI")
- Feature drift (KS test) and odds drift detection (v2)
- Per-league CLV trend granularity (meaningful only after multi-market shipped)
- Auto-promotion of model registry on CLV improvement (v2 — Phase 2 D-05 deferred)
- Pinnacle `/historical` backfill (Phase 02.1 deferred this; Phase 4 inherits)
- Backfill of missed CLV snapshots after VPS downtime (would produce non-true closing lines)
- Telegram bot user commands (`/status`, `/clv_today`, `/pause`) — alerts are one-way in v1

</domain>

<decisions>
## Implementation Decisions

### Graceful Degradation Policy

- **D-01:** Claude API failure default stays **conservative** (Phase 3 D-07 preserved). Add feature flag `Settings.claude_failure_mode: Literal["filter", "skip"] = "filter"`.
  - `"filter"` (default): pick persisted with `status='filtered'`, `reason_code='claude_api_unavailable'`, never sent (Phase 3 D-07 behavior unchanged).
  - `"skip"`: pick persisted with `status='pending'`, `claude_validation='SKIPPED'`, sent to Telegram with a `🤖❌` marker indicating Claude was unreachable.
  - **Resolves Phase 3 D-07 ↔ Phase 4 SC#2 contradiction:** SC#2 must be reworded by the planner to read "feature flag `claude_failure_mode` exists; default 'filter' preserves account-longevity-first stance; 'skip' is opt-in via `.env` once CLV track record justifies it." Both code paths exist; one is dormant at v1.

- **D-02:** Odds API failure during CLV snapshot → **skip silently** (no `clv_records` row written). The pick keeps its `pick_id` but no CLV row is ever created for that fixture. Logged at WARNING level (`structlog.warning("clv_snapshot_skipped", fixture_id=..., reason=...)`).
  - **Phase 4 SC#2 wording must be revised:** "picks still send but CLV recording is deferred" → "picks still send; CLV record is skipped on Odds-API failure and not backfilled (acceptable rare loss)."
  - Rationale: Pinnacle moves post-match; a backfilled snapshot is no longer the true closing line. Better to lose the row than record a misleading one. Pre-existing nightly cron at 03:00 UTC is left as-is for now (may be repurposed later); explicit deferred-backfill design is rejected.

- **D-03:** Ops alerts (API outages, missed jobs, CLV trend, drift) go to a **separate** Telegram channel via new env var `TELEGRAM_OPS_CHANNEL_ID`. Picks channel (`TELEGRAM_CHANNEL_ID` from Phase 3 D-13) stays clean.
  - Two `TelegramSender` instances bound to the two channel IDs, or one sender with channel parameter — implementation choice for planner.
  - Both channels validated by the same pydantic-settings validator (starts with `-100`, ≥8 chars).

- **D-04:** API retry budgets stay as-is (no Settings knobs added).
  - Claude validator: 2 attempts, 60s sleep — already at [src/bip/core/claude/validator.py:96-137](src/bip/core/claude/validator.py#L96-L137).
  - OddsApiClient: tenacity 3 attempts with exponential backoff — already at [src/bip/clv/client.py:53-58](src/bip/clv/client.py#L53-L58).
  - Tighten only if production data shows transient failures aren't being absorbed.

### Production Entrypoint, systemd, Heartbeat

- **D-05:** Production main lives at **`src/bip/production/__main__.py`**. Invoke with `python -m bip.production`. Clean separation from the existing `bip.train.__main__` (training CLI).
  - Responsibilities: load `Settings`, validate required env (Anthropic key, Odds API key, both Telegram channel IDs, Supabase creds), instantiate `OddsApiClient` + `ClvRecorder` + `ClaudeValidator` + `PickEngine` + `PipelineOrchestrator` + ops `TelegramSender`, register all scheduler jobs (existing + Phase 4 additions), call `await orchestrator.start()`, run `asyncio.run(main())`, handle SIGTERM via `asyncio` signal handler → `await orchestrator.shutdown()`.
  - Companion module `src/bip/production/__init__.py` may expose `build_orchestrator(settings)` for tests.

- **D-06:** systemd unit shape:
  - User: dedicated `bip` system user (created by deployment script). Not root.
  - `Restart=always`, `RestartSec=10`.
  - `EnvironmentFile=/etc/bip/.env` (mode `600`, owned by `bip:bip`). Secrets never embedded in unit file.
  - `WatchdogSec=600` (10 min) — systemd kills + restarts the service if heartbeat mtime stales beyond this.
  - `StandardOutput=journal`, `StandardError=journal` — structlog JSON logs go straight to journald.
  - `WorkingDirectory=/opt/bip`, `ExecStart=/opt/bip/.venv/bin/python -m bip.production`.
  - Unit file lives at `deploy/systemd/bip.service` (versioned in repo).

- **D-07:** Heartbeat mechanism: APScheduler `IntervalTrigger(minutes=5)` job that touches `Settings.heartbeat_file_path` (default `/var/run/bip/heartbeat`).
  - Implementation: `Path(settings.heartbeat_file_path).touch()` in an async-safe wrapper.
  - systemd `WatchdogSec=600` reads the file's mtime; if older than 600s → restart. Native systemd integration, zero external deps.
  - Heartbeat directory must be created during deployment (`/var/run/bip/` owned by `bip:bip`).

- **D-08:** Auto-recovery on VPS restart: reuse `_auto_recover` at [src/bip/core/scheduler/orchestrator.py:89-138](src/bip/core/scheduler/orchestrator.py#L89-L138) **as-is**. Add a single structlog event `auto_recover_complete` (with counts of jobs re-queued) so journal monitoring can confirm successful restart-handling.
  - Backfilling missed reconciliation / missed CLV is **explicitly out of scope** (deferred — see deferred section).

### CLV Trend Alert (CLV-03)

- **D-09:** Cadence: hourly cron `CronTrigger(minute=0)`. Job queries last 50 settled CLV records (`SELECT clv_percentage FROM clv_records WHERE pinnacle_closing_odds IS NOT NULL ORDER BY created_at DESC LIMIT 50`), passes to existing `compute_rolling_clv_average()` at [src/bip/clv/recorder.py:78-93](src/bip/clv/recorder.py#L78), checks `< Settings.clv_trend_alert_threshold` (default `1.0` for +1%).
  - Decoupled from `_record_clv` — no race conditions on concurrent writes.
  - 24 checks/day is cheap (one Supabase `LIMIT 50` query each).

- **D-10:** Scope: **global + per-market** dimensions. The same job computes:
  - Global rolling-50 (all settled picks across all markets).
  - Per-market rolling-50 only when that market has ≥50 settled picks (otherwise skipped — no false-alarm noise from small samples).
  - At v1 (Phase 3 = 1X2-only), this effectively reduces to global. Per-market dimension structure ships now so Phase 6 corners drops in cleanly without re-architecting.
  - Per-league dimension is **not** added (deferred — meaningful only after large multi-league sample).

- **D-11:** Cooldown: 12h, **in-memory** (`dict[str, datetime]` keyed on `f"{scope}:{market}"` inside the `ClvTrendChecker` class). Restart resets the cooldown — acceptable cost is at most one duplicate alert per restart.
  - Edge-triggered semantics rejected: simpler to fire-and-cooldown than to track above/below transitions.

- **D-12:** Alert message format: **trend value only** (minimal).
  ```
  ⚠️ CLV +0.7% < +1% threshold
  ```
  - Sent to ops channel (D-03), not picks channel.
  - Per-market alerts append `[market: 1X2]` to the message: `⚠️ CLV +0.6% < +1% threshold [market: 1X2]`.
  - No recommendation text, no breakdown — operator already knows the playbook (pause + audit per CLV-03).

### Performance Metrics Aggregator (CLV-04) + Weekly Drift

- **D-13:** Aggregator cadence: daily cron `CronTrigger(hour=23, minute=0)` (UTC). Single pass computes and upserts metrics for **all four periods** in one job:
  - `period='daily'` (yesterday)
  - `period='weekly'` (trailing 7 days, rolling — re-upserted daily so the row reflects the latest week)
  - `period='monthly'` (trailing 30 days, rolling — re-upserted daily)
  - `period='all_time'` (everything settled — re-upserted daily)
  - Upsert keyed on `(sport, league, market, period, period_start)` via existing `PerformanceMetricRepository.upsert()` at [src/bip/core/storage/repositories.py:376-389](src/bip/core/storage/repositories.py#L376-L389). Idempotent on re-run.

- **D-14:** Weekly model-CLV drift check (single drift signal at v1).
  - Cadence: weekly cron `CronTrigger(day_of_week='mon', hour=6, minute=0)` (UTC).
  - Comparison: rolling **4-week mean CLV** (last 28 days) vs **prior 4-week mean CLV** (29-56 days ago). Both per league + market combo with ≥30 settled picks in each window.
  - Alert thresholds (compound):
    - **Hard:** absolute drop ≥ **2 percentage points** (e.g., +3.5% → +1.0%).
    - **Soft:** drop ≥ **1.5 × stdev** of the prior 4-week window (catches statistically meaningful regressions even when absolute change is small).
    - Either trigger fires the alert.
  - Alert routes to ops channel (D-03). Message format mirrors D-12 minimalism: `⚠️ DRIFT [league=PL market=1X2] -2.3pp (3.5% → 1.2%)`.
  - Feature drift (KS test) and odds drift are **explicitly deferred** to v2.

- **D-15:** Aggregator math location: new module **`src/bip/core/metrics/aggregator.py`**.
  - Pure functions: `compute_daily_metrics(client, period_start, period_end) -> list[PerformanceMetric]`, `compute_weekly_drift(client, sport, league, market) -> DriftResult | None`.
  - `bip.core.metrics.__init__` exposes the public API.
  - Sport-agnostic per CORE-02 — every public function takes `sport` as a parameter, never branches on it.

- **D-16:** Implementation: **hybrid** SQL + Polars.
  - Aggregator (D-13): pushed to Postgres via a new `PerformanceMetricRepository.compute_period(sport, league, market, period_start, period_end) -> PerformanceMetric` method. Single `SELECT count(*) FILTER (WHERE status='won') AS won, sum(...) FROM picks p LEFT JOIN clv_records c ON p.id = c.pick_id WHERE p.sport=$1 AND p.league=$2 AND p.market=$3 AND p.created_at BETWEEN $4 AND $5` round trip per (sport,league,market) tuple.
  - Drift check (D-14): Polars over rows fetched via `PickRepository` + `ClvRecordRepository`. Polars handles distribution work (mean, stdev) with consistent dtypes and reuses 02.1 P10 patterns. Fetch is bounded (≤56 days × current pick volume).
  - One pattern per concern; aggregator stays cheap, drift stays flexible.

### Claude's Discretion

- Whether the heartbeat job is a top-level scheduler `IntervalTrigger` or a wrapper around the existing scheduler's tick loop — both work; planner picks the simplest.
- Exact module split between `bip.production.__main__` and a `bip.production.builder.build_orchestrator(settings)` helper (recommended for testability).
- Whether `ClvTrendChecker` and `MetricsAggregator` are classes or free functions — recommend classes since both hold cooldown state / scheduler handles, but free functions inside the orchestrator are acceptable.
- The exact field set of the `DriftResult` dataclass returned by `compute_weekly_drift` — must include enough info to build the alert message (D-14) and write a `drift_events` Supabase row if the planner adds one.
- Whether to log heartbeat ticks (`structlog.debug("heartbeat", path=...)`) every tick or rate-limit them (debug noise vs journal volume).
- Whether `compute_period` repository method takes a single `(sport, league, market)` triple or accepts `None` for "all" and groups internally — single-triple is simpler; planner can choose.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Requirements (locked)
- `.planning/REQUIREMENTS.md` §CLV-03 — CLV trend alert (rolling 50-pick avg < +1% → Telegram). Pending → satisfied here.
- `.planning/REQUIREMENTS.md` §CLV-04 — Performance metrics aggregator (ROI, yield, avg CLV, W/L/V by sport/league/market/period). Pending → satisfied here.
- `.planning/REQUIREMENTS.md` §DATA-04 — APScheduler `AsyncIOScheduler` pipeline (Phase 1 contract; Phase 4 extends with heartbeat + metrics + drift jobs).
- `.planning/ROADMAP.md` Phase 4 §Success Criteria — five SC items. **SC#1 (drift) and SC#2 (graceful degradation) wording must be reconciled by the planner against D-01, D-02, D-14.**

### Prior Phase Decisions (locked contracts)
- `.planning/phases/01-foundation-data-pipeline-clv/01-CONTEXT.md` D-03 — Per-fixture DateTrigger model, AsyncIOScheduler, MemoryJobStore, daily orchestrator at 06:00 UTC, `_auto_recover` on startup. Phase 4 reuses without modification.
- `.planning/phases/01-foundation-data-pipeline-clv/01-CONTEXT.md` D-04 — Nightly CLV reconciliation cron at 03:00 UTC (currently a stub). Phase 4 leaves it as-is per D-02 (no deferred-backfill design).
- `.planning/phases/03-pick-engine-delivery-account-protection/03-CONTEXT.md` D-07 — Conservative Claude-failure semantics (filter + reason_code='claude_api_unavailable'). **Preserved as the default in D-01**; SKIPPED is opt-in via feature flag.
- `.planning/phases/03-pick-engine-delivery-account-protection/03-CONTEXT.md` D-13 — Single Telegram picks channel via `TELEGRAM_CHANNEL_ID`. Phase 4 adds a *separate* `TELEGRAM_OPS_CHANNEL_ID` (D-03); picks channel stays untouched.

### Source files to extend / create
- `src/bip/production/__main__.py` (NEW) — production entrypoint per D-05.
- `src/bip/production/__init__.py` (NEW) — `build_orchestrator(settings)` helper for tests.
- `src/bip/core/scheduler/orchestrator.py` — extend `start()` to register heartbeat (D-07), CLV trend (D-09), metrics aggregator (D-13), drift check (D-14) cron jobs. Existing `_auto_recover` adds structlog event (D-08). Reference: [orchestrator.py:65-81](src/bip/core/scheduler/orchestrator.py#L65-L81), [orchestrator.py:89-138](src/bip/core/scheduler/orchestrator.py#L89-L138).
- `src/bip/core/settings.py` — add `claude_failure_mode`, `telegram_ops_channel_id`, `heartbeat_file_path`, `clv_trend_alert_threshold`, `clv_trend_cooldown_hours`, `drift_check_min_picks_per_window`, `drift_absolute_threshold_pct`, `drift_stdev_multiplier` (validator pattern from [settings.py:39-58](src/bip/core/settings.py#L39-L58)).
- `src/bip/core/metrics/__init__.py` (NEW) — public API exports.
- `src/bip/core/metrics/aggregator.py` (NEW) — `compute_daily_metrics`, `compute_weekly_drift`, `DriftResult` dataclass per D-15.
- `src/bip/core/storage/repositories.py` — add `PerformanceMetricRepository.compute_period(...)` method per D-16. Existing model + repo: [repositories.py:370-407](src/bip/core/storage/repositories.py#L370-L407).
- `src/bip/clv/recorder.py` — `compute_rolling_clv_average` already exists at [recorder.py:78-93](src/bip/clv/recorder.py#L78-L93); add a thin `ClvTrendChecker` class (or free function) that wraps it with the 12h cooldown (D-11).
- `src/bip/core/claude/validator.py` — add a code path for D-01 `"skip"` mode (currently always returns `None` after retries). Phase 3 D-07 path stays the default.
- `src/bip/core/picks/engine.py` — branch on `Settings.claude_failure_mode` when validator returns `None` (D-01). Today the engine unconditionally filters at [engine.py:115-116](src/bip/core/picks/engine.py#L115-L116).
- `src/bip/core/telegram/` — extend sender to support both picks channel and ops channel (D-03). One sender with channel param OR two sender instances — planner choice.
- `deploy/systemd/bip.service` (NEW) — systemd unit per D-06.
- `deploy/install.sh` or `deploy/README.md` (NEW) — deployment runbook (create `bip` user, `/etc/bip/.env`, `/var/run/bip/`, install systemd unit, enable + start service).

### Tech Stack Constraints
- `CLAUDE.md` §Technology Stack — APScheduler 3.11.x (NOT 4.x), structlog for all logging, no FastAPI / web server (rules out HTTP /health endpoint), pydantic-settings for env config.
- `CLAUDE.md` §What NOT to Use — confirms "FastAPI / web server" rejection, supports D-07 file-touch heartbeat over HTTP /health.

### External References
- systemd `Type=notify` + `WatchdogSec=` documentation — https://www.freedesktop.org/software/systemd/man/systemd.service.html#WatchdogSec= (referenced for D-06, D-07).
- APScheduler 3.x `IntervalTrigger` and `CronTrigger` reference — https://apscheduler.readthedocs.io/en/3.x/modules/triggers/ (referenced for D-07, D-09, D-13, D-14).

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- [src/bip/core/scheduler/orchestrator.py](src/bip/core/scheduler/orchestrator.py) `PipelineOrchestrator` — already wires `_daily_orchestrator` (06:00 UTC cron), per-fixture T-2h / T-30m / kickoff-1m CLV / kickoff+150m reconcile DateTriggers, and `_auto_recover` on startup. Phase 4 adds 4 new cron jobs (heartbeat, CLV trend, metrics, drift) to the same scheduler instance — no new scheduler.
- [src/bip/clv/recorder.py:78-93](src/bip/clv/recorder.py#L78-L93) `compute_rolling_clv_average(clv_values: list[float]) -> float` — exists, never called. Phase 4 wraps it with cooldown + Telegram alert (D-09–D-12).
- [src/bip/core/storage/models.py:184-216](src/bip/core/storage/models.py#L184-L216) `PerformanceMetric` Pydantic model — fully defined (sport, league, market, period, period_start/end, total_picks, won/lost/void, total_staked, total_pnl, roi, yield_pct, avg_clv, avg_edge). No schema migration needed.
- [src/bip/core/storage/repositories.py:370-407](src/bip/core/storage/repositories.py#L370-L407) `PerformanceMetricRepository` — has `upsert()` and `get_by_league_market()`. Phase 4 adds a `compute_period()` method that runs the SQL aggregation and returns a `PerformanceMetric`.
- [src/bip/core/claude/validator.py:96-137](src/bip/core/claude/validator.py#L96-L137) `ClaudeValidator` — 2-attempt retry returns `None`. PickEngine consumes `None` as "filter" today; Phase 4 D-01 adds a feature-flag branch.
- [src/bip/clv/client.py:53-58](src/bip/clv/client.py#L53-L58) `OddsApiClient` — tenacity 3-attempt retry already in place. Phase 4 changes nothing here; orchestrator continues to skip silently on terminal failure (D-02).
- [src/bip/core/settings.py](src/bip/core/settings.py) `Settings` (BaseSettings) — pydantic-settings with `@field_validator` pattern. Phase 4 extends in place per D-05 wiring needs.

### Established Patterns
- pydantic-settings + `.env` for all config (extend Settings, never hardcode). All Phase 4 knobs follow this pattern.
- `@field_validator` for env-var validation (mirrors `_validate_channel_id` at [settings.py:39-58](src/bip/core/settings.py#L39-L58)) — apply same shape to `telegram_ops_channel_id`.
- structlog keyword logging — every Phase 4 event (`heartbeat_tick`, `clv_trend_check`, `clv_trend_alert_fired`, `metrics_aggregation_complete`, `drift_check_complete`, `drift_alert_fired`) uses `logger.info("event_name", **kwargs)`.
- `@dataclass(client: Client)` for repositories. `PerformanceMetricRepository.compute_period` follows the same shape.
- Atomic writes (`.tmp` + `Path.replace()`) — heartbeat file uses `Path.touch()` directly (no content) so no atomicity concern; mtime alone is the signal.
- structlog event names use snake_case + past tense for completed work, present tense for in-flight (existing convention).
- CronTrigger / IntervalTrigger / DateTrigger — full APScheduler vocabulary already exercised in `orchestrator.start()` and `_register_fixture_jobs`.

### Integration Points
- `PipelineOrchestrator.start()` at [orchestrator.py:65-81](src/bip/core/scheduler/orchestrator.py#L65-L81) is the single hook for adding cron jobs. Phase 4 appends 4 calls inside `start()`:
  1. heartbeat — `add_job(self._tick_heartbeat, trigger=IntervalTrigger(minutes=5), id='heartbeat')`
  2. CLV trend check — `add_job(self._check_clv_trend, trigger=CronTrigger(minute=0), id='clv_trend')`
  3. metrics aggregator — `add_job(self._aggregate_metrics, trigger=CronTrigger(hour=23, minute=0), id='metrics_aggregator')`
  4. weekly drift check — `add_job(self._check_drift, trigger=CronTrigger(day_of_week='mon', hour=6, minute=0), id='weekly_drift')`
- The orchestrator's `__init__` gains an optional `metrics_aggregator: MetricsAggregator | None = None` and `clv_trend_checker: ClvTrendChecker | None = None` for tests; `bip.production.__main__` passes real instances.
- The PickEngine claude-failure branch (D-01) lives at [engine.py:115-116](src/bip/core/picks/engine.py#L115-L116) — wrap the existing filter logic in `if settings.claude_failure_mode == "filter":` else build a `Pick(status='pending', claude_validation='SKIPPED', ...)` and continue to send.
- TelegramSender gains a second instance bound to `Settings.telegram_ops_channel_id` for ops alerts (D-03). Pick alerts continue using the picks-channel sender (Phase 3 D-13 path unchanged).
- `_auto_recover` adds a `logger.info("auto_recover_complete", jobs_re_queued=count)` at the end (D-08).
- systemd unit ExecStart points at `/opt/bip/.venv/bin/python -m bip.production` — `bip.production.__main__` is the only callable surface.

</code_context>

<specifics>
## Specific Ideas

- **Heartbeat path** should default to `/var/run/bip/heartbeat` but accept any path via `Settings.heartbeat_file_path`. Tests use `tmp_path / "heartbeat"`. The directory must exist and be writable by the `bip` user — install script creates it.
- **systemd `WatchdogSec=600`** must be larger than `IntervalTrigger(minutes=5)` heartbeat cadence with comfortable margin. 10 min watchdog vs 5 min ticks gives 2x margin — survives one missed tick without restart, restarts on two consecutive misses.
- **CLV trend cooldown state** is intentionally in-memory (`dict[str, datetime]` on the `ClvTrendChecker` instance). Restart cost = at most one duplicate alert. Persisting cooldown state in Supabase is overkill at v1; revisit if alert duplication during restarts becomes operationally noisy.
- **Per-market CLV trend** at v1 (Phase 3 = 1X2-only): the `≥50 settled` guard means the per-market check stays dormant until 50 settled 1X2 picks exist; the global check runs from pick 50 onward. Phase 6 corners adds a second market that crosses 50 → per-market alerts naturally activate without code changes.
- **Drift check minimum sample**: enforce `≥30 settled picks per (league, market) per 4-week window`. Below that, skip the comparison (no alert, no false alarm). Implement as `if len(recent) < min_picks or len(prior) < min_picks: return None`.
- **Drift signal direction**: only alert on **drops**. CLV improvements don't trigger alerts (no operational action needed). The `>=` comparisons are one-sided.
- **Aggregator idempotency**: re-running the same daily cron must not double-count. The repository upsert is keyed on `(sport, league, market, period, period_start)` — picks count and pnl are recomputed from source-of-truth `picks` table each run. Manual mid-day re-runs (CLI `python -m bip.production aggregate --day 2026-05-03`) are safe by design even though the CLI is not in scope for this phase.
- **Settings serialization for tests**: tests should construct `Settings(_env_file=None, supabase_url=..., ...)` directly, not load from `.env`. The new Phase 4 fields all need sensible defaults so test instantiation stays terse.
- **Ops alert HTML escaping**: Telegram HTML mode (Phase 3 D-12) requires `&`, `<`, `>` escaping. Trend/drift alert messages are simple ASCII — no escaping needed today, but keep the same `html.escape()` pattern as the picks template to avoid surprises if league/market names ever contain special chars.
- **Migration: none required.** All Phase 4 work is application-layer. `picks`, `clv_records`, `performance_metrics` schemas are sufficient.
- **Deployment runbook precedence**: `deploy/install.sh` is preferred over a long README — copy-paste-runnable beats prose. Idempotent (re-runnable on existing install).

</specifics>

<deferred>
## Deferred Ideas

- **Web admin dashboard / breakdown UI for alerts** — CLAUDE.md rules out FastAPI/web server in v1; ops view is journald + Supabase Studio.
- **Feature drift (KS test on recent vs training distribution)** — v2; needs training-time feature snapshot stored alongside model artifact (Phase 2 doesn't currently emit one).
- **Odds drift (opening vs closing gap widening)** — v2; useful signal but Phase 4 v1 picks one drift type to keep scope tight.
- **Per-league CLV trend dimension** — meaningful only after multi-market and multi-season volume; deferred until Phase 6 corners + a full season of data.
- **Backfill of missed CLV snapshots after VPS downtime** — deliberate non-feature; late snapshots aren't true closing lines and would silently corrupt the CLV record.
- **Backfill of missed reconciliation jobs >150 min past kickoff** — current `_auto_recover` doesn't handle this; deferred to Phase 4.x or v2 (rare in practice with `Restart=always`).
- **Auto-promotion of model registry on CLV improvement** — Phase 2 D-05 deferred this; Phase 4 inherits the deferral. Manual promotion via the existing training CLI stays the contract.
- **Pinnacle `/historical` backfill** — Phase 02.1 deferred this; Phase 4 inherits.
- **Edge-triggered CLV trend alerts (cross above → cross below detection)** — rejected in favor of fire-and-cooldown for simplicity; revisit if 12h cooldown produces noise.
- **Telegram bot user commands (`/status`, `/clv_today`, `/pause`)** — Phase 3 deferred; Phase 4 keeps alerts one-way.
- **Persistent cooldown / alert-state table in Supabase** — revisit if in-memory cooldown duplicates alerts on restart frequently.
- **API retry knob exposure as Settings fields** (`claude_max_attempts`, etc.) — defer until production data shows tuning is needed.

</deferred>

<reconciliations>
## ROADMAP Success-Criteria Reconciliations

These narrow ROADMAP §Phase 4 §Success Criteria to match locked CONTEXT.md decisions.
Final patch to ROADMAP.md applied in 04-08-PLAN (Wave 7).

### SC#1 Reconciliation — drift scope narrowed to model-CLV only

**Original ROADMAP wording (line 119):**
> "If rolling 50-pick average CLV drops below +1%, a Telegram warning is sent
> recommending to pause betting and audit"

**Status:** This is the CLV trend alert (CLV-03), NOT drift. The drift item is
implicit in §Phases line 18 ("CLV trend alerting"). Both must coexist.

**Original CONTEXT.md (D-14) wording:**
> "Weekly model-CLV drift check"

**Reconciled wording for ROADMAP §Phase 4 §SC list (Wave 7 patch):**

> SC#1: Weekly model-CLV drift check (last 4-week mean CLV vs prior 4-week mean)
> per (league, market) with ≥30 settled picks per window — fires Telegram alert
> on hard drop ≥2pp OR soft drop ≥1.5×stdev (where stdev is computed over daily
> mean CLV in the prior window, floored at 1.0pp). Feature drift (KS test) and
> odds drift are explicitly deferred to v2.

**Justification:** RESEARCH §Drift Statistical Method shows the soft-gate stdev
needs a floor (heavy-tailed CLV at n=30) and `Settings.drift_stdev_floor_pp = 1.0`
is the new field that enforces it. Per CONTEXT.md `<deferred>` block, feature-drift
and odds-drift are out of scope.

### SC#2 Reconciliation — graceful degradation feature-flag wording

**Original ROADMAP wording (line 120-121):**
> "When Claude API is unavailable, the pipeline sends picks with
> `claude_validation='SKIPPED'` instead of failing; when Odds API is unavailable,
> picks still send but CLV recording is deferred"

**Conflict:** Phase 3 D-07 says Claude failure → `filter` (NOT `SKIPPED`).
Phase 4 D-02 says Odds API failure → CLV record SKIPPED, NOT deferred.

**Reconciled wording for ROADMAP §Phase 4 §SC list (Wave 7 patch):**

> SC#2: Graceful degradation. Claude API failure: feature flag
> `Settings.claude_failure_mode` controls behavior. Default `"filter"` preserves
> Phase 3 D-07 (account-longevity-first) — pick is persisted with
> `status='filtered', reason_code='claude_api_unavailable'`, never sent. Opt-in
> `"skip"` (set via `.env` once CLV track record justifies it) — pick is
> persisted with `status='pending', claude_validation='SKIPPED'`, sent to
> Telegram with a 🤖❌ marker. Odds API failure during CLV snapshot: skip
> silently — no `clv_records` row written, picks still send (no backfill of
> missed snapshots; Pinnacle moves post-match make backfill non-true closing
> lines).

**Justification:** Phase 3 D-07 (`filter`) is the locked default; Phase 4 D-01
adds the opt-in flag. Phase 4 D-02 explicitly rejects deferred-backfill design.
Both code paths exist; one is dormant at v1.
</reconciliations>

---

*Phase: 04-production-orchestration*
*Context gathered: 2026-05-03*
