"""Launcher, __main__ wiring and hot reload (task 19).

Nothing here binds a real port except port 0, opens a browser, or spawns a server: every
process and browser call is injected. Files go under tmp_path only.
"""
import json
import re
import socket
import sys
import threading
import types
from datetime import date
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

import config as engine_config
from gui import __main__ as gui_main
from gui import hot_reload, jobs, launcher, state_api, view_model

REPO = Path(__file__).resolve().parents[2]
BAT = REPO / "scripts" / "gui.bat"
FFMPEG_FIX = ("FFmpeg is missing from dependencies/ffmpeg. Put ffmpeg.exe and ffprobe.exe there, "
              "then press Check again.")


def make_config(root: Path, *, ffmpeg: bool = True, tesseract: bool = True) -> engine_config.Config:
    tools = root / "dependencies" / "ffmpeg"
    tools.mkdir(parents=True, exist_ok=True)
    if ffmpeg:
        (tools / "ffmpeg.exe").write_bytes(b"")
        (tools / "ffprobe.exe").write_bytes(b"")
    tess = root / "tesseract.exe"
    if tesseract:
        tess.write_bytes(b"")
    return engine_config.Config(
        clips_path=root / "clips", output_path=root / "out", archive_path=root / "archive",
        ffmpeg=tools / "ffmpeg.exe", ffprobe=tools / "ffprobe.exe", cache_dir=root / "cache",
        tesseract=tess, min_batch_seconds=600, target_batch_seconds=900, protect_recent_clips=5,
        state_path=root / "state.json", force_rescan_cache=False, use_pass2_scanner=False,
        youtube_channel_id="test", vlc_path=None)


def named(checks, name):
    return next(c for c in checks if c.name == name)


# ----- preflight ---------------------------------------------------------------------

def test_preflight_missing_ffmpeg_returns_fix_sentence(tmp_path):
    cfg = make_config(tmp_path, ffmpeg=False)
    checks = launcher.preflight(0, repo_root=tmp_path, loader=lambda: cfg)
    ffmpeg = named(checks, "ffmpeg")
    assert ffmpeg.ok is False
    assert ffmpeg.detail == FFMPEG_FIX
    assert ffmpeg.blocking is False


def test_preflight_config_failure_is_blocking(tmp_path):
    def broken():
        raise FileNotFoundError("config.json not found")

    checks = launcher.preflight(0, repo_root=tmp_path, loader=broken)
    cfg = named(checks, "config")
    assert cfg.ok is False and cfg.blocking is True
    assert "config.json not found" in cfg.detail


def test_preflight_healthy_tree_passes(tmp_path):
    cfg = make_config(tmp_path)
    checks = launcher.preflight(0, repo_root=tmp_path, loader=lambda: cfg)
    assert [c.name for c in checks] == ["python", "imports", "config", "ffmpeg", "tesseract", "logs", "port"]
    assert all(c.ok for c in checks), [(c.name, c.detail) for c in checks if not c.ok]


def test_preflight_logs_dir_is_created_under_repo_root(tmp_path):
    cfg = make_config(tmp_path)
    launcher.preflight(0, repo_root=tmp_path, loader=lambda: cfg)
    assert (tmp_path / "data" / "logs").is_dir()


# ----- check, answers ----------------------------------------------------------------

