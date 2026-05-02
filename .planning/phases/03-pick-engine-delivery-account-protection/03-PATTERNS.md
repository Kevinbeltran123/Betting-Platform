# Phase 3: Pick Engine + Delivery + Account Protection — Pattern Map

**Mapped:** 2026-05-02
**Files analyzed:** 18 NEW + 6 EXTEND + 1 PORT = 25 total
**Analogs found:** 22 / 25 (3 GREENFIELD — Anthropic SDK + python-telegram-bot + Jinja2 introduce new dependency surfaces, but ALL re-use the established `@dataclass(client)` / `from __future__ import annotations` / `structlog.get_logger(__name__)` / pydantic-settings extension / atomic-write conventions)

---

## File → Analog Reference Table

| New / Modified File | Role | Data-flow Position | Closest Analog | Pattern to Replicate |
|---|---|---|---|---|
| `src/bip/core/types.py` *(EXTEND)* | enum / domain types | configuration | `src/bip/core/types.py:16` (existing `PickStatus(StrEnum)`) | Add 2 enum members `filtered = "filtered"`, `rejected = "rejected"` — preserve `StrEnum` base + lowercase string values + alphabetically grouped block |
| `src/bip/core/storage/models.py` *(EXTEND `Pick`)* | pydantic data model | persistence | `src/bip/core/storage/models.py:46` (existing `Pick` BaseModel) | Add 4 optional fields with `\| None = None` default; extend `to_supabase_dict()` (model_dump + status.value); preserve `model_config = ConfigDict(extra="ignore")` |
| `src/bip/core/storage/repositories.py` *(EXTEND `PickRepository`)* | repository | persistence | `src/bip/core/storage/repositories.py:96` (existing `PickRepository`, lines 95–144) | Add `get_window_picks(sport, hours)`, `update_status_by_fixture`, `get_pending_for_fixture`, `query_pending_sends` — every method is `try/except Exception → raise StorageError(...) from e` |
| `src/bip/core/settings.py` *(EXTEND)* | settings (pydantic-settings) | configuration | `src/bip/core/settings.py:1-22` | Add `telegram_channel_id: str = ""`, `anthropic_api_key: str = ""`, `claude_model: str = "claude-sonnet-4-6"`, `max_kelly_fraction: float = 0.25` — keep flat field-list style (NO Config nesting); existing `telegram_bot_token` already present |
| `src/bip/core/picks/__init__.py` *(NEW)* | package init | configuration | `src/bip/clv/__init__.py` / `src/bip/scheduler/__init__.py` | One-line module docstring + re-export of `PickEngine` |
| `src/bip/core/picks/engine.py` *(NEW)* | orchestration class | processing core | `src/bip/clv/recorder.py:60-129` (`ClvRecorder` class) + `src/bip/scheduler/orchestrator.py:24-67` (`PipelineOrchestrator` __init__ + start) | Class with `__init__(self, pick_repo, validator, scheduler, sender, settings)`; async `evaluate(prediction, opening_odds) -> Pick \| None`; structlog `logger.info("pick_evaluated", fixture_id=..., decision=...)` |
| `src/bip/core/picks/account_longevity.py` *(NEW)* | pure-function utility | processing core | `src/bip/train/backtest.py:1-58` (free-functions module with module-level constants + numpy ops) + `src/bip/clv/recorder.py:22-57` (free `calculate_clv_percentage` + `compute_rolling_clv_average`) | Module-level pure functions: `deterministic_jitter`, `quarter_kelly_units`, `round_to_nearest_half_unit`, `deterministic_send_at`, `exceeds_60pct_cap`. NO classes. `from __future__ import annotations`. Module docstring cites D-10/D-11 + Pitfall 1 (md5 vs `hash()`) |
| `src/bip/core/claude/__init__.py` *(NEW)* | package init | configuration | `src/bip/clv/__init__.py` | One-line docstring |
| `src/bip/core/claude/validator.py` *(NEW)* | external API client / validator | input boundary | `src/bip/clv/client.py:37-90` (`OddsApiClient` async wrapper with retry) + research §B (anthropic AsyncAnthropic with strict tool_use) | `__init__(api_key, model, learnings_text, learnings_sha)` storing `_client = AsyncAnthropic(api_key=..., max_retries=2)`; `async def validate(...) -> ClaudeVerdict \| None`; D-07 retry loop = `for attempt in range(2): try: ... except (RateLimitError, APIError): ... if attempt == 0: await asyncio.sleep(60)`. structlog `logger.info("claude_validator_success", cache_read=...)`. `ClaudeVerdict` is a `pydantic.BaseModel` co-located in this file |
| `src/bip/core/claude/learnings_loader.py` *(NEW)* | resource loader | input boundary | `src/bip/sports/football/config/league_registry.py` (yaml registry loader, `Path(__file__).parent / "config"` style) + `src/bip/train/registry.py:78-88` (atomic write + `Path.replace`) | `class LearningsLoader` OR module-level `load_learnings() -> tuple[str, str]` (text, git_sha). Use `subprocess.run(["git", "log", "-1", "--format=%H", str(path)])` with `capture_output=True`; fallback to `hashlib.sha256(text.encode()).hexdigest()[:16]` when not a git repo / file uncommitted (Risks & Landmines item 5) |
| `src/bip/core/claude/prompts/football-learnings.md` *(PORT)* | static asset | input boundary | none in repo (greenfield) — port verbatim from `Claude_Sport_Betting/learnings/football-learnings.md` | Copy file unchanged (Spanish content preserved per D-05). Path mirrors `src/bip/sports/football/config/leagues/*.yaml` package-data layout |
| `src/bip/core/telegram/__init__.py` *(NEW)* | package init | configuration | `src/bip/clv/__init__.py` | One-line docstring; re-export `TelegramBot`, `TelegramSender` |
| `src/bip/core/telegram/bot.py` *(NEW)* | external API client | output boundary | `src/bip/sports/football/client.py:33-90` (async client + context manager) + research §A | `class TelegramBot` with `__init__(self, token: str, channel_id: str)`; builds `Application` via `ApplicationBuilder().token(token).rate_limiter(AIORateLimiter(max_retries=3)).build()`; `async def start()` calls `initialize()` + `start()` (NO `updater.start_polling()`); `async def shutdown()` + `async def send_html(text)`. structlog event names: `telegram_bot_started`, `telegram_send_success`, `telegram_retry_after` |
| `src/bip/core/telegram/sender.py` *(NEW)* | template-rendering service | output boundary | research §G (jinja2 sender) + `src/bip/sports/football/features.py` (free-function helpers) | Module-level `env = Environment(loader=PackageLoader("bip.core.telegram", "templates"), autoescape=select_autoescape(["html"]), trim_blocks=True, lstrip_blocks=True)`; `def render_pick(pick: Pick) -> str`; `class TelegramSender` taking `bot: TelegramBot` with `async def send_pick(pick: Pick) -> None` that renders + calls `bot.send_html` |
| `src/bip/core/telegram/templates/pick.html` *(NEW)* | Jinja2 template (HTML) | output boundary | none — first template in repo | Plain Jinja2 with `{# comments #}` referring to D-12/D-14/D-15 + length budget; `\| e` escape on every `pick.*` substitution; `WARNING` emoji prefix only for `pick.claude_validation == "FLAG"`; `{% for bullet in summary_bullets[:3] %}` capped at 3 |
| `src/bip/scheduler/orchestrator.py` *(EXTEND)* | scheduler integration | orchestration | `src/bip/scheduler/orchestrator.py:118-157` (`_register_fixture_jobs`) + `:159-172` (`_run_pipeline`) | Add `_register_reconciliation(fixture, now)` helper using `DateTrigger(run_date=kickoff + timedelta(minutes=150))`, `id=f"reconcile_{fixture.fixture_id}"`, `replace_existing=True`, `misfire_grace_time=600` (Pitfall 7). Add `async def _reconcile_results(fixture)` (research §C). Extend `_run_pipeline` to call `await self.pick_engine.evaluate(...)` after `plugin.predict()` at `t_minus_2h` / `t_minus_30m`. Extend `_auto_recover` per Pitfall 6 to re-queue `pending` picks < 30 min old without scheduled send job |
| `supabase/migrations/20260502000000_add_claude_validation_to_picks.sql` *(NEW)* | migration | persistence | `supabase/migrations/20260423000000_add_is_shadow.sql` (single `ALTER ... ADD COLUMN IF NOT EXISTS`) + `supabase/migrations/20260101000000_base_schema.sql:60-67` (current `picks_status_check` constraint) + research §E | Wrap in `BEGIN; ... COMMIT;` (Pitfall 5); `ALTER TABLE picks ADD COLUMN IF NOT EXISTS claude_validation VARCHAR(10), ADD COLUMN IF NOT EXISTS claude_reasoning TEXT, ADD COLUMN IF NOT EXISTS claude_summary VARCHAR(120), ADD COLUMN IF NOT EXISTS claude_validated_at TIMESTAMPTZ;` then `DROP CONSTRAINT IF EXISTS picks_status_check; ADD CONSTRAINT picks_status_check CHECK (status IN (..., 'filtered', 'rejected'));` then `CREATE INDEX IF NOT EXISTS idx_picks_sport_market_created` for D-09. Header comment cites D-08 + D-03 + Pitfall 5 |
| `scripts/verify_migration_004.sql` OR `.py` *(NEW)* | verification utility | persistence (read-only) | `scripts/verify_migration_003.py:1-107` | If keeping `.py`: copy verify_migration_003.py shape verbatim — `derive_db_url`, `psycopg.connect(db_url)`, parameterized `information_schema.columns` query for the 4 new columns + `pg_get_constraintdef` query for `picks_status_check`; `print("OK: ...")` on success, return code 1 on fail. If `.sql`: emit a read-only script Kevin runs in psql/Supabase SQL editor mirroring research §E verification block |
| `scripts/corners_gate_probe.md` *(NEW manual checklist)* | manual artifact / checklist | input boundary (data-deficit gate) | none in repo (greenfield) — recommend mirroring `.planning/phases/02.1-.../*-CONTEXT.md` markdown-section style | Plain markdown `## Checklist` with `- [ ]` boxes per league × per market window; `## Findings template` block Kevin fills in pointing to `corners_gate_findings.md` |
| `scripts/corners_gate_findings.md` *(NEW template)* | manual artifact | input boundary | none — paired with the probe checklist | Markdown skeleton: `## Premier League / La Liga / Bundesliga / Serie A / Ligue 1` headers with sub-bullets (markets seen, odds range, min stake, exact naming) |
| `scripts/corners_gate_coverage.py` *(NEW)* | one-shot Polars script | input boundary | `scripts/seed_historical.py` (CLI script importing Settings + ParquetStore) + research §D | `from __future__ import annotations`; module-level `LEAGUES`, `COVERAGE_THRESHOLD`, `MIN_SEASONS`, `CORNER_TIMING_COLS` constants; `compute_coverage(store) -> pl.DataFrame`; `gate_decision(df) -> tuple[bool, str]`; `main()` writes `scripts/corners_gate_coverage.md` via atomic write (`Path.with_suffix(".md.tmp").write_text(md); tmp.replace(out)`); `raise SystemExit(0 if passed else 1)`; `if __name__ == "__main__": main()` |
| `scripts/corners_gate_descope.py` *(NEW, sister of coverage)* | one-shot orchestration script | output boundary | `scripts/verify_migration_003.py:51-103` (single-purpose CLI with sys.exit) + D-18 spec | Reads outcome of coverage script + manual probe; runs `gsd-sdk query roadmap.move-phase`; appends STATE.md Blockers entry via atomic write; produces a single git commit. structlog events: `corners_gate_descope_started`, `corners_gate_artifacts_written` |
| `tests/picks/__init__.py` + `tests/picks/test_account_longevity.py` *(NEW)* | unit tests | (test) | `tests/test_clv_recorder.py:1-95` (TestClvCalculation pure-function tests) + `tests/test_backtest_simulate_pick.py` | Class-grouped tests (`TestQuarterKelly`, `TestDeterministicJitter`, `TestMarketCap`); `from bip.core.picks.account_longevity import ...` imported INSIDE each test fn (matches existing project convention). Subprocess test for D-10 stability (Pitfall 1) via `subprocess.run(["python", "-c", "..."], env={"PYTHONHASHSEED": "0"})` |
| `tests/picks/test_engine.py` *(NEW)* | integration tests | (test) | `tests/test_clv_recorder.py:29-47` (mock-based ClvRecorder.record test) + `tests/conftest.py:46-69` (`mock_client` + `setup_mock_chain`) | Use existing `mock_client` fixture; mock the validator + sender via `unittest.mock.AsyncMock`; assert `pick_repo.insert` called with `status='filtered' \| 'rejected' \| 'pending'` per branch |
| `tests/claude/__init__.py` + `tests/claude/test_validator.py` + `tests/claude/test_learnings_loader.py` *(NEW)* | unit tests with AsyncMock | (test) | `tests/test_clv_client.py` (async client with mocked HTTP) + `tests/test_scheduler.py:1-78` (AsyncMock pattern) | Mock `AsyncAnthropic` with `unittest.mock.AsyncMock`; assert tool_choice / strict / cache_control wiring; for D-07 use `side_effect=[APIError(...), APIError(...)]` then assert `await asyncio.sleep` was awaited with `60` (use `monkeypatch` on `asyncio.sleep`) |
| `tests/telegram/__init__.py` + `tests/telegram/test_bot.py` + `tests/telegram/test_sender.py` *(NEW)* | unit tests | (test) | `tests/test_scheduler.py` + `tests/test_apifootball_get_odds.py` (httpx-mock pattern) | `test_bot.py` asserts `_app._rate_limiter is not None`, asserts `updater.start_polling` is NEVER called; `test_sender.py` asserts HTML escape of `<script>` in team name |
| `tests/scheduler/test_reconcile.py` *(NEW)* | unit tests | (test) | `tests/test_scheduler.py:9-78` | Mock `ApiFootballClient.get_fixture` returning `status: "FT"` → assert `pick_repo.update_status` called with `"won"`/`"lost"`; `status: "2H"` → assert `scheduler.add_job` called again with new DateTrigger 30 min in future |
| `tests/scripts/__init__.py` + `tests/scripts/test_corners_gate_*.py` *(NEW)* | unit / structural tests | (test) | `tests/test_seed_checkpoint.py` (script-level test pattern) | `test_probe_md_structure` reads `scripts/corners_gate_probe.md`, asserts presence of required `##` headers; `test_coverage_threshold_logic` injects synthetic `pl.DataFrame` and asserts pass/fail decision |
| `tests/conftest.py` *(EXTEND)* | shared fixtures | (test) | `tests/conftest.py:35-69` (existing `settings` + `mock_client` + `setup_mock_chain`) | Add `mock_anthropic_client` fixture returning canned `ClaudeVerdict`; add `mock_telegram_bot` fixture (records `send_message` calls). Extend `settings` fixture's `monkeypatch.setenv` block with `TELEGRAM_CHANNEL_ID="-1001234567890"`, `ANTHROPIC_API_KEY="test-anthropic"`, `CLAUDE_MODEL="claude-sonnet-4-6"` |

