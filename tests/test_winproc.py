"""Tests for winproc.py - backend child processes never open a console window."""

import ast
import subprocess
import sys
from pathlib import Path

import pytest

import winproc

SRC_DIR = Path(__file__).resolve().parents[1] / "src"
SUBPROCESS_CALLS = {"run", "Popen", "check_output", "call"}


@pytest.mark.skipif(sys.platform != "win32", reason="CREATE_NO_WINDOW is Windows-only")
def test_no_window_equals_create_no_window():
    assert winproc.NO_WINDOW == subprocess.CREATE_NO_WINDOW


def test_no_window_is_an_int_flag():
    assert isinstance(winproc.NO_WINDOW, int)


def test_every_subprocess_call_under_src_passes_creationflags():
    offenders = []
    for path in sorted(SRC_DIR.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if (isinstance(func, ast.Attribute) and func.attr in SUBPROCESS_CALLS
                    and isinstance(func.value, ast.Name) and func.value.id == "subprocess"):
                if not any(kw.arg == "creationflags" for kw in node.keywords):
                    rel = path.relative_to(SRC_DIR.parent).as_posix()
                    offenders.append(f"{rel}:{node.lineno} subprocess.{func.attr}")
    assert not offenders, (
        "subprocess call(s) without creationflags (would open a console window "
        "under pythonw): " + "; ".join(offenders)
    )
