# copied from a sibling local GUI kit (__main__.py)
"""Entry point: python -m gui.

Launcher verbs (--launch, --stop, --check, --status, --preflight) run in the caller's process and
return an exit code. Without one of them the module serves the GUI: state routes, the loopback
guard, the page shell and, unless --no-watch, the hot-reload watcher. Subcommands verify and capture
take their own flags and are handed the rest of argv; ui_check is still a stub.

The page shell is imported lazily (gui.shell), so the launcher verbs run before it exists.
"""
from __future__ import annotations

import argparse
import importlib
import sys
from pathlib import Path

from gui import hot_reload, jobs, launcher, security
from gui.sources import FixtureSource, RealSource

CHECK_COMMANDS = ("verify", "capture")
STUB_COMMANDS = ("ui_check",)


def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="python -m gui", description="RivalsVidMaker local GUI")
    p.add_argument("command", nargs="?", choices=CHECK_COMMANDS + STUB_COMMANDS, default=None)
    p.add_argument("--launch", action="store_true", help="start detached (windowless) and open the browser")
    p.add_argument("--stop", action="store_true", help="stop the listener on the port")
    p.add_argument("--check", action="store_true", help="print the running build and boot id")
    p.add_argument("--status", action="store_true", help="say whether something listens on the port")
    p.add_argument("--preflight", action="store_true", help="run the start-up checks and print them")
    p.add_argument("--no-watch", action="store_true", help="turn hot reload off")
    p.add_argument("--no-browser", action="store_true", help="do not open a browser on launch")
    p.add_argument("--no-dialog", action="store_true", help="no message box on a windowless failure")
    p.add_argument("--port", type=int, default=security.DEFAULT_PORT)
    p.add_argument("--fixture", default=None, help="serve a canned fixture instead of the real library")
    return p.parse_args(argv)


def _say(text: str) -> None:
    if sys.stdout is not None:
        sys.stdout.write(text + "\n")


class WiredSource:
    """Adds the running job and the job history to the source snapshot (StateApi has no job feed).
    An idle runner leaves the inner source's fixture job and activity untouched."""

    def __init__(self, inner, runner):
        self.inner = inner
        self.runner = runner

    @property
    def fixture(self):
        return getattr(self.inner, "fixture", None)

    def read(self) -> dict:
        data = dict(self.inner.read())
        current = self.runner.current()
        if current is not None:
            data["job"] = current
        history = self.runner.history()
        if history:
            data["activity"] = list(history)
        return data


def _default_builder(source, runner, tab):
    # Lazy: the page shell is imported on first show. import_module reads sys.modules, so a
    # stubbed gui.shell is honoured even after the real module set the package attribute.
    shell = importlib.import_module("gui.shell")
    shell.build_page(source, initial_tab=tab)


def make_page_handler(source, runner, builder=None):
    build = builder or _default_builder

    def handler(tab=None):
        return build(source, runner, tab)

    return handler


def _stub(name: str) -> int:
    _say(f"{name} is not built yet")
    return 2


def _check_verb(name: str, rest: list[str]) -> int:
    # Imported lazily: the checks drive Chrome and the launcher verbs never need them.
    if name == "verify":
        from gui import verify
        return verify.main(rest)
    from gui import capture
    return capture.main(rest)


def serve(args: argparse.Namespace) -> int:
    root = launcher.REPO_ROOT
    if sys.stdout is None or sys.stderr is None:  # pythonw: route output to today's log
        log = open(launcher.log_path(root), "a", encoding="utf-8", buffering=1)
        sys.stdout = sys.stderr = log
    if args.fixture:
        source = FixtureSource(args.fixture)
    else:
        from config import load
        source = RealSource(load(root / "config" / "config.json"))
    state_dir = root / "data" / "gui"
    state_dir.mkdir(parents=True, exist_ok=True)
    runner = jobs.JobRunner(state_dir / "jobs.json", log_path=launcher.log_path(root))
    wired = WiredSource(source, runner)
    port = args.port

    from nicegui import app, ui
    from gui import state_api

    app.add_middleware(security.LoopbackGuard, port_fn=lambda: port)
    state_api.register(app, wired)
    handler = make_page_handler(wired, runner)

    @ui.page("/")
    def index():
        handler(tab=None)

    @ui.page("/tab/{tab}")
    def tab_page(tab: str):
        handler(tab=tab)

    if not args.no_watch:
        hot_reload.BUSY_CHECK = lambda: runner.busy
        hot_reload.start_watcher(str(root / "src"))
    launcher.log_line("serve", f"serving on port {port} (fixture={args.fixture or 'none'})", repo_root=root)
    ui.run(host=security.BIND_HOST, port=port, show=False, reload=False, title="RivalsVidMaker")
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] in CHECK_COMMANDS:  # their own flags (--fast, --widths) are parsed by the verb
        return _check_verb(argv[0], argv[1:])
    args = parse_args(argv)
    if args.command in STUB_COMMANDS:
        return _stub(args.command)
    if args.preflight:
        return launcher.run_preflight(args.port)
    if args.stop:
        return launcher.stop(args.port)
    if args.status:
        return launcher.status(args.port)
    if args.check:
        return launcher.check(args.port)
    if args.launch:
        return launcher.launch(args.port, argv, dialog=not args.no_dialog, browser=not args.no_browser)
    return serve(args)


if __name__ == "__main__":
    sys.exit(main())