---

## Greenfield Files (no analog — flag for planner judgment)

These files introduce new technologies / file types not yet present in the repo. Layouts below match the closest existing convention.

1. **`src/bip/core/telegram/templates/pick.html`** — first Jinja2 template in the repo.
   *Suggested layout:* `src/bip/core/telegram/templates/pick.html` (mirrors `src/bip/sports/football/config/leagues/*.yaml` package-data convention — assets live next to the module that loads them so `PackageLoader("bip.core.telegram", "templates")` resolves cleanly).

2. **`src/bip/core/claude/prompts/football-learnings.md`** — first markdown asset shipped inside the `bip` package (existing markdown lives only in `.planning/`).
   *Suggested layout:* `src/bip/core/claude/prompts/football-learnings.md`. Loader uses `Path(__file__).parent / "prompts" / "football-learnings.md"` (same idiom as `_LEAGUES_DIR = Path(__file__).parent / "config" / "leagues"` in `src/bip/sports/football/plugin.py:40`).

3. **`scripts/corners_gate_probe.md`** + **`scripts/corners_gate_findings.md`** — first hand-edited markdown checklists living under `scripts/` (existing scripts/ contains only `.py`).
   *Suggested layout:* keep as `.md` siblings of `corners_gate_coverage.py` so the manual + automated halves of the gate live together. Cross-reference each other in their `## Companion Files` section.

