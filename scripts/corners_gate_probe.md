# CORNERS-01 Gate Probe — Manual Checklist (Part A / D-17a)

**Phase:** 3 (Pick Engine + Delivery + Account Protection)
**Owner:** Kevin
**Purpose:** Verify Betano offers the corner time-window markets that Phase 6 (Timed Corners Module) depends on. Gate failure on either Part A (this file) or Part B (`corners_gate_coverage.py`) auto-descopes Phase 6 to v2-deferred per D-18.

---

## Companion Files

- `scripts/corners_gate_findings.md` — fill in your findings here AFTER completing the checklist below.
- `scripts/corners_gate_coverage.py` — Part B (automated Polars query over the 02.1 Parquet store). Run AFTER Part A is complete.
- `scripts/corners_gate_descope.py` — D-18 descope orchestration. Run if EITHER Part A or Part B fails.
- `.planning/phases/03-pick-engine-delivery-account-protection/03-CONTEXT.md` D-17, D-18 — locked decisions.

---

## Checklist

Complete every item below. Save findings into `scripts/corners_gate_findings.md` as you go.

### Setup

- [ ] Log in to Betano (sportsbook account)
- [ ] Switch to LIVE betting view
- [ ] Confirm timezone matches league kickoff times to avoid confusing live vs upcoming

### Per league — pick 3-5 upcoming fixtures across each of the 5 leagues

For EACH league below, verify the corner markets offered. For each fixture probed, take a screenshot and record findings.

#### Premier League
- [ ] Fixture 1 probed (link / screenshot)
- [ ] Fixture 2 probed
- [ ] Fixture 3 probed
- [ ] Fixture 4 probed (optional)
- [ ] Fixture 5 probed (optional)

#### La Liga
- [ ] Fixture 1 probed
- [ ] Fixture 2 probed
- [ ] Fixture 3 probed
- [ ] Fixture 4 probed (optional)
- [ ] Fixture 5 probed (optional)

#### Bundesliga
- [ ] Fixture 1 probed
- [ ] Fixture 2 probed
- [ ] Fixture 3 probed
- [ ] Fixture 4 probed (optional)
- [ ] Fixture 5 probed (optional)

#### Serie A
- [ ] Fixture 1 probed
- [ ] Fixture 2 probed
- [ ] Fixture 3 probed
- [ ] Fixture 4 probed (optional)
- [ ] Fixture 5 probed (optional)

#### Ligue 1
- [ ] Fixture 1 probed
- [ ] Fixture 2 probed
- [ ] Fixture 3 probed
- [ ] Fixture 4 probed (optional)
- [ ] Fixture 5 probed (optional)

### Per fixture — what to capture

For EACH probed fixture record in `corners_gate_findings.md`:

- [ ] **Markets seen** — does Betano list any of the 6 expected windows (0-15, 15-30, 30-45, 45-60, 60-75, 75-90)? Or different bucketing (e.g., "Total Corners 1H", "Total Corners 2H")? Or NO corner-window market at all (only "Total Corners")?
- [ ] **Exact market naming convention** — copy verbatim. Example: `Córners 1ª Mitad - Más/Menos 5.5` vs `Total Corners First Half Over/Under 5.5`. Naming matters for future scraping or any cross-API mapping.
- [ ] **Odds range** — typical odds across the markets seen (e.g., 1.85 - 2.15 for Over/Under main lines).
- [ ] **Minimum stake** — Betano enforces a min stake per bet; record the value (currency-aware).
- [ ] **Screenshot** — store at `scripts/corners_evidence/<league>_<fixture_id>.png` (gitignored if confidential, link in findings.md).

### Gate decision (Part A only)

After all fixtures probed, write the verdict in `corners_gate_findings.md` under `## Part A — Gate Decision`:

- [ ] **PASS** — Betano offers per-window corner markets (any bucketing that lets us bet ON specific time windows; not just totals) for ALL 5 leagues across ≥3 fixtures each.
- [ ] **FAIL** — markets do NOT exist OR are inconsistent across leagues OR Betano only offers full-match totals.

If FAIL, run `python scripts/corners_gate_descope.py --part a --reason "<one-liner>"` after Part B (whether B passes or fails) to trigger the D-18 descope flow.

If PASS, await Part B (`corners_gate_coverage.py`) outcome before any commit / next-step decision.

---

## Findings template

See `scripts/corners_gate_findings.md` for the structured template to fill in as you work through the checklist.
