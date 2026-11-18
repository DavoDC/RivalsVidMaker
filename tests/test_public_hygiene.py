"""Public-text hygiene: no internal work-item numbers and no em or en dashes in shipped text.

The dash characters are built with chr() so this file holds none, and the work-item
probe strings are split so this file does not match its own pattern.
"""
import re
import shutil
import subprocess
from pathlib import Path

import pytest

EM_DASH = chr(0x2014)
EN_DASH = chr(0x2013)
WORK_ITEM = re.compile(r"\b[Tt]ask \d+[a-z]?\b")
DASH = re.compile(f"[{EM_DASH}{EN_DASH}]")
ROOT = Path(__file__).resolve().parents[1]
SCAN_DIRS = ("src/", "tests/", "docs/")
SCAN_FILES = ("CLAUDE.md", "README.md")


def hygiene_hits(text: str) -> list[str]:
    return WORK_ITEM.findall(text) + DASH.findall(text)


def test_hygiene_hits_flags_work_item_and_dashes():
    assert hygiene_hits("# " + "ta" + "sk 12: fix")
    assert hygiene_hits("a " + chr(0x2014) + " b")
    assert hygiene_hits("a " + chr(0x2013) + " b")
    assert hygiene_hits("a task list, the tasks run") == []


def _tracked_scan_files() -> list[str]:
    if shutil.which("git") is None:
        pytest.skip("git is not available")
    try:
        out = subprocess.run(  # window-ok: test-time git call, never runs in the GUI
            ["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True
        ).stdout
    except (OSError, subprocess.CalledProcessError):
        pytest.skip("git ls-files failed")
    keep = []
    for rel in out.splitlines():
        if not rel.endswith((".py", ".md")):
            continue
        if rel.startswith(SCAN_DIRS) or rel in SCAN_FILES:
            keep.append(rel)
    return keep


def test_tracked_text_has_no_hygiene_hits():
    failures = []
    for rel in _tracked_scan_files():
        text = (ROOT / rel).read_text(encoding="utf-8")
        for number, line in enumerate(text.splitlines(), start=1):
            if hygiene_hits(line):
                failures.append(f"{rel}:{number}: {line.strip()}")
    assert not failures, "hygiene hits:\n" + "\n".join(failures)


def test_no_tracked_runtime_data():
    # data/ holds cache, logs, output and analysis that are rebuilt locally; git must not track it.
    if shutil.which("git") is None:
        pytest.skip("git is not available")
    try:
        out = subprocess.run(  # window-ok: test-time git call, never runs in the GUI
            ["git", "ls-files", "data"], cwd=ROOT, capture_output=True, text=True, check=True
        ).stdout
    except (OSError, subprocess.CalledProcessError):
        pytest.skip("git ls-files failed")
    tracked = out.splitlines()
    assert not tracked, (
        "runtime data is tracked (untrack with git rm -r --cached data):\n" + "\n".join(tracked)
    )
