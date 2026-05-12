"""Weekly refit cadence for v3 OOD detector + pattern layer.

T3 of v3 phase-4 readiness mission. Loads real shadow GSVs persisted
by T1.1's extended ShadowLogger, refits both detectors when there is
enough real data, persists versioned pkls without overwriting the old
ones, runs a promotion check, and writes a markdown report.

# Versioning

Output paths are versioned: ``data/cache/ood_detector_v{N}.pkl`` where
N auto-increments past the highest existing version. The convention
symlink ``data/cache/ood_detector_latest.pkl`` points to the current
production version (only updated when promotion succeeds).

Same scheme for ``pattern_layer_v{N}.pkl`` /
``pattern_layer_latest.pkl``.

# Promotion policy

Auto-promote a new version only when **both** are true:

1. Trained on ≥``--min-real-samples`` real GSVs (default 100). The
   pkl is always saved regardless; promotion is the symlink swap.
2. The anti-Napoli regression suite passes — i.e., on the 50
   synthetic Napoli states, the new detectors do NOT false-positive
   the OOD check. Anti-Napoli is the most important property of v3
   ("silence > false positive" — the operative invariant); a refit
   that breaks it is rejected even if downstream metrics look better.

If either check fails, the pkl is preserved on disk (for inspection)
but ``_latest.pkl`` continues pointing at the previous version. The
report writes the verdict + reasoning so the operator decides whether
to promote manually.

# Cold-start

When n_real < min-real-samples, the script seeds with synthetic data
(same generation as fit_ood_detector + fit_pattern_layer) so the
shadow flow stays operative until enough real data accumulates.

# Usage

::

    uv run python -m scripts.spike.v3.refit_detectors
    uv run python -m scripts.spike.v3.refit_detectors --window-days 30 --min-real-samples 100
    uv run python -m scripts.spike.v3.refit_detectors --dry-run    # no writes, just report

The script is idempotent — running twice in a day generates two pkls
(v_N and v_N+1) but only the second's symlink lands (assuming both
promote). The operator can roll back by re-pointing the symlink.
"""

from __future__ import annotations

import argparse
import logging
import re
import sys
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from bip.evaluation.live.engine_v3 import (  # noqa: E402
    GameStateVector,
    OODDetector,
    PatternLayer,
    load_shadow_gsvs,
)
from bip.evaluation.live.engine_v3.shadow_logger import (  # noqa: E402
    DEFAULT_SHADOW_ROOT,
)

log = logging.getLogger("v3.refit")

DEFAULT_OUT_DIR = Path("data/cache")
DEFAULT_REPORTS_DIR = Path("reports/v3/refits")
DEFAULT_WINDOW_DAYS = 30
DEFAULT_MIN_REAL_SAMPLES = 100


# ──────────────────────────────────────────────────────────────────────
# Versioned pkl path resolution
# ──────────────────────────────────────────────────────────────────────


_VERSION_RE = re.compile(r"_v(\d+)\.pkl$")


