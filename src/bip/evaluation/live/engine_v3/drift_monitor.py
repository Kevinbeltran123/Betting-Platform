"""Calibration drift monitor — sec 5.6 of LIVE_ENGINE_V3_DESIGN.md.

Watches each ``(market_family, minute_bucket)`` cell with a rolling
window of recent settled picks. On every new observation:

1. Compute the empirical win rate over the last ``window_size``
   observations in the cell.
2. Compute the expected win rate (mean of predicted_p over the same
   window).
3. Run a two-sample Kolmogorov-Smirnov test between predicted
   probabilities and outcomes (interpreted as a binary distribution).
4. If the KS test rejects at p < 0.01 the cell is flagged as
   *drifted* — the calibration there is no longer valid, the operator
   should pause picks from that cell and recalibrate.

Why KS, not Brier:
- Brier score is a point-wise quality metric. Drift is about a
  distributional shift between "what the predictor thinks" and "what
  the world produced". KS detects shape changes (skew, polarisation)
  that average-based metrics miss.

Why per (family, minute_bucket):
- Calibration drift is rarely global. Sec 5.6 explicitly says cells
  drift independently — a goals 60-75 cell can stay aligned while
  btts 75-90 falls off when the bookmaker tightens late lines.

Why rolling, not cumulative:
- A 200-pick window forgets last week's regime. Calibration that was
  valid 3 months ago may be invalid today; the rolling window forces
  the monitor to look at recent observations only.

Operational contract:
- ``observe(family, minute, predicted_p, outcome)`` appends to the
  cell's window, oldest dropped past ``window_size``.
- ``status(family, minute)`` returns a ``DriftStatus`` with the
  current empirical wr, expected wr, KS p-value, and a boolean
  ``is_drifted`` flag.
- ``drifted_cells()`` returns all (family, bucket) pairs currently
  failing the test — the operator-facing summary.

Thread-safety: a single ``threading.Lock`` guards mutation. Live
ingestion of one observation at a time is the only writer; readers can
call ``status`` / ``drifted_cells`` freely.

Phase-3 will:
- Persist observation history to parquet (currently in-memory only).
- Auto-suspend the cell in the no-bet gate when ``is_drifted`` flips.
- Recalibrate the IsotonicCalibrator cell from the new observations.
"""
from __future__ import annotations

import threading
from collections import deque
from dataclasses import dataclass, field
from typing import Deque

import numpy as np
from scipy import stats  # type: ignore[import-untyped]

from bip.evaluation.live.engine_v3.calibrator import minute_bucket
from bip.evaluation.live.engine_v3.thesis import MarketFamily


# ──────────────────────────────────────────────────────────────────────
# DriftStatus — per-cell snapshot
# ──────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class DriftStatus:
    """Per-cell calibration health snapshot."""

    family: str
    minute_bucket: str
    n: int
    empirical_win_rate: float
    expected_win_rate: float
    ks_statistic: float
    ks_p_value: float
    is_drifted: bool
    is_warm: bool  # True once ``n >= min_observations``


# ──────────────────────────────────────────────────────────────────────
# Per-cell rolling window
# ──────────────────────────────────────────────────────────────────────


@dataclass
class _CellWindow:
    """Rolling buffer of (predicted_p, outcome) pairs for one cell."""

    predicted_ps: Deque[float] = field(default_factory=deque)
    outcomes: Deque[int] = field(default_factory=deque)

    def append(self, p: float, outcome: int, max_size: int) -> None:
        self.predicted_ps.append(p)
        self.outcomes.append(outcome)
        while len(self.predicted_ps) > max_size:
            self.predicted_ps.popleft()
            self.outcomes.popleft()

    def __len__(self) -> int:
        return len(self.predicted_ps)


# ──────────────────────────────────────────────────────────────────────
# Monitor
# ──────────────────────────────────────────────────────────────────────


_DEFAULT_WINDOW = 200
_DEFAULT_MIN_OBS = 30
_DEFAULT_KS_ALPHA = 0.01


