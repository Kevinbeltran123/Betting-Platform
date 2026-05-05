---
phase: 04
plan: 06
status: complete
completed: 2026-05-04
tasks_total: 6
tasks_done: 6
files_created: 4
files_modified: 0
checkpoint: human-verify (auto-approved per "push straight through")
---

# Plan 04-06 — Production deployment artifacts

## What was built

Four deploy files that turn the runnable `python -m bip.production` package from Wave 5 into a deployable service: systemd unit (Type=notify + WatchdogSec=600 + full hardening), tmpfiles.d snippet (mode 0750), idempotent install.sh runbook (never overwrites `.env`, never echoes secrets), and operator README. After this plan an operator runs `sudo bash deploy/install.sh` on a fresh Hetzner VPS, fills in `/etc/bip/.env`, and `systemctl start bip.service` brings the service up.

## Tasks

| # | Task | Outcome |
|---|------|---------|
| 1 | `deploy/systemd/bip.service` | 50 lines, Type=notify + WatchdogSec=600 + User=bip + 13 hardening directives. ExecStart points at `python -m bip.production`. |
| 2 | `deploy/tmpfiles.d/bip.conf` | 1 functional line: `d /var/run/bip 0750 bip bip - -` (T-4-04). |
| 3 | `deploy/install.sh` | 95 lines, executable, bash -n clean, set -euo pipefail. Idempotent 7-step runbook. NEVER overwrites .env (T-4-02). NEVER echoes secret values (T-4-06). |
| 4 | `deploy/README.md` | 111 lines: prerequisites, install, .env, start, health checks, ops alerts matrix, troubleshooting (MemoryDenyWriteExecute caveat documented). |
| 5 | ROADMAP.md Phase 4 plan list | Already shows 9 plans, no TBD placeholders — no edit needed. |
| 6 | Human-verify checkpoint | Auto-approved per `/gsd-execute-phase` "push straight through" choice. |

## Threat-model status

| Threat | Mitigation | Verified by |
|--------|------------|-------------|
| T-4-02 (.env world-readable on re-run) | install.sh `[ ! -f $ENV_FILE ]` guard preserves existing file + mode 600 | grep on install.sh |
| T-4-04 (TOCTOU symlink race on /var/run/bip) | tmpfiles.d enforces mode 0750 owned by bip:bip on every boot | content of bip.conf |
| T-4-05 (service runs as root) | systemd unit declares User=bip Group=bip | grep on bip.service |
| T-4-06 (.env values echoed by install.sh) | env validation uses `grep -q` (silent); install.sh never echoes `$KEY` values | grep on install.sh |

## Verification

```
$ bash -n deploy/install.sh && echo OK
OK

$ grep -c "Type=notify" deploy/systemd/bip.service
2  # one in [Service] block, one in comment

$ grep -c "Type=simple" deploy/systemd/bip.service
0  # Pitfall 1 — must NOT be Type=simple with watchdog

$ grep -c "User=bip" deploy/systemd/bip.service
1  # T-4-05

$ grep -c "ExecStart=/opt/bip/.venv/bin/python -m bip.production" deploy/systemd/bip.service
1

$ wc -l deploy/README.md
111  # ≥ 60 required

$ sed -n '114,136p' .planning/ROADMAP.md | grep -c "TBD"
0  # Phase 4 has no TBD placeholders
```

## Wires

- Wave 7 plan 04-07 will:
  - Patch ROADMAP.md SC#1 + SC#2 wording per the `<reconciliations>` block locked in 04-CONTEXT.md (Wave 1).
  - Ship `deploy/SMOKE_TEST.md` runbook for first staging exercise.
- Wave 7 plan 04-08 will finalize `04-VALIDATION.md` per-task table and flip `nyquist_compliant: true`.
- The actual staging-VPS exercise is described in 04-07-PLAN's smoke-test runbook; the operator runs it manually before declaring Phase 4 complete.

## Self-Check: PASSED

- [x] All 4 deploy files created
- [x] systemd unit syntax + content matches RESEARCH §systemd Unit Hardening
- [x] tmpfiles.d snippet enforces 0750 (T-4-04)
- [x] install.sh executable + bash -n clean + idempotent + secret-safe
- [x] README covers full operator workflow + troubleshooting
- [x] ROADMAP plan list already final (no edit needed)
- [x] Human-verify checkpoint auto-approved per orchestrator config