---

## Code Excerpts to Replicate

### 1. `src/bip/core/storage/repositories.py:27-44` — `@dataclass(client: Client)` repository pattern

```python
@dataclass
class PredictionRepository:
    """Repository for the predictions table."""

    client: Client

    def insert(self, prediction: Prediction) -> dict:
        """Insert a prediction and return the created record."""
        try:
            response = (
                self.client.table("predictions")
                .insert(prediction.to_supabase_dict())
                .execute()
            )
            return response.data[0]
        except Exception as e:
            raise StorageError(f"Failed to insert into predictions: {e}") from e
```
**Use this for:** every new method on `PickRepository` (`get_window_picks`, `update_status_by_fixture`, `get_pending_for_fixture`, `query_pending_sends`).
**What to copy:** `@dataclass`, single `client: Client` field, `try/except Exception → raise StorageError(...) from e`, fluent-chain style, `.execute().data` access pattern.
**What to change:** the `.table(...)` name + the method body's specific filters (e.g., `.gte("created_at", iso_str).eq("sport", sport)` for the rolling-168h window).

---

### 2. `src/bip/core/storage/models.py:46-75` — `Pick` model + `to_supabase_dict()`

```python
class Pick(BaseModel):
    model_config = ConfigDict(extra="ignore")

    prediction_id: int | None = None
    fixture_id: int
    league: str
    sport: str = "football"
    market: str
    selection: str
    model_probability: float
    implied_probability: float
    edge: float
    best_odds: float
    bookmaker: str
    kelly_fraction: float | None = None
    suggested_stake: float | None = None
    status: PickStatus = PickStatus.pending

    def to_supabase_dict(self) -> dict:
        data = self.model_dump()
        data["status"] = self.status.value
        return data
```
**Use this for:** the `Pick` model EXTENSION (D-08 adds claude_*).
**What to copy:** `model_config = ConfigDict(extra="ignore")`, `\| None = None` defaults, enum `.value` serialization, `model_dump()` first then mutate.
**What to change:** add 4 fields:
```python
    claude_validation: str | None = None      # CONFIRM | FLAG | REJECT | SKIPPED | None
    claude_reasoning: str | None = None
    claude_summary: str | None = None
    claude_validated_at: datetime | None = None
```
And in `to_supabase_dict`: `if self.claude_validated_at is not None: data["claude_validated_at"] = self.claude_validated_at.isoformat()`.

