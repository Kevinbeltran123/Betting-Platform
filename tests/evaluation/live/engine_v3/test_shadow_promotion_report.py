"""Tests for scripts/spike/v3/shadow_promotion_report.py.

All tests are OFFLINE — synthetic gate_denials.parquet + stubbed grader.
No network calls, no Sportmonks client.

Coverage:
- _read_shadow_denials reads only is_shadow=True rows from date range.
- _compute_rule_result produces deterministic per-rule deltas.
- effective_N column present in every RulePromotionResult.
- build_promotion_report with stubbed grader produces expected P/L and
  recommendation for a simple scenario.
- KEEP-SHADOW emitted when effective_N < MIN_EFFECTIVE_N.
- PROMOTE emitted when delta_pl > 0 and data is sufficient.
- REVERT emitted when delta_pl < -REVERT_LOSS_THRESHOLD and data is sufficient.
- _format_markdown and _format_json produce well-formed output with all rules present.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from datetime import UTC, date, datetime, timezone
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock

import polars as pl
import pytest

from scripts.spike.v3.shadow_promotion_report import (
    MIN_EFFECTIVE_N,
    REVERT_LOSS_THRESHOLD,
    PromotionReport,
    RulePromotionResult,
    _compute_rule_result,
    _format_json,
    _format_markdown,
    _grade_denial_rows,
    _read_shadow_denials,
    _recommend,
    build_promotion_report,
)


# ──────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────

DATE = "2026-05-15"
DATE_DT = datetime(2026, 5, 15, 20, 0, 0, tzinfo=UTC)


def _write_denials_parquet(path: Path, rows: list[dict]) -> None:
    """Write a gate_denials.parquet to path."""
    path.parent.mkdir(parents=True, exist_ok=True)
    pl.DataFrame(rows).write_parquet(path)


def _make_denial_row(
    fixture_id: int = 1001,
    thesis_id: str = "t-001",
    rule_number: int = 8,
    is_shadow: bool = True,
    family: str = "goals",
    direction: str = "over",
) -> dict:
    return {
        "fixture_id": fixture_id,
        "timestamp_utc": DATE_DT,
        "thesis_id": thesis_id,
        "archetype": "momentum_collapse",
        "family": family,
        "market_id": f"match_goals_over_2.5",
        "rule_number": rule_number,
        "reason": f"shadow_rule_{rule_number}",
        "mes_score": 3.5,
        "direction": direction,
        "is_shadow": is_shadow,
    }


@dataclass
class _FakeGradedPick:
    fixture_id: int
    thesis_id: str
    market_id: str
    pick_timestamp_utc: Any
    status: str
    profit_units: float
    bookmaker_odd: float | None
    settled_at: Any


def _stub_grader_client(graded_picks: list[_FakeGradedPick]) -> Any:
    """Return a mock grader client. grade_picks_for_date returns the given picks."""
    from bip.evaluation.live.engine_v3.runtime.v3_grader import GradeReport

    client = AsyncMock()

    async def _grade(date_iso: str, *, shadow_root: Path, client: Any):
        report = GradeReport(
            n_picks_input=len(graded_picks),
            n_fixtures=len({p.fixture_id for p in graded_picks}),
            n_fixtures_finished=len({p.fixture_id for p in graded_picks}),
            n_won=sum(1 for p in graded_picks if p.status == "won"),
            n_lost=sum(1 for p in graded_picks if p.status == "lost"),
            n_void=0,
            n_pending=0,
            n_ungradable=0,
        )
        return graded_picks, report

    return _grade


# ──────────────────────────────────────────────────────────────────────
# _read_shadow_denials
# ──────────────────────────────────────────────────────────────────────


class TestReadShadowDenials:
    def test_reads_only_is_shadow_true(self, tmp_path: Path):
        part_dir = tmp_path / f"dt={DATE}"
        rows = [
            _make_denial_row(thesis_id="shadow", is_shadow=True),
            _make_denial_row(thesis_id="enforced", is_shadow=False),
        ]
        _write_denials_parquet(part_dir / "gate_denials.parquet", rows)

        result = _read_shadow_denials(tmp_path, DATE, DATE)
        assert len(result) == 1
        assert result[0]["thesis_id"] == "shadow"

    def test_returns_empty_when_no_shadow_rows(self, tmp_path: Path):
        part_dir = tmp_path / f"dt={DATE}"
        rows = [_make_denial_row(is_shadow=False)]
        _write_denials_parquet(part_dir / "gate_denials.parquet", rows)

        result = _read_shadow_denials(tmp_path, DATE, DATE)
        assert result == []

    def test_filters_by_date_range(self, tmp_path: Path):
        # Write rows for two dates
        for d in ["2026-05-14", "2026-05-15", "2026-05-16"]:
            part_dir = tmp_path / f"dt={d}"
            _write_denials_parquet(
                part_dir / "gate_denials.parquet",
                [_make_denial_row(thesis_id=f"t-{d}", is_shadow=True)],
            )
        # Only request 2026-05-14 to 2026-05-15
        result = _read_shadow_denials(tmp_path, "2026-05-14", "2026-05-15")
        thesis_ids = {r["thesis_id"] for r in result}
        assert "t-2026-05-14" in thesis_ids
        assert "t-2026-05-15" in thesis_ids
        assert "t-2026-05-16" not in thesis_ids

    def test_returns_empty_when_no_parquets(self, tmp_path: Path):
        result = _read_shadow_denials(tmp_path, DATE, DATE)
        assert result == []

    def test_skips_partitions_without_is_shadow_column(self, tmp_path: Path):
        """Parquet without is_shadow column should be silently skipped."""
        part_dir = tmp_path / f"dt={DATE}"
        part_dir.mkdir(parents=True)
        # Write parquet without is_shadow column
        pl.DataFrame([{"fixture_id": 1, "thesis_id": "t1", "rule_number": 8}]).write_parquet(
            part_dir / "gate_denials.parquet"
        )
        result = _read_shadow_denials(tmp_path, DATE, DATE)
        assert result == []


# ──────────────────────────────────────────────────────────────────────
# _recommend
# ──────────────────────────────────────────────────────────────────────


class TestRecommend:
    def test_keep_shadow_when_insufficient_data(self):
        rec, notes = _recommend(n=3, effective_N=2, delta_pl=5.0, delta_precision=0.1)
        assert rec == "KEEP-SHADOW"
        assert "Insufficient" in notes

    def test_revert_when_large_negative_pl(self):
        rec, notes = _recommend(
            n=10, effective_N=MIN_EFFECTIVE_N, delta_pl=-REVERT_LOSS_THRESHOLD - 0.1, delta_precision=-0.1
        )
        assert rec == "REVERT"

    def test_promote_when_positive_pl_and_sufficient_data(self):
        rec, notes = _recommend(
            n=10, effective_N=MIN_EFFECTIVE_N, delta_pl=3.0, delta_precision=0.05
        )
        assert rec == "PROMOTE"

    def test_keep_shadow_on_mixed_signals(self):
        rec, notes = _recommend(
            n=10, effective_N=MIN_EFFECTIVE_N, delta_pl=0.5, delta_precision=-0.1
        )
        assert rec == "KEEP-SHADOW"


# ──────────────────────────────────────────────────────────────────────
# _compute_rule_result
# ──────────────────────────────────────────────────────────────────────


class TestComputeRuleResult:
    def _make_enriched_rows(
        self,
        n_won: int,
        n_lost: int,
        fixture_ids: list[int] | None = None,
    ) -> list[dict]:
        rows = []
        fixture_ids = fixture_ids or list(range(1, n_won + n_lost + 1))
        book_odd = 2.0
        for i in range(n_won):
            rows.append({
                "fixture_id": fixture_ids[i] if i < len(fixture_ids) else i + 1,
                "thesis_id": f"t-won-{i}",
                "rule_number": 8,
                "graded_status": "won",
                "profit_units": book_odd - 1.0,  # 1.0u
                "bookmaker_odd": book_odd,
            })
        for i in range(n_lost):
            idx = n_won + i
            rows.append({
                "fixture_id": fixture_ids[idx] if idx < len(fixture_ids) else idx + 1,
                "thesis_id": f"t-lost-{i}",
                "rule_number": 8,
                "graded_status": "lost",
                "profit_units": -1.0,
                "bookmaker_odd": book_odd,
            })
        return rows

    def test_effective_N_present(self):
        rows = self._make_enriched_rows(3, 2)
        result = _compute_rule_result(
            "rule_8", rows, overall_win_rate=0.5, clv_by_thesis={}, overall_clv_mean=None
        )
        assert result.effective_N == 5  # 5 unique fixture_ids (1..5)

    def test_effective_N_deduplicates_fixtures(self):
        # 5 picks from only 2 fixtures → effective_N=2
        rows = self._make_enriched_rows(3, 2, fixture_ids=[1, 1, 1, 2, 2])
        result = _compute_rule_result(
            "rule_8", rows, overall_win_rate=0.5, clv_by_thesis={}, overall_clv_mean=None
        )
        assert result.effective_N == 2

    def test_delta_pl_sum(self):
        rows = self._make_enriched_rows(3, 2)
        result = _compute_rule_result(
            "rule_8", rows, overall_win_rate=0.5, clv_by_thesis={}, overall_clv_mean=None
        )
        # 3 won (1.0u each) + 2 lost (-1.0u each) = 1.0u net
        assert abs(result.delta_pl - 1.0) < 1e-6

    def test_delta_volume_is_negative_n(self):
        rows = self._make_enriched_rows(2, 3)
        result = _compute_rule_result(
            "rule_8", rows, overall_win_rate=0.5, clv_by_thesis={}, overall_clv_mean=None
        )
        assert result.delta_volume == -5  # would reduce by n

    def test_clv_delta_computed_when_coverage(self):
        rows = self._make_enriched_rows(2, 1)
        clv_by_thesis = {
            "t-won-0": 5.0,
            "t-won-1": 3.0,
            "t-lost-0": 1.0,
        }
        result = _compute_rule_result(
            "rule_8", rows, overall_win_rate=0.5, clv_by_thesis=clv_by_thesis, overall_clv_mean=2.0
        )
        # mean of [5.0, 3.0, 1.0] = 3.0; overall=2.0 → clv_delta=1.0
        assert result.clv_delta is not None
        assert abs(result.clv_delta - 1.0) < 1e-6

    def test_clv_delta_none_when_no_coverage(self):
        rows = self._make_enriched_rows(2, 1)
        result = _compute_rule_result(
            "rule_8", rows, overall_win_rate=0.5, clv_by_thesis={}, overall_clv_mean=2.0
        )
        assert result.clv_delta is None

    def test_keep_shadow_insufficient_data(self):
        rows = self._make_enriched_rows(1, 1, fixture_ids=[1, 2])
        result = _compute_rule_result(
            "rule_8", rows, overall_win_rate=0.5, clv_by_thesis={}, overall_clv_mean=None
        )
        assert result.recommendation == "KEEP-SHADOW"

    def test_promote_with_sufficient_positive_pl(self):
        # 8 won, 2 lost → delta_pl = 8*1 + 2*(-1) = 6 > 0; effective_N=10 >= MIN
        fixture_ids = list(range(1, 11))
        rows = self._make_enriched_rows(8, 2, fixture_ids=fixture_ids)
        result = _compute_rule_result(
            "rule_8", rows, overall_win_rate=0.5, clv_by_thesis={}, overall_clv_mean=None
        )
        assert result.recommendation == "PROMOTE"

    def test_revert_with_large_negative_pl(self):
        # 1 won, 9 lost → delta_pl = 1 - 9 = -8 < -REVERT_LOSS_THRESHOLD; effective_N=10 >= MIN
        fixture_ids = list(range(1, 11))
        rows = self._make_enriched_rows(1, 9, fixture_ids=fixture_ids)
        result = _compute_rule_result(
            "rule_8", rows, overall_win_rate=0.9, clv_by_thesis={}, overall_clv_mean=None
        )
        assert result.recommendation == "REVERT"


# ──────────────────────────────────────────────────────────────────────
# build_promotion_report (synthetic, stubbed grader)
# ──────────────────────────────────────────────────────────────────────


class TestBuildPromotionReport:
    @pytest.mark.asyncio
    async def test_report_contains_all_rules(self, tmp_path: Path):
        """Report always contains rule_8, rule_9, dom_gap entries."""
        report = await build_promotion_report(
            date_start=DATE,
            date_end=DATE,
            shadow_root=tmp_path,
            grader_client=None,
        )
        rule_names = {r.rule for r in report.rules}
        assert "rule_8" in rule_names
        assert "rule_9" in rule_names
        assert "dom_gap_0.025vs0.04" in rule_names

    @pytest.mark.asyncio
    async def test_effective_N_always_present(self, tmp_path: Path):
        """effective_N is present on every rule result."""
        report = await build_promotion_report(
            date_start=DATE,
            date_end=DATE,
            shadow_root=tmp_path,
            grader_client=None,
        )
        for rule in report.rules:
            assert hasattr(rule, "effective_N"), f"effective_N missing on {rule.rule}"
            assert isinstance(rule.effective_N, int)

    @pytest.mark.asyncio
    async def test_deterministic_deltas_with_stubbed_grader(self, tmp_path: Path):
        """With synthetic denials + stubbed grader → deterministic delta_pl."""
        # Write gate_denials.parquet with 3 rule_8 is_shadow rows across 3 fixtures
        part_dir = tmp_path / f"dt={DATE}"
        part_dir.mkdir(parents=True)
        denial_rows = [
            _make_denial_row(fixture_id=1001, thesis_id="t-001", rule_number=8),
            _make_denial_row(fixture_id=1002, thesis_id="t-002", rule_number=8),
            _make_denial_row(fixture_id=1003, thesis_id="t-003", rule_number=8),
        ]
        # Also write a picks.parquet so grade_picks_for_date can read it
        pick_rows = [
            {
                "fixture_id": 1001,
                "timestamp_utc": DATE_DT,
                "thesis_id": "t-001",
                "archetype": "momentum_collapse",
                "thesis_layer": "A",
                "rule_id": "r1",
                "family": "goals",
                "direction": "over",
                "magnitude_pp": 5.0,
                "horizon_minutes": 15,
                "market_id": "match_goals_over_2.5",
                "line_value": 2.5,
                "bookmaker_odd": 2.0,
                "kelly_full_pct": 0.05,
                "fair_prob": 0.55,
                "base_edge": 0.1,
                "signal_clarity": 0.7,
                "book_slowness": 0.3,
                "liquidity_score": 0.8,
                "conditional_variance": 0.1,
                "mes_score": 3.5,
                "confidence_prior": 0.6,
                "activated_at_minute": 35,
            },
        ]
        pl.DataFrame(denial_rows).write_parquet(part_dir / "gate_denials.parquet")
        pl.DataFrame(pick_rows).write_parquet(part_dir / "picks.parquet")

        # Stub grader: t-001=won, t-002=lost, t-003=lost
        fake_graded = [
            _FakeGradedPick(
                fixture_id=1001, thesis_id="t-001", market_id="match_goals_over_2.5",
                pick_timestamp_utc=DATE_DT, status="won", profit_units=1.0,
                bookmaker_odd=2.0, settled_at=DATE_DT,
            ),
            _FakeGradedPick(
                fixture_id=1002, thesis_id="t-002", market_id="match_goals_over_2.5",
                pick_timestamp_utc=DATE_DT, status="lost", profit_units=-1.0,
                bookmaker_odd=2.0, settled_at=DATE_DT,
            ),
            _FakeGradedPick(
                fixture_id=1003, thesis_id="t-003", market_id="match_goals_over_2.5",
                pick_timestamp_utc=DATE_DT, status="lost", profit_units=-1.0,
                bookmaker_odd=2.0, settled_at=DATE_DT,
            ),
        ]

        # Patch grade_picks_for_date in the report module with our stub
        from unittest.mock import patch

        async def fake_grade(date_iso, *, shadow_root, client):
            from bip.evaluation.live.engine_v3.runtime.v3_grader import GradeReport
            report = GradeReport(3, 3, 3, 1, 2, 0, 0, 0)
            return fake_graded, report

        import scripts.spike.v3.shadow_promotion_report as spr_mod

        with patch.object(spr_mod, "grade_picks_for_date", side_effect=fake_grade):
            report = await build_promotion_report(
                date_start=DATE,
                date_end=DATE,
                shadow_root=tmp_path,
                grader_client=object(),  # non-None triggers grading path
            )

        rule_8 = next(r for r in report.rules if r.rule == "rule_8")
        # delta_pl = 1.0 (won) + (-1.0) + (-1.0) = -1.0
        assert abs(rule_8.delta_pl - (-1.0)) < 1e-6
        assert rule_8.n == 3
        assert rule_8.effective_N == 3
        # effective_N < MIN_EFFECTIVE_N → KEEP-SHADOW
        assert rule_8.recommendation == "KEEP-SHADOW"

    @pytest.mark.asyncio
    async def test_no_shadow_data_returns_empty_report(self, tmp_path: Path):
        report = await build_promotion_report(
            date_start=DATE,
            date_end=DATE,
            shadow_root=tmp_path,
            grader_client=None,
        )
        assert report.n_shadow_denials_total == 0
        assert report.n_fixtures_total == 0


# ──────────────────────────────────────────────────────────────────────
# _format_markdown and _format_json
# ──────────────────────────────────────────────────────────────────────


def _make_report() -> PromotionReport:
    return PromotionReport(
        date_start="2026-05-10",
        date_end="2026-05-14",
        n_shadow_denials_total=10,
        n_fixtures_total=6,
        overall_win_rate=0.5,
        overall_clv_mean=2.5,
        rules=[
            RulePromotionResult(
                rule="rule_8", n=5, effective_N=5,
                delta_pl=2.0, delta_precision=0.1, delta_volume=-5,
                clv_delta=1.5, recommendation="PROMOTE",
                notes="Positive delta.",
            ),
            RulePromotionResult(
                rule="rule_9", n=3, effective_N=3,
                delta_pl=-3.5, delta_precision=-0.1, delta_volume=-3,
                clv_delta=None, recommendation="REVERT",
                notes="Large loss.",
            ),
            RulePromotionResult(
                rule="dom_gap_0.025vs0.04", n=2, effective_N=2,
                delta_pl=0.0, delta_precision=0.0, delta_volume=-2,
                clv_delta=None, recommendation="KEEP-SHADOW",
                notes="Insufficient data.",
            ),
        ],
    )


class TestFormatting:
    def test_markdown_contains_all_rules(self):
        report = _make_report()
        md = _format_markdown(report)
        assert "rule_8" in md
        assert "rule_9" in md
        assert "dom_gap_0.025vs0.04" in md
        assert "PROMOTE" in md
        assert "REVERT" in md
        assert "KEEP-SHADOW" in md

    def test_json_is_valid_and_contains_all_rules(self):
        report = _make_report()
        j = _format_json(report)
        data = json.loads(j)
        assert data["n_shadow_denials_total"] == 10
        rule_names = [r["rule"] for r in data["rules"]]
        assert "rule_8" in rule_names
        assert "rule_9" in rule_names
        assert "dom_gap_0.025vs0.04" in rule_names

    def test_json_effective_N_present(self):
        report = _make_report()
        data = json.loads(_format_json(report))
        for r in data["rules"]:
            assert "effective_N" in r, f"effective_N missing in {r['rule']}"

    def test_markdown_table_header_present(self):
        report = _make_report()
        md = _format_markdown(report)
        assert "| Rule |" in md
        assert "effective_N" in md
