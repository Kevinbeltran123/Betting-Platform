"""Tests for the start_caffeinate helper in scripts/spike/sportmonks/watch.py.

We don't actually spawn caffeinate in tests — it's a real macOS process
that would survive past test teardown. Instead we exercise the
control-flow branches: non-macOS, opt-out env var, missing binary,
Popen failure.
"""
from __future__ import annotations

import scripts.spike.sportmonks.watch as watch


def test_returns_none_on_non_darwin(monkeypatch):
    monkeypatch.setattr(watch.platform, "system", lambda: "Linux")
    assert watch.start_caffeinate() is None


def test_returns_none_when_opt_out(monkeypatch):
    monkeypatch.setattr(watch.platform, "system", lambda: "Darwin")
    monkeypatch.setenv("WATCH_NO_CAFFEINATE", "1")
    assert watch.start_caffeinate() is None


def test_returns_none_when_opt_out_truthy_strings(monkeypatch):
    monkeypatch.setattr(watch.platform, "system", lambda: "Darwin")
    for val in ("true", "yes", "TRUE", "Yes"):
        monkeypatch.setenv("WATCH_NO_CAFFEINATE", val)
        assert watch.start_caffeinate() is None, f"opt-out failed for {val!r}"


def test_returns_none_when_caffeinate_missing(monkeypatch):
    monkeypatch.setattr(watch.platform, "system", lambda: "Darwin")
    monkeypatch.delenv("WATCH_NO_CAFFEINATE", raising=False)
    monkeypatch.setattr(watch.shutil, "which", lambda name: None)
    assert watch.start_caffeinate() is None


def test_returns_none_when_popen_raises(monkeypatch):
    """OSError from subprocess.Popen (e.g., resource exhaustion) is
    swallowed — caffeinate is best-effort, never a critical path."""
    monkeypatch.setattr(watch.platform, "system", lambda: "Darwin")
    monkeypatch.delenv("WATCH_NO_CAFFEINATE", raising=False)
    monkeypatch.setattr(watch.shutil, "which", lambda name: "/usr/bin/caffeinate")

    class _BrokenPopen:
        def __init__(self, *args, **kwargs):
            raise OSError("synthetic — Popen unavailable")

    monkeypatch.setattr(watch.subprocess, "Popen", _BrokenPopen)
    assert watch.start_caffeinate() is None


def test_uses_correct_caffeinate_flags(monkeypatch):
    """Sanity: when caffeinate IS spawned, it uses -i -m -s -w <pid>
    (no -d, so display can dim while system stays awake)."""
    monkeypatch.setattr(watch.platform, "system", lambda: "Darwin")
    monkeypatch.delenv("WATCH_NO_CAFFEINATE", raising=False)
    monkeypatch.setattr(watch.shutil, "which", lambda name: "/usr/bin/caffeinate")

    captured: dict = {}

    class _FakePopen:
        def __init__(self, args, **kwargs):
            captured["args"] = list(args)
            captured["kwargs"] = kwargs

    monkeypatch.setattr(watch.subprocess, "Popen", _FakePopen)
    proc = watch.start_caffeinate()
    assert proc is not None
    args = captured["args"]
    assert args[0] == "/usr/bin/caffeinate"
    assert "-i" in args  # prevent idle sleep
    assert "-m" in args  # prevent disk sleep
    assert "-s" in args  # prevent system sleep on AC
    assert "-d" not in args  # display sleep IS allowed (lid can close)
    # -w PID binds caffeinate to our process
    assert "-w" in args
    pid_idx = args.index("-w") + 1
    assert int(args[pid_idx]) > 0
