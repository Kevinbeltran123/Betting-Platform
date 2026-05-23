"""bip.pipeline — v4 orchestrator + delivery + CLV workers.

Sprint 2 of the v4 refactor. See plan:
  /Users/kevin_beltran/.claude/plans/revisa-la-planeaci-n-que-linear-wave.md

This package is the v4 replacement for the legacy src/bip/production/
orchestration code. It works exclusively over the predictions_raw
table + BaseModel contract. The old PickEngine / production/ stack
keeps running unchanged until v4 passes its gate.
"""

from bip.pipeline.clv_worker import (
    ClvRunSummary,
    ClvWorker,
    OddsClientProtocol,
    ResultClientProtocol,
)
from bip.pipeline.delivery_worker import (
    DeliveryRunSummary,
    DeliveryWorker,
)
from bip.pipeline.orchestrator import (
    Orchestrator,
    OrchestratorRunSummary,
)
from bip.pipeline.protocols import (
    ClaudeValidatorProtocol,
    SupabaseClientProtocol,
    TelegramSenderProtocol,
)

__all__ = [
    "ClaudeValidatorProtocol",
    "ClvRunSummary",
    "ClvWorker",
    "DeliveryRunSummary",
    "DeliveryWorker",
    "OddsClientProtocol",
    "Orchestrator",
    "OrchestratorRunSummary",
    "ResultClientProtocol",
    "SupabaseClientProtocol",
    "TelegramSenderProtocol",
]
