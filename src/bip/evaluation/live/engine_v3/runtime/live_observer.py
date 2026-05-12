"""Live observer for v3 picks — see what v3 fires in real time without
touching v2's Telegram path.

The dual-write runtime calls ``observer.on_pick(...)`` for each allowed
ShadowPick after the pipeline returns successfully. Observers are
SIDE-EFFECT ONLY — they never raise, never block (best-effort), and
never modify pick state. They exist purely so the operator can WATCH
v3's behaviour during a jornada without flipping any production
switches.

Why an Observer Protocol instead of just printing inside dual_write:

- Lets the operator swap stdout for a log file, a second Telegram
  channel, or a websocket later without touching the runtime.
- Keeps the runtime free of UX decisions (formatting, coloring,
  filtering).
- Easy to wire ZERO observers in test paths.

Wiring (watch.py at startup)::

    from bip.evaluation.live.engine_v3.runtime.live_observer import (
        StdoutObserver,
        build_observer_from_env,
    )

    observer = build_observer_from_env()  # respects V3_LIVE_OBSERVE
    runtime = DualWriteRuntime.from_paths(observer=observer)

Activating::

    export V3_LIVE_OBSERVE=true
    # optional: V3_LIVE_OBSERVE_LOG=/path/to/v3_live.log (stdout by default)

Deactivating: ``unset V3_LIVE_OBSERVE`` (or set to false). Next watch
iteration picks up the change at startup; for a running process you
need to restart.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, Protocol, TextIO

from bip.evaluation.live.engine_v3.gsv import GameStateVector
from bip.evaluation.live.engine_v3.mispricing_window import WindowResult
from bip.evaluation.live.engine_v3.pipeline import ShadowPick


# ──────────────────────────────────────────────────────────────────────
# Protocol — anything that records a pick callback satisfies this.
# ──────────────────────────────────────────────────────────────────────


class LivePickObserver(Protocol):
    """Side-effect-only callback for each v3 allowed pick.

    Implementations MUST NOT raise — the runtime calls them inside a
    best-effort try/except and a thrown observer would only spam logs.
    Implementations MUST NOT block — they run inside asyncio.to_thread,
    so I/O is fine, but anything synchronous + slow (e.g., a
    requests.post with no timeout) eats the v3 latency budget.
    """

    def on_pick(
        self,
        pick: ShadowPick,
        gsv: GameStateVector,
        window: WindowResult | None,
    ) -> None: ...


# ──────────────────────────────────────────────────────────────────────
# Pick formatter — THIS IS THE OPERATOR-OWNED UX SURFACE
# ──────────────────────────────────────────────────────────────────────


def format_v3_pick(
    pick: ShadowPick,
    gsv: GameStateVector,
    window: WindowResult | None,
) -> str:
    """Return ONE line describing the v3 pick, ready to print.

    THIS FUNCTION IS THE OPERATOR'S UX SURFACE. The default below is a
    starting point — customize it for what you want to see scrolling
    during a live jornada. Trade-offs to consider:

    - **Conciseness**: a busy jornada produces 5-20 picks/min. If the
      line is too long, you lose the ability to scan.
    - **Information density**: fixture_id alone is meaningless; you
      probably want minute + market direction + family at minimum.
    - **Visual cues**: terminal color codes (ANSI) help spot tier or
      window labels quickly. Run ``echo -e "\\e[31mRED\\e[0m"`` to
      test if your terminal supports them.
    - **Audit value**: include the archetype + layer so you can spot
      "rule" vs "pattern" theses without grep'ing the parquet later.

    Available fields:

    - ``pick.fixture_id`` (int)
    - ``pick.timestamp_utc`` (datetime)
    - ``pick.full_thesis.archetype`` (ThesisArchetype enum)
    - ``pick.full_thesis.source.layer`` (str: "rule" or "pattern")
    - ``pick.full_thesis.prediction.family`` (MarketFamily enum)
    - ``pick.full_thesis.prediction.direction`` (str: over/under/yes/no/...)
    - ``pick.candidate.market_id`` (str)
    - ``pick.candidate.fair_prob`` (float)
    - ``pick.candidate.mes.score`` (float, the MES total)
    - ``pick.candidate.mes.base_edge`` (float)
    - ``gsv.time.minute`` (int)
    - ``gsv.score.home_goals`` / ``gsv.score.away_goals`` (int)
    - ``gsv.tactical.game_phase`` (str: "cagey_closed"/"open_attacking"/etc)
    - ``window.label`` (str: "HOT"/"OPTIMAL"/"WARM"/"COLD"/"INDEFINITE")
    """
    # TODO (operator): customize this format to your live-jornada needs.
    # The default below is intentionally minimal. Replace it.
    minute = gsv.time.minute
    score = f"{gsv.score.home_goals}-{gsv.score.away_goals}"
    archetype = pick.full_thesis.archetype.value
    layer = pick.full_thesis.source.layer
    family = pick.full_thesis.prediction.family.value
    direction = pick.full_thesis.prediction.direction
    edge = pick.candidate.mes.base_edge * 100  # percent
    mes = pick.candidate.mes.score
    win = window.label if window is not None else "?"
    return (
        f"[{layer}] fid={pick.fixture_id} min={minute:>2d} {score} "
        f"{archetype:<25} → {family}/{direction} "
        f"edge={edge:+.2f}% MES={mes:.2f} win={win}"
    )


# ──────────────────────────────────────────────────────────────────────
# Built-in observers
# ──────────────────────────────────────────────────────────────────────


class NullObserver:
    """No-op observer. Default when V3_LIVE_OBSERVE is unset."""

    def on_pick(
        self,
        pick: ShadowPick,
        gsv: GameStateVector,
        window: WindowResult | None,
    ) -> None:
        return None


class StdoutObserver:
    """Writes each pick to a file-like stream (stdout by default).

    Pass ``stream`` to redirect to a file or alternate sink. The
    observer flushes after each line so picks appear without
    waiting for buffer fill.
    """

    def __init__(
        self,
        *,
        stream: TextIO | None = None,
        prefix: str = "v3:",
        formatter: Any = format_v3_pick,
    ) -> None:
        self._stream = stream or sys.stdout
        self._prefix = prefix
        self._format = formatter

    def on_pick(
        self,
        pick: ShadowPick,
        gsv: GameStateVector,
        window: WindowResult | None,
    ) -> None:
        try:
            line = self._format(pick, gsv, window)
            print(f"{self._prefix} {line}", file=self._stream, flush=True)
        except Exception:  # noqa: BLE001
            # Observers MUST NEVER throw into the runtime. Silently
            # swallow a formatter bug rather than risk the v3 dual-write
            # loop logging spam every iteration.
            return None


class FileObserver(StdoutObserver):
    """Same as StdoutObserver but writes to a file with line-buffered IO.

    The file is opened in append mode and stays open for the process
    lifetime. Mid-jornada rotations are not supported (kill the watch
    process to rotate).
    """

    def __init__(
        self,
        path: Path | str,
        *,
        prefix: str = "v3:",
        formatter: Any = format_v3_pick,
    ) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        # Line-buffered append mode — picks appear in tail -f in real time.
        stream = path.open("a", encoding="utf-8", buffering=1)
        super().__init__(stream=stream, prefix=prefix, formatter=formatter)
        self._path = path

    @property
    def path(self) -> Path:
        return self._path


# ──────────────────────────────────────────────────────────────────────
# Env-driven factory
# ──────────────────────────────────────────────────────────────────────


_TRUE_VALUES = {"1", "true", "yes", "on"}


def build_observer_from_env() -> LivePickObserver:
    """Construct the observer dictated by environment variables.

    - ``V3_LIVE_OBSERVE`` unset / falsey → ``NullObserver``
    - ``V3_LIVE_OBSERVE=true`` and ``V3_LIVE_OBSERVE_LOG`` unset →
      ``StdoutObserver`` (prints to the watch.py terminal)
    - ``V3_LIVE_OBSERVE=true`` and ``V3_LIVE_OBSERVE_LOG=/path/to/v3.log``
      → ``FileObserver`` writing to that path; ``tail -f`` it from a
      second terminal.
    """
    enabled = os.getenv("V3_LIVE_OBSERVE", "").strip().lower() in _TRUE_VALUES
    if not enabled:
        return NullObserver()
    log_path = os.getenv("V3_LIVE_OBSERVE_LOG", "").strip()
    if log_path:
        return FileObserver(log_path)
    return StdoutObserver()


__all__ = [
    "FileObserver",
    "LivePickObserver",
    "NullObserver",
    "StdoutObserver",
    "build_observer_from_env",
    "format_v3_pick",
]
