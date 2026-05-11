"""Live Engine v3 — causal-reasoning pipeline.

See ``Papers/LIVE_ENGINE_V3_DESIGN.md`` for the architectural blueprint.

Phase-2 surface (this commit adds): MES, Market Selector, Conditional
Predictor (corners + goals families), No-Bet Policy Gate. The pipeline
+ recorders land in the next commit.
"""
from bip.evaluation.live.engine_v3.archetypes import generate_theses
from bip.evaluation.live.engine_v3.conditional_predictor import (
    ConditionalPredictor,
    CornersPredictor,
    Goals2HPredictor,
    PredictionPoint,
)
from bip.evaluation.live.engine_v3.gsv import (
    CardsState,
    CornerState,
    CriticalEvent,
    FlowState,
    GameStateVector,
    MarketLine,
    MarketSnapshot,
    NumericalState,
    PreMatchPriors,
    RosterState,
    ScoreState,
    TacticalState,
    TimeState,
    XGState,
)
from bip.evaluation.live.engine_v3.gsv_builder import GSVBuilder
from bip.evaluation.live.engine_v3.market_selector import (
    MarketCandidate,
    family_for_market_id,
    select_markets,
)
from bip.evaluation.live.engine_v3.mes import MESResult, compute_mes
from bip.evaluation.live.engine_v3.no_bet_gate import (
    GateResult,
    NoBetVerdict,
    allowed_candidates,
    run_gate,
)
from bip.evaluation.live.engine_v3.thesis import (
    CausalChain,
    CausalStep,
    ConditionalShift,
    GSVPredicate,
    InvalidationTrigger,
    MarketFamily,
    Thesis,
    ThesisArchetype,
    ThesisSource,
    TimeWindow,
)

__all__ = [
    "CardsState",
    "CausalChain",
    "CausalStep",
    "ConditionalPredictor",
    "ConditionalShift",
    "CornerState",
    "CornersPredictor",
    "CriticalEvent",
    "FlowState",
    "GSVBuilder",
    "GSVPredicate",
    "GameStateVector",
    "GateResult",
    "Goals2HPredictor",
    "InvalidationTrigger",
    "MESResult",
    "MarketCandidate",
    "MarketFamily",
    "MarketLine",
    "MarketSnapshot",
    "NoBetVerdict",
    "NumericalState",
    "PreMatchPriors",
    "PredictionPoint",
    "RosterState",
    "ScoreState",
    "TacticalState",
    "Thesis",
    "ThesisArchetype",
    "ThesisSource",
    "TimeState",
    "TimeWindow",
    "XGState",
    "allowed_candidates",
    "compute_mes",
    "family_for_market_id",
    "generate_theses",
    "run_gate",
    "select_markets",
]
