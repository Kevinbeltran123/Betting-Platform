# Gap Audit Report

**Auditor:** Claude (Opus 4.7, 1M context)
**Date:** 2026-05-03
**Scope:** `.planning/` documentation vs `src/bip/` and `tests/` implementation
**Method:** Read VERIFICATION/VALIDATION/SUMMARY artifacts; compare each requirement (CORE/DATA/ML/CLV/PICK/CLAUDE/CORNERS/SCALE) against actual source files; grep mitigations for each PITFALLS.md entry; sample-read engine, orchestrator, plugin, validator, sender, recorder, repositories.

---

## Sumario ejecutivo

- **Total gaps:** 24 (5 críticos, 8 graves, 8 moderados, 3 menores)
- **Top 3 riesgos para llegar a producción:**
  1. **Orchestrator integration is broken on the live wiring** (G-CODE-01 + G-CODE-02). `_run_pipeline` calls `self.plugin.get_opening_odds(...)` (no such method on `SportPlugin`/`FootballPlugin`) and applies `getattr(p, "market", ...)` to dicts returned by `PickRepository.get_pending_for_fixture()`. Both bugs are masked because every orchestrator test stubs them with `AsyncMock`. The first real run will throw `AttributeError`; the D-01 dup-alert guard will silently never fire. This is the single most dangerous gap.
  2. **Per-market edge thresholds are documented but ignored at runtime** (G-MAINT-01). Every league YAML and `markets.yaml` declares per-market thresholds (1X2 = 0.08, BTTS/OU = 0.05, AH = 0.06, corners = 0.07). `PickEngine.evaluate` hardcodes the single `EDGE_THRESHOLD_PCT = 0.05` from `bip.train.backtest`. Picks against 1X2 (the only Phase 3 market) will fire at 5% edge instead of the configured 8%, contradicting the YAML and inflating volume well above design.
  3. **CLV-03 alerting + CLV-04 aggregation never run in production** (G-LOGIC-04 + G-LOGIC-05). `compute_rolling_clv_average()` exists as a pure function but no scheduler job invokes it; no Telegram warning fires when avg CLV drops below +1%. `PerformanceMetric.upsert()` exists but nothing aggregates results into it. The system can record CLV but cannot detect or surface CLV decay — defeating the project's own "primary metric" promise.

---

## Gaps por dimensión

### 1. Estructura de código

Documented architecture (`.planning/research/ARCHITECTURE.md` Component Boundaries table) prescribes specific module locations. Actual layout differs significantly. Most are deliberate consolidations that are NOT documented anywhere as decisions.

