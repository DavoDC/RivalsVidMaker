"""Seam test: only gui.bridge imports the mutating engine modules, and no GUI module prints or reads input.

AST based, so a comment or a string cannot hide an import. The detector is also tested on
small sources so a broken detector cannot pass the real check by finding nothing.
"""
import ast
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src"
GUI = SRC / "gui"
MUTATING = {"pipeline", "cleanup", "preprocess", "uploader", "encoder", "clip_sorter", "dedup"}
ALLOWED = {"gui.bridge"}
FORBIDDEN_CALLS = {"input", "print"}


def module_name(path: Path) -> str:
    parts = list(path.relative_to(SRC).with_suffix("").parts)
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def gui_files(root: Path = GUI) -> list[Path]:
    return sorted(p for p in root.rglob("*.py") if "__pycache__" not in p.parts)


def mutating_imports(source: str) -> set[str]:
    """Names of mutating engine modules a source imports, or 'state.save' for the save function."""
    tree = ast.parse(source)
    hits: set[str] = set()
    state_names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                top = alias.name.split(".")[0]
                if top in MUTATING:
                    hits.add(alias.name)
                if alias.name == "state":
                    state_names.add(alias.asname or "state")
        elif isinstance(node, ast.ImportFrom) and node.module:
            top = node.module.split(".")[0]
            if top in MUTATING:
                hits.add(node.module)
            if top == "state" and any(a.name in ("save", "*") for a in node.names):
                hits.add("state.save")
        elif isinstance(node, ast.Call):
            func = node.func
            name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", "")
            if name in ("import_module", "__import__") and node.args and isinstance(node.args[0], ast.Constant):
                value = str(node.args[0].value)
                if value.split(".")[0] in MUTATING:
                    hits.add(value)
    for node in ast.walk(tree):
        if (isinstance(node, ast.Attribute) and node.attr == "save"
                and isinstance(node.value, ast.Name) and node.value.id in state_names):
            hits.add("state.save")
    return hits


def forbidden_calls(source: str) -> list[str]:
    found = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in FORBIDDEN_CALLS:
            found.append(f"{node.func.id}() at line {node.lineno}")
    return found


def test_only_bridge_imports_mutating_engine_modules():
    importers = {}
    for path in gui_files():
        hits = mutating_imports(path.read_text(encoding="utf-8"))
        if hits:
            importers[module_name(path)] = sorted(hits)
    assert set(importers) == ALLOWED, f"unexpected importers: {importers}"


def test_no_gui_module_prints_or_reads_input():
    offenders = {}
    for path in gui_files():
        found = forbidden_calls(path.read_text(encoding="utf-8"))
        if found:
            offenders[module_name(path)] = found
    assert offenders == {}


def test_detector_flags_each_mutating_import_form():
    assert mutating_imports("import cleanup\n") == {"cleanup"}
    assert mutating_imports("import pipeline as p\n") == {"pipeline"}
    assert mutating_imports("from encoder import encode\n") == {"encoder"}
    assert mutating_imports("from clip_sorter import sort_clips\n") == {"clip_sorter"}
    assert mutating_imports("from state import save\n") == {"state.save"}
    assert mutating_imports("import state\nstate.save({}, p)\n") == {"state.save"}
    assert mutating_imports("import importlib\nimportlib.import_module('uploader')\n") == {"uploader"}


def test_detector_allows_read_only_imports():
    assert mutating_imports("from state import load, is_youtube_confirmed\n") == set()
    assert mutating_imports("import state\nstate.load(p)\n") == set()
    assert mutating_imports("import clip_scanner, batcher, config\n") == set()


def test_detector_flags_print_and_input():
    assert forbidden_calls("print('x')\n") == ["print() at line 1"]
    assert forbidden_calls("x = input('?')\n") == ["input() at line 1"]
    assert forbidden_calls("log.info('print')\n") == []
