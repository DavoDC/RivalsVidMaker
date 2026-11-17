# copied from a sibling local GUI kit (ui_check.py)
"""Painted-state check: the data-testid values painted on the page against the state rows.

Pure functions, no HTTP and no browser. state_row_ids() takes every testid in a /state.json
snapshot; painted_rows() keeps the painted testids that name a row (ROW_KINDS), so shell
ids such as nav-clips or header are not counted. problems() reports each row missing from
the page and each painted row the state does not have. Exit 0 = no problems, 1 = problems.
"""
from __future__ import annotations

import re

# Row kinds that the state contract names (view_model.py); a testid of one of these kinds is a row.
ROW_KINDS = ("clip-char", "clip-root", "lowvalue", "plan-clip", "fate", "video", "archive", "job")
_ATTR = re.compile(r'data-testid=\\?"([^"\\]+)\\?"')
_JSON = re.compile(r'"(?:testid|data-testid)"\s*:\s*"([^"]+)"')


def extract_testids(source: str, prefix: str = "") -> set[str]:
    found = set(_ATTR.findall(source)) | set(_JSON.findall(source))
    return {t for t in found if t.startswith(prefix)}


def state_row_ids(snapshot) -> set[str]:
    """Every "testid" value anywhere in a state snapshot (or one tab's data)."""
    found: set[str] = set()
    stack = [snapshot]
    while stack:
        node = stack.pop()
        if isinstance(node, dict):
            for key, value in node.items():
                if key == "testid" and isinstance(value, str):
                    found.add(value)
                else:
                    stack.append(value)
        elif isinstance(node, list):
            stack.extend(node)
    return found


def painted_rows(testids) -> set[str]:
    """The painted testids that name a state row (their kind is in ROW_KINDS)."""
    prefixes = tuple(f"{kind}-" for kind in ROW_KINDS)
    return {t for t in testids if t.startswith(prefixes)}


def compare(state_ids: set[str], painted: set[str]) -> dict:
    return {"missing": sorted(state_ids - painted), "unexpected": sorted(painted - state_ids)}


def problems(state_ids: set[str], painted: set[str]) -> list[str]:
    result = compare(state_ids, painted)
    return ([f"missing on page: {t}" for t in result["missing"]]
            + [f"unexpected on page: {t}" for t in result["unexpected"]])


def exit_code(failures: list[str]) -> int:
    return 1 if failures else 0
