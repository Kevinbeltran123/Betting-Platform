"""Live Engine v3 — Phase 3 expansion.

Phase-3 surface (commit 2): predictors + calibration stack. Promotion
layer (confidence modulator, stake rotation, Tier-D promoter) lands in
the next commit.
"""
from bip.evaluation.live.engine_v3.phase3.calibration import (
    IsotonicCell,
    TimeBucketedIsotonic,
    transfer_calibration,
)
from bip.evaluation.live.engine_v3.phase3.cards_predictor import CardsPredictor
from bip.evaluation.live.engine_v3.phase3.drift_detector import (
    CalibrationDriftDetector,
    DriftReport,
)
from bip.evaluation.live.engine_v3.phase3.next_goal_predictor import (
    NextGoalPredictor,
)
from bip.evaluation.live.engine_v3.phase3.props_predictor import (
    PlayerPrior,
    PlayerPropsPredictor,
)
from bip.evaluation.live.engine_v3.phase3.regimes import (
    RegimeKey,
    all_minute_buckets,
    bucket_gsv,
    minute_bucket,
)

__all__ = [
    "CalibrationDriftDetector",
    "CardsPredictor",
    "DriftReport",
    "IsotonicCell",
    "NextGoalPredictor",
    "PlayerPrior",
    "PlayerPropsPredictor",
    "RegimeKey",
    "TimeBucketedIsotonic",
    "all_minute_buckets",
    "bucket_gsv",
    "minute_bucket",
    "transfer_calibration",
]
