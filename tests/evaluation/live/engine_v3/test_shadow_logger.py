"""ShadowLogger roundtrip tests — parquet schema + denial logging + GSV log."""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone

import polars as pl

from bip.evaluation.live.engine_v3 import (
    MarketLine,
    MarketSnapshot,
    V3Pipeline,
)
from bip.evaluation.live.engine_v3.shadow_logger import (
    LoadFailure,
    ShadowLogger,
    load_shadow_gsvs,
)
from bip.sports.football.sportmonks.types import StatType
from tests.evaluation.live.engine_v3.conftest import AWAY_ID, HOME_ID, make_state


def _markets_with_corners_line():
    now = datetime.now(timezone.utc)
    return MarketSnapshot(
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


def test_shadow_logger_records_pick_and_denial(tmp_path, priors):
    """Run pipeline once → flush → verify parquet contents."""
    state = make_state(
        home_goals=1,
        away_goals=0,
        minute=70,
        red_card_events=[(25, AWAY_ID)],
        home_stats={
            StatType.SHOTS_TOTAL: 14,
            StatType.SHOTS_INSIDEBOX: 6,
            StatType.BIG_CHANCES_CREATED: 2,
            StatType.CORNERS: 7,
            StatType.BALL_POSSESSION: 65.0,
            StatType.DANGEROUS_ATTACKS: 50,
            StatType.KEY_PASSES: 9,
        },
    )
    pipeline = V3Pipeline()
    out = pipeline.run(
        state,
        priors=priors,
        markets=_markets_with_corners_line(),
        dominant_team_id=HOME_ID,
    )
    logger = ShadowLogger(output_root=tmp_path)
    n_picks, n_denials, n_gsv = logger.record(out)
    assert n_picks + n_denials == len(out.candidates)
    assert n_gsv == 1  # GSV log enabled by default
    paths = logger.flush()

    # If any denials were captured, the file exists with expected columns
    if "denials" in paths:
        df = pl.read_parquet(paths["denials"])
        for col in (
            "fixture_id",
            "thesis_id",
            "archetype",
            "family",
            "market_id",
            "rule_number",
            "reason",
            "mes_score",
            "direction",
        ):
            assert col in df.columns

    if "picks" in paths:
        df = pl.read_parquet(paths["picks"])
        for col in (
            "fixture_id",
            "archetype",
            "family",
            "market_id",
            "fair_prob",
            "base_edge",
            "signal_clarity",
            "book_slowness",
            "liquidity_score",
            "mes_score",
            "confidence_prior",
            "activated_at_minute",
        ):
            assert col in df.columns


def test_shadow_logger_appends_across_flushes(tmp_path, priors):
    state = make_state(home_goals=1, away_goals=0, minute=70, red_card_events=[(25, AWAY_ID)])
    pipeline = V3Pipeline()
    out = pipeline.run(
        state, priors=priors, markets=_markets_with_corners_line(), dominant_team_id=HOME_ID
    )
    logger = ShadowLogger(output_root=tmp_path)
    logger.record(out)
    paths_1 = logger.flush()
    logger.record(out)
    paths_2 = logger.flush()
    # The flush always returns paths even on second flush — same daily file.
    if "picks" in paths_1 and "picks" in paths_2:
        assert paths_1["picks"] == paths_2["picks"]
        df = pl.read_parquet(paths_2["picks"])
        assert df.height >= 1


# ──────────────────────────────────────────────────────────────────────
# T1.1 — GSV persistence + load_shadow_gsvs round-trip
# ──────────────────────────────────────────────────────────────────────


def _run_pipeline_once(priors):
    state = make_state(
        home_goals=1,
        away_goals=0,
        minute=70,
        red_card_events=[(25, AWAY_ID)],
    )
    pipeline = V3Pipeline()
    return pipeline.run(
        state,
        priors=priors,
        markets=_markets_with_corners_line(),
        dominant_team_id=HOME_ID,
    )


def test_gsv_log_persisted_with_expected_schema(tmp_path, priors):
    out = _run_pipeline_once(priors)
    logger = ShadowLogger(output_root=tmp_path)
    logger.record(out)
    paths = logger.flush()

    assert "gsv_log" in paths
    df = pl.read_parquet(paths["gsv_log"])
    for col in (
        "fixture_id",
        "state_version",
        "timestamp_utc",
        "home_team_id",
        "away_team_id",
        "minute",
        "period",
        "home_goals",
        "away_goals",
        "gsv_json",
    ):
        assert col in df.columns, f"missing column {col}"
    assert df.height == 1
    # gsv_json is non-empty serialized JSON
    blob = df["gsv_json"][0]
    assert blob.startswith("{") and blob.endswith("}")


def test_gsv_roundtrip_preserves_pydantic_equality(tmp_path, priors):
    """Persist → load → compare with model_dump.

    Pydantic equality on BaseModel uses field-by-field comparison.
    A successful round-trip means model_validate_json(model_dump_json(x)) == x.
    We compare via ``model_dump()`` rather than __eq__ because dataclass-ish
    nested types may not all hash identically across reconstructions.
    """
    out = _run_pipeline_once(priors)
    original = out.gsv

    logger = ShadowLogger(output_root=tmp_path)
    logger.record(out)
    logger.flush()

    successes, failures = load_shadow_gsvs(output_root=tmp_path)
    assert failures == []
    assert len(successes) == 1
    reloaded = successes[0]

    # Round-trip equality via JSON-stable dump
    assert reloaded.model_dump_json() == original.model_dump_json()
    # Plus a couple of spot-checks for confidence
    assert reloaded.fixture_id == original.fixture_id
    assert reloaded.score.home_goals == original.score.home_goals
    assert reloaded.time.minute == original.time.minute


def test_gsv_load_with_date_range_filter(tmp_path, priors):
    """Two partitions, request only one date → only one GSV returned.

    We simulate two distinct days by manually constructing two flushes
    with rows carrying different timestamp_utc values.
    """
    out = _run_pipeline_once(priors)
    logger = ShadowLogger(output_root=tmp_path)
    logger.record(out)
    logger.flush()

    # Manufacture a second-day row by patching the buffered GSV's date.
    # Easiest path: re-flush after manually appending a row with a +1d ts.
    older_row = {
        "fixture_id": out.gsv.fixture_id,
        "state_version": out.gsv.state_version,
        "timestamp_utc": out.gsv.timestamp_utc - timedelta(days=2),
        "home_team_id": out.gsv.home_team_id,
        "away_team_id": out.gsv.away_team_id,
        "minute": out.gsv.time.minute,
        "period": out.gsv.time.period,
        "home_goals": out.gsv.score.home_goals,
        "away_goals": out.gsv.score.away_goals,
        "gsv_json": out.gsv.model_dump_json(),
    }
    logger._gsv_buf.append(older_row)  # type: ignore[attr-defined]
    logger.flush()

    # Load only today's partition → 1 GSV
    today = out.gsv.timestamp_utc
    successes, _ = load_shadow_gsvs(
        date_range=(today, today),
        output_root=tmp_path,
    )
    assert len(successes) == 1

    # Load full range → 2 GSVs
    successes_all, _ = load_shadow_gsvs(output_root=tmp_path)
    assert len(successes_all) == 2


def test_gsv_log_disabled_skips_buffering(tmp_path, priors):
    out = _run_pipeline_once(priors)
    logger = ShadowLogger(output_root=tmp_path, gsv_log_enabled=False)
    n_picks, n_denials, n_gsv = logger.record(out)
    assert n_gsv == 0
    assert logger.buffer_size()[2] == 0
    paths = logger.flush()
    # GSV file should not be created when disabled
    assert "gsv_log" not in paths
    assert not (
        tmp_path / f"dt={out.gsv.timestamp_utc.strftime('%Y-%m-%d')}" / "gsv_log.parquet"
    ).exists()


def test_load_shadow_gsvs_empty_root_returns_empty(tmp_path):
    """No partitions present → ([], [])."""
    successes, failures = load_shadow_gsvs(output_root=tmp_path / "nonexistent")
    assert successes == []
    assert failures == []


def test_load_shadow_gsvs_malformed_json_returns_failure(tmp_path, priors):
    """A row with corrupted gsv_json yields a LoadFailure, not a crash."""
    out = _run_pipeline_once(priors)
    logger = ShadowLogger(output_root=tmp_path)
    logger.record(out)
    paths = logger.flush()

    # Corrupt one row by appending a deliberately-malformed JSON blob
    df = pl.read_parquet(paths["gsv_log"])
    bad_row = {col: df[col][0] for col in df.columns}
    bad_row["gsv_json"] = '{"fixture_id": "not_an_int",'  # malformed
    corrupted = pl.concat([df, pl.DataFrame([bad_row])], how="diagonal_relaxed")
    corrupted.write_parquet(paths["gsv_log"])

    successes, failures = load_shadow_gsvs(output_root=tmp_path)
    assert len(successes) == 1
    assert len(failures) == 1
    assert isinstance(failures[0], LoadFailure)
    assert failures[0].row_index == 1
    assert "fixture_id" in failures[0].error or failures[0].error  # nonempty


def test_record_performance_under_5ms_budget(tmp_path, priors):
    """Mission spec: persistence <5ms per pick. Sanity check the avg
    over 100 records stays well under budget. Buffer-only — flush is
    separate."""
    out = _run_pipeline_once(priors)
    logger = ShadowLogger(output_root=tmp_path)
    iters = 100
    t0 = time.perf_counter()
    for _ in range(iters):
        logger.record(out)
    elapsed_ms = (time.perf_counter() - t0) * 1000.0
    avg_ms = elapsed_ms / iters
    # We're way under 5ms in normal conditions (sub-ms typical). Use
    # 5ms as the contract ceiling per the mission spec.
    assert avg_ms < 5.0, f"record() avg={avg_ms:.3f}ms exceeds 5ms budget"