| ID | Severidad | Componente prometido | Estado real | Ubicación esperada vs real | Impacto |
|----|-----------|----------------------|-------------|----------------------------|---------|
| G-CODE-01 | **Crítico** | `SportPlugin.get_opening_odds(fixture_id) -> dict` (called from orchestrator at `src/bip/scheduler/orchestrator.py:247-249`) | **Method does not exist** on either `SportPlugin` ABC (`src/bip/sports/__init__.py:44-70`) or `FootballPlugin` (`src/bip/sports/football/plugin.py`). | Code path will `AttributeError` on first real run; only `AsyncMock` in `tests/scheduler/test_orchestrator.py:135,174,205` hides this. | First production T-2h tick crashes the pipeline. |
| G-CODE-02 | **Crítico** | `pick_repo.get_pending_for_fixture()` returns `list[Pick]` objects so `getattr(p, "market", None)` works (`src/bip/scheduler/orchestrator.py:230-232`) | Returns `list[dict]` (`src/bip/core/storage/repositories.py:169-184`) and is **synchronous** (no `async def`). Orchestrator `await`s it and uses `getattr` for dict access — both wrong. | `getattr(dict, "market", None)` always returns `None`, so D-01 dup-alert guard silently passes through and a duplicate Telegram alert fires at T-30min. `await` on a sync method that returns a list will raise `TypeError`. Both hidden by `AsyncMock` in tests. | Duplicate alert + crash. The dup-alert guard described in 03-08-SUMMARY does not actually run. |
| G-CODE-03 | Grave | `core/ev_engine.py` and `core/kelly.py` (per ARCHITECTURE.md Component Boundaries) | Folded into `src/bip/core/picks/account_longevity.py` (Kelly) and `src/bip/train/backtest.py` (EV via `simulate_pick`). No `ev_engine.py` exists. | Re-use is fine, but the location drift is **undocumented** — ARCHITECTURE.md still prescribes the old layout, and a plan that imports `from bip.core.ev_engine import ...` will fail. STATE.md decision log records D-02 ("EDGE_THRESHOLD_PCT lives in bip.train.backtest") but the EV engine itself was never given a home decision. | Future devs will misroute imports; ML pipeline and pick engine share `simulate_pick` via `bip.train` which is technically the wrong layer (train depends on Phase 2; core/picks now depends on bip.train). |
| G-CODE-04 | Grave | `core/scheduler.py` (ARCHITECTURE.md, lines 92, 723) | Lives at `src/bip/scheduler/orchestrator.py` (top-level package, not under `core/`). | Violates the "core layer is sport-agnostic glue" prescription in CORE-02. The scheduler is sport-agnostic but sits outside `core/`. Import paths and CORE-02 traceability now ambiguous. | Cosmetic for now; trips up CORE-02 verification when re-audited. |
| G-CODE-05 | Grave | `core/pipeline.py` — end-to-end pipeline runner per ARCHITECTURE.md line 93 and Phase 6 Build-Order | **Does not exist.** `PipelineOrchestrator._run_pipeline` is a private method on the scheduler, not a separate module. | The "scheduler triggers PipelineRunner that calls registry that loads plugin" 3-tier separation never materialised — scheduler does both jobs. Any future second sport (tennis) will need to either inject another plugin into the same orchestrator or copy-paste the orchestration loop. | Direct violation of SCALE-01 design (Plugin Registry should be discovered by a Pipeline Runner, not hardwired via constructor). Phase 7 tennis scaffold will require refactor. |
| G-CODE-06 | Grave | `core/registry.py` — Plugin Registry pattern (ARCHITECTURE.md Pattern 1, line 92, 605-625) | **Does not exist.** `PipelineOrchestrator.__init__` accepts a single `plugin: SportPlugin` argument; no decorator/registry mechanism. | The whole "plug a sport in by `@PluginRegistry.register('tennis')`" extensibility is missing. Anyone adding tennis must thread it through every constructor. SCALE-01 (tennis scaffold without core changes) becomes impossible without a refactor. | Architectural promise of plugin discovery is unfulfilled; tennis scaffold won't work without changing scheduler/main wiring. |
| G-CODE-07 | Grave | `core/claude/augmenter.py` — Role B confidence_modifier (ARCHITECTURE.md line 101, REQUIREMENTS.md CLAUDE-02) | **Does not exist.** Only `validator.py` (Role C) is implemented. Plugin's `build_claude_context()` returns an empty `ClaudeContext` (plugin.py:347-353). | Phase 5 work; documented as deferred in ROADMAP. But the plugin already has the abstract method and stubs out empty content — no compile-time signal that Phase 5 owes the wiring. | Acceptable per roadmap, but the empty stub is a maintainability time-bomb (no `NotImplementedError`, callers think they have a context). |
| G-CODE-08 | Moderado | `core/health.py` — heartbeat file + monitoring (ARCHITECTURE.md lines 583-593, Phase 6) | **Does not exist.** No heartbeat, no health endpoint, no systemd timer. | Production deployment per ARCHITECTURE.md requires this; without it, hangs are invisible until "no Telegram alert today" is noticed by hand. | Phase 6 owes this; flag now so it isn't forgotten when single-VPS deploy ships. |
| G-CODE-09 | Moderado | `core/metrics.py` — Performance aggregator (ARCHITECTURE.md line 107) | **Does not exist.** `PerformanceMetricRepository` exists in `repositories.py:371-407` but no module computes the aggregates that get upserted. | Documented daily 06:00 UTC aggregator job in ARCHITECTURE.md is missing; CLV-04 cannot produce PerformanceMetric rows. | CLV-04 is "satisfied" in REQUIREMENTS only by virtue of having the table model — no data ever lands in it. |
| G-CODE-10 | Menor | `bip/scheduler/__init__.py` exists; `core/scheduler.py` does not | The package layout uses `bip/scheduler/` as a peer to `bip/core/` and `bip/sports/` instead of nested under `bip/core/`. | Three-tier layering (Data/Intelligence/Delivery) was meant to live entirely under `core/`. The scheduler being a peer module is undocumented. | Cosmetic; surfaces if a future audit greps `core/` for "everything sport-agnostic". |

### 2. Lógica comportamental

Each PITFALLS.md item (1-13) and Anti-Pattern (1-4) examined against code evidence. **Mitigation status:** ✅ found, ⚠ partial, ❌ missing.