@dataclass
class CalibrationDriftMonitor:
    """Per-cell rolling drift monitor.

    Use one monitor per process. Persistence is the caller's job
    (Phase 3); for Phase 2, the monitor is rebuildable by replaying
    settled picks.
    """

    window_size: int = _DEFAULT_WINDOW
    min_observations: int = _DEFAULT_MIN_OBS
    ks_alpha: float = _DEFAULT_KS_ALPHA
    _cells: dict[tuple[str, str], _CellWindow] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    # ── ingestion ──────────────────────────────────────────────────────

    def observe(
        self,
        family: MarketFamily,
        minute: int,
        predicted_p: float,
        outcome: int,
    ) -> None:
        """Record one settled-pick observation in the appropriate cell.

        ``outcome`` is 1 for win, 0 for loss. Push / void picks should
        not be recorded — they're not informative for calibration.
        """
        if outcome not in (0, 1):
            raise ValueError(f"outcome must be 0 or 1, got {outcome!r}")
        bucket = minute_bucket(minute)
        key = (family.value, bucket)
        with self._lock:
            cell = self._cells.setdefault(key, _CellWindow())
            cell.append(float(predicted_p), int(outcome), self.window_size)

    # ── inspection ────────────────────────────────────────────────────

    def status(self, family: MarketFamily, minute: int) -> DriftStatus:
        bucket = minute_bucket(minute)
        key = (family.value, bucket)
        with self._lock:
            cell = self._cells.get(key)
            if cell is None or len(cell) == 0:
                return DriftStatus(
                    family=family.value,
                    minute_bucket=bucket,
                    n=0,
                    empirical_win_rate=0.0,
                    expected_win_rate=0.0,
                    ks_statistic=0.0,
                    ks_p_value=1.0,
                    is_drifted=False,
                    is_warm=False,
                )
            xs = np.asarray(list(cell.predicted_ps), dtype=np.float64)
            ys = np.asarray(list(cell.outcomes), dtype=np.float64)
        n = len(xs)
        is_warm = n >= self.min_observations
        empirical = float(ys.mean())
        expected = float(xs.mean())
        # Two-sample KS between predicted probabilities and outcomes.
        # Note: outcomes are 0/1 — a degenerate CDF. KS still meaningful as
        # a "is the predicted distribution consistent with these binary
        # observations" test, the same statistic used in the design doc.
        if is_warm:
            stat, pval = stats.ks_2samp(xs, ys)
            stat = float(stat)
            pval = float(pval)
        else:
            stat = 0.0
            pval = 1.0
        is_drifted = is_warm and pval < self.ks_alpha
        return DriftStatus(
            family=family.value,
            minute_bucket=bucket,
            n=n,
            empirical_win_rate=empirical,
            expected_win_rate=expected,
            ks_statistic=stat,
            ks_p_value=pval,
            is_drifted=is_drifted,
            is_warm=is_warm,
        )

    def drifted_cells(self) -> list[DriftStatus]:
        """All cells currently flagged drifted. Operator-facing summary."""
        out: list[DriftStatus] = []
        with self._lock:
            keys = list(self._cells.keys())
        for fam_str, bucket in keys:
            # Recover a representative minute for this bucket. Use the
            # midpoint of the bucket label, which keeps minute_bucket()
            # consistent.
            mid = _bucket_midpoint(bucket)
            try:
                fam = MarketFamily(fam_str)
            except ValueError:
                continue
            s = self.status(fam, mid)
            if s.is_drifted:
                out.append(s)
        return out

    def coverage(self) -> dict[str, dict[str, int]]:
        out: dict[str, dict[str, int]] = {}
        with self._lock:
            for (fam, bucket), cell in self._cells.items():
                out.setdefault(fam, {})[bucket] = len(cell)
        return out


def _bucket_midpoint(bucket: str) -> int:
    """Approximate minute representative for a bucket label."""
    table = {
        "0-15": 7,
        "15-30": 22,
        "30-45": 37,
        "45-60": 52,
        "60-75": 67,
        "75-90": 82,
        "90+": 95,
    }
    return table.get(bucket, 45)


__all__ = ["CalibrationDriftMonitor", "DriftStatus"]
