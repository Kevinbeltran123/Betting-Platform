"""Tests for ``scripts.spike.v3.replay_shadow``.

T1.2 invariants:
- ``load_detectors`` returns ``(None, None)`` and logs (no crash) when
  pkls are missing.
- ``load_detectors`` round-trips when valid pkls exist.
- ``_audit_record`` emits the expected schema for a frame, including
  ``ood`` block only when the detector is fitted.
- ``AuditJSONLWriter`` writes one JSON line per record, flushes
  on each write, and is safe to use as a context manager.
"""

from __future__ import annotations

import json

import pytest

from bip.evaluation.live.engine_v3 import (
    OODDetector,
    PreMatchPriors,
    V3Pipeline,
)
from scripts.spike.v3.replay_shadow import (
    AuditJSONLWriter,
    _audit_record,
    load_detectors,
)


@pytest.fixture
def priors() -> PreMatchPriors:
    """Mirror of the conftest fixture from tests/evaluation/live/engine_v3.

    Inlined here because tests/spike/v3 has no conftest.py and pytest
    fixture collection does not cross unrelated package boundaries.
    """
    return PreMatchPriors(
        lambda_home_prematch=2.10,
        lambda_away_prematch=0.95,
        expected_corners_total=10.4,
        expected_cards_total=3.95,
        elo_diff=120.0,
    )


# ──────────────────────────────────────────────────────────────────────
# load_detectors
# ──────────────────────────────────────────────────────────────────────


def test_load_detectors_missing_pkls_returns_none_no_crash(tmp_path, caplog):
    """Both paths point nowhere → (None, None) + warning logs."""
    ood_path = tmp_path / "missing_ood.pkl"
    pat_path = tmp_path / "missing_pattern.pkl"
    with caplog.at_level("WARNING"):
        ood, pattern = load_detectors(ood_path, pat_path)
    assert ood is None
    assert pattern is None
    # Both warnings emitted
    warnings = " ".join(r.message for r in caplog.records)
    assert "OOD pkl not found" in warnings
    assert "pattern layer pkl not found" in warnings


def test_load_detectors_none_args_returns_none(tmp_path):
    """Explicit None paths skip the layer (CLI '' value)."""
    ood, pattern = load_detectors(None, None)
    assert ood is None
    assert pattern is None


def test_load_detectors_with_valid_pkl_loads(tmp_path):
    """Save an unfitted OOD detector, reload, verify the load function works."""
    detector = OODDetector()  # unfitted; just exercising save/load
    pkl_path = tmp_path / "test_ood.pkl"
    detector.save(pkl_path)

    ood, pattern = load_detectors(pkl_path, None)
    assert ood is not None
    assert isinstance(ood, OODDetector)
    assert pattern is None


# ──────────────────────────────────────────────────────────────────────
# _audit_record
# ──────────────────────────────────────────────────────────────────────


def _run_pipeline_for_audit(priors):
    """Build a real PipelineOutput from the v3 conftest fixtures."""
    from datetime import datetime, timezone

    from bip.evaluation.live.engine_v3 import MarketLine, MarketSnapshot
    from tests.evaluation.live.engine_v3.conftest import AWAY_ID, HOME_ID, make_state

    state = make_state(home_goals=1, away_goals=0, minute=70, red_card_events=[(25, AWAY_ID)])
    now = datetime.now(timezone.utc)
    markets = MarketSnapshot(
        lines={
            "match_corners_over_10.5": MarketLine(
                market_id="match_corners_over_10.5",
                side_a_decimal=2.10,
                line_value=10.5,
                max_stake_cap=400.0,
                last_update_utc=now,
            ),
        }
    )
    pipeline = V3Pipeline()
    return pipeline.run(state, priors=priors, markets=markets, dominant_team_id=HOME_ID)


def test_audit_record_minimum_schema(priors):
    out = _run_pipeline_for_audit(priors)
    record = _audit_record(out, ood=None)

    for key in (
        "fixture_id",
        "state_version",
        "timestamp_utc",
        "minute",
        "period",
        "score",
        "dominant_losing",
        "n_theses",
        "thesis_layers",
        "thesis_archetypes",
        "n_candidates",
        "candidates",
        "gate_verdicts",
        "allowed_count",
        "denied_count",
        "mispricing_window",
        "ood",
    ):
        assert key in record, f"missing audit key {key}"

    # ood block None when detector is None
    assert record["ood"] is None

    # gate_verdicts has rule_number=None for allowed, int for denied
    for gv in record["gate_verdicts"]:
        if gv["allowed"]:
            assert gv["rule_number"] is None
        else:
            assert isinstance(gv["rule_number"], int)


def test_audit_record_ood_block_populated_when_fitted(priors, monkeypatch):
    """If the detector is fitted and scores cleanly, ood block has data."""
    out = _run_pipeline_for_audit(priors)

    # Construct a minimal "fitted-looking" OOD with a stub score method
    detector = OODDetector()
    detector.is_fitted = True
    detector.threshold = 3.0
    # Patch score() to return a constant so we can assert
    monkeypatch.setattr(detector, "score", lambda gsv: 1.42)
    record = _audit_record(out, ood=detector)
    assert record["ood"] is not None
    assert record["ood"]["score"] == pytest.approx(1.42)
    assert record["ood"]["threshold"] == pytest.approx(3.0)


def test_audit_record_jsonable(priors):
    """The record must round-trip through json without crashing."""
    out = _run_pipeline_for_audit(priors)
    record = _audit_record(out, ood=None)
    blob = json.dumps(record)
    reloaded = json.loads(blob)
    assert reloaded["fixture_id"] == record["fixture_id"]


# ──────────────────────────────────────────────────────────────────────
# AuditJSONLWriter
# ──────────────────────────────────────────────────────────────────────


def test_audit_writer_writes_one_line_per_record(tmp_path):
    path = tmp_path / "audit_test.jsonl"
    with AuditJSONLWriter(path) as writer:
        writer.write({"a": 1})
        writer.write({"b": 2})

    lines = path.read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) == 2
    assert json.loads(lines[0]) == {"a": 1}
    assert json.loads(lines[1]) == {"b": 2}


def test_audit_writer_creates_parent_directory(tmp_path):
    path = tmp_path / "nested" / "subdir" / "audit.jsonl"
    with AuditJSONLWriter(path) as writer:
        writer.write({"hello": "world"})
    assert path.exists()
    assert json.loads(path.read_text(encoding="utf-8").strip()) == {"hello": "world"}


def test_audit_writer_close_idempotent(tmp_path):
    """Closing twice should not raise."""
    path = tmp_path / "audit.jsonl"
    writer = AuditJSONLWriter(path)
    writer.write({"x": 1})
    writer.close()
    writer.close()  # second close — must not crash