| ID | Severidad | Pitfall/Anti-pattern | Mitigación documentada | Evidencia en código (sí/no/parcial) | Riesgo |
|----|-----------|----------------------|-----------------------|--------------------------------------|--------|
| G-LOGIC-01 | Grave | **Pitfall 1** — Vanity accuracy vs CLV | "Every backtest fold must compute simulated CLV" | ✅ `train/pipeline.py:204-217` invokes `apply_slippage` + `compute_clv` per pick; `walk_forward_mean_clv_pct` persisted to `metadata.json`. **But:** never run on real data (Phase 02.1 deferral); zero production CLV history exists. | Synthetic green; empirical never-validated. STATE blockers list this. |
| G-LOGIC-02 | Crítico | **Pitfall 7** — CLV computation errors (vig removal, closing-line timing, market efficiency, sample size) | "Always convert to vig-free implied probabilities before comparing" | ❌ **No vig-removal code anywhere.** Grep for `remove_vig`/`fair_prob`/`vig` in `src/` and `tests/` returns zero hits. `clv/recorder.py:22-39` does raw `(odds_at_pick / closing_odds - 1) * 100` against the unprocessed Pinnacle line. | Every CLV number recorded by the system is biased downward by the Pinnacle vig (≈2-4%). The "+3% CLV" target is meaningless without vig removal. **Project-defining metric is wrong.** |
| G-LOGIC-03 | Grave | **Pitfall 7** — closing-line timing | "Use The Odds API to capture Pinnacle odds at kickoff (not hours before)" | ⚠ Snapshot scheduled at `kickoff + 105min` (`scheduler/orchestrator.py:191-199`). That's *post-match*, not "at kickoff". `_record_clv` is a logging stub only — no actual call to `OddsApiClient.fetch_pinnacle_closing_odds`. | The closing-line timing is wrong direction (post-match = settled odds, not closing). And the recorder isn't even wired. CLV will be either uncomputable or computed against the wrong snapshot. |
| G-LOGIC-04 | Crítico | **CLV-03** (Requirement) — alert if rolling 50-pick CLV drops below +1% | `compute_rolling_clv_average` exists (`clv/recorder.py:42-57`) | ❌ Function exists but **no caller invokes it**. No scheduler job, no Telegram trigger. `grep -r "compute_rolling_clv_average" src/` returns only the definition. | The "primary metric pause-and-audit alert" never fires. The single most important production safety mechanism is dead code. |
| G-LOGIC-05 | Grave | **CLV-04** (Requirement) — performance aggregation by sport/league/market/period | `PerformanceMetric` model + `PerformanceMetricRepository.upsert()` exist | ❌ No aggregation code: nothing reads results+CLV and produces ROI/yield/avg_clv rows. The scheduler has no daily/weekly aggregator job. | Performance dashboard is empty by design; without aggregates, you can't see model degradation, drift, per-league ROI, etc. ARCHITECTURE.md's "drift detection (weekly)" promise is unfulfilled. |
| G-LOGIC-06 | Grave | **Anti-Pattern 3** — Real-time odds in feature pipeline (circular) | "Use odds ONLY in EV calculation layer" | ⚠ Likely OK — `features.py` doesn't reference odds, but `seed_historical.py` writes odds to a separate Parquet store and `pipeline.py:122-135` joins features ⨝ results ⨝ odds for CLV computation. **Risk:** if a future engineer adds an odds-derived feature column, the join makes leakage trivial. No assertion or test guards against an `opening_*` column appearing in the feature schema. | Latent anti-pattern; needs a static guard. |
| G-LOGIC-07 | Moderado | **Pitfall 4 #3** — closing odds as features | (covered above) | ⚠ See G-LOGIC-06. Specifically: nothing prevents a contributor from passing `opening_home/draw/away` columns into the model. | Same as above. |
| G-LOGIC-08 | Grave | **Pitfall 8** — Claude API as production bottleneck (latency, fallback, caching) | "Implement fallback: if Claude API fails, proceed without modifier (use 0 adjustment)" + "Cache Claude responses by fixture ID for backtest reproducibility" | ⚠ Partial: validator has 2-attempt retry then returns `None` and pick is `filtered/claude_api_unavailable` (engine.py:96-97). That's stricter than ARCHITECTURE.md's "approve by default" — D-07 explicitly chose "conservative". **But:** no fixture-id cache layer for reproducibility/backtest replay. | Phase 5 (Role B shadow mode) and any backtest replaying historical Claude verdicts will be non-deterministic. |
| G-LOGIC-09 | Moderado | **Pitfall 10** — Telegram delivery delay, MarkdownV2 fragility | "Use HTML formatting" + "rate-limited queue" | ✅ `TelegramBot` uses `parse_mode='HTML'` (D-12) and `AIORateLimiter(max_retries=3)` from python-telegram-bot. **Missing:** delivery confirmation via `getUpdates`; no test of all 5-league team names with diacritics through HTML escaping. | Acceptable for v1; flag for Phase 6 hardening. |
| G-LOGIC-10 | Moderado | **Pitfall 11** — SportPlugin ABC over-engineering for football | "Design ABC with tennis scaffold in mind" | ⚠ ABC has 5 methods, all reasonably general. **But:** `predict(features, market)` returns `ProbabilityMap` whose `probabilities` dict is implicitly `{"1": ..., "X": ..., "2": ...}` (1X2). Tennis won't have a draw column; the contract is silently football-shaped. | Refactor expected when tennis is added (acknowledged in Pitfall 11). |
| G-LOGIC-11 | Grave | **Pitfall 12** — Supabase connection limits | "Use connection pooling (Supavisor/PgBouncer)" + "stagger execution windows" | ❌ `supabase_client.py:11-13` is `create_client(url, key)` — no pooling, no Supavisor URL, no PgBouncer. Each call to `get_supabase_client()` creates a fresh client. | At 5 leagues × ~5 fixtures/day × 4 jobs (T-2h, T-30m, T+105m, reconcile) × concurrent ops, connection-limit risk is real. With more sports/leagues, will hit Pro-tier 60-conn cap. |
| G-LOGIC-12 | Moderado | **Pitfall 13** — Model versioning without reproducibility | "Version tuple (model, feature_pipeline_hash, calibration, claude_prompt_version)" | ⚠ Partial: `ModelMetadata` has `feature_set_hash`, `git_commit`, `sklearn_version`, `base_model_packages`. **Missing:** `claude_prompt_version` / `learnings_sha` is logged in Claude verdicts but **not** in `Prediction` rows or `Pick` rows. Cannot reproduce a 3-week-old pick's Claude verdict from DB alone. | Audit/replay broken across learnings updates. |
| G-LOGIC-13 | Crítico | **Pitfall 3** — Betano account restriction (stake camouflage) | "Vary stake amounts: never bet exact calculated amounts" + "rotate markets" + "stagger withdrawals" | ⚠ Stake jitter (±10%, deterministic md5) ✅; round to 0.5u ✅; market rotation (60% cap) ✅ but **structurally dormant in 1X2-only Phase 3** (acknowledged in `account_longevity.py:104-106`). Send-time variance ✅ (D-11). **Missing:** no recreational-noise-bet logic; no withdrawal-pattern logic; no monitor of accepted-stake-amount trend. | Account survives weeks 1-2; restriction risk grows after that without market diversification. The mitigation is theoretical until a second market lands. |
| G-LOGIC-14 | Moderado | **Anti-Pattern 1** — Martingale on corners | "Quarter-Kelly maximum on ALL markets" | ✅ `quarter_kelly_units(...max_fraction=0.25)` enforced; clamped to `[0, max_fraction]`. No escalation logic anywhere. Max stake also enforced (settings.max_kelly_fraction). | Mitigated. |
| G-LOGIC-15 | Moderado | **Anti-Pattern 4** — Feature factory | "Fewer, well-validated features > many noisy" | ⚠ Current Phase 1 featureset is small (`features.py` ~10 features), so anti-pattern not triggered. **No CI guard** against feature-count explosion. Feature additions go through plain code review only. | Latent. |