---

### 3. `src/bip/scheduler/orchestrator.py:118-157` — `add_job(DateTrigger)` per fixture

```python
def _register_fixture_jobs(self, fixture: object, now: datetime) -> None:
    kickoff = fixture.kickoff_utc
    fixture_id = fixture.fixture_id

    t_minus_2h = kickoff - timedelta(hours=2)
    if t_minus_2h > now:
        self.scheduler.add_job(
            self._run_pipeline,
            trigger=DateTrigger(run_date=t_minus_2h),
            args=[fixture, "t_minus_2h"],
            id=f"pipeline_{fixture_id}_t_minus_2h",
            replace_existing=True,
        )
```
**Use this for:**
- the new `_register_reconciliation` helper (`kickoff + timedelta(minutes=150)`, `id=f"reconcile_{fixture_id}"`, **add `misfire_grace_time=600`** per Pitfall 7);
- the dynamic `add_job` call inside `PickEngine.evaluate()` for the send job (`id=f"send_pick_{pick.fixture_id}_{pick.market}"`, **add `misfire_grace_time=300`**, `replace_existing=True` for D-11 idempotency).

**What to copy:** the `if t_minus_X > now:` guard against past-dated triggers, deterministic job IDs, `replace_existing=True`.
**What to change:** the trigger time (kickoff + 150min for reconcile; deterministic-from-seed `send_at` for send), the callable, and add `misfire_grace_time` per the Pitfall.

---

### 4. `src/bip/scheduler/orchestrator.py:1-21` — module imports + structlog/pydantic conventions

```python
"""APScheduler 3.x pipeline orchestrator.

CRITICAL: Uses APScheduler 3.x API (AsyncIOScheduler + add_job).
Do NOT use 4.x API (AsyncScheduler + add_schedule) — APScheduler 4.x is still alpha.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import structlog
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger

from bip.core.errors import SchedulerError
from bip.core.settings import Settings
from bip.sports import SportPlugin

logger = structlog.get_logger(__name__)
```
**Use this for:** every new `.py` file in Phase 3 (`engine.py`, `account_longevity.py`, `validator.py`, `learnings_loader.py`, `bot.py`, `sender.py`, `corners_gate_coverage.py`, `corners_gate_descope.py`).
**What to copy verbatim:**
- Module docstring with CRITICAL hazard call-out where applicable (e.g., for `account_longevity.py`: "CRITICAL: Use hashlib.md5 NOT Python `hash()` — PYTHONHASHSEED salt").
- `from __future__ import annotations` as the FIRST statement after the docstring.
- Import ordering: stdlib → third-party (with blank line) → first-party (`bip.*`) (with blank line).
- `import structlog` then `logger = structlog.get_logger(__name__)` after all imports.
- `datetime` import: `from datetime import UTC, datetime, timedelta` (not `timezone.utc` — repo uses `UTC` alias).

---

