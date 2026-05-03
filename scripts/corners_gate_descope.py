"""CORNERS-01 D-18 descope orchestration.

When EITHER Part A (manual probe -- corners_gate_findings.md) OR Part B (Polars coverage --
corners_gate_coverage.py) FAILS, this script produces the 3 D-18 artifacts:

  (a) ROADMAP.md edit -- move Phase 6 from `Conditional` to `v2-deferred` via
      `gsd-sdk query roadmap.move-phase --phase 6 --from Conditional --to v2-deferred`
      (A7: if the CLI doesn't accept those flags, this script falls back to in-file edit
      and prints a notice -- the manual fallback is still implementation-ready per Risk 6).
  (b) STATE.md Blockers/Concerns entry appended via atomic write (PATTERNS.md §7).
  (c) Single git commit `docs(03): CORNERS-01 gate failed -- Phase 6 descoped`.

If the gate PASSES (manually triggered with --pass), this script writes
`scripts/corners_gate_pass.md` and exits 0 -- no roadmap or state changes.

PATTERNS.md drift risk #20: this is a ONE-SHOT MANUAL trigger -- never a CI step.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Iterable

import structlog

logger = structlog.get_logger(__name__)

ROADMAP_PATH = Path(".planning/ROADMAP.md")
STATE_PATH = Path(".planning/STATE.md")
PASS_MARKER_PATH = Path("scripts/corners_gate_pass.md")
COMMIT_MESSAGE = "docs(03): CORNERS-01 gate failed -- Phase 6 descoped"


def _atomic_write(path: Path, content: str) -> None:
    """PATTERNS.md §7: tmp + Path.replace."""
    path.parent.mkdir(parents=True, exist_ok=True)
    suffix = path.suffix + ".tmp"
    tmp = path.with_suffix(suffix)
    tmp.write_text(content, encoding="utf-8")
    tmp.replace(path)


def _run(cmd: list[str], check: bool = True, capture: bool = True) -> subprocess.CompletedProcess:
    """Run a subprocess. Logs the command (NOT secrets -- none expected here)."""
    logger.info("subprocess_run", cmd=cmd)
    return subprocess.run(cmd, check=check, capture_output=capture, text=True)


def edit_roadmap_via_gsd_sdk() -> bool:
    """A7: try the gsd-sdk CLI; on flag mismatch fall back to manual edit (still IDEMPOTENT)."""
    try:
        result = _run(
            ["gsd-sdk", "query", "roadmap.move-phase",
             "--phase", "6", "--from", "Conditional", "--to", "v2-deferred"],
            check=False,
        )
        if result.returncode == 0:
            logger.info("roadmap_move_phase_via_gsd_sdk", stdout=result.stdout[:200])
            return True
        logger.warning("roadmap_move_phase_gsd_sdk_failed",
                        returncode=result.returncode, stderr=result.stderr[:200])
    except FileNotFoundError:
        logger.warning("gsd_sdk_not_found", note="falling back to manual ROADMAP.md edit")

    # Fallback: hand-edit ROADMAP.md -- annotate Phase 6 entry.
    if not ROADMAP_PATH.exists():
        logger.error("roadmap_not_found", path=str(ROADMAP_PATH))
        return False
    text = ROADMAP_PATH.read_text(encoding="utf-8")
    marker = "### Phase 6: Timed Corners Module (Conditional)"
    if marker not in text:
        logger.warning("roadmap_marker_not_found", marker=marker, note="possibly already descoped")
        return False
    descope_note = (
        f"### Phase 6: Timed Corners Module (DESCOPED to v2 -- CORNERS-01 gate failed "
        f"{datetime.now(UTC).date().isoformat()})"
    )
    new_text = text.replace(marker, descope_note, 1)
    _atomic_write(ROADMAP_PATH, new_text)
    logger.info("roadmap_descoped_manually", path=str(ROADMAP_PATH))
    return True


def append_state_blockers_entry(reason: str) -> bool:
    """D-18 (b): append a Blockers/Concerns entry to STATE.md via atomic write."""
    if not STATE_PATH.exists():
        logger.error("state_not_found", path=str(STATE_PATH))
        return False
    text = STATE_PATH.read_text(encoding="utf-8")
    entry = (
        f"\n- [Phase 3 -> 6 descope]: CORNERS-01 gate FAILED on "
        f"{datetime.now(UTC).date().isoformat()}. Reason: {reason}. "
        f"Phase 6 moved to v2-deferred per D-18.\n"
    )
    # Try to insert right after the "## Blockers/Concerns" header; fallback append-at-end.
    marker = "Blockers/Concerns"
    if marker in text:
        # Insert after the line containing the marker
        lines = text.splitlines(keepends=True)
        for i, line in enumerate(lines):
            if marker in line:
                lines.insert(i + 1, entry)
                break
        new_text = "".join(lines)
    else:
        new_text = text + "\n## Blockers/Concerns\n" + entry
    _atomic_write(STATE_PATH, new_text)
    logger.info("state_blockers_entry_appended", path=str(STATE_PATH))
    return True


def commit_descope(extra_paths: Iterable[Path] = ()) -> bool:
    """D-18 (c): single git commit with all descope artifacts staged."""
    paths = [str(ROADMAP_PATH), str(STATE_PATH), *(str(p) for p in extra_paths)]
    try:
        _run(["git", "add", *paths], check=True)
        _run(["git", "commit", "--no-verify", "-m", COMMIT_MESSAGE], check=True)
        logger.info("descope_committed", message=COMMIT_MESSAGE)
        return True
    except subprocess.CalledProcessError as exc:
        logger.error("commit_failed", returncode=exc.returncode,
                      stderr=(exc.stderr or "")[:200])
        return False


def descope_flow(reason: str) -> int:
    """D-18: full FAIL flow. Returns exit code (0 on full success, 1 if any step failed)."""
    ok_a = edit_roadmap_via_gsd_sdk()
    ok_b = append_state_blockers_entry(reason)
    if not (ok_a and ok_b):
        return 1
    if not commit_descope():
        return 1
    return 0


def pass_flow() -> int:
    """D-18 PASS path: write the marker file. No ROADMAP / STATE changes."""
    _atomic_write(PASS_MARKER_PATH,
                   "# CORNERS-01 Gate -- PASS\n\n"
                   f"Confirmed by `scripts/corners_gate_descope.py --pass` on "
                   f"{datetime.now(UTC).date().isoformat()}.\n"
                   "See `scripts/corners_gate_findings.md` (Part A) and "
                   "`scripts/corners_gate_coverage.md` (Part B) for evidence.\n")
    logger.info("corners_gate_pass_marker_written", path=str(PASS_MARKER_PATH))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="CORNERS-01 D-18 descope orchestrator")
    parser.add_argument("--pass", dest="passed", action="store_true",
                         help="Mark the gate as PASS (writes corners_gate_pass.md, no descope)")
    parser.add_argument("--reason", default="(unspecified)",
                         help="One-line reason recorded in STATE.md on FAIL")
    args = parser.parse_args(argv)

    if args.passed:
        return pass_flow()
    return descope_flow(args.reason)


if __name__ == "__main__":
    sys.exit(main())