### 3. Escalabilidad

| ID | Severidad | Asunción actual | Punto de quiebre | Cuándo morderá |
|----|-----------|-----------------|------------------|----------------|
| G-SCALE-01 | Crítico | Single `PipelineOrchestrator` constructed with one `plugin: SportPlugin` | Cannot run football + tennis concurrently without instantiating two orchestrators (separate scheduler instances, separate Telegram bots) — and Telegram bot constructor only accepts one channel | Phase 7 (tennis scaffold). SCALE-01 explicitly requires sport-agnostic core with no code changes; current design needs refactor. |
| G-SCALE-02 | Grave | Claude validator runs on the critical path: every pick blocks until Claude returns or 60s timeout fires (engine.py:94 → validator.py:96-130). 2 attempts × 60s = up to 2 minutes per pick. | At 20 fixtures × 1 market each = 20 sequential blocks. ARCHITECTURE.md said "batch async, not sequential" + "60s budget across all fixtures." Engine is sequential per fixture; orchestrator iterates fixtures sequentially in `_daily_orchestrator` and registers DateTrigger jobs which fire concurrently — but each job's `evaluate()` call is sequential within itself. | At ≥5 leagues × 5 fixtures = 25 fixtures, 30-min window between T-2h scheduled jobs may overlap with Claude latency outliers. Current 1-2 league scale is OK. |
| G-SCALE-03 | Grave | `supabase_client.py` creates raw `Client` per call, no pool, no Supavisor URL. Repos are dataclasses with one client each. | At ≥3 sports / ≥10 concurrent jobs, will exceed Supabase Pro 60-direct-conn limit. Pitfall 12 explicitly calls this out. | Phase 7+. Mitigation needs to land before tennis scales fixture count. |
| G-SCALE-04 | Grave | Telegram: one `TELEGRAM_CHANNEL_ID` env var; `send_html(text)` writes to `int(self._channel_id)`. | v2 plan ("paid sub-feed") needs per-user channels; current design forces a single channel. Adding a second channel = config rewrite + sender refactor. | v2 release. |
| G-SCALE-05 | Moderado | Parquet partition layout: features = 4-level (sport/league/season/matchday); results & odds = 3-level (sport/league/season). | At ~50 leagues, the season-level Parquet files become large and force whole-season scans for read_results. Hive pruning works at season granularity but not finer. | At 50 leagues / multi-sport. CORNERS-01 coverage script already uses `pl.scan_parquet` lazily so somewhat mitigated. |
| G-SCALE-06 | Moderado | `learnings_loader.py` caches the file in module-level `_CACHE` after first load. Single learnings file (`football-learnings.md`). | Tennis or NBA need their own learnings; current design is football-only path. | Phase 7+. |
| G-SCALE-07 | Moderado | All retries are tenacity `wait_exponential(min=2, max=60), stop_after_attempt(5)`. Per-endpoint, no global rate limit awareness. | API-Football Pro is 300 req/min. At 5 leagues × 5 endpoints (fixtures/stats/lineups/odds/h2h) × concurrent fixtures, can theoretically burst past 300/min. No `asyncio.Semaphore` / token bucket. Pitfall 9 #4. | At 10+ leagues during pre-kickoff burst. |
| G-SCALE-08 | Moderado | `bip.scheduler` uses `MemoryJobStore` (default for AsyncIOScheduler). Pitfall 6 mitigation re-queues lost send jobs from DB on restart. | OK while pick volume < 50/day. **But:** any other DateTrigger (clv, reconcile) that fires while process is restarting is silently lost — only `send_pick_*` jobs get re-queued. | Reconciliation can be re-driven by humans, but CLV snapshots are unrecoverable post-kickoff window. |

