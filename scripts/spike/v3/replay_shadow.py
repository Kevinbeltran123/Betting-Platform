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
        --ood-path data/cache/ood_detector_v1.pkl \
        --pattern-path data/cache/pattern_layer_v1.pkl \
        --max-fixtures 30 \
        --mes-threshold 0.6 \
        --audit

The script is **deterministic**: no API calls, no Telegram, no DB
writes outside the shadow parquets. Safe to run on any historical
cache as a regression / what-if tool.

T1.2 additions: the OOD detector and pattern layer pkls (produced by
fit_ood_detector.py / fit_pattern_layer.py) are loaded by default if
present at the conventional paths. Replay then exactly mirrors the
production Tier-1.3 setup so the audit trail captures the SAME
rule-level decisions that watch.py will see. If a pkl is missing the
script logs a structured warning and proceeds with that layer = None;
no crash.

The ``--audit`` flag writes one JSONL row per processed GSV under
``reports/v3/replay_audit/<run_id>.jsonl`` carrying the full audit
trail: theses, candidates, MES breakdown, gate verdict per candidate,
mispricing window, and the OOD score when available. This is the
structure the Phase-4 weekly review reads to reconstruct why a
specific pick was emitted (or not).

Why a separate script: per the design (sec 7.5 "Shadow-vs-live
divergence"), the v3 must run *alongside* the current pipeline, not
through it. Putting it inside ``watch.py`` couples lifecycles and
risks the v3 inadvertently feeding the operator. This script proves
the principle by being structurally incapable of any side-effect on
the live system.
"""

from __future__ import annotations

import argparse
import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from bip.evaluation.live.engine_v3 import (
    MarketLine,
    MarketSnapshot,
    OODDetector,
    PatternLayer,
    PipelineOutput,
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

DEFAULT_OOD_PATH = Path("data/cache/ood_detector_v1.pkl")
DEFAULT_PATTERN_PATH = Path("data/cache/pattern_layer_v1.pkl")
DEFAULT_AUDIT_ROOT = Path("reports/v3/replay_audit")

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
# Detector loading (T1.2)
# ──────────────────────────────────────────────────────────────────────


def load_detectors(
    ood_path: Path | None,
    pattern_path: Path | None,
) -> tuple[OODDetector | None, PatternLayer | None]:
    """Load OOD detector + pattern layer pkls if present.

    Missing pkl → warn + return None for that layer. This is the same
    safety contract watch.py will use: shadow can degrade gracefully
    rather than failing closed.

    Returns ``(ood_detector, pattern_layer)``.
    """
    ood = None
    if ood_path is not None and ood_path.exists():
        try:
            ood = OODDetector.load(ood_path)
            log.info("loaded OOD detector from %s", ood_path)
        except Exception as exc:
            log.warning("OOD detector load failed at %s: %s — using None", ood_path, exc)
    elif ood_path is not None:
        log.warning("OOD pkl not found at %s — replay runs without rule #9", ood_path)

    pattern = None
    if pattern_path is not None and pattern_path.exists():
        try:
            pattern = PatternLayer.load(pattern_path)
            log.info("loaded pattern layer from %s", pattern_path)
        except Exception as exc:
            log.warning("pattern layer load failed at %s: %s — using None", pattern_path, exc)
    elif pattern_path is not None:
        log.warning(
            "pattern layer pkl not found at %s — replay runs rule-layer-only",
            pattern_path,
        )

    return ood, pattern


# ──────────────────────────────────────────────────────────────────────
# Audit JSONL writer (T1.2 --audit mode)
# ──────────────────────────────────────────────────────────────────────


def _audit_record(out: PipelineOutput, ood: OODDetector | None) -> dict[str, Any]:
    """Build one audit row capturing the full chain for a frame.

    Schema is intentionally flat-ish so polars / jq can slice it without
    custom unpacking. Per-candidate detail lives in ``candidates`` and
    ``gate_verdicts`` lists, indexable by position.
    """
    gsv = out.gsv
    ood_score: float | None = None
    ood_threshold: float | None = None
    if ood is not None and ood.is_fitted:
        try:
            ood_score = ood.score(gsv)
            ood_threshold = ood.threshold
        except Exception as exc:  # noqa: BLE001
            log.debug("OOD scoring failed: %s", exc)

    return {
        "fixture_id": int(gsv.fixture_id),
        "state_version": int(gsv.state_version),
        "timestamp_utc": gsv.timestamp_utc.isoformat(),
        "minute": int(gsv.time.minute),
        "period": gsv.time.period,
        "score": [int(gsv.score.home_goals), int(gsv.score.away_goals)],
        "dominant_losing": bool(gsv.score.dominant_losing),
        "n_theses": len(out.theses),
        "thesis_layers": [t.source.layer for t in out.theses],
        "thesis_archetypes": [t.archetype.value for t in out.theses],
        "n_candidates": len(out.candidates),
        "candidates": [
            {
                "market_id": c.market_id,
                "family": c.family.value,
                "thesis_id": c.thesis.id,
                "thesis_layer": c.thesis.source.layer,
                "fair_prob": float(c.fair_prob),
                "mes_score": float(c.mes.score),
                "base_edge": float(c.mes.base_edge),
                "signal_clarity": float(c.mes.signal_clarity),
                "book_slowness": float(c.mes.book_slowness),
                "liquidity_score": float(c.mes.liquidity_score),
                "conditional_variance": float(c.mes.conditional_variance),
            }
            for c in out.candidates
        ],
        "gate_verdicts": [
            {
                "market_id": r.candidate.market_id,
                "allowed": bool(r.verdict.allowed),
                "rule_number": (int(r.verdict.rule_number) if r.verdict.rule_number else None),
                "reason": r.verdict.reason,
            }
            for r in out.gate_results
        ],
        "allowed_count": sum(1 for r in out.gate_results if r.verdict.allowed),
        "denied_count": sum(1 for r in out.gate_results if not r.verdict.allowed),
        "mispricing_window": (
            {
                "label": out.mispricing_window.label.value
                if hasattr(out.mispricing_window.label, "value")
                else str(out.mispricing_window.label),
                "multiplier": float(out.mispricing_window.multiplier),
                "age_sec": (
                    float(out.mispricing_window.age_sec)
                    if out.mispricing_window.age_sec is not None
                    else None
                ),
            }
            if out.mispricing_window is not None
            else None
        ),
        "ood": (
            {"score": ood_score, "threshold": ood_threshold} if ood_score is not None else None
        ),
    }


class AuditJSONLWriter:
    """Append-mode JSONL writer that flushes after every record."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # Open in append so the same run_id can be resumed if re-invoked.
        self._fh = self.path.open("a", encoding="utf-8")

    def write(self, record: dict[str, Any]) -> None:
        self._fh.write(json.dumps(record) + "\n")
        self._fh.flush()

    def close(self) -> None:
        try:
            self._fh.close()
        except Exception:  # noqa: BLE001
            pass

    def __enter__(self) -> AuditJSONLWriter:
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()


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
    audit_writer: AuditJSONLWriter | None = None,
    ood_detector: OODDetector | None = None,
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
            captured = datetime.strptime(path.stem, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
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
            state,
            priors=priors,
            markets=markets,
            now_utc=captured,
        )
        n_picks, n_denials, _n_gsv = logger.record(out)
        if audit_writer is not None:
            audit_writer.write(_audit_record(out, ood_detector))
        total_picks += n_picks
        total_denials += n_denials
    return total_picks, total_denials


# ──────────────────────────────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────────────────────────────


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--cache-root",
        type=Path,
        default=DEFAULT_CACHE_ROOT,
        help="Sportmonks cache root.",
    )
    p.add_argument(
        "--shadow-root",
        type=Path,
        default=DEFAULT_SHADOW_ROOT,
        help="V3 shadow output root.",
    )
    p.add_argument(
        "--ood-path",
        type=Path,
        default=DEFAULT_OOD_PATH,
        help="Path to OOD detector pkl. Use '' to disable.",
    )
    p.add_argument(
        "--pattern-path",
        type=Path,
        default=DEFAULT_PATTERN_PATH,
        help="Path to pattern layer pkl. Use '' to disable.",
    )
    p.add_argument("--max-fixtures", type=int, default=0, help="0 = all fixtures, else cap.")
    p.add_argument(
        "--max-snapshots",
        type=int,
        default=0,
        help="0 = all snapshots per fixture.",
    )
    p.add_argument("--mes-threshold", type=float, default=0.6, help="No-bet rule 5 threshold.")
    p.add_argument(
        "--commentary-required",
        action="store_true",
        help="Enforce no-bet rule 6 strictness.",
    )
    p.add_argument(
        "--audit",
        action="store_true",
        help=("Write per-frame JSONL audit trail under reports/v3/replay_audit/<run_id>.jsonl"),
    )
    p.add_argument(
        "--audit-root",
        type=Path,
        default=DEFAULT_AUDIT_ROOT,
        help="Directory for audit JSONL files when --audit is set.",
    )
    p.add_argument("--log-level", default="INFO")
    return p.parse_args()


