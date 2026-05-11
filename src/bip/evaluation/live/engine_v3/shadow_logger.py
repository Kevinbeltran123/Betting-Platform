"""Shadow-mode pick logger — appends V3 PipelineOutput to parquet.

Phase 2 deliverable from sec 10. The output structure mirrors the
``LineRecorder`` pattern: daily partitions under
``data/cache/v3_shadow/dt=YYYY-MM-DD/{picks,gate_denials}.parquet``.

Two files per day:

- ``picks.parquet``: one row per allowed candidate (the would-be bet)
- ``gate_denials.parquet``: one row per rejected candidate with rule
  number + reason (sec 7.2 audit trail requirement)

The shadow output is read-only from the operator's perspective — Phase
2 of sec 10 forbids routing these to Telegram. They feed the Phase-2
comparison: v3 shadow ROI vs current-system ROI on the same fixture
cohort.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from bip.evaluation.live.engine_v3.pipeline import PipelineOutput

DEFAULT_SHADOW_ROOT = Path("data/cache/v3_shadow")


def _date_partition(ts: datetime) -> str:
    return ts.strftime("dt=%Y-%m-%d")


def _pick_row(pick, fixture_id: int, ts: datetime) -> dict[str, Any]:
    t = pick.full_thesis
    return {
        "fixture_id": int(fixture_id),
        "timestamp_utc": ts,
        "thesis_id": t.id,
        "archetype": t.archetype.value,
        "thesis_layer": t.source.layer,
        "rule_id": t.source.identifier,
        "family": t.prediction.family.value,
        "direction": t.prediction.direction,
        "magnitude_pp": float(t.prediction.magnitude_pp),
        "horizon_minutes": int(t.prediction.horizon.horizon_minutes),
        "market_id": pick.candidate.market_id,
        "fair_prob": float(pick.candidate.fair_prob),
        "base_edge": float(pick.candidate.mes.base_edge),
        "signal_clarity": float(pick.candidate.mes.signal_clarity),
        "book_slowness": float(pick.candidate.mes.book_slowness),
        "liquidity_score": float(pick.candidate.mes.liquidity_score),
        "conditional_variance": float(pick.candidate.mes.conditional_variance),
        "mes_score": float(pick.candidate.mes.score),
        "confidence_prior": float(t.confidence_prior),
        "activated_at_minute": int(t.activated_at_minute),
    }


def _denial_row(result, fixture_id: int, ts: datetime) -> dict[str, Any]:
    cand = result.candidate
    return {
        "fixture_id": int(fixture_id),
        "timestamp_utc": ts,
        "thesis_id": cand.thesis.id,
        "archetype": cand.thesis.archetype.value,
        "family": cand.family.value,
        "market_id": cand.market_id,
        "rule_number": int(result.verdict.rule_number or 0),
        "reason": result.verdict.reason,
        "mes_score": float(cand.mes.score),
        "direction": cand.thesis.prediction.direction,
    }


class ShadowLogger:
    """Buffered parquet logger for shadow picks + gate denials."""

    def __init__(self, output_root: Path | str = DEFAULT_SHADOW_ROOT) -> None:
        self.output_root = Path(output_root)
        self._pick_buf: list[dict[str, Any]] = []
        self._denial_buf: list[dict[str, Any]] = []

    def record(self, output: PipelineOutput) -> tuple[int, int]:
        """Append the picks + denials from one pipeline frame.

        Returns ``(n_picks, n_denials)`` recorded this call."""
        ts = output.gsv.timestamp_utc
        fixture_id = output.gsv.fixture_id

        for pick in output.allowed_picks:
            self._pick_buf.append(_pick_row(pick, fixture_id, ts))

        for r in output.gate_results:
            if r.verdict.allowed:
                continue
            self._denial_buf.append(_denial_row(r, fixture_id, ts))

        return len(output.allowed_picks), sum(
            1 for r in output.gate_results if not r.verdict.allowed
        )

    def flush(self, timestamp_utc: datetime | None = None) -> dict[str, Path]:
        """Write buffers to parquet partitions.

        Returns dict keyed by ``picks``/``denials`` to the parquet path
        written, omitting entries that were empty."""
        out: dict[str, Path] = {}
        ts = timestamp_utc or datetime.now(timezone.utc)
        date_dir = self.output_root / _date_partition(ts)
        date_dir.mkdir(parents=True, exist_ok=True)

        if self._pick_buf:
            path = date_dir / "picks.parquet"
            self._append_parquet(path, self._pick_buf)
            self._pick_buf.clear()
            out["picks"] = path

        if self._denial_buf:
            path = date_dir / "gate_denials.parquet"
            self._append_parquet(path, self._denial_buf)
            self._denial_buf.clear()
            out["denials"] = path

        return out

    def buffer_size(self) -> tuple[int, int]:
        return len(self._pick_buf), len(self._denial_buf)

    @staticmethod
    def _append_parquet(path: Path, rows: list[dict[str, Any]]) -> None:
        import polars as pl
        new_df = pl.DataFrame(rows)
        if path.exists():
            try:
                existing = pl.read_parquet(path)
                combined = pl.concat([existing, new_df], how="diagonal_relaxed")
            except Exception:
                combined = new_df
        else:
            combined = new_df
        combined.write_parquet(path)


__all__ = ["DEFAULT_SHADOW_ROOT", "ShadowLogger"]
