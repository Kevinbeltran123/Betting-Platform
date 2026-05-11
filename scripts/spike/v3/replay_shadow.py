"""Replay live Engine v3 shadow over cached Sportmonks snapshots.

Phase-1/Phase-2 bridge tool. Walks the local Sportmonks cache
(``data/cache/sportmonks/snapshots/<fixture>/<timestamp>.json``),
projects each snapshot into a ``GameStateVector``, runs the V3
pipeline, and persists the shadow output (allowed picks +
rule-keyed denials) to ``data/cache/v3_shadow/dt=YYYY-MM-DD/``.

Usage
-----

::

    uv run python scripts/spike/v3/replay_shadow.py \
        --cache-root data/cache/sportmonks \
        --shadow-root data/cache/v3_shadow \
        --max-fixtures 30 \
        --mes-threshold 0.6

The script is **deterministic**: no API calls, no Telegram, no DB
writes outside the shadow parquets. Safe to run on any historical
cache as a regression / what-if tool.

Why a separate script: per the design (sec 7.5 "Shadow-vs-live
divergence"), the v3 must run *alongside* the current pipeline, not
through it. Putting it inside ``watch.py`` couples lifecycles and
risks the v3 inadvertently feeding the operator. This script proves
the principle by being structurally incapable of any side-effect on
the live system.
"""
from __future__ import annotations

import argparse
import logging
from datetime import datetime, timezone
from pathlib import Path

from bip.evaluation.live.engine_v3 import (
    MarketLine,
    MarketSnapshot,
    PreMatchPriors,
    V3Pipeline,
)
from bip.evaluation.live.engine_v3.shadow_logger import (
    DEFAULT_SHADOW_ROOT,
    ShadowLogger,
)
from bip.evaluation.live.match_state import LiveMatchState
from bip.sports.football.sportmonks.cache import DEFAULT_CACHE_ROOT, SportmonksCache
from bip.sports.football.sportmonks.schemas import Fixture

log = logging.getLogger("v3.replay")


# ──────────────────────────────────────────────────────────────────────
# Sportmonks → MarketSnapshot adapter
# ──────────────────────────────────────────────────────────────────────


def market_snapshot_from_fixture(fixture: Fixture, *, captured_at: datetime) -> MarketSnapshot:
    """Pull live-odds entries from the fixture payload into a typed snapshot.

    Sportmonks emits in-play odds as a list under ``fixture.inplay_odds``
    (when the include is requested). Each ``Odd`` has ``market_description``,
    ``label`` (selection), ``value`` (decimal), ``market_id``, and
    ``updated_at``. We index by ``market_description + selection`` so
    over/under and yes/no both end up as separate market lines.

    For Phase-1 we are conservative: we ignore odd entries with no
    market_description and we cap ``max_stake_cap`` at a flat default
    of 1.0 (Phase 2 wires the real cap from Sportmonks when emitted).
    """
    lines: dict[str, MarketLine] = {}
    # Sportmonks Fixture schema may name this `inplay_odds` or `odds` — be
    # defensive across schema versions.
    odds = getattr(fixture, "inplay_odds", None) or getattr(fixture, "odds", None) or []
    for o in odds:
        desc = (getattr(o, "market_description", None) or "").strip().lower()
        label = (getattr(o, "label", None) or "").strip().lower()
        value = getattr(o, "value", None) or getattr(o, "decimal", None)
        if not desc or value is None:
            continue
        try:
            decimal = float(value)
        except (TypeError, ValueError):
            continue
        if decimal <= 1.0:
            continue
        market_id = _build_market_id(desc, label, getattr(o, "total", None))
        # Concatenate label so over/under and yes/no live as separate lines.
        if market_id in lines:
            continue
        updated_at_raw = getattr(o, "latest_bookmaker_update", None)
        last_update = _parse_dt(updated_at_raw) or captured_at
        lines[market_id] = MarketLine(
            market_id=market_id,
            side_a_decimal=decimal,
            side_b_decimal=None,
            line_value=_parse_total(getattr(o, "total", None)),
            max_stake_cap=1.0,
            last_update_utc=last_update,
        )
    return MarketSnapshot(lines=lines)


def _parse_dt(raw) -> datetime | None:
    if isinstance(raw, datetime):
        return raw if raw.tzinfo else raw.replace(tzinfo=timezone.utc)
    if not raw:
        return None
    try:
        return datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        return None


def _parse_total(raw) -> float | None:
    if raw is None:
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def _build_market_id(description: str, label: str, total) -> str:
    """Compose a normalised v3 market id string from a Sportmonks Odd.

    Heuristic mapping intentionally simple — the v3 ``family_for_market_id``
    is the canonical resolver downstream. Examples:

    - ``description="match goals"`` + ``label="over"`` + ``total=2.5``
      → ``"match_goals_over_2.5"``
    - ``description="both teams to score"`` + ``label="yes"``
      → ``"both_teams_to_score_yes"`` (matches the BTTS prefix)
    """
    desc_norm = description.replace(" ", "_").replace("/", "_")
    bits = [desc_norm]
    if label:
        bits.append(label.replace(" ", "_"))
    total_val = _parse_total(total)
    if total_val is not None:
        bits.append(str(total_val))
    return "_".join(bits)


