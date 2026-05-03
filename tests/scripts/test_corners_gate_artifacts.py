"""GREEN structural tests for CORNERS-01 D-17a manual checklist + findings template."""
from __future__ import annotations

from pathlib import Path

import pytest


PROBE_PATH = Path("scripts/corners_gate_probe.md")
FINDINGS_PATH = Path("scripts/corners_gate_findings.md")


class TestProbeArtifacts:
    def test_probe_md_exists(self):
        assert PROBE_PATH.exists(), f"{PROBE_PATH} missing — run plan 03-09 Task 1"

    def test_probe_md_structure(self):
        """D-17a: required sections — Checklist, Companion Files, Findings template."""
        content = PROBE_PATH.read_text()
        for header in ("## Checklist", "## Companion Files", "## Findings template"):
            assert header in content, f"missing required section {header!r}"

    def test_probe_lists_all_5_leagues(self):
        content = PROBE_PATH.read_text()
        for league in ("Premier League", "La Liga", "Bundesliga", "Serie A", "Ligue 1"):
            assert f"#### {league}" in content, f"missing league section #### {league}"

    def test_probe_references_companion_files(self):
        content = PROBE_PATH.read_text()
        for fname in ("corners_gate_findings", "corners_gate_coverage", "corners_gate_descope"):
            assert fname in content, f"missing companion-file reference {fname}"

    def test_probe_references_decisions(self):
        """D-17 + D-18 must be cited."""
        content = PROBE_PATH.read_text()
        assert "D-17" in content, "D-17 reference missing"
        assert "D-18" in content, "D-18 reference missing"

    def test_probe_no_yaml_frontmatter(self):
        """Open Question #5: plain Markdown headers — no YAML front-matter."""
        first_line = PROBE_PATH.read_text().splitlines()[0]
        assert not first_line.startswith("---"), (
            "probe.md starts with YAML front-matter — Open Question #5 chose plain markdown"
        )


class TestFindingsTemplate:
    def test_findings_md_exists(self):
        assert FINDINGS_PATH.exists(), f"{FINDINGS_PATH} missing — run plan 03-09 Task 2"

    def test_findings_template_has_all_5_leagues(self):
        """D-17a: per-league section per the 5 covered leagues."""
        content = FINDINGS_PATH.read_text()
        for league in ("Premier League", "La Liga", "Bundesliga", "Serie A", "Ligue 1"):
            assert f"### {league}" in content, f"missing per-league header ### {league}"

    def test_findings_template_has_gate_decision_block(self):
        """D-17a + D-18: PASS/FAIL verdict block must exist for the descope decision."""
        content = FINDINGS_PATH.read_text()
        assert "Part A — Gate Decision" in content
        assert "**PASS**" in content
        assert "**FAIL**" in content

    def test_findings_template_has_companion_descope_reference(self):
        """D-18: findings.md must direct Kevin to the descope script on FAIL."""
        content = FINDINGS_PATH.read_text()
        assert "corners_gate_descope.py" in content
