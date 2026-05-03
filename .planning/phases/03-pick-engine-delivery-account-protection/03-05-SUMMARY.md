---
phase: 03-pick-engine-delivery-account-protection
plan: 5
status: complete
completed: 2026-05-03
duration: ~5min (executed by orchestrator after subagent Bash denial)
tasks_total: 2
tasks_done: 2
commits: 2
requirements_addressed:
  - CLAUDE-01
---

# Plan 03-05 Summary — Claude Role C validator

## What was built

The async wrapper around Anthropic's Messages API that runs strict tool_use validation against historical learnings. Returns typed `ClaudeVerdict` or `None` on D-07 retry-exhausted state.

- **`src/bip/core/claude/validator.py`**:
  - `VALIDATE_PICK_TOOL` — strict=True, additionalProperties=false (D-06)
  - `_TOOL_CHOICE` module constant — Pitfall 3 cache-invalidation guard
  - `ClaudeVerdict` Pydantic model — verdict enum, summary ≤120 chars (D-06)
  - `ClaudeValidator.validate()` — 2-attempt loop, 60s sleep between (D-07)
  - 2-block system prompt — instructions + learnings with `cache_control: ephemeral` (D-05, Pitfall 4)
- **`pyproject.toml`** — `anthropic>=0.50` (resolved 0.97.0)

## Tests

7 GREEN: schema strict, verdict enum, summary length, double-retry, success-no-sleep, cache_control on learnings block, tool_choice constancy.

## Commits

- `7c619cd`: feat(03-05): pin anthropic>=0.50 for strict tool_use
- `6b6b827`: feat(03-05): ClaudeValidator with strict tool_use + D-07 retry (CLAUDE-01)

## Deviations

**One:** Subagent (Sonnet) self-denied Bash access despite project-level `bypassPermissions`. Orchestrator (main thread) executed the plan directly per the canonical implementation in 03-RESEARCH §B. Code is identical to plan spec — no design changes.

**Strategy adjustment:** Remaining waves (3-06, 03-07, 03-08) executed by orchestrator directly to avoid subagent reliability issues.
