"""GREEN tests for CORNERS-01 D-18 descope orchestrator (3 artifacts on FAIL, marker on PASS)."""
from __future__ import annotations

import subprocess


class TestDescope:
    def test_descope_three_artifacts(self, tmp_path, monkeypatch):
        """D-18: gate FAIL produces (a) ROADMAP edit, (b) STATE entry, (c) git commit."""
        from scripts import corners_gate_descope as desc

        # Stage tmp paths so the test never touches real .planning/
        roadmap = tmp_path / "ROADMAP.md"
        state = tmp_path / "STATE.md"
        roadmap.write_text("### Phase 6: Timed Corners Module (Conditional)\n", encoding="utf-8")
        state.write_text("## Blockers/Concerns\n", encoding="utf-8")
        monkeypatch.setattr(desc, "ROADMAP_PATH", roadmap)
        monkeypatch.setattr(desc, "STATE_PATH", state)

        # Force the gsd-sdk fallback path (so the test does not depend on the CLI)
        def fake_run(cmd, check=False, capture=True, text=True):
            res = subprocess.CompletedProcess(cmd, 0, stdout="ok", stderr="")
            # Simulate gsd-sdk being absent
            if cmd[:2] == ["gsd-sdk", "query"]:
                raise FileNotFoundError("gsd-sdk not installed")
            return res
        monkeypatch.setattr(desc, "_run", fake_run)

        rc = desc.descope_flow("Polars coverage fail -- home_corners absent")

        assert rc == 0
        # (a) ROADMAP edited
        assert "DESCOPED to v2" in roadmap.read_text()
        # (b) STATE entry appended
        assert "CORNERS-01 gate FAILED" in state.read_text()
        assert "Polars coverage fail" in state.read_text()
        # (c) git commit attempted (via fake_run -- verified by no exception raised)

    def test_pass_writes_corners_gate_pass_md(self, tmp_path, monkeypatch):
        """D-18 PASS path: writes scripts/corners_gate_pass.md, no roadmap/state mutation."""
        from scripts import corners_gate_descope as desc

        marker = tmp_path / "corners_gate_pass.md"
        monkeypatch.setattr(desc, "PASS_MARKER_PATH", marker)

        rc = desc.pass_flow()
        assert rc == 0
        assert marker.exists()
        assert "CORNERS-01 Gate -- PASS" in marker.read_text()

    def test_fail_returns_nonzero_when_roadmap_missing(self, tmp_path, monkeypatch):
        from scripts import corners_gate_descope as desc
        # ROADMAP_PATH does not exist -> edit_roadmap_via_gsd_sdk returns False after fallback
        monkeypatch.setattr(desc, "ROADMAP_PATH", tmp_path / "missing.md")
        monkeypatch.setattr(desc, "STATE_PATH", tmp_path / "state.md")
        # Force gsd-sdk fallback
        def fake_run(cmd, **kw):
            if cmd[:2] == ["gsd-sdk", "query"]:
                raise FileNotFoundError("gsd-sdk not installed")
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
        monkeypatch.setattr(desc, "_run", fake_run)

        rc = desc.descope_flow("test reason")
        assert rc == 1   # bail out before STATE / commit because ROADMAP missing

    def test_main_dispatches_pass_vs_descope(self, tmp_path, monkeypatch):
        from scripts import corners_gate_descope as desc
        monkeypatch.setattr(desc, "PASS_MARKER_PATH", tmp_path / "pass.md")
        rc = desc.main(["--pass"])
        assert rc == 0
        assert (tmp_path / "pass.md").exists()
