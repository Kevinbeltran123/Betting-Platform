# Phase 4: Production Orchestration - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-05-03
**Phase:** 04-production-orchestration
**Areas discussed:** Graceful degradation policy, Production entrypoint + systemd + heartbeat, CLV trend alert (CLV-03), Metrics aggregator + weekly drift

---

## Graceful Degradation Policy

### Q: Claude API failure policy in production — how do we resolve the Phase 3 vs Phase 4 contradiction?

| Option | Description | Selected |
|--------|-------------|----------|
| Feature flag, default conservative | `Settings.claude_failure_mode = 'filter'`. Default keeps Phase 3 D-07; flip to 'skip' via .env once CLV justifies it. | ✓ |
| Flip default to SKIPPED | Match Phase 4 SC#2 exactly: pick always sends with `claude_validation='SKIPPED'` after 2 retries. Overrides Phase 3 D-07. | |
| Keep filter, change SC#2 | Phase 3 D-07 stands; rewrite Phase 4 SC#2 to filter+ops alert. Most conservative. | |

**User's choice:** Feature flag, default conservative.
**Notes:** Resolves the contradiction by making the SKIPPED behavior an opt-in code path. Phase 4 SC#2 wording must be revised by the planner.

### Q: Odds API failure during CLV snapshot — skip the record or defer with a placeholder?

| Option | Description | Selected |
|--------|-------------|----------|
| Defer: write placeholder row | `clv_records` row with NULL closing odds; nightly cron at 03:00 UTC backfills. | |
| Skip: no row, log only | No record on failure; nightly cron has nothing to backfill. CLV permanently missing for that pick. | ✓ |

**User's choice:** Skip silently.
**Notes:** Pinnacle moves post-match — backfilled snapshot is not the true closing line. Better to lose the row than record a misleading one. Phase 4 SC#2 wording ("CLV recording is deferred") must be revised.

### Q: Where do system-health alerts go?

| Option | Description | Selected |
|--------|-------------|----------|
| Same channel, distinct prefix | All alerts to `TELEGRAM_CHANNEL_ID` with `[OPS]` or `⚠️` prefix. | |
| Separate ops channel | Add `TELEGRAM_OPS_CHANNEL_ID`. Picks stay clean. | ✓ |
| External monitor only | Push to healthchecks.io / UptimeRobot; no Telegram for ops. | |

**User's choice:** Separate ops channel.
**Notes:** Picks channel stays focused on betting alerts; ops noise isolated.

### Q: API retry budget — how aggressive before declaring degradation?

| Option | Description | Selected |
|--------|-------------|----------|
| Reuse existing | Claude 2/60s, Odds tenacity 3/exp. No new knobs. | ✓ |
| Add Settings knobs | Expose retry counts and delays in Settings. | |
| Tighten Claude retry | Drop 60s sleep to 15s (4 attempts in 60s instead of 2). | |

**User's choice:** Reuse existing.
**Notes:** Don't add knobs without empirical justification.

---

## Production Entrypoint + systemd + Heartbeat

### Q: Where does the production main() live?

| Option | Description | Selected |
|--------|-------------|----------|
| src/bip/production/__main__.py | New `bip.production` subpackage. `python -m bip.production`. Clean separation from `bip.train.__main__`. | ✓ |
| src/bip/__main__.py | Top-level. `python -m bip`. Visual conflict with `python -m bip.train`. | |
| scripts/run_production.py | Runner script outside the package. Less Pythonic, harder to test. | |

**User's choice:** `src/bip/production/__main__.py`.
**Notes:** —

### Q: systemd unit shape

| Option | Description | Selected |
|--------|-------------|----------|
| Dedicated user, Restart=always, EnvironmentFile | User=`bip`, RestartSec=10, EnvironmentFile=/etc/bip/.env, WatchdogSec=600. | ✓ |
| Run as root, Restart=on-failure | Simpler; no user creation. Less secure. | |
| Defer to plan-phase | Capture intent; planner picks directives. | |

**User's choice:** Dedicated user, Restart=always, EnvironmentFile.
**Notes:** —

### Q: Heartbeat mechanism

| Option | Description | Selected |
|--------|-------------|----------|
| File touch + systemd WatchdogSec | APScheduler interval job touches file; systemd reads mtime. | ✓ |
| healthchecks.io ping | External service alerts via email/Slack. | |
| Both (file touch + healthchecks.io) | Belt + suspenders. | |
| HTTP /health endpoint | aiohttp server on localhost. Adds web-server dep (CLAUDE.md rejects FastAPI). | |

**User's choice:** File touch + systemd WatchdogSec.
**Notes:** —

### Q: Auto-recover on VPS restart — anything to extend?

| Option | Description | Selected |
|--------|-------------|----------|
| Reuse as-is | `_auto_recover` exists at orchestrator.py:89-138; add structlog event for journal visibility. | ✓ |
| Extend to backfill missed reconciliation | Re-queue reconciliation jobs >150min past kickoff. | |
| Extend to backfill missed CLV | Late snapshots; not true closing lines. | |

**User's choice:** Reuse as-is.
**Notes:** —

---

## CLV Trend Alert (CLV-03)

### Q: When does the CLV trend check run?

| Option | Description | Selected |
|--------|-------------|----------|
| Hourly cron | `CronTrigger(minute=0)` queries last 50, computes rolling avg, alerts if < +1%. | ✓ |
| After every CLV write | Hooked into `_record_clv`. Most responsive; risk of thundering herd. | |
| Daily at 23:00 UTC | One rollup per day. Cheapest. Slowest reaction. | |

