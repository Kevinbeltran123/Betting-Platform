"""Account longevity protections: Kelly sizing, deterministic jitter, send-time variance, market cap.

CRITICAL: Use hashlib.md5 — NOT Python's `hash()` (salted by PYTHONHASHSEED, breaks
reproducibility across process restarts). See Phase 3 RESEARCH Pitfall 1.

Implements:
- PICK-02: quarter_kelly_units + round_to_nearest_half_unit
- PICK-03 / D-09: exceeds_60pct_cap (rolling 168h market-cap drop-on-bind)
- PICK-03 / D-10: deterministic_jitter (md5-seeded, ±10%)
- PICK-03 / D-11: deterministic_send_at (random.Random(fixture_id), 0-1800s window)

D-02: NEVER duplicate EDGE_THRESHOLD_PCT or simulate_pick. Import from bip.train.backtest in the
engine layer (plan 03-07); this module owns sizing/timing math only.
"""

from __future__ import annotations

import hashlib
import random
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from bip.core.storage.repositories import PickRepository


# ─────────────────────────────────────────────────────────────────────────────
# PICK-02: Kelly sizing + 0.5-unit rounding (anti-fingerprinting)
# ─────────────────────────────────────────────────────────────────────────────

def quarter_kelly_units(edge: float, odds: float, max_fraction: float = 0.25) -> float:
    """Quarter Kelly stake fraction.

    PICK-02: kelly_fraction = (edge / (odds - 1)) × 0.25.

    Args:
        edge: fractional edge (0.05 = 5%); negative edges clamped to 0.
        odds: decimal odds (≥ 1.0); odds ≤ 1.0 returns 0.0 to avoid div-by-zero.
        max_fraction: Kelly cap (default 0.25 = quarter Kelly).

    Returns:
        Stake as a fraction of bankroll, clamped to [0.0, max_fraction].
    """
    if odds <= 1.0:
        return 0.0
    full_kelly = edge / (odds - 1.0)
    return max(0.0, min(full_kelly, 1.0)) * max_fraction


def round_to_nearest_half_unit(stake: float) -> float:
    """Round stake to nearest 0.5 unit.

    PICK-02: anti-fingerprinting — bookmakers profile users by stake granularity.
    Rounding to 0.5u (vs 0.01u) makes each user indistinguishable from manual punters.
    """
    return round(stake * 2) / 2


# ─────────────────────────────────────────────────────────────────────────────
# D-10: deterministic stake jitter (md5-seeded)
# ─────────────────────────────────────────────────────────────────────────────

def deterministic_jitter(fixture_id: int, market: str) -> float:
    """Return jitter in [-0.10, +0.10] seeded by (fixture_id, market) via md5.

    D-10 + Pitfall 1: Python's built-in `hash(str)` is salted by PYTHONHASHSEED at
    process start, so the same input yields different ints across restarts. md5 is
    deterministic across all platforms / restarts / Python versions.

    Open Question #7: first 4 bytes (32 bits of entropy) modulo 21 → uniform on 0..20.
    """
    digest = hashlib.md5(f"{fixture_id}-{market}".encode()).digest()
    n = int.from_bytes(digest[:4], "big") % 21       # 0..20
    return (n - 10) / 100.0                          # -0.10..+0.10


# ─────────────────────────────────────────────────────────────────────────────
# D-11: deterministic send-time variance
# ─────────────────────────────────────────────────────────────────────────────

def deterministic_send_at(prediction_completed_at: datetime, fixture_id: int) -> datetime:
    """send_at = prediction_completed_at + Random(fixture_id).randint(0, 1800)s.

    D-11: Each call constructs a FRESH random.Random(seed=fixture_id). No global RNG
    state leak. Reproducible — re-running for the same fixture yields the same send_at.
    """
    rng = random.Random(fixture_id)
    return prediction_completed_at + timedelta(seconds=rng.randint(0, 1800))


# ─────────────────────────────────────────────────────────────────────────────
# D-09: 60% market-cap rolling 168h check (drop-on-bind)
# ─────────────────────────────────────────────────────────────────────────────

def exceeds_60pct_cap(
    pick_repo: "PickRepository",
    market: str,
    sport: str,
    hours: int = 168,
    min_sample: int = 5,
) -> bool:
    """Return True if adding this pick would push `market` past 60% of sent picks in `hours`.

    D-09: Rolling 168h window. Drop-on-bind, not defer. Phase 3 note — with 1X2-only
    markets the cap is structurally dormant (single market always 100%); the mechanism
    is built now so Phase 6 corners + future BTTS/Over-Under plug in cleanly.

    PATTERNS.md drift risk #10: query reads from Supabase (single source of truth),
    NOT Polars over Parquet — uses idx_picks_sport_market_created (migration 004).

    Args:
        pick_repo: PickRepository — provides get_window_picks(sport, hours).
        market: market this pick would be in.
        sport: sport filter for the window query.
        hours: rolling window size in hours (default 168 = 7 days).
        min_sample: below this many sent picks in the window, do NOT gate (returns False).

    Returns:
        True if (count of `market` + 1) / (total + 1) > 0.60. Else False.
    """
    rows = pick_repo.get_window_picks(sport=sport, hours=hours)
    if len(rows) < min_sample:
        return False
    same_market = sum(1 for r in rows if r.get("market") == market)
    return (same_market + 1) / (len(rows) + 1) > 0.60
