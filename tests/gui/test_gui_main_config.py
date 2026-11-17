"""--config PATH: the GUI, --preflight and --launch read the config file the flag names.

Every loader, launcher verb and spawn call is injected or monkeypatched. Nothing reads the real
config/config.json, and nothing spawns a server or binds a port other than port 0.
"""
from pathlib import Path

import pytest

from gui import __main__ as gui_main
from gui import launcher
from gui.sources import FixtureSource, RealSource


class FakeLoader:
    """Records every path it is called with and returns a sentinel config object."""

    def __init__(self):
        self.paths = []
        self.config = object()

    def __call__(self, path):
        self.paths.append(Path(path))
        return self.config


def test_parse_args_config_defaults_to_none():
    assert gui_main.parse_args([]).config is None


def test_parse_args_config_takes_the_given_path():
    args = gui_main.parse_args(["--config", "scratch/config.json"])
    assert args.config == "scratch/config.json"


def test_load_source_loads_the_given_config_path(tmp_path):
    loader = FakeLoader()
    given = tmp_path / "scratch.json"
    args = gui_main.parse_args(["--config", str(given)])
    config, source = gui_main.load_source(args, tmp_path, loader=loader)
    assert loader.paths == [given]
    assert config is loader.config
    assert isinstance(source, RealSource)


def test_load_source_defaults_to_the_repo_config_json(tmp_path):
    loader = FakeLoader()
    args = gui_main.parse_args([])
    config, source = gui_main.load_source(args, tmp_path, loader=loader)
    assert loader.paths == [tmp_path / "config" / "config.json"]
    assert config is loader.config
    assert isinstance(source, RealSource)


def test_real_source_holds_the_config_that_load_source_returns(tmp_path):
    loader = FakeLoader()
    config, source = gui_main.load_source(gui_main.parse_args([]), tmp_path, loader=loader)
    assert source.config is config


def test_load_source_fixture_mode_never_calls_the_loader(tmp_path):
    loader = FakeLoader()
    args = gui_main.parse_args(["--fixture", "empty", "--config", str(tmp_path / "x.json")])
    config, source = gui_main.load_source(args, tmp_path, loader=loader)
    assert loader.paths == []
    assert config is None
    assert isinstance(source, FixtureSource) and source.fixture == "empty"


def test_preflight_with_config_checks_that_file(tmp_path, monkeypatch, capsys):
    paths = []
    monkeypatch.setattr(launcher.engine_config, "load", lambda path: paths.append(Path(path)) or object())

    def fake_preflight(port, loader=None, label="config/config.json"):
        loader()  # the real checks would read the repo logs folder; only the loader is under test
        return []

    monkeypatch.setattr(launcher, "preflight", fake_preflight)
    given = tmp_path / "scratch.json"
    assert gui_main.main(["--preflight", "--config", str(given), "--port", "0"]) == 0
    capsys.readouterr()
    assert paths == [given]


def test_preflight_without_config_keeps_the_default_loader(monkeypatch):
    seen = []
    monkeypatch.setattr(launcher, "preflight", lambda port, loader=None: seen.append(loader) or [])
    assert launcher.run_preflight(0) == 0
    assert seen == [None]


def test_launch_argv_keeps_the_config_flag(tmp_path, monkeypatch):
    seen = []
    monkeypatch.setattr(launcher, "launch", lambda port, argv, **kw: seen.append(list(argv)) or 0)
    given = str(tmp_path / "scratch.json")
    assert gui_main.main(["--launch", "--config", given, "--port", "9"]) == 0
    argv = seen[0]
    assert argv[argv.index("--config") + 1] == given
    child = launcher.child_argv("pythonw", 9, argv)
    assert child[child.index("--config") + 1] == given