**User's choice:** Hourly cron.
**Notes:** —

### Q: Trend scope at v1

| Option | Description | Selected |
|--------|-------------|----------|
| Global only | Single rolling-50 across all picks. v1-appropriate (1X2-only). | |
| Global + per-league | 6 alert checks per cadence. False alarms before 50 picks per league. | |
| Global + per-market | Useful only post-Phase 6; today reduces to global. | ✓ |

**User's choice:** Global + per-market.
**Notes:** Per-market dimension structure ships now (gated on ≥50 picks per market) so Phase 6 corners drops in cleanly. At v1 this effectively reduces to global.

### Q: Throttle: once an alert fires, when can it fire again?

| Option | Description | Selected |
|--------|-------------|----------|
| 12h cooldown | In-memory; restart cost = at most one duplicate alert. | ✓ |
| 24h cooldown | Once-a-day max. Misses same-day re-dips. | |
| Until trend recovers | Edge-triggered. Most precise; needs persistent state. | |

**User's choice:** 12h cooldown (in-memory).
**Notes:** —

### Q: Alert message content

| Option | Description | Selected |
|--------|-------------|----------|
| Trend value + recommendation | `⚠️ CLV Trend Alert\nRolling: +0.7% (threshold: +1%)\n...` | |
| Full breakdown | + per-league + recent pick IDs + dashboard link. Adds scope creep. | |
| Trend value only | `⚠️ CLV +0.7% < +1% threshold`. Minimal. | ✓ |

**User's choice:** Trend value only.
**Notes:** Operator already knows the playbook (CLV-03: pause + audit).

---

## Metrics Aggregator + Weekly Drift

### Q: Performance metrics aggregator cadence + scope?

| Option | Description | Selected |
|--------|-------------|----------|
| Daily 23:00 UTC, all periods | Single daily cron computes daily/weekly/monthly/all_time. Idempotent upsert. | ✓ |
| Multi-tier cron | Daily/weekly/monthly each on their own cron. More jobs. | |
| On-demand + nightly | CLI command + nightly cron. Useful for backfills. | |

**User's choice:** Daily 23:00 UTC, all periods.
**Notes:** —

### Q: What does 'weekly drift check' mean for v1?

| Option | Description | Selected |
|--------|-------------|----------|
| Model CLV drift, 4-week vs prior 4-week | Drop ≥ 1.5×stdev OR > 2pp absolute → alert. Reuses CLV data. | ✓ |
| Feature drift (KS test) | Per-feature distribution test. Heavier; needs training snapshot. | |
| Odds-vs-opening drift | Bookmaker sharpening signal. | |
| Skip weekly drift this phase | Defer until 4 weeks of production data exist. | |

**User's choice:** Model CLV drift, 4-week vs prior 4-week.
**Notes:** Compound threshold (hard 2pp + soft 1.5×stdev). Drop-only (improvements don't alert). Other drift types deferred.

### Q: Where does the aggregator math live?

| Option | Description | Selected |
|--------|-------------|----------|
| core/metrics/aggregator.py | New `bip.core.metrics` module. Pure functions. Sport-agnostic per CORE-02. | ✓ |
| core/picks/metrics.py | Co-located with PickEngine. Risks bloating picks module. | |
| scripts/aggregate_metrics.py | Standalone script. Less testable. | |

**User's choice:** `core/metrics/aggregator.py`.
**Notes:** —

### Q: Aggregation implementation — SQL or Polars?

| Option | Description | Selected |
|--------|-------------|----------|
| Supabase SQL via repository | Push rollup to Postgres; single round trip. | |
| Polars over Parquet snapshot | Pull + compute in Polars. More flexible for drift math. | |
| Hybrid | SQL for aggregator (groupby), Polars for drift (KS/distribution). | ✓ |

**User's choice:** Hybrid.
**Notes:** Right tool for each job — aggregator stays cheap, drift stays flexible.

---

## Claude's Discretion

- Heartbeat job shape (top-level IntervalTrigger vs wrapper around scheduler tick).
- Module split between `bip.production.__main__` and `bip.production.builder.build_orchestrator(settings)`.
- `ClvTrendChecker` and `MetricsAggregator` as classes vs free functions.
- Exact field set of `DriftResult` dataclass.
- Heartbeat tick log level (debug vs info; rate-limited vs every tick).
- `compute_period` signature (single triple vs `None`-as-all).

## Deferred Ideas

- Web admin dashboard / breakdown UI (CLAUDE.md rejects FastAPI in v1).
- Feature drift (KS test) — v2.
- Odds-vs-opening drift — v2.
- Per-league CLV trend dimension — needs multi-market multi-season volume.
- Backfill of missed CLV snapshots after VPS downtime — would corrupt CLV records.
- Backfill of reconciliation >150min past kickoff — Phase 4.x or v2.
- Auto-promotion of model registry on CLV improvement — Phase 2 D-05 deferred; inherited.
- Pinnacle `/historical` backfill — Phase 02.1 deferred; inherited.
- Edge-triggered CLV trend alerts — rejected for simplicity.
- Telegram bot user commands — one-way alerts in v1.
- Persistent cooldown table in Supabase — revisit if in-memory duplication is noisy.
- API retry knobs in Settings — defer until production justifies it.
