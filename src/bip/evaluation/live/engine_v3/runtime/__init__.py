"""V3 runtime adapters — wiring into the production loop.

Phase-4 deliverables that live alongside the engine but are NOT part
of the pure pipeline: the dual-write runtime (T1.3) that bridges
watch.py to V3Pipeline + ShadowLogger without leaking any side effect
into v2's Telegram path.
"""

from bip.evaluation.live.engine_v3.runtime.dual_write import (
    DEFAULT_KILL_SWITCH_PATH,
    DEFAULT_V3_TIMEOUT_SEC,
    DualWriteRuntime,
    is_v3_kill_switch_engaged,
    is_v3_shadow_enabled,
)
from bip.evaluation.live.engine_v3.runtime.refit_scheduler import (
    RefitJob,
    register_refit_job,
)

__all__ = [
    "DEFAULT_KILL_SWITCH_PATH",
    "DEFAULT_V3_TIMEOUT_SEC",
    "DualWriteRuntime",
    "RefitJob",
    "is_v3_kill_switch_engaged",
    "is_v3_shadow_enabled",
    "register_refit_job",
]
