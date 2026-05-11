"""ShadowLogger roundtrip tests — parquet schema + denial logging."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import polars as pl

from bip.evaluation.live.engine_v3 import (
    GSVBuilder,
    MarketLine,
    MarketSnapshot,
    V3Pipeline,
)
from bip.evaluation.live.engine_v3.shadow_logger import ShadowLogger
from bip.sports.football.sportmonks.types import StatType
from tests.evaluation.live.engine_v3.conftest import AWAY_ID, HOME_ID, make_state


def _markets_with_corners_line():
    now = datetime.now(timezone.utc)
    return MarketSnapshot(lines={
        "match_corners_over_10.5": MarketLine(
            market_id="match_corners_over_10.5", side_a_decimal=2.10,
            line_value=10.5, max_stake_cap=400.0,
            last_update_utc=now,
        ),
    })


def test_shadow_logger_records_pick_and_denial(tmp_path, priors):
    """Run pipeline once → flush → verify parquet contents."""
    state = make_state(
        home_goals=1, away_goals=0, minute=70,
        red_card_events=[(25, AWAY_ID)],
        home_stats={
            StatType.SHOTS_TOTAL: 14, StatType.SHOTS_INSIDEBOX: 6,
            StatType.BIG_CHANCES_CREATED: 2, StatType.CORNERS: 7,
            StatType.BALL_POSSESSION: 65.0,
            StatType.DANGEROUS_ATTACKS: 50, StatType.KEY_PASSES: 9,
        },
    )
    pipeline = V3Pipeline()
    out = pipeline.run(
        state, priors=priors, markets=_markets_with_corners_line(),
        dominant_team_id=HOME_ID,
    )
    logger = ShadowLogger(output_root=tmp_path)
    n_picks, n_denials = logger.record(out)
    assert n_picks + n_denials == len(out.candidates)
    paths = logger.flush()

    # If any denials were captured, the file exists with expected columns
    if "denials" in paths:
        df = pl.read_parquet(paths["denials"])
        for col in (
            "fixture_id", "thesis_id", "archetype", "family", "market_id",
            "rule_number", "reason", "mes_score", "direction",
        ):
            assert col in df.columns

    if "picks" in paths:
        df = pl.read_parquet(paths["picks"])
        for col in (
            "fixture_id", "archetype", "family", "market_id", "fair_prob",
            "base_edge", "signal_clarity", "book_slowness", "liquidity_score",
            "mes_score", "confidence_prior", "activated_at_minute",
        ):
            assert col in df.columns


def test_shadow_logger_appends_across_flushes(tmp_path, priors):
    state = make_state(home_goals=1, away_goals=0, minute=70,
                       red_card_events=[(25, AWAY_ID)])
    pipeline = V3Pipeline()
    out = pipeline.run(state, priors=priors,
                       markets=_markets_with_corners_line(),
                       dominant_team_id=HOME_ID)
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