### 5. `src/bip/clv/recorder.py:60-129` — service class with `__init__(self, client)` + structlog event logging

```python
class ClvRecorder:
    """Records CLV measurements to Supabase.

    Uses ClvRecordRepository for all database interactions.
    Captures odds_fetched_at timestamp for data-freshness monitoring (D-04c).
    """

    def __init__(self, client: Client) -> None:
        self._repo = ClvRecordRepository(client=client)

    def record(self, pick_id: int, ...) -> ClvRecord:
        ...
        try:
            self._repo.insert(clv_record)
        except Exception as exc:
            raise ClvError(f"Failed to record CLV for pick_id={pick_id}: {exc}") from exc

        logger.info(
            "clv_recorded",
            pick_id=pick_id,
            fixture_id=fixture_id,
            market=market,
            odds_at_pick=odds_at_pick,
            ...
        )
        return clv_record
```
**Use this for:** `PickEngine` (constructor takes repo + collaborators; `evaluate()` logs every decision branch with structured kwargs; raises a domain error on persistence failure).
**What to copy:** structlog event names as snake_case past-tense verbs (`pick_evaluated`, `pick_filtered`, `pick_rejected`, `pick_sent`); always include `fixture_id` + `market` as the first two log kwargs; raise `StorageError` not generic `Exception`.
**What to change:** the collaborator signature (PickEngine takes 5 deps, not 1) and the event names.

---

### 6. `src/bip/sports/football/client.py:33-65` — async client lifecycle (init / aclose / context manager)

```python
class ApiFootballClient:
    def __init__(self, api_key: str) -> None:
        self._client = httpx.AsyncClient(
            base_url=BASE_URL,
            headers={"x-apisports-key": api_key},
            timeout=httpx.Timeout(30.0),
        )

    async def __aenter__(self) -> ApiFootballClient:
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._client.aclose()
```
**Use this for:** `TelegramBot` (init builds the `Application`, `start()` initializes/starts, `shutdown()` stops/shuts down). The `ClaudeValidator` does NOT need this pattern — `AsyncAnthropic` manages its own httpx pool internally.
**What to copy:** stash the client on `self._<name>`; explicit lifecycle methods; never reach into `self._client.*` from callers.
**What to change:** for `TelegramBot`, replace `httpx.AsyncClient` with `ApplicationBuilder().token(token).rate_limiter(AIORateLimiter(max_retries=3)).build()`; lifecycle methods are `start()/shutdown()` (not `__aenter__/__aexit__`) because the bot is owned by the orchestrator for the entire process lifetime.

---

### 7. `src/bip/train/registry.py:78-88` — atomic file write

```python
def save(self) -> None:
    """Atomic write: .tmp then Path.replace()."""
    try:
        self.registry_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.registry_path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(self.data, indent=2, sort_keys=True))
        tmp.replace(self.registry_path)
    except Exception as e:
        raise StorageError(
            f"Failed to write registry {self.registry_path}: {e}"
        ) from e
```
**Use this for:**
- `scripts/corners_gate_coverage.py` writing `corners_gate_coverage.md`;
- `scripts/corners_gate_descope.py` writing the STATE.md Blockers entry;
- ANY future on-disk artifact emission in this phase.
**What to copy:** `parent.mkdir(parents=True, exist_ok=True)` first, write to `.tmp` sibling, `tmp.replace(target)`, wrap in `try/except → raise StorageError`.
**What to change:** the file extension on `.tmp` (`.md.tmp` for markdown).

---

### 8. `src/bip/clv/client.py:37-90` — async API client with tenacity retry

