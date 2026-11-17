# copied from a sibling local GUI kit (verify.py)
"""One-command GUI verification.

  python -m gui verify          pytest + ui_check on every fixture + the full capture matrix
  python -m gui verify --fast   pytest + ui_check on every fixture + a fast capture (3 fixtures, 1440 only)

Prints one final line: [PASS] name (Ns) + ... or [FAIL] name=code ... and exits 0 or 1.
Every step runs even when an earlier one fails, so one run shows every failing step.
"""
from __future__ import annotations

import argparse
import importlib
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def _say(text: str) -> None:
    sys.stdout.write(text + "\n")
FAST_SCENARIOS = "ready,empty,config_broken"
FAST_WIDTHS = "1440"
UI_CHECK_WIDTH = 1440


def run_steps(steps) -> tuple[int, str]:
    """steps: [(name, callable returning an exit code)]. Every step runs."""
    results = []
    for name, fn in steps:
        started = time.monotonic()
        try:
            code = fn()
        except Exception as e:  # a crashing step is a failed step
            _say(f"[step {name}] crashed: {e}")
            code = "error"
        results.append((name, code, time.monotonic() - started))
    bad = [(n, c) for n, c, _t in results if c != 0]
    if bad:
        return 1, "[FAIL] " + " ".join(f"{n}={c}" for n, c in bad)
    return 0, "[PASS] " + " + ".join(f"{n} ({t:.0f}s)" for n, _c, t in results)


def _pytest() -> int:
    return subprocess.call([sys.executable, "-m", "pytest", "-q"], cwd=str(REPO),
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))


ROW_TAB = (("clip-char", "clips"), ("clip-root", "clips"), ("lowvalue", "clips"), ("plan-clip", "compile"),
           ("video", "videos"), ("fate", "videos"), ("archive", "archive"), ("job", "activity"))


def tab_of(testid: str):
    """The tab key a row testid belongs to, or None for shell ids (nav-clips, header)."""
    for prefix, tab in ROW_TAB:
        if testid.startswith(prefix + "-"):
            return tab
    return None


def keep_for(tabs):
    """Predicate for ui_check: keeps only the rows that belong to one of the given tabs."""
    wanted = set(tabs)
    return lambda testid: tab_of(testid) in wanted


def opted_in_tabs(load=importlib.import_module) -> list:
    """Tab keys whose gui/tabs/<key>.py module sets PAINTS_ROWS = True."""
    from gui import tabdefs
    return [key for key in tabdefs.KEYS if getattr(load(f"gui.tabs.{key}"), "PAINTS_ROWS", False) is True]


def _ui_check() -> int:
    """Rows of the tabs that opt in (PAINTS_ROWS = True) must be painted on every fixture. None opted in: pass."""
    from gui import capture, fixtures
    tabs = opted_in_tabs()
    if not tabs:
        _say("ui_check: 0 tabs painted")
        return 0
    chrome = capture.find_chrome()
    if not chrome:
        _say("ui_check could not run: Chrome was not found.")
        return 2
    browser = capture.Browser(chrome)
    scratch = Path(tempfile.mkdtemp(prefix="rvm-uicheck-"))
    failed = 0
    try:
        for scenario in fixtures.SCENARIOS:
            server = capture.DemoServer(scenario)
            try:
                problems = capture.painted_problems(browser, server.base, tabs, scratch, UI_CHECK_WIDTH,
                                                    keep=keep_for(tabs))
            finally:
                server.stop()
            _say("  %s %s" % ("FAIL" if problems else "ok  ", scenario))
            for p in problems:
                _say("       - " + p)
            failed += 1 if problems else 0
    finally:
        browser.close()
        for png in scratch.glob("*.png"):
            png.unlink()
        scratch.rmdir()
    return 1 if failed else 0


def _capture(fast: bool) -> int:
    from gui import capture
    if fast:
        return capture.main(["--scenarios", FAST_SCENARIOS, "--widths", FAST_WIDTHS])
    return capture.main([])


def build_steps(fast: bool):
    return [("pytest", _pytest), ("ui_check", _ui_check), ("capture", lambda: _capture(fast))]


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--fast", action="store_true", help="fast capture: three fixtures at 1440 only")
    ns = p.parse_args(argv)
    code, line = run_steps(build_steps(ns.fast))
    _say(line)
    return code


if __name__ == "__main__":
    sys.exit(main())