def main() -> None:
    args = _parse_args()
    logging.basicConfig(level=args.log_level)
    cache = SportmonksCache(root=args.cache_root)

    # --ood-path '' / --pattern-path '' disables each layer explicitly.
    ood_path = args.ood_path if str(args.ood_path) else None
    pat_path = args.pattern_path if str(args.pattern_path) else None
    ood, pattern = load_detectors(ood_path, pat_path)

    pipeline = V3Pipeline(
        mes_threshold=args.mes_threshold,
        commentary_required=args.commentary_required,
        ood_detector=ood,
        pattern_layer=pattern,
    )
    logger = ShadowLogger(output_root=args.shadow_root)

    audit_writer: AuditJSONLWriter | None = None
    audit_path: Path | None = None
    if args.audit:
        run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S") + "_" + uuid.uuid4().hex[:8]
        audit_path = args.audit_root / f"{run_id}.jsonl"
        audit_writer = AuditJSONLWriter(audit_path)
        log.info("audit mode: writing JSONL to %s", audit_path)

    fixture_ids = cache.list_fixtures()
    if args.max_fixtures:
        fixture_ids = fixture_ids[: args.max_fixtures]
    log.info("v3 replay: %d fixtures", len(fixture_ids))

    tot_picks = 0
    tot_denials = 0
    try:
        for fid in fixture_ids:
            n_p, n_d = replay_one_fixture(
                fid,
                cache,
                pipeline,
                logger,
                max_snapshots=args.max_snapshots or None,
                audit_writer=audit_writer,
                ood_detector=ood,
            )
            tot_picks += n_p
            tot_denials += n_d
            if (n_p + n_d) > 0:
                log.info("fixture %s — picks=%d denials=%d", fid, n_p, n_d)
    finally:
        if audit_writer is not None:
            audit_writer.close()

    paths = logger.flush()
    log.info("flushed %s", paths)
    log.info("TOTAL: picks=%d denials=%d", tot_picks, tot_denials)
    if audit_path is not None:
        log.info("audit JSONL: %s", audit_path)


if __name__ == "__main__":
    main()