class _BuildHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        body = json.dumps({"line": "RivalsVidMaker abc1234 01/02/2026", "sha": "abc1234",
                           "dirty": False, "date": "01/02/2026", "boot_id": "boot123abc",
                           "started_at": "2026-11-17T10:00:00+00:00"}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


def _free_port() -> int:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def test_check_prints_build_and_boot_id_and_exits_zero_when_server_answers():
    server = HTTPServer(("127.0.0.1", 0), _BuildHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        lines = []
        code = launcher.check(server.server_address[1], listener=lambda p: None, out=lines.append)
        assert launcher.answers(server.server_address[1]) is True
    finally:
        server.shutdown()
        server.server_close()
    assert code == 0
    assert "RivalsVidMaker abc1234 01/02/2026" in lines
    assert "boot_id boot123abc" in lines


def test_check_exits_nonzero_when_nothing_answers():
    port = _free_port()
    lines = []
    assert launcher.check(port, listener=lambda p: None, out=lines.append) == 1
    assert launcher.answers(port) is False
    assert lines and lines[0].startswith(f"not running on port {port}")


# ----- launch lifecycle ---------------------------------------------------------------

class _FakeProc:
    def __init__(self, code=None):
        self.code = code

    def poll(self):
        return self.code


def _recorder_popen(calls, proc=None):
    def popen(argv, **kwargs):
        calls.append((argv, kwargs))
        return proc or _FakeProc()
    return popen


def test_launch_refuses_on_blocking_failure_and_spawns_nothing(tmp_path):
    calls, opened = [], []
    code = launcher.launch(
        0, ["--launch"], dialog=False, browser=True, popen=_recorder_popen(calls),
        preflight_fn=lambda p: [launcher.Check("config", False, "bad", True)],
        listener=lambda p: None, open_browser=opened.append, repo_root=tmp_path)
    assert code == 1
    assert calls == [] and opened == []


def test_launch_starts_with_missing_tool_so_the_page_can_show_the_fix(tmp_path):
    calls, opened = [], []
    code = launcher.launch(
        0, ["--launch", "--fixture", "empty", "--no-watch"], dialog=False, browser=True,
        popen=_recorder_popen(calls),
        preflight_fn=lambda p: [launcher.Check("ffmpeg", False, FFMPEG_FIX, False)],
        listener=lambda p: None, ready=lambda p: True, open_browser=opened.append,
        repo_root=tmp_path)
    assert code == 0
    argv, kwargs = calls[0]
    assert argv[1:3] == ["-m", "gui"] and "--fixture" in argv and "--no-watch" in argv
    assert kwargs["cwd"] == str(tmp_path)
    assert kwargs["env"]["PYTHONPATH"] == str(tmp_path / "src")
    assert opened == [launcher.security.open_url(0)]


def test_launch_over_an_old_instance_stops_it_and_does_not_open_a_second_browser(tmp_path):
    calls, opened, stopped = [], [], []
    code = launcher.launch(
        0, [], dialog=False, browser=True, popen=_recorder_popen(calls),
        preflight_fn=lambda p: [], listener=lambda p: 4242, stop_fn=stopped.append,
        ready=lambda p: True, open_browser=opened.append, repo_root=tmp_path)
    assert code == 0
    assert stopped == [0]
    assert opened == []


def test_launch_with_no_browser_flag_never_opens_a_browser(tmp_path):
    calls, opened = [], []
    launcher.launch(
        0, [], dialog=False, browser=False, popen=_recorder_popen(calls),
        preflight_fn=lambda p: [], listener=lambda p: None, ready=lambda p: True,
        open_browser=opened.append, repo_root=tmp_path)
    assert opened == []


def test_launch_reports_a_child_that_exits_before_answering(tmp_path):
    calls = []
    code = launcher.launch(
        0, [], dialog=False, browser=True,
        popen=_recorder_popen(calls, proc=_FakeProc(code=1)),
        preflight_fn=lambda p: [], listener=lambda p: None, ready=lambda p: False,
        open_browser=lambda url: pytest.fail("no browser after a failed start"),
        repo_root=tmp_path)
    assert code == 1


def test_child_argv_drops_launcher_flags_and_keeps_fixture_and_no_watch():
    argv = launcher.child_argv("pythonw.exe", 8476, [
        "--launch", "--fixture", "empty", "--no-watch", "--port", "9", "--no-browser", "--no-dialog"])
    assert argv == ["pythonw.exe", "-m", "gui", "--fixture", "empty", "--no-watch", "--port", "8476"]


def test_log_path_is_one_file_per_day_under_data_logs(tmp_path):
    assert launcher.log_path(tmp_path, date(2026, 11, 17)) == tmp_path / "data" / "logs" / "gui_2026-11-17.log"


def test_log_line_writes_to_todays_file(tmp_path):
    launcher.log_line("launch", "spawning test", repo_root=tmp_path)
    files = list((tmp_path / "data" / "logs").glob("gui_*.log"))
    assert len(files) == 1 and re.fullmatch(r"gui_\d{4}-\d{2}-\d{2}\.log", files[0].name)
    assert "[launch] spawning test" in files[0].read_text(encoding="utf-8")


def test_wait_port_free_is_false_while_held_and_true_after_release():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    s.listen()
    port = s.getsockname()[1]
    try:
        assert launcher.wait_port_free(port, timeout=0.3) is False
    finally:
        s.close()
    assert launcher.wait_port_free(port, timeout=2.0) is True


def test_parse_netstat_listener_finds_the_listening_pid():
    text = ("  TCP    127.0.0.1:8476    0.0.0.0:0    LISTENING    4321\n"
            "  TCP    127.0.0.1:9000    0.0.0.0:0    LISTENING    77\n")
    assert launcher.parse_netstat_listener(text, 8476) == 4321
    assert launcher.parse_netstat_listener(text, 1234) is None


def test_parse_tcp_table_listener_accepts_blank_and_listen_state():
    assert launcher.parse_tcp_table_listener("127.0.0.1 4321 Listen\n", 8476) == 4321
    assert launcher.parse_tcp_table_listener("127.0.0.1 4321\n", 8476) == 4321
    assert launcher.parse_tcp_table_listener("0.0.0.0 4321 Listen\n", 8476) is None


# ----- gui.bat -----------------------------------------------------------------------

def test_gui_bat_runs_pythonw_launch_and_ends_exit_zero():
    text = BAT.read_text(encoding="utf-8")
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    assert "pythonw -m gui --launch %*" in lines
    assert lines[-1] == "exit /b 0"


def test_gui_bat_has_no_user_specific_path_and_no_window_holding_shell():
    text = BAT.read_text(encoding="utf-8")
    assert not re.search(r"[A-Za-z]:\\", text)
    assert "Users" not in text and "GitHubRepos" not in text
    assert "cmd /k" not in text and "pause" not in text
    assert "start " not in text.lower()


def test_gui_bat_sets_pythonpath_to_src_relative_to_the_bat():
    text = BAT.read_text(encoding="utf-8")
    assert 'cd /d "%~dp0.."' in text
    assert 'set "PYTHONPATH=%CD%\\src"' in text


# ----- __main__: verbs, page handler, lazy shell, job wiring --------------------------

def test_parse_args_reads_the_documented_flags():
    args = gui_main.parse_args(["--launch", "--fixture", "empty", "--no-watch", "--port", "9000"])
    assert args.launch is True and args.fixture == "empty" and args.no_watch is True
    assert args.port == 9000 and args.command is None


@pytest.mark.parametrize("verb", ["ui_check"])
def test_stub_subcommands_say_not_built_yet_and_exit_two(verb, capsys):
    assert gui_main.main([verb]) == 2
    assert "not built yet" in capsys.readouterr().out


def test_check_flag_dispatches_to_launcher_check(monkeypatch):
    seen = []
    monkeypatch.setattr(launcher, "check", lambda port: seen.append(port) or 0)
    assert gui_main.main(["--check", "--port", "9"]) == 0
    assert seen == [9]


def test_launch_flag_passes_the_raw_argv_through(monkeypatch):
    seen = {}

    def fake_launch(port, passthrough, **kwargs):
        seen.update(port=port, passthrough=passthrough, **kwargs)
        return 0

    monkeypatch.setattr(launcher, "launch", fake_launch)
    assert gui_main.main(["--launch", "--no-browser", "--fixture", "empty"]) == 0
    assert seen["passthrough"] == ["--launch", "--no-browser", "--fixture", "empty"]
    assert seen["browser"] is False and seen["dialog"] is True


class _StubSource:
    def __init__(self, payload, fixture=None):
        self.payload = payload
        self.fixture = fixture

    def read(self):
        return dict(self.payload)


def test_page_handler_passes_the_tab_to_the_injected_builder():
    calls = []
    source, runner = _StubSource({}), object()
    handler = gui_main.make_page_handler(source, runner, builder=lambda s, r, tab: calls.append((s, r, tab)))
    handler(tab="archive")
    assert calls == [(source, runner, "archive")]


def test_default_builder_imports_shell_only_when_a_page_is_built(monkeypatch):
    seen = []
    stub = types.ModuleType("gui.shell")
    stub.build_page = lambda source, *, initial_tab=None, **kwargs: seen.append(initial_tab)
    monkeypatch.setitem(sys.modules, "gui.shell", stub)
    handler = gui_main.make_page_handler(_StubSource({}), object(), builder=None)
    handler(tab="clips")
    assert seen == ["clips"]


def test_wired_source_adds_the_running_job_and_history_to_the_snapshot(tmp_path):
    runner = jobs.JobRunner(tmp_path / "jobs.json")
    release = threading.Event()
    runner.start("scan", "Scan Clips", lambda ctx: release.wait(5))
    try:
        wired = gui_main.WiredSource(_StubSource({"activity": []}), runner)
        assert wired.read()["job"]["title"] == "Scan Clips"
        assert state_api.StateApi(wired).snapshot()["job"]["title"] == "Scan Clips"
    finally:
        release.set()
        runner.wait(5)
    history = gui_main.WiredSource(_StubSource({"activity": []}), runner).read()["activity"]
    assert history[0]["title"] == "Scan Clips" and history[0]["state"] == jobs.DONE
    shown = view_model.snapshot(gui_main.WiredSource(_StubSource({}), runner))
    assert shown["activity"]["jobs"][0]["result"] == jobs.DONE


def test_wired_source_keeps_fixture_job_and_activity_when_runner_is_idle(tmp_path):
    payload = {"job": {"id": "f1", "kind": "scan", "title": "Fixture job"},
               "activity": [{"kind": "sort", "title": "Sort", "result": "done"}]}
    runner = jobs.JobRunner(tmp_path / "jobs.json")
    wired = gui_main.WiredSource(_StubSource(payload, fixture="empty"), runner)
    data = wired.read()
    assert data["job"]["title"] == "Fixture job"
    assert data["activity"] == payload["activity"]
    assert wired.fixture == "empty"


# ----- hot reload --------------------------------------------------------------------

def test_trigger_path_is_data_dot_cache_under_the_repo():
    assert Path(hot_reload.TRIGGER_PATH).resolve() == (REPO / "data" / ".cache" / "reload.trigger").resolve()


def test_trigger_is_deferred_while_a_job_runs(tmp_path, monkeypatch):
    trigger = tmp_path / "reload.trigger"
    trigger.write_text("x", encoding="utf-8")
    restarts = []
    monkeypatch.setattr(hot_reload, "_restart", lambda: restarts.append(1))
    handled = hot_reload._check_trigger(str(tmp_path), str(trigger), busy=lambda: True)
    assert handled is True
    assert trigger.exists() and restarts == []


def test_trigger_with_a_syntax_error_does_not_restart(tmp_path, monkeypatch):
    watch = tmp_path / "src"
    watch.mkdir()
    (watch / "bad.py").write_text("def broken(:\n", encoding="utf-8")
    trigger = tmp_path / "reload.trigger"
    trigger.write_text("x", encoding="utf-8")
    restarts = []
    monkeypatch.setattr(hot_reload, "_restart", lambda: restarts.append(1))
    assert hot_reload._check_trigger(str(watch), str(trigger), busy=lambda: False) is True
    assert restarts == []


def test_trigger_restarts_when_idle_and_the_source_compiles(tmp_path, monkeypatch):
    watch = tmp_path / "src"
    watch.mkdir()
    (watch / "good.py").write_text("x = 1\n", encoding="utf-8")
    trigger = tmp_path / "reload.trigger"
    trigger.write_text("x", encoding="utf-8")
    restarts = []
    monkeypatch.setattr(hot_reload, "_restart", lambda: restarts.append(1))
    hot_reload._check_trigger(str(watch), str(trigger), busy=lambda: False)
    assert restarts == [1]
    assert not trigger.exists()


def test_check_syntax_names_the_bad_file(tmp_path):
    (tmp_path / "bad.py").write_text("def broken(:\n", encoding="utf-8")
    ok, error = hot_reload.check_syntax(str(tmp_path))
    assert ok is False and "bad.py" in error


def test_restart_runs_the_module_form_with_the_same_arguments():
    assert hot_reload.restart_argv(["--port", "0"]) == [sys.executable, "-m", "gui", "--port", "0"]