# ──────────────────────────────────────────────────────────────────────
# Replay
# ──────────────────────────────────────────────────────────────────────


def derive_priors_from_predictions(fixture: Fixture) -> PreMatchPriors:
    """Best-effort priors: pull lambda anchors from Sportmonks predictions.

    When the fixture has ``CORRECT_SCORE_PROBABILITY`` (type_id 240), we
    compute the marginal expected goals per side from the grid. Fall
    back to constant defaults when missing — the v3 pipeline doesn't
    crash with neutral priors, it just makes weaker thesis claims.
    """
    lam_h = 1.35
    lam_a = 1.15
    for p in fixture.predictions or []:
        if p.type_id != 240 or not p.predictions:
            continue
        scores = p.predictions.get("scores") if isinstance(p.predictions, dict) else None
        if not isinstance(scores, dict):
            continue
        e_h = e_a = 0.0
        total = 0.0
        for k, v in scores.items():
            if not isinstance(k, str) or k == "other":
                continue
            try:
                h_str, a_str = k.split("-")
                h, a = int(h_str), int(a_str)
                w = float(v) / 100.0
            except (TypeError, ValueError):
                continue
            e_h += h * w
            e_a += a * w
            total += w
        if total > 0:
            lam_h = e_h / total
            lam_a = e_a / total
        break
    return PreMatchPriors(
        lambda_home_prematch=lam_h,
        lambda_away_prematch=lam_a,
    )


def replay_one_fixture(
    fixture_id: int,
    cache: SportmonksCache,
    pipeline: V3Pipeline,
    logger: ShadowLogger,
    *,
    max_snapshots: int | None = None,
) -> tuple[int, int]:
    """Replay all snapshots for one fixture. Returns (n_picks, n_denials)."""
    snapshots = cache.list_snapshots(fixture_id)
    if max_snapshots:
        snapshots = snapshots[:max_snapshots]
    total_picks = 0
    total_denials = 0
    for path in snapshots:
        try:
            fixture = cache.load_snapshot(path)
        except Exception as exc:
            log.warning("could not load snapshot %s: %s", path, exc)
            continue
        try:
            captured = datetime.strptime(path.stem, "%Y%m%dT%H%M%SZ").replace(
                tzinfo=timezone.utc
            )
        except ValueError:
            captured = datetime.now(timezone.utc)
        try:
            state = LiveMatchState.from_fixture(fixture, snapshot_taken_at=captured)
        except Exception as exc:
            log.warning("could not build state for %s: %s", path, exc)
            continue
        priors = derive_priors_from_predictions(fixture)
        markets = market_snapshot_from_fixture(fixture, captured_at=captured)
        if not markets.lines:
            continue
        out = pipeline.run(
            state, priors=priors, markets=markets, now_utc=captured,
        )
        n_picks, n_denials = logger.record(out)
        total_picks += n_picks
        total_denials += n_denials
    return total_picks, total_denials


# ──────────────────────────────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────────────────────────────


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--cache-root", type=Path, default=DEFAULT_CACHE_ROOT,
                   help="Sportmonks cache root.")
    p.add_argument("--shadow-root", type=Path, default=DEFAULT_SHADOW_ROOT,
                   help="V3 shadow output root.")
    p.add_argument("--max-fixtures", type=int, default=0,
                   help="0 = all fixtures, else cap.")
    p.add_argument("--max-snapshots", type=int, default=0,
                   help="0 = all snapshots per fixture.")
    p.add_argument("--mes-threshold", type=float, default=0.6,
                   help="No-bet rule 5 threshold.")
    p.add_argument("--commentary-required", action="store_true",
                   help="Enforce no-bet rule 6 strictness.")
    p.add_argument("--log-level", default="INFO")
    return p.parse_args()


def main() -> None:
    args = _parse_args()
    logging.basicConfig(level=args.log_level)
    cache = SportmonksCache(root=args.cache_root)
    pipeline = V3Pipeline(
        mes_threshold=args.mes_threshold,
        commentary_required=args.commentary_required,
    )
    logger = ShadowLogger(output_root=args.shadow_root)

    fixture_ids = cache.list_fixtures()
    if args.max_fixtures:
        fixture_ids = fixture_ids[: args.max_fixtures]
    log.info("v3 replay: %d fixtures", len(fixture_ids))

    tot_picks = 0
    tot_denials = 0
    for fid in fixture_ids:
        n_p, n_d = replay_one_fixture(
            fid, cache, pipeline, logger,
            max_snapshots=args.max_snapshots or None,
        )
        tot_picks += n_p
        tot_denials += n_d
        if (n_p + n_d) > 0:
            log.info("fixture %s — picks=%d denials=%d", fid, n_p, n_d)

    paths = logger.flush()
    log.info("flushed %s", paths)
    log.info("TOTAL: picks=%d denials=%d", tot_picks, tot_denials)


if __name__ == "__main__":
    main()