```python
class OddsApiClient:
    def __init__(self, api_key: str) -> None:
        self._api_key = api_key
        self._client = httpx.AsyncClient(base_url=self.BASE_URL, timeout=httpx.Timeout(30.0))

    async def __aenter__(self) -> "OddsApiClient": return self
    async def __aexit__(self, *_: object) -> None: await self.aclose()
    async def aclose(self) -> None: await self._client.aclose()

    @retry(
        retry=retry_if_exception(_is_retryable_http_error),
        wait=wait_exponential(multiplier=1, min=2, max=60),
        stop=stop_after_attempt(3),
        reraise=True,
    )
    async def fetch_pinnacle_closing_odds(self, ...) -> dict | None:
        ...
```
**Use this for:** `ClaudeValidator` (similar shape but D-07 specifies a hand-rolled 2-attempt loop with 60-second sleep — do NOT use tenacity for the OUTER loop because D-07's retry semantics differ from exponential backoff. The inner SDK-level retry is handled by `AsyncAnthropic(max_retries=2)`).
**What to copy from this analog:** the import grouping (`from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential`), the `_is_retryable_http_error` predicate name style.
**What to NOT copy:** the `@retry(...)` decorator on the public method — D-07 mandates hand-rolled `for attempt in range(2)` loop with `await asyncio.sleep(60)`.

---

### 9. `supabase/migrations/20260423000000_add_is_shadow.sql` (full file) — idempotent migration shape

```sql
-- Migration 003: Add is_shadow for ML-05 shadow-mode prediction logging
-- MUST be applied BEFORE any shadow prediction write (RESEARCH.md anti-pattern warning).

ALTER TABLE predictions
    ADD COLUMN IF NOT EXISTS is_shadow BOOLEAN NOT NULL DEFAULT false;

-- Index for production-only reads (Phase 3 pick engine reads is_shadow=false)
CREATE INDEX IF NOT EXISTS idx_predictions_is_shadow ON predictions (is_shadow);
```
**Use this for:** migration 004's overall shape — header comment block citing the requirement (D-08, D-03), `IF NOT EXISTS` everywhere, no DROP without `IF EXISTS` guard.
**What to copy:** the `-- Migration NNN: <one-line summary>` header; the `MUST be applied BEFORE ...` warning if there is a write-path dependency; `CREATE INDEX IF NOT EXISTS` after column adds.
**What to ADD beyond this analog:** `BEGIN;` / `COMMIT;` wrapper (Pitfall 5 — atomic CHECK constraint widening); `DROP CONSTRAINT IF EXISTS picks_status_check; ADD CONSTRAINT picks_status_check CHECK (status IN (..., 'filtered', 'rejected'));` block.

---

### 10. `scripts/verify_migration_003.py:51-103` — verification script shape

```python
def main() -> int:
    settings = Settings()
    db_password = os.environ.get("SUPABASE_DB_PASSWORD")
    if not db_password:
        print("FAIL: SUPABASE_DB_PASSWORD not set in environment")
        return 1

    db_url = derive_db_url(settings.supabase_url, db_password)
    sanitized_host = db_url.rsplit("@", 1)[-1]   # WR-02: never log password

    try:
        with psycopg.connect(db_url) as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT column_name, data_type, is_nullable, column_default "
                "FROM information_schema.columns "
                "WHERE table_name=%s AND column_name=%s",
                ("predictions", "is_shadow"),
            )
            ...
```
**Use this for:** `scripts/verify_migration_004.py` (or `.sql`) — reuses `derive_db_url`, password handling, parameterized queries, structlog event + `print("OK: ...")` pattern.
**What to copy verbatim:** the `derive_db_url` function (lines 32-48), the `sanitized_host` rsplit guard (T-02.1-02 + WR-02), all `cur.execute(query, params)` parameterization (T-02.1-03 — no f-strings).
**What to change:** the four column names checked (`claude_validation`, `claude_reasoning`, `claude_summary`, `claude_validated_at`) plus a `pg_get_constraintdef` query for `picks_status_check` confirming the widened enum.

---

### 11. `tests/conftest.py:35-69` — fixture conventions

```python
@pytest.fixture
def settings(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://test.supabase.co")
    monkeypatch.setenv("SUPABASE_KEY", "test-supabase-key-12345")
    monkeypatch.setenv("API_FOOTBALL_KEY", "test-api-football-key")
    monkeypatch.setenv("ODDS_API_KEY", "test-odds-api-key")
    from bip.core.settings import Settings
    return Settings()


@pytest.fixture
def mock_client() -> MagicMock:
    """Supabase client mock with fluent API chain support."""
    client = MagicMock()
    return client


def setup_mock_chain(client: MagicMock, data: list | None = None) -> MagicMock:
    """Set up fluent Supabase method chain to return given data."""
    ...
    builder.insert.return_value = builder
    builder.select.return_value = builder
    builder.update.return_value = builder
    builder.upsert.return_value = builder
    builder.eq.return_value = builder
    builder.order.return_value = builder
    builder.limit.return_value = builder
    client.table.return_value = builder
    return builder
```
**Use this for:** extending `tests/conftest.py` with Phase 3 fixtures.
**What to copy:** `monkeypatch.setenv` then `from ... import Settings; return Settings()` (defer import after env mutation); `setup_mock_chain` helper for chained `.eq().gte().execute()` sequences in `test_account_longevity.py::test_market_cap`.
**What to add:**
- `mock_anthropic_client` fixture: `client = MagicMock(); client.messages.create = AsyncMock(return_value=...)` returning a fake `Message` object whose `content[0]` has `.type == "tool_use"` and `.input == {...}`.
- `mock_telegram_bot` fixture: `bot = MagicMock(); bot.send_html = AsyncMock(); return bot` and assert `bot.send_html.await_args` in tests.
- Extend the `settings` fixture with `monkeypatch.setenv("TELEGRAM_CHANNEL_ID", "-1001234567890")`, `("ANTHROPIC_API_KEY", "test-anthropic-key")`, `("CLAUDE_MODEL", "claude-sonnet-4-6")`.

---

### 12. `src/bip/train/backtest.py:1-58` (full file) — pure-function module convention

```python
"""Walk-forward CLV backtest math -- ML-02.

CLV staked odds MUST use opening odds x (1 - slippage_pct), NOT closing odds.
Retrofitting closing-odds CLV later invalidates every earlier backtest result.
"""

from __future__ import annotations

import numpy as np

SLIPPAGE_PCT: float = 0.015          # 1.5% -- mid-range of 1-2% spec (ML-02)
EDGE_THRESHOLD_PCT: float = 0.05     # D-10 — Phase 3 pick engine imports this


def simulate_pick(
    model_probs: np.ndarray,
    opening_odds: np.ndarray,
    threshold: float = EDGE_THRESHOLD_PCT,
) -> int | None:
    ...
```
**Use this for:** `src/bip/core/picks/account_longevity.py` (free functions, no class, module-level constants with type-annotated assignment + decision-ID comment).
**What to copy verbatim:**
- Module docstring with CRITICAL hazard line at the top (for account_longevity: "CRITICAL: Use hashlib.md5 — NOT Python's `hash()` (salted by PYTHONHASHSEED).").
- `from __future__ import annotations` first import.
- Module-level constants annotated `NAME: type = value  # decision-ID — context`.
- Functions take primitive args, return primitives or `None`.
- NEVER duplicate `EDGE_THRESHOLD_PCT` or `simulate_pick` — IMPORT them: `from bip.train.backtest import EDGE_THRESHOLD_PCT, simulate_pick` (D-02 explicitly forbids re-implementation).

---

### 13. `src/bip/sports/football/plugin.py:40` — package-data path idiom

```python
_LEAGUES_DIR = Path(__file__).parent / "config" / "leagues"
```
**Use this for:** `src/bip/core/claude/learnings_loader.py`:
```python
_LEARNINGS_PATH = Path(__file__).parent / "prompts" / "football-learnings.md"
```
**What to copy:** module-private constant (leading underscore), `Path(__file__).parent` anchor, no string concatenation with `os.path.join`.

---

## Project Conventions Detected

1. **`from __future__ import annotations`** — first import after the docstring in EVERY `.py` file. (Verified across `src/bip/scheduler/orchestrator.py`, `src/bip/core/storage/repositories.py`, `src/bip/sports/football/client.py`, `src/bip/sports/football/plugin.py`, `src/bip/train/backtest.py`.)

2. **`structlog.get_logger(__name__)`** initialised once at module level after imports; event names are `snake_case_past_tense` (`pipeline_started`, `clv_recorded`, `fixture_parse_failed`, `predict_cold_start`); first kwargs are always identifiers (`fixture_id`, `pick_id`, `league`).

3. **Domain errors live in `bip.core.errors`** — `StorageError`, `ClvError`, `ApiError`, `SchedulerError`, `ConfigurationError`, `DataValidationError`. **Add NEW errors here**, do not pepper modules with bespoke exceptions. Phase 3 needs: `PickError(Exception)`, `ClaudeError(Exception)`, `TelegramError(Exception)`. The pattern is `class XError(Exception): """one-line docstring."""` (see `src/bip/core/errors.py:1-26`).

4. **`@dataclass` for repositories** holding a `client: Client` — every persistence-layer class is `@dataclass(client: Client)` (8 instances in `src/bip/core/storage/repositories.py`).

5. **`try/except Exception → raise <Domain>Error(f"...: {e}") from e`** — the standard wrap-and-rethrow idiom (8x in `repositories.py`, 1x in `recorder.py`, 1x in `train/registry.py`).

6. **`to_supabase_dict()` on every storage model** — `model_dump()` first, then mutate (enum `.value`, datetime `.isoformat()`).

7. **`pydantic-settings` Settings class is FLAT** — single `Settings(BaseSettings)` with `model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")`; new fields appended to the existing class (no namespacing, no per-feature settings classes).

8. **Polars (NOT pandas) for ALL DataFrame work** — verified `polars==1.40.1` in pyproject; `pandas` is NOT a runtime dep. The CORNERS-01 coverage script must use Polars (`pl.col`, `pl.len`, `pl.scan_parquet`).

9. **Atomic writes via `tmp.write_text(...); tmp.replace(target)`** — `src/bip/train/registry.py:78-88` is the canonical example; reuse for `corners_gate_*.md`.

10. **APScheduler 3.x ONLY** — `from apscheduler.schedulers.asyncio import AsyncIOScheduler` + `from apscheduler.triggers.{cron,date} import CronTrigger, DateTrigger`. NEVER `apscheduler.AsyncScheduler` or `apscheduler.add_schedule` (4.x alpha).

11. **`UTC` alias from datetime** — `from datetime import UTC, datetime, timedelta`; `datetime.now(UTC)` (NOT `datetime.utcnow()`, NOT `timezone.utc`). 4 occurrences across orchestrator, recorder, models, plugin.

12. **Async context managers for I/O clients** — `async with ApiFootballClient(...) as client:` pattern (plugin.py:84). Use this idiom for any new short-lived async client; `TelegramBot` is the exception (long-lived for process lifetime → explicit `start()/shutdown()`).

13. **Tests import-inside-function** — every test method does `from bip.<module> import <symbol>` INSIDE the function body, not at module top. Verified across `tests/test_clv_recorder.py:13`, `tests/test_scheduler.py:14,22,49`. Reasons: per-test monkeypatch of env vars before import; isolated import errors per test.

14. **Tests use `MagicMock()` + fluent-chain `setup_mock_chain` helper for Supabase**; `unittest.mock.AsyncMock` for async coroutines. Verified `tests/test_scheduler.py:9` (`MagicMock`, `AsyncMock`).

15. **Decision-ID comments** — every non-obvious choice is annotated with the source decision: `# D-10 — Phase 3 pick engine imports this`, `# WR-02: ...`, `# CR-01: ...`. Mirror this in every Phase 3 file: `# D-10`, `# Pitfall 1`, `# CLAUDE-01`, etc.

16. **Test files live FLAT under `tests/`** as `tests/test_<thing>.py` (verified — 28 files, no subdirectory layer in current state). RESEARCH.md proposes `tests/picks/`, `tests/claude/`, `tests/telegram/`, `tests/scheduler/`, `tests/scripts/` subdirectories with `__init__.py`. **PATTERN DRIFT NOTE:** This is a DEPARTURE from the current flat convention. The planner should either (a) explicitly justify the new directory layout in CONTEXT or (b) keep flat naming: `tests/test_picks_account_longevity.py`, `tests/test_picks_engine.py`, etc. Recommendation: ADOPT the subdirectory layout because Phase 3 adds 11 test files and flat would push `tests/` past ~40 files; document the convention shift in `tests/__init__.py`.

---

## Pattern Drift Risks

The planner WILL be tempted to introduce these new patterns when an existing one would do better. Each item below points to the specific decision and the existing analog.

1. **DON'T use `random.random()` or Python's `hash()` for stake jitter.** D-10 + Pitfall 1 + Risks-and-Landmines item 1 + this PATTERNS.md §12 ALL mandate `hashlib.md5(f"{fixture_id}-{market}".encode()).digest()[:4]` → `int.from_bytes(..., "big") % 21 - 10`. Echo the rule in the `account_longevity.py` MODULE DOCSTRING ("CRITICAL: ...") and assert it in `test_jitter_stable_across_processes` via subprocess invocation with varied `PYTHONHASHSEED`.

2. **DON'T re-implement `EDGE_THRESHOLD_PCT` or `simulate_pick`.** D-02 forbids it. Import: `from bip.train.backtest import EDGE_THRESHOLD_PCT, simulate_pick`. The pick engine consumes — never reproduces — this logic.

3. **DON'T add a per-feature settings class** (e.g., `TelegramSettings`, `ClaudeSettings`). Convention #7: extend the single flat `Settings` in `src/bip/core/settings.py:6-22`. New fields go at the bottom of the existing class with sensible defaults so tests that don't set them still pass.

4. **DON'T split learnings.md into chunks.** Pitfall 4 — chunks below 2048 tokens silently fail to cache (no error). Pass the entire file as ONE system block per D-05 ("verbatim").

5. **DON'T branch `tool_choice` between production and debug.** Pitfall 3 — invalidates the cache. The `validate_pick` call must use `tool_choice={"type": "tool", "name": "validate_pick"}` 100% of the time. Debug pathways live in a SEPARATE module / script.

6. **DON'T forget `additionalProperties: false` in the Anthropic tool schema.** Pitfall — `strict: true` is rejected without it. Code Excerpt §B in RESEARCH.md is canonical.

7. **DON'T skip `application.start()` after `application.initialize()`.** PTB v22 manual lifecycle — initialize alone doesn't make `bot.send_message` callable from another task on the loop. Code Excerpt §A in RESEARCH.md is canonical.

8. **DON'T call `application.updater.start_polling()`.** D-13 + research §A: send-only bot. Polling burns API quota and adds inbound surface we don't want.

9. **DON'T use `BackgroundScheduler`.** Existing convention — `tests/test_scheduler.py:14` asserts `isinstance(orch.scheduler, AsyncIOScheduler)`. Reconcile + send jobs MUST register on the existing `self.scheduler`, not a new instance.

10. **DON'T duplicate the rolling-168h query in Polars over Parquet.** Discretion item from CONTEXT.md + RESEARCH.md recommends Supabase. The `picks` table is the source of truth; a Polars snapshot would drift. Add `idx_picks_sport_market_created` in migration 004 so the query is sub-50ms.

11. **DON'T use `tenacity` for the Anthropic D-07 retry loop.** D-07's "wait 60s, retry once" semantics differ from exponential backoff. Use a hand-rolled `for attempt in range(2): try: ... except (RateLimitError, APIError): ... if attempt == 0: await asyncio.sleep(60)`. (TENACITY IS USED for the API-Football and Odds-API clients — see Code Excerpt §8 — but those have different retry semantics.)

12. **DON'T re-implement `derive_db_url` in `verify_migration_004.py`.** Import or duplicate verbatim with attribution comment from `scripts/verify_migration_003.py:32-48`. Same for the `sanitized_host` rsplit guard (T-02.1-02 + WR-02). Never log the DB password.

13. **DON'T treat `telegram_channel_id` as `int`.** Pitfall 8 — channels are `-100*` prefixed; pydantic `int` accepts negatives but JSON serialization may drop the leading `-` in some paths. Keep as `str` in `Settings`, validate the `-100` prefix in a `@field_validator`, cast to `int` only at the `Bot.send_message(chat_id=int(self._channel_id))` call site.

14. **DON'T forget `replace_existing=True`** on `add_job`. Existing convention (4 occurrences in `orchestrator.py`). Required for D-11 idempotency: re-running `evaluate()` for the same prediction must NOT create a second send job.

15. **DON'T use `from datetime import timezone; timezone.utc`.** Repo uses `from datetime import UTC; datetime.now(UTC)`. 4 occurrences confirm convention #11.

16. **DON'T put new tests in flat `tests/test_<x>.py`** if RESEARCH.md's subdirectory layout is adopted. Decide ONCE in the planner output and apply consistently. (Recommendation: subdirectories — see convention #16 above.)

17. **DON'T forget to extend `to_supabase_dict()` for `claude_validated_at`.** The model-EXTENSION pattern (Code Excerpt §2) requires both adding the field AND serializing the datetime to ISO string in `to_supabase_dict()`. Forgetting the second step ships `None` for valid timestamps.

18. **DON'T skip the `BEGIN; COMMIT;` wrapper in migration 004.** Pitfall 5 — without it, a partial DROP+failed-ADD leaves the table without ANY status CHECK constraint, allowing arbitrary status values until manual repair.

19. **DON'T build a custom test for "bot has rate limiter."** Use `assert orch._app._rate_limiter is not None` (research validation table item: `test_aiorate_limiter_attached`). The `_app` accessor is internal — adopting this assertion encodes the contract that `AIORateLimiter` is wired without coupling to PTB internals beyond what's necessary.

20. **DON'T treat the corners gate as an automated CI step.** D-17a is a MANUAL probe. The `.md` artifacts are hand-edited. Only `corners_gate_coverage.py` is automated. The descope flow is one-shot, manually triggered.

---

## PATTERN MAPPING COMPLETE