### 4. Mantenibilidad

| ID | Severidad | Issue | Archivos afectados | Refactor recomendado |
|----|-----------|-------|--------------------|---------------------|
| G-MAINT-01 | **Crítico** | Per-market edge thresholds in `markets.yaml` and `leagues/*.yaml` are **completely ignored**. `PickEngine.evaluate` uses hardcoded `EDGE_THRESHOLD_PCT = 0.05` from `bip.train.backtest`, regardless of which market the prediction targets. | `src/bip/core/picks/engine.py:78`; `src/bip/train/backtest.py:11-12`; `src/bip/sports/football/config/markets.yaml`; `src/bip/sports/football/config/leagues/*.yaml` | Inject threshold from `markets.yaml` per-market keyed by `prediction.market`; or accept threshold as `evaluate(prediction, opening_odds, threshold=)` arg and have orchestrator look it up. CORE-05 ("markets defined as runtime YAML") is silently violated. |
| G-MAINT-02 | Grave | Tests that mask real wiring bugs. `tests/scheduler/test_orchestrator.py:135,145,174,184,205,211` use `AsyncMock` for `plugin.get_opening_odds` and `pick_repo.get_pending_for_fixture` — methods that either don't exist or are sync. The tests pass green; the production code fails on first run. | `tests/scheduler/test_orchestrator.py`; `src/bip/scheduler/orchestrator.py:229,247-250` | Replace AsyncMocks with concrete `pick_repo` instance backed by an in-memory dict; add a `tests/test_plugin_contract.py` assertion that any method orchestrator calls on `plugin` exists on the `SportPlugin` ABC. |
| G-MAINT-03 | Grave | REQUIREMENTS.md traceability table desync: marks all CORE/DATA/CLV requirements as **`Pending`** even though Phase 1 + 2 + 02.1 are complete (per ROADMAP/STATE). Only ML-02 and ML-03 show `Complete`. | `.planning/REQUIREMENTS.md:96-129` | Single bulk update during Phase 3 closeout. Better: convert table to a generated artifact driven by git commit messages or plan SUMMARY frontmatter. |
| G-MAINT-04 | Grave | Engine's signature mismatch. Orchestrator calls `pick_engine.evaluate(prob_map, opening_odds)` (a `ProbabilityMap`), but `engine.evaluate(self, prediction, opening_odds)` then accesses `prediction.fixture_id`, `prediction.market`, `prediction.probabilities`, `prediction.sport`, `prediction.home_team`, `prediction.away_team`, `prediction.kickoff_utc`, `prediction.is_lineup_adjusted`, `prediction.model_version`, `prediction.league`. `ProbabilityMap` has only `fixture_id`, `market`, `probabilities`, `model_version`, `computed_at` — no team names, no league, no sport, no lineup flag. | `src/bip/scheduler/orchestrator.py:250`; `src/bip/core/picks/engine.py:65-109,195-213`; `src/bip/sports/__init__.py:30-35` | Either change orchestrator to fetch a `Prediction` (DB row), or extend `ProbabilityMap` to carry team names+league+sport+lineup flag. AsyncMocks in tests hide this completely. |
| G-MAINT-05 | Grave | Magic-string market names. `"1X2"` (in orchestrator.py:231,242,340), `"onextwo"` (in `markets.yaml`), `"h2h"` (in `clv/client.py:23`), and `"1"/"X"/"2"` (selection keys in engine) are all the same concept under different spellings. No central enum, no validation that the engine's `market` field matches a YAML key. | `src/bip/scheduler/orchestrator.py`; `src/bip/sports/football/config/markets.yaml`; `src/bip/clv/client.py`; `src/bip/core/picks/engine.py:45` | Define `MarketKey = Literal["onextwo","btts","ou","ah","corners"]` in `core/types.py` and rename the orchestrator's `"1X2"` to `"onextwo"`. |
| G-MAINT-06 | Moderado | `_record_clv` (orchestrator.py:258-260) is a logging stub. There's a `ClvRecorder` class but the orchestrator never instantiates it or calls `recorder.record(...)`. | `src/bip/scheduler/orchestrator.py:258-260`; `src/bip/clv/recorder.py:60-129` | Wire CLV recorder into the orchestrator constructor and call from `_record_clv`. |
| G-MAINT-07 | Moderado | `_reconcile_clv` (orchestrator.py:262-263) is a logging-only stub for the daily 03:00 UTC job. No reconciliation logic. | `src/bip/scheduler/orchestrator.py:262-263` | Replace with the actual nightly reconciliation pass over picks missing CLV records. |
| G-MAINT-08 | Moderado | `Prediction.kickoff_utc` is set to `features.computed_at` (plugin.py:311,334) — a logical bug. The kickoff time is never actually known at the point of insertion. Comment says "caller/pipeline enriches" but no one does. | `src/bip/sports/football/plugin.py:311,334` | Pass `fixture.kickoff_utc` through `predict(features, market, fixture)` or change `FeatureMatrix` to carry `kickoff_utc`. |
| G-MAINT-09 | Moderado | `_EnsembleProbaWrapper` known-wart (re-fits on a 1-row slice to satisfy FrozenEstimator). Documented as "known ergonomic wart" in 02.1 SUMMARY but never refactored. | `src/bip/train/pipeline.py:64-100` (approx) | Replace with `sklearn.frozen.FrozenEstimator` directly, or skip the wrapper. |
| G-MAINT-10 | Moderado | Hardcoded reschedule cadence (`+30 min` retry in orchestrator.py:307) and max retries (`_RECONCILE_MAX_RETRIES = 4`) are class constants; not configurable per league or via Settings. | `src/bip/scheduler/orchestrator.py:36-37,306-313` | Move to `Settings` for ops control. |
| G-MAINT-11 | Menor | `home_team=""` / `away_team=""` blanks in `_write_prediction_rows` (plugin.py:309-310,332-333). Comment says "caller enriches; acceptable blank at predict-only scope" but no caller does. | `src/bip/sports/football/plugin.py:309-310,332-333` | Either pass fixture down or refuse to write predictions without team names. |
| G-MAINT-12 | Menor | `OddsApiClient.fetch_historical_closing` is a documented stub returning `None` (clv/client.py:115-135). Caller path never triggers a real Pinnacle historical fetch — Phase 02.1 D-01 deferral. | `src/bip/clv/client.py:115-135` | Track in backlog with explicit follow-up plan. |

