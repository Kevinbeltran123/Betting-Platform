"""Filter for the Day-4 watch.py stdout stream.

Stdin: raw watch.py output (typically piped from `tail -n 0 -F`).
Stdout: one line per "novel" event, where novel means:
- First time we see this (fixture, market, selection) trio (v2 picks)
- ANY v3 shadow pick emission (regardless of dedup)
- Any error / exception / kill switch / low rate-limit

A 30-minute window per trio. After that, the trio is "forgotten" and a
re-emission would re-fire. This matches the operator's mental model:
the same pick re-priced is the same bet; only flag genuinely new ones.

Usage from Monitor:
    tail -n 0 -F logs/watch_day4_stdout.log | uv run python scripts/spike/v3/_monitor_dedupe.py
"""
from __future__ import annotations

import re
import sys
import time

# Pattern: "🚨/⚠️ NEW PICK: +XX.YY% home vs away (min N) market/selection @ odd"
PICK_RE = re.compile(
    r"NEW PICK:.*?([A-Z][^()]+?) \(min \d+\)\s+([^/]+)/([^\s]+)"
)
TIME_RE = re.compile(r"^\[(\d{2}:\d{2}:\d{2})\]")

WINDOW_SECONDS = 30 * 60  # 30 min dedup window

seen: dict[str, float] = {}  # key → timestamp_seen


def now_ts() -> float:
    return time.time()


def maybe_emit(line: str) -> None:
    """Decide if this line should reach the operator."""
    # Always pass through errors / exceptions / kill switch / low rate-limit.
    if any(tok in line for tok in (
        "ERROR", "Traceback", "Exception", "🛑", "❌",
        "kill_switch", "V3_SHADOW",
    )):
        sys.stdout.write(line)
        sys.stdout.flush()
        return

    # Always pass through v3 shadow events.
    if "v3 shadow" in line or "shadow pick" in line:
        sys.stdout.write(line)
        sys.stdout.flush()
        return

    # Low rate-limit (< 100 remaining)
    if re.search(r"remaining'?: '?\d{1,2},", line):
        sys.stdout.write(f"⚠️ LOW RATE-LIMIT: {line}")
        sys.stdout.flush()
        return

    m = PICK_RE.search(line)
    if not m:
        # Not a pick line — drop.
        return

    fixture = m.group(1).strip()
    market = m.group(2).strip()
    selection = m.group(3).strip()
    key = f"{fixture}|{market}|{selection}"
    now = now_ts()
    last_seen = seen.get(key)
    if last_seen is not None and (now - last_seen) < WINDOW_SECONDS:
        # Suppress: same trio recently emitted.
        return
    seen[key] = now
    sys.stdout.write(line)
    sys.stdout.flush()


def main() -> None:
    for line in sys.stdin:
        if not line.endswith("\n"):
            line = line + "\n"
        maybe_emit(line)


if __name__ == "__main__":
    main()
