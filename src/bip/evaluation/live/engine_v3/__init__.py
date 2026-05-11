"""Live Engine v3 — causal-reasoning pipeline.

See ``Papers/LIVE_ENGINE_V3_DESIGN.md`` for the architectural blueprint.

Phase-1 surface (this commit): GSV primitives + rule-layer hypothesis
generation. The MES / Market Selector / No-Bet Gate / pipeline /
recorders land in follow-up commits.
"""
from bip.evaluation.live.engine_v3.archetypes import generate_theses
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
    "ConditionalShift",
    "CornerState",
    "CriticalEvent",
    "FlowState",
    "GSVBuilder",
    "GSVPredicate",
    "GameStateVector",
    "InvalidationTrigger",
    "MarketFamily",
    "MarketLine",
    "MarketSnapshot",
    "NumericalState",
    "PreMatchPriors",
    "RosterState",
    "ScoreState",
    "TacticalState",
    "Thesis",
    "ThesisArchetype",
    "ThesisSource",
    "TimeState",
    "TimeWindow",
    "XGState",
    "generate_theses",
]