---

## Hallazgos transversales

### Sincronización planning ↔ código (high friction)

- **REQUIREMENTS.md traceability table is stale (G-MAINT-03).** Phase 1 (CORE-01..05, DATA-01..05, CLV-01..04), Phase 2 (ML-01,04,05), Phase 02.1 (close-gaps), and Phase 3 plans 03-01..08 all marked Pending despite VERIFICATION reports green. Only ML-02/ML-03 were updated.
- **ARCHITECTURE.md prescribes paths that no longer match.** `core/ev_engine.py`, `core/kelly.py`, `core/pipeline.py`, `core/registry.py`, `core/scheduler.py`, `core/health.py`, `core/metrics.py`, `core/claude/augmenter.py` — all referenced as Component Boundaries rows but none of these files exist. Decisions to consolidate are not logged in STATE.md decision list.
- **Phase 3 RESEARCH/PATTERNS list 17 D-* and 7 R-* markers**; some appear in code comments (D-01..D-16) but PATTERNS.md drift-risk numbering (#5, #10, #11, #13, #17) is referenced in code without a single source-of-truth doc.
- **Phase 02.1 had explicit deferred items** ("real PL smoke train") that STATE.md correctly carries but REQUIREMENTS.md does not flag — the table doesn't show "structurally PASS / empirically PENDING".

### Tests presentes pero verificando lo equivocado

- **`tests/scheduler/test_orchestrator.py` uses `AsyncMock` to patch over real method-shape errors.** Methods that don't exist on the production plugin (`get_opening_odds`) and methods that are sync but `await`ed (`get_pending_for_fixture`) appear to work. The tests assert log lines, not behaviour — so the dup-alert guard test passes even though the production guard is structurally broken.
- **`tests/picks/test_engine.py`** likely uses similar mock-Prediction objects that have all the attributes the engine touches. Worth re-reading in isolation: if it constructs a fake object with `home_team`/`league`/`sport`/etc., it's hiding the `ProbabilityMap` mismatch bug (G-MAINT-04). I did not deep-read this file in this audit.
- **Synthetic E2E test for TrainingPipeline** (Plan 02.1-11) asserts WIRING (CLV is float-or-None) but **not values** (no assertion that CLV is non-zero on synthetic data with edge). Acknowledged by Phase 02.1 verification.

### Plans 03-09 / 03-10 / 03-11 — what they DID and DIDN'T deliver

All three are committed (`9e54d92` / `84d66be` and SUMMARY files exist).

- **03-09:** delivers `scripts/corners_gate_probe.md` + `scripts/corners_gate_findings.md` — two **template Markdown files for Kevin to fill in by hand**. The Findings file currently has `_(fill in)_` placeholders. CORNERS-01 Part A (manual probe) is *unstarted at the human level*.
- **03-10:** delivers `corners_gate_coverage.py` (Polars over Phase 02.1 Parquet stores) + `corners_gate_descope.py`. Part B is automated. **But:** depends on real seeded historical odds data which (per Phase 02.1 deferral) does not exist yet. Coverage script will return zero rows on a fresh install.
- **03-11:** delivers `scripts/smoke_e2e_pick.py` + `scripts/smoke_e2e_runbook.md` — manual smoke runner. Has not been executed (no commit evidence; script has `live services` requirement). Will surface G-CODE-01, G-CODE-02, G-MAINT-04 the moment it runs.

**What is left in the air:**
- CORNERS-01 gate decision (Part A still requires human-completed Markdown).
- Phase 3 verification report — `.planning/phases/03-pick-engine-delivery-account-protection/03-VERIFICATION.md` does not exist. Phase 3 was executed but never verified.
- The empirical smoke train from Phase 02.1 (≈1,520 API credits) is still pending and remains a precondition for ML-02/ML-03 to flip to "empirically PASS".

---

## Recomendaciones priorizadas

### P0 — Critical (block Phase 3 closeout)

1. **Fix orchestrator wiring bugs before any live run** (G-CODE-01, G-CODE-02, G-MAINT-04). *Severidad: Crítico. Esfuerzo: M (4-8h).*
   - Add `get_opening_odds(fixture_id) -> dict` to `SportPlugin` and `FootballPlugin`.
   - Make `PickRepository.get_pending_for_fixture` either return Pydantic `Pick` objects or change orchestrator to use `p["market"]` dict access. Decide sync vs async and remove the `await`.
   - Resolve the `ProbabilityMap` ↔ `Prediction` shape mismatch in `engine.evaluate`. Either build a real `Prediction` row in the orchestrator before calling `evaluate`, or shrink the engine's expectations.
   - Replace `AsyncMock` patches in `tests/scheduler/test_orchestrator.py` with concrete fakes that share the production type signatures. **Why:** the smoke runner (03-11) will hit these immediately. The dup-alert guard is silently dead today.

2. **Add vig removal to CLV computation** (G-LOGIC-02). *Severidad: Crítico. Esfuerzo: S (2-4h).*
   - Implement `remove_vig(odds_set: dict) -> dict` returning fair-line probabilities (proportional or Shin or worst-case bookmaker).
   - Update `clv/recorder.calculate_clv_percentage` to compare staked odds against the vig-free closing fair line.
   - Add a test that verifies CLV against a known {1: 1.95, X: 3.40, 2: 4.20} → vig-free probabilities sum to 1.0.
   - **Why:** the entire project's success metric is biased without this. Pitfall 7 explicitly calls it out.

3. **Wire per-market edge thresholds from markets.yaml into `PickEngine.evaluate`** (G-MAINT-01). *Severidad: Crítico. Esfuerzo: S (2-4h).*
   - Engine accepts `threshold` arg; orchestrator looks up `markets.yaml` row by `prediction.market` and passes its `edge_threshold`.
   - Drop the import of `EDGE_THRESHOLD_PCT` from engine module-level (keep in train.backtest for backtest defaults).
   - **Why:** CORE-05 is silently violated; 1X2 picks fire at 5% instead of the documented 8%.

### P1 — Critical (production safety / before live picks)

4. **Implement CLV-03 alert and a daily aggregator** (G-LOGIC-04, G-LOGIC-05, G-CODE-09). *Severidad: Crítico. Esfuerzo: M (1-2 days).*
   - Add `core/metrics.py` with a `daily_performance_aggregator` and a `clv_drift_check`.
   - Register in `PipelineOrchestrator.start()` as cron jobs (06:00 UTC daily; weekly Monday for drift).
   - When rolling 50-pick avg CLV < +1%, push Telegram warning via existing `send_html`.
   - **Why:** ARCHITECTURE.md and REQUIREMENTS both promise this; it's the single safety mechanism for the project's primary metric.

5. **Wire `ClvRecorder.record()` into `_record_clv`** (G-MAINT-06, G-LOGIC-03). *Severidad: Grave. Esfuerzo: S (2-4h).*
   - `_record_clv(fixture)` must fetch Pinnacle closing via `OddsApiClient.fetch_pinnacle_closing_odds`, compute and persist via `ClvRecorder.record(...)`.
   - Decide closing-line timing (kickoff-1min vs kickoff+105min) and document. Pitfall 7 says kickoff.

### P2 — Grave (architectural debt to repay before Phase 4-5)

6. **Reconcile ARCHITECTURE.md vs actual layout** (G-CODE-03..10). *Severidad: Grave. Esfuerzo: M (4-6h).*
   - Either update ARCHITECTURE.md to reflect the consolidated layout (engine + Kelly in `core/picks/`, scheduler at top level), or move modules to match the document.
   - Add the missing PluginRegistry pattern as a one-screen `core/registry.py` to unblock SCALE-01.

7. **Resync REQUIREMENTS.md traceability table** (G-MAINT-03). *Severidad: Grave. Esfuerzo: S (1-2h).*
   - Walk all 30 requirements, set status from VERIFICATION/SUMMARY artifacts.
   - Consider a `gsd-status-sync` script that inspects each plan's `requirements_addressed` frontmatter.

8. **Add Supabase connection pooling** (G-LOGIC-11, G-SCALE-03). *Severidad: Grave. Esfuerzo: S (1-2h).*
   - Switch `supabase_url` to the Supavisor pooled URL; cache the client at module level and inject it (already DI-friendly).
   - Add a fixture-count-vs-connection-count assertion in tests.

### P3 — Moderado / Menor (track in backlog)

9. **Cache Claude verdicts by fixture-id for replayability** (G-LOGIC-08, G-LOGIC-12). *Severidad: Moderado. Esfuerzo: S (2-3h).*
   - Add a `claude_verdicts` table or extend `predictions.claude_*` columns; persist `learnings_sha` alongside.

10. **Static guard against odds-derived feature columns** (G-LOGIC-06). *Severidad: Moderado. Esfuerzo: S (1h).*
    - Add an assertion in `FeatureEngineer.to_parquet_row`: feature names must not match `^opening_|^closing_|^pinnacle_`.

---

## Apéndice: verificaciones que NO pude completar

Items that need additional context or longer investigation:

- **`tests/picks/test_engine.py`** — I did not deep-read this file. It very likely constructs fake Prediction objects with all the fields the engine touches, hiding G-MAINT-04. Worth re-reading in isolation to confirm.
- **Migration 004** — referenced repeatedly (idx_picks_sport_market_created; widens picks_status_check; adds claude_validation/reasoning/summary/validated_at columns) but I did not open the SQL file. Should verify it actually creates `idx_picks_sport_market_created` (relied on by `get_window_picks`).
- **`scripts/seed_historical.py`** — has been touched extensively in Phase 02.1; I did not check whether `--seasons --leagues` argparse matches the documented invocation in `02.1-VERIFICATION.md` line 30.
- **`features.py` H2H/Elo/motivation features** — I confirmed `as_of_date`/`computed_at` plumbing exists but did not inspect every per-feature implementation. A spot-check of `_pressing_tactical` and `_h2h` would catch any Pitfall 4 #1 ("aggregate season stats including target") sneaking through.
- **Phase 3 `03-VERIFICATION.md` does not exist** — Phase 3 has not been formally verified, so this audit fills only part of that role. A full `/gsd-verify-work` pass is recommended before declaring Phase 3 complete.
- **Empirical smoke train results** — referenced as Phase 02.1's deferred work; status unchanged since 2026-04-30. ~1,520 API-Football Pro credits would convert ML-02/ML-03 from structural-PASS to empirical-PASS.

---

_End of audit._