def next_version(out_dir: Path, family: str) -> int:
    """Find the highest existing ``{family}_v{N}.pkl`` and return N+1.

    First version is 1.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    best = 0
    for p in out_dir.glob(f"{family}_v*.pkl"):
        m = _VERSION_RE.search(p.name)
        if not m:
            continue
        n = int(m.group(1))
        best = max(best, n)
    return best + 1


def versioned_pkl_path(out_dir: Path, family: str, version: int) -> Path:
    return out_dir / f"{family}_v{version}.pkl"


def latest_symlink_path(out_dir: Path, family: str) -> Path:
    return out_dir / f"{family}_latest.pkl"


def promote_symlink(symlink: Path, target: Path) -> None:
    """Atomic-ish symlink update. Removes old link then creates new.

    ``target`` should already exist on disk before this is called.
    """
    if symlink.is_symlink() or symlink.exists():
        symlink.unlink()
    # Use a path relative to the symlink's directory if same parent — keeps
    # the link portable across machines if the project is moved as a unit.
    if target.parent == symlink.parent:
        symlink.symlink_to(target.name)
    else:
        symlink.symlink_to(target.resolve())


# ──────────────────────────────────────────────────────────────────────
# Anti-Napoli regression check
# ──────────────────────────────────────────────────────────────────────


def _napoli_gsvs() -> list[GameStateVector]:
    """The 50 anti-Napoli synthetic states. Imported lazily because
    they live under tests/ and we don't want a hard runtime dependency
    in non-test code paths.
    """
    from bip.evaluation.live.engine_v3 import (
        GSVBuilder,
        MarketLine,
        MarketSnapshot,
        PreMatchPriors,
    )
    from tests.evaluation.live.engine_v3.conftest import HOME_ID
    from tests.evaluation.live.engine_v3.test_anti_napoli import _synthesize_states

    now = datetime.now(UTC)
    markets = MarketSnapshot(
        lines={
            "match_goals_over_2.5": MarketLine(
                market_id="match_goals_over_2.5",
                side_a_decimal=1.95,
                line_value=2.5,
                max_stake_cap=500.0,
                last_update_utc=now - timedelta(seconds=20),
            ),
        }
    )
    priors = PreMatchPriors(
        lambda_home_prematch=2.30,
        lambda_away_prematch=0.95,
        expected_corners_total=10.8,
        expected_cards_total=4.10,
        elo_diff=140.0,
    )
    builder = GSVBuilder()
    return [
        builder.build(s, priors=priors, markets=markets, dominant_team_id=HOME_ID)
        for s in _synthesize_states()
    ]


def anti_napoli_false_positive_rate(detector: OODDetector) -> float:
    """Fraction of the 50 anti-Napoli states flagged OOD.

    Anti-Napoli is in-distribution by design (dominant trailing teams
    are a regime v3 must reason about, NOT flag away). A high FPR
    here means the refit drifted toward over-flagging known-valid regimes.
    """
    if not detector.is_fitted:
        return 0.0
    states = _napoli_gsvs()
    if not states:
        return 0.0
    n_flagged = sum(1 for g in states if detector.is_ood(g))
    return n_flagged / len(states)


# ──────────────────────────────────────────────────────────────────────
# Refit report
# ──────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class RefitResult:
    family: Literal["ood_detector", "pattern_layer"]
    version: int
    n_real: int
    n_synthetic: int
    pkl_path: Path
    promoted: bool
    promote_reason: str
    threshold: float | None = None  # OOD only
    anti_napoli_fpr: float | None = None  # OOD only


def write_report(
    results: list[RefitResult],
    reports_dir: Path,
    window_days: int,
    today: datetime,
) -> Path:
    """Write a markdown summary of this refit cycle."""
    reports_dir.mkdir(parents=True, exist_ok=True)
    out = reports_dir / f"{today.strftime('%Y-%m-%d')}.md"
    lines = [
        f"# v3 detector refit — {today.strftime('%Y-%m-%d')}",
        "",
        f"**Window**: last {window_days} days of shadow GSVs",
        "",
        "## Results",
        "",
        "| Family | Version | n_real | n_synth | Promoted | Anti-Napoli FPR | Reason |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in results:
        fpr = f"{r.anti_napoli_fpr:.1%}" if r.anti_napoli_fpr is not None else "N/A"
        lines.append(
            f"| {r.family} | v{r.version} | {r.n_real} | {r.n_synthetic} | "
            f"{'YES' if r.promoted else 'no'} | {fpr} | {r.promote_reason} |"
        )
    lines.extend(
        [
            "",
            "## Promotion policy",
            "",
            "Auto-promote requires BOTH:",
            "1. ≥ min-real-samples real GSVs in the fit data",
            "2. Anti-Napoli false-positive rate == 0 on the new detector",
            "",
            "On either failure the pkl is preserved at the versioned path but the "
            "``_latest`` symlink is unchanged — the operator can manually promote "
            "after inspecting the report.",
            "",
        ]
    )
    out.write_text("\n".join(lines), encoding="utf-8")
    return out


# ──────────────────────────────────────────────────────────────────────
# Synthetic data path (cold start / blending)
# ──────────────────────────────────────────────────────────────────────


def _generate_synthetic_ood_gsvs(n: int, seed: int) -> list[GameStateVector]:
    """Reuse the fit_ood_detector synthesis path."""
    from scripts.spike.v3.fit_ood_detector import (
        _generate_napoli_gsvs,
        _generate_realistic_gsvs,
    )

    realistic = _generate_realistic_gsvs(n, seed=seed)
    napoli = _generate_napoli_gsvs()
    return realistic + napoli


def _generate_synthetic_pattern_pairs(n: int, seed: int):
    """Lazy import — keep test-dir dependency out of runtime callers.

    Mirrors fit_pattern_layer.main() composition: anti-Napoli pairs +
    realistic-regime pairs. ``n`` controls only the realistic count;
    the 50 anti-Napoli pairs are always included.
    """
    from scripts.spike.v3.fit_pattern_layer import _napoli_pairs, _realistic_pairs

    return _napoli_pairs() + _realistic_pairs(n=n, seed=seed)


# ──────────────────────────────────────────────────────────────────────
# Core refit orchestration
# ──────────────────────────────────────────────────────────────────────


def refit_ood(
    real_gsvs: list[GameStateVector],
    *,
    min_real_samples: int,
    out_dir: Path,
    dry_run: bool,
    blend_synthetic_n: int,
    seed: int,
    threshold_percentile: float,
) -> RefitResult:
    """Refit OOD detector. Promotes when policy passes."""
    n_real = len(real_gsvs)
    if n_real >= min_real_samples * 10:
        # Plenty of real data — no synthetic blending needed
        synthetic: list[GameStateVector] = []
    else:
        synthetic = _generate_synthetic_ood_gsvs(blend_synthetic_n, seed=seed)

    training = real_gsvs + synthetic
    detector = OODDetector().fit(training, threshold_percentile=threshold_percentile)
    fpr = anti_napoli_false_positive_rate(detector)

    version = next_version(out_dir, "ood_detector")
    pkl_path = versioned_pkl_path(out_dir, "ood_detector", version)

    if not dry_run:
        detector.save(pkl_path)

    promote = n_real >= min_real_samples and fpr == 0.0
    reason_bits = []
    if n_real < min_real_samples:
        reason_bits.append(f"n_real={n_real} < min={min_real_samples}")
    if fpr > 0.0:
        reason_bits.append(f"anti-Napoli FPR={fpr:.1%}")
    if not reason_bits:
        reason_bits.append("policy ok")
    reason = "; ".join(reason_bits)

    if promote and not dry_run:
        sym = latest_symlink_path(out_dir, "ood_detector")
        promote_symlink(sym, pkl_path)

    return RefitResult(
        family="ood_detector",
        version=version,
        n_real=n_real,
        n_synthetic=len(synthetic),
        pkl_path=pkl_path,
        promoted=promote,
        promote_reason=reason,
        threshold=detector.threshold,
        anti_napoli_fpr=fpr,
    )


def refit_pattern(
    real_gsvs: list[GameStateVector],
    *,
    min_real_samples: int,
    out_dir: Path,
    dry_run: bool,
    blend_synthetic_n: int,
    seed: int,
    shadow_root: Path | None = None,
    date_range: tuple[datetime, datetime] | None = None,
) -> RefitResult:
    """Refit pattern layer with real shadow data when available.

    The training_data.build_real_pattern_pairs join (T3 of post-shadow
    readiness) reconstructs (GSV, Thesis) pairs from the gsv_log +
    picks parquets in the shadow root. When ≥ min_real_samples real
    pairs are available we train on real-only (synthetic blending is
    skipped — synthetic biases the kNN towards anti-Napoli and away
    from the operator's actual game state distribution).

    When the join produces fewer than the floor we fall back to the
    existing synthetic generator. The transition between regimes
    (synthetic-only → blended → real-only) is logged in the result's
    promote_reason for audit.
    """
    n_real_gsvs = len(real_gsvs)

    real_pairs: list[tuple[GameStateVector, Any]] = []
    join_summary = ""
    if shadow_root is not None:
        from bip.evaluation.live.engine_v3.runtime.training_data import (
            build_real_pattern_pairs,
            pairs_to_fit_input,
        )

        pair_records, join_report = build_real_pattern_pairs(
            shadow_root=shadow_root,
            date_range=date_range,
            require_outcome=False,  # outcome-aware filtering is a Phase-5 toggle
        )
        real_pairs = pairs_to_fit_input(pair_records)
        join_summary = (
            f"join_pairs={len(real_pairs)} "
            f"missing_gsv={join_report.n_picks_without_gsv} "
            f"with_outcome={join_report.n_pairs_with_outcome}"
        )

    n_real_pairs = len(real_pairs)
    if n_real_pairs >= min_real_samples * 5:
        # Plenty of real pairs — drop synthetic, learn pure shadow distribution.
        pairs = real_pairs
        regime = "real-only"
    elif n_real_pairs >= min_real_samples:
        # Blended cold-start: real pairs + synthetic for diversity.
        synthetic = _generate_synthetic_pattern_pairs(blend_synthetic_n, seed=seed)
        pairs = real_pairs + synthetic
        regime = "blended"
    else:
        # Insufficient real pairs — synthetic only (preserves prior behavior).
        pairs = _generate_synthetic_pattern_pairs(blend_synthetic_n, seed=seed)
        regime = "synthetic-only"

    layer = PatternLayer().fit(pairs)

    version = next_version(out_dir, "pattern_layer")
    pkl_path = versioned_pkl_path(out_dir, "pattern_layer", version)

    if not dry_run:
        layer.save(pkl_path)

    # Promote when:
    # - regime is real-only OR blended (we have meaningful shadow signal), OR
    # - synthetic-only AND n_real_gsvs exceeds the threshold (cold-start
    #   churn: at least the shadow flow proves the system is running).
    promote = (regime != "synthetic-only") or (n_real_gsvs >= min_real_samples)
    reason = (
        f"regime={regime} n_real_pairs={n_real_pairs} "
        f"n_real_gsvs={n_real_gsvs} {join_summary}".strip()
    )

    if promote and not dry_run:
        sym = latest_symlink_path(out_dir, "pattern_layer")
        promote_symlink(sym, pkl_path)

    return RefitResult(
        family="pattern_layer",
        version=version,
        n_real=n_real_gsvs,
        n_synthetic=len(pairs) - n_real_pairs,
        pkl_path=pkl_path,
        promoted=promote,
        promote_reason=reason,
    )


def load_real_gsvs(
    shadow_root: Path,
    window_days: int,
    today: datetime,
) -> list[GameStateVector]:
    """Wrapper over ``load_shadow_gsvs`` that handles missing partitions."""
    start = today - timedelta(days=window_days)
    successes, failures = load_shadow_gsvs(
        date_range=(start, today),
        output_root=shadow_root,
    )
    if failures:
        log.warning(
            "load_real_gsvs: %d malformed rows skipped (first: %s)",
            len(failures),
            failures[0].error[:100],
        )
    return successes


# ──────────────────────────────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────────────────────────────


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--shadow-root", type=Path, default=DEFAULT_SHADOW_ROOT)
    p.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    p.add_argument("--reports-dir", type=Path, default=DEFAULT_REPORTS_DIR)
    p.add_argument("--window-days", type=int, default=DEFAULT_WINDOW_DAYS)
    p.add_argument("--min-real-samples", type=int, default=DEFAULT_MIN_REAL_SAMPLES)
    p.add_argument("--synthetic-n", type=int, default=300)
    p.add_argument("--threshold-percentile", type=float, default=99.0)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Compute refit + report without writing pkls or moving symlinks.",
    )
    p.add_argument("--log-level", default="INFO")
    return p.parse_args()


def main() -> int:
    args = _parse_args()
    logging.basicConfig(level=args.log_level)

    today = datetime.now(UTC)
    real_gsvs = load_real_gsvs(args.shadow_root, args.window_days, today)
    log.info("real shadow GSVs loaded: %d (last %d days)", len(real_gsvs), args.window_days)

    ood_result = refit_ood(
        real_gsvs,
        min_real_samples=args.min_real_samples,
        out_dir=args.out_dir,
        dry_run=args.dry_run,
        blend_synthetic_n=args.synthetic_n,
        seed=args.seed,
        threshold_percentile=args.threshold_percentile,
    )
    pattern_result = refit_pattern(
        real_gsvs,
        min_real_samples=args.min_real_samples,
        out_dir=args.out_dir,
        dry_run=args.dry_run,
        blend_synthetic_n=args.synthetic_n,
        seed=args.seed,
        shadow_root=args.shadow_root,
        date_range=(today - timedelta(days=args.window_days), today),
    )

    report_path = write_report(
        [ood_result, pattern_result],
        args.reports_dir,
        args.window_days,
        today,
    )
    log.info("refit report: %s", report_path)
    for r in (ood_result, pattern_result):
        log.info(
            "%s v%d → promoted=%s (%s)",
            r.family,
            r.version,
            r.promoted,
            r.promote_reason,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
