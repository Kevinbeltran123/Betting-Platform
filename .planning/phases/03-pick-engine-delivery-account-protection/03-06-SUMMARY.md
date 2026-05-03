---
phase: 03-pick-engine-delivery-account-protection
plan: 6
status: complete
completed: 2026-05-03
duration: ~10min (executed by orchestrator)
tasks_total: 3
tasks_done: 3
commits: 3
requirements_addressed:
  - PICK-04
---

# Plan 03-06 Summary — Telegram delivery layer

## What was built

Send-only Telegram bot + Jinja2-templated sender for one-message-per-pick delivery (D-12).

- **`src/bip/core/telegram/bot.py`** — `TelegramBot`:
  - `Application` lifecycle: `initialize()` → `start()` → `shutdown()` (drift risk #7)
  - `AIORateLimiter(max_retries=3)` (Pitfall 2 + Risks 2)
  - NO polling — outbound only (drift risk #8, D-13)
  - `send_html()` with `ParseMode.HTML`, channel_id cast at send site (drift risk #13)
- **`src/bip/core/telegram/sender.py`** — `TelegramSender` + `render_pick()`:
  - Jinja2 `Environment(PackageLoader, autoescape=select_autoescape(["html"]))` (T-3-XSS)
  - claude_summary split on ` * ` separator, capped at 3 bullets (D-15)
- **`src/bip/core/telegram/templates/pick.html`** — Jinja2 template:
  - FLAG branch: WARNING entity (`&#x26A0;&#xFE0F;`) + `Claude flagged: <reason_code>` (D-14)
  - CONFIRM branch: clean header
  - Telegram HTML tags only (no `<div>`/`<span>`/`<p>`)
- **`pyproject.toml`** — `python-telegram-bot[rate-limiter]==22.7` + `jinja2>=3.1`

## Tests

15 GREEN total:
- 6 bot tests: no-polling, rate_limiter wired, init-then-start, error cases, settings validator integration
- 9 sender tests: XSS escape, FLAG marker, CONFIRM clean, bullet cap (3), separator literal, empty summary, length budget, allowed-tags-only, stake=None renders 0.0u

## Commits

- `2a07afe`: feat(03-06): add python-telegram-bot[rate-limiter]==22.7 + jinja2
- `19913c0`: feat(03-06): TelegramBot with AIORateLimiter, no polling (PICK-04 D-13)
- `7f2e255`: feat(03-06): TelegramSender + Jinja2 template (PICK-04 D-12, D-14, D-15)

## Deviations

**One:** Plan-spec `assert bot._app._rate_limiter is not None` failed — in PTB 22.7 the rate_limiter is exposed at `app.bot.rate_limiter`, not `app._rate_limiter`. Test updated to `bot._app.bot.rate_limiter` + `isinstance(AIORateLimiter)` check. Same Pitfall 2 / Risks 2 invariant (rate limiter wired) — just verified at the correct attribute path for the installed library version.
