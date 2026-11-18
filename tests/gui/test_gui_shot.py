"""The shot verb (src/gui/shot.py): step grammar, output path, argparse defaults and wiring.

Nothing here starts Chrome or a server. The live run is a manual step, not a test.
"""
from pathlib import Path

import pytest

from gui import __main__ as gui_main
from gui import shot

REPO = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("raw, action", [
    ("click:Compile", ("click", "Compile")),
    ("tap:Upload", ("tap", "Upload")),
    ("select:#lang=English", ("select", "#lang", "English")),
    ("fill:input[name=x]=12", ("fill", "input[name=x]", "12")),
    ("wait:1.5", ("wait", 1.5)),
    ("eval:1+1", ("eval", "1+1")),
])
def test_each_step_form_parses_to_its_action(raw, action):
    assert shot.parse_step(raw) == action


@pytest.mark.parametrize("raw", ["hover:x", "click:", "select:sel", "wait:abc", "eval:", "noColon"])
def test_unknown_or_malformed_steps_are_rejected(raw):
    with pytest.raises(ValueError):
        shot.parse_step(raw)


def test_output_path_for_compile_at_1440_sits_in_the_shot_folder():
    path = shot.shot_path("compile", 1440)
    assert path.parent.as_posix().endswith("data/captures/shot")
    assert path.name.startswith("compile-1440") and path.suffix == ".png"
    assert path.is_absolute()


def test_gitignore_covers_the_capture_folder():
    assert "data/captures/" in (REPO / ".gitignore").read_text(encoding="utf-8").splitlines()


def test_argparse_defaults_are_ready_fixture_1440_by_900():
    args = shot.parse_args(["compile"])
    assert args.tab == "compile"
    assert args.fixture == "ready" and args.url is None
    assert args.width == 1440 and args.height == 900
    assert args.steps == []


def test_steps_may_follow_the_flags():
    args = shot.parse_args(["compile", "--fixture", "plan", "click:Compile"])
    assert args.fixture == "plan" and args.steps == ["click:Compile"]


def test_fixture_and_url_together_are_refused():
    with pytest.raises(SystemExit):
        shot.parse_args(["compile", "--fixture", "plan", "--url", "http://127.0.0.1:9"])


def test_shot_is_wired_in_main_like_capture(monkeypatch):
    seen = []
    monkeypatch.setattr(shot, "main", lambda argv: seen.append(list(argv)) or 0)
    assert gui_main.main(["shot", "compile", "--fixture", "plan"]) == 0
    assert seen == [["compile", "--fixture", "plan"]]
