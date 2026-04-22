# Phase 1: Foundation + Data Pipeline + CLV - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-04-22
**Phase:** 01-foundation-data-pipeline-clv
**Areas discussed:** Code migration strategy, SportPlugin ABC design, Scheduler job strategy, CLV snapshot timing

---

## Code Migration Strategy

| Option | Description | Selected |
|--------|-------------|----------|
| Copy and adapt in-place | Copy ~650 LOC (6 files + 5 YAML configs) into new repo. Rename namespace. Add `sport` column in same commit. Football_analysis retires when new platform is green. | ✓ |
| Local editable dep | `uv add --editable ../Football_analysis`. No copy step, but cross-repo changes are fragile and VPS deploy requires both repos. | |

**User's choice:** Copy and adapt (Recommended)
**Notes:** All 6 files need structural changes (sport column, namespace rename, settings expansion) — editable dep fights every CORE-0x requirement.

---

## SportPlugin ABC Design

| Option | Description | Selected |
|--------|-------------|----------|
| Typed Pydantic BaseModels | ProbabilityMap, FixtureData, etc. as BaseModel. Pydantic validates at plugin boundary. Consistent with existing codebase. | ✓ |
| typing.Protocol | Structural typing, no inheritance. No return-value validation at boundary. | |
| Minimal ABC + dicts | Fastest to define. Core must defensively cast every plugin return. | |

**User's choice:** Typed Pydantic BaseModels (Recommended)

**Follow-up — ProbabilityMap shape:**

| Option | Description | Selected |
|--------|-------------|----------|
| Sport-agnostic from day 1 | `probabilities: dict[str, float]` keyed by outcome name. Football uses "1","X","2". Tennis uses "H","A". EV engine iterates keys, zero sport-specific code in core/. | ✓ |
| Football-specific named fields | `home_win`, `draw`, `away_win`, `btts_yes`, etc. Phase 7 Tennis requires breaking change. | |

**User's choice:** Sport-agnostic from day 1 (Recommended)

---

## Scheduler Job Strategy

| Option | Description | Selected |
|--------|-------------|----------|
| Per-fixture DateTrigger jobs | Daily orchestrator at 06:00 UTC creates DateTrigger jobs for each fixture (T-2h, T-30min). Jobs self-clean after firing. | ✓ |
| Polling window every 5 min | Single IntervalTrigger queries "fixtures in next window" each tick. Survives restarts but 5-min jitter and more complex logic. | |

**User's choice:** Per-fixture DateTrigger jobs (Recommended)

**Follow-up — Restart guard:**

| Option | Description | Selected |
|--------|-------------|----------|
| Auto-recover on startup | On scheduler start, detect missing jobs and re-schedule remaining fixtures. No manual intervention. | ✓ |
| Wait for next day | Restart drops today's remaining fixtures. Unacceptable for production. | |

**User's choice:** Auto-recover on startup (Recommended)

---

## CLV Snapshot Timing

| Option | Description | Selected |
|--------|-------------|----------|
| Fixed-delay T+105min + nightly reconciliation | DateTrigger at kickoff+105min. Nightly 03:00 UTC job re-checks NULL rows. Same-day CLV alerts, ~75 req/month. | ✓ |
| Next-day batch at 03:00 UTC | Single daily job. Simpler but CLV trend alerts delayed up to 18 hours. | |

**User's choice:** Fixed-delay T+105min + nightly reconciliation (Recommended)
**Notes:** Polling was eliminated — budget math: 7 polls/match × 75 matches/month = 525 requests, exceeds 500-request Rookie tier.

---

## Claude's Discretion

- Exact field names for `FixtureData`, `FeatureMatrix`, `ClaudeContext` Pydantic models
- New platform package name
- Directory layout within `src/`
- Whether `Settings` splits into `CoreSettings` + sport-specific or stays unified

## Deferred Ideas

None — discussion stayed within Phase 1 scope.
