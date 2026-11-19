"""
oldcomp_guard.py - Keep the OldCompilations folder read-only. Pure path checks and a read-only open.

OldCompilations holds the source videos for the one-off archive run. Every output path in that
run must pass assert_outside_oldcomp before anything is written. Inputs are opened only through
open_readonly. This module never deletes, moves or renames anything.
"""

import os
from pathlib import Path


class OldCompViolation(Exception):
    """Raised when a path that would be written points inside OldCompilations."""


def _comparable(path) -> str:
    """Resolved absolute path (symlinks followed), normalised for case on Windows."""
    return os.path.normcase(str(Path(path).resolve()))


def assert_outside_oldcomp(path, oldcomp_root) -> None:
    """
    Raise OldCompViolation if path resolves to oldcomp_root or anywhere below it.

    Symlinks and '..' are resolved first, so a link or a climbing path cannot sneak in.
    Comparison is case-insensitive on Windows. Paths that only share a text prefix
    (OldCompilationsMeta) are not inside the root and are allowed.
    """
    root = _comparable(oldcomp_root)
    target = _comparable(path)
    try:
        inside = os.path.commonpath([target, root]) == root
    except ValueError:
        # Different drives: cannot be inside the root.
        inside = False
    if inside:
        raise OldCompViolation(f"refusing to write inside OldCompilations: {path}")


def open_readonly(path):
    """Open an input for binary reading. The only way oldcomp code opens source videos."""
    return open(path, "rb")
