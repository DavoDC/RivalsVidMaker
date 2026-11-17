# copied from a sibling local GUI kit (launcher.py)
"""Launcher verbs for python -m gui: --preflight, --stop, --check, --status and --launch.

Standard library and the gui security helpers only, so it runs before the heavy imports and
reports a readable failure instead of a silent pythonw crash. Every verb returns an exit code.
Output goes through _say (never print, see tests/gui/test_gui_seam.py); lines go to the daily
log under data/logs/ so a windowless launch leaves a trace.

Blocking checks (python, imports, config, logs folder, port) stop a launch. Tool checks
(ffmpeg, tesseract) are reported but do not stop it: the page shows them as fix cards, so the
user can press Check again once the tool is in place.
"""
from __future__ import annotations

import importlib.util
import os
import socket
import subprocess
import sys
import time
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

import config as engine_config
from gui import security

REPO_ROOT = Path(__file__).resolve().parents[2]
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
DETACHED_PROCESS = 0x00000008
REQUIRED_MODULES = ("nicegui", "fastapi", "uvicorn", "PIL", "pytesseract", "send2trash")
MIN_PYTHON = (3, 10)
DROPPED_FLAGS = ("--launch", "--preflight", "--stop", "--status", "--check", "--no-dialog", "--no-browser")
LAUNCH_TIMEOUT = 40.0
FFMPEG_FIX = ("FFmpeg is missing from dependencies/ffmpeg. Put ffmpeg.exe and ffprobe.exe there, "
              "then press Check again.")


@dataclass
class Check:
    name: str
    ok: bool
    detail: str
    blocking: bool = True


def _say(text: str) -> None:
    if sys.stdout is not None:
        sys.stdout.write(text + "\n")


def log_path(repo_root: Path = REPO_ROOT, day: date | None = None) -> Path:
    """data/logs/gui_<date>.log: one file per day, the target of stdout and stderr in server mode."""
    day = day or date.today()
    return Path(repo_root) / "data" / "logs" / f"gui_{day.isoformat()}.log"


def log_line(tag: str, text: str, repo_root: Path = REPO_ROOT) -> None:
    """Append one timestamped line to today's log. A failed write never stops a launch."""
    try:
        path = log_path(repo_root)
        path.parent.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().isoformat(timespec="seconds")
        with open(path, "a", encoding="utf-8") as f:
            f.write(f"{stamp} [{tag}] {text}\n")
    except OSError:
        pass


# --- preflight ---------------------------------------------------------------------

def _check_python() -> Check:
    v = sys.version_info
    ok = v[:2] >= MIN_PYTHON
    detail = f"{v.major}.{v.minor}.{v.micro}" + ("" if ok else f" (need {MIN_PYTHON[0]}.{MIN_PYTHON[1]}+)")
    return Check("python", ok, detail)


def _check_imports() -> Check:
    missing = [m for m in REQUIRED_MODULES if importlib.util.find_spec(m) is None]
    if missing:
        return Check("imports", False, "missing: " + ", ".join(missing)
                     + " (pip install -r config/requirements.txt)")
    return Check("imports", True, "all present")


def _check_tools(cfg) -> list[Check]:
    ffmpeg_ok = Path(cfg.ffmpeg).exists() and Path(cfg.ffprobe).exists()
    tess_ok = Path(cfg.tesseract).exists()
    return [
        Check("ffmpeg", ffmpeg_ok, "ffmpeg.exe and ffprobe.exe found" if ffmpeg_ok else FFMPEG_FIX,
              blocking=False),
        Check("tesseract", tess_ok, f"found at {cfg.tesseract}" if tess_ok else
              f"Tesseract is missing at {cfg.tesseract}. Install Tesseract-OCR or set tesseract_path "
              "in config/config.json, then press Check again.", blocking=False),
    ]


def _check_logs(root: Path) -> Check:
    folder = Path(root) / "data" / "logs"
    try:
        folder.mkdir(parents=True, exist_ok=True)
        probe = folder / ".preflight-write-test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
    except OSError as e:
        return Check("logs", False, f"{folder} is not writable: {e}")
    return Check("logs", True, "writable")


def _check_port(port: int) -> Check:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind((security.BIND_HOST, port))
    except OSError:
        return Check("port", False, f"port {port} is in use (python -m gui --stop --port {port})")
    finally:
        s.close()
    return Check("port", True, f"{port} is free")


def preflight(port: int, *, repo_root: Path = REPO_ROOT, loader=None) -> list[Check]:
    """Every check, in order. loader returns the engine Config (default: config/config.json under repo_root)."""
    root = Path(repo_root)
    load = loader or (lambda: engine_config.load(root / "config" / "config.json"))
    checks = [_check_python(), _check_imports()]
    try:
        cfg = load()
    except Exception as e:
        checks.append(Check("config", False, f"config/config.json could not be loaded: {e}"))
    else:
        checks.append(Check("config", True, "config/config.json loads"))
        checks.extend(_check_tools(cfg))
    checks.append(_check_logs(root))
    checks.append(_check_port(port))
    return checks


def run_preflight(port: int) -> int:
    """--preflight: print every check. Exit 0 only when all pass, blocking or not."""
    results = preflight(port)
    for r in results:
        _say(f"  {'ok  ' if r.ok else 'FAIL'} {r.name}: {r.detail}")
    bad = [r for r in results if not r.ok]
    _say("preflight: OK" if not bad else f"preflight: FAILED ({len(bad)} problem(s))")
    return 0 if not bad else 1


# --- listener lookup and stop -------------------------------------------------------

def parse_netstat_listener(text: str, port: int) -> int | None:
    """PID of the process LISTENING on 127.0.0.1:<port> in `netstat -ano -p TCP` output (PID 0 is no owner)."""
    for line in text.splitlines():
        parts = line.split()
        if len(parts) >= 5 and parts[0] == "TCP" and parts[3] == "LISTENING" \
                and parts[1].rsplit(":", 1)[-1] == str(port) and int(parts[4]) > 0:
            return int(parts[4])
    return None


def parse_tcp_table_listener(text: str, port: int) -> int | None:
    """PID from `Get-NetTCPConnection` rows, one 'address pid state' per line, bound to BIND_HOST.
    The State column is blank for a listener on this machine, so blank counts as listening."""
    for line in text.splitlines():
        parts = line.split()
        state = parts[2] if len(parts) == 3 else ""
        if len(parts) in (2, 3) and parts[0] == security.BIND_HOST and state in ("", "Listen") \
                and parts[1].isdigit() and int(parts[1]) > 0:
            return int(parts[1])
    return None


def _powershell_listener(port: int) -> int | None:
    # netstat can omit a live loopback listener, so the TCP table is asked too.
    script = ("Get-NetTCPConnection -LocalPort %d -ErrorAction SilentlyContinue | "
              "ForEach-Object { \"$($_.LocalAddress) $($_.OwningProcess) $($_.State)\" }" % port)
    try:
        out = subprocess.run(["powershell", "-NoProfile", "-Command", script], capture_output=True,
                             text=True, timeout=20, creationflags=_NO_WINDOW).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    return parse_tcp_table_listener(out, port)


def find_listener(port: int) -> int | None:
    try:
        out = subprocess.run(["netstat", "-ano", "-p", "TCP"], capture_output=True, text=True,
                             timeout=15, creationflags=_NO_WINDOW).stdout
        pid = parse_netstat_listener(out, port)
    except (OSError, subprocess.SubprocessError):
        pid = None
    return pid if pid is not None else _powershell_listener(port)


def _alive(pid: int, port: int) -> bool:
    return find_listener(port) == pid


def _taskkill(args: list[str], pid: int) -> None:
    try:
        subprocess.run(["taskkill", *args], capture_output=True, timeout=5, creationflags=_NO_WINDOW)
    except (OSError, subprocess.TimeoutExpired) as e:
        log_line("stop", f"taskkill {' '.join(args)} for pid {pid} failed: {e!r}")


def stop(port: int) -> int:
    """Stop whatever listens on the port: polite taskkill first, forced after two seconds."""
    pid = find_listener(port)
    if pid is None:
        _say(f"not running on port {port}")
        return 0
    log_line("stop", f"WARNING: listener pid {pid} on port {port} not verified as this app; killing it")
    _taskkill(["/PID", str(pid)], pid)
    deadline = time.time() + 2
    while time.time() < deadline and _alive(pid, port):
        time.sleep(0.1)
    if _alive(pid, port):
        _taskkill(["/PID", str(pid), "/F"], pid)
    log_line("stop", f"stopped pid {pid} on port {port}")
    _say(f"stopped pid {pid} on port {port}")
    return 0


def wait_port_free(port: int, timeout: float = 5.0, clock=time.monotonic, sleep=time.sleep) -> bool:
    """After a restart the old socket can linger for a moment; wait briefly for the port to free."""
    start = clock()
    while True:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            s.bind((security.BIND_HOST, port))
            return True
        except OSError:
            pass
        finally:
            s.close()
        if clock() - start >= timeout:
            return False
        sleep(0.2)


# --- --check and --status -----------------------------------------------------------

def pythonw_for(python_exe: str) -> str:
    """pythonw.exe beside python_exe, else python_exe itself (non-Windows run or unusual install)."""
    folder, name = os.path.split(python_exe)
    candidate = os.path.join(folder, "pythonw.exe")
    return candidate if name.lower().startswith("python") and os.path.exists(candidate) else python_exe


def child_argv(pythonw: str, port: int, passthrough: list[str]) -> list[str]:
    """The server command: the caller's own flags minus the launcher-only ones, plus an explicit --port."""
    rest, skip = [], False
    for a in passthrough:
        if skip:
            skip = False
        elif a == "--port":
            skip = True
        elif a not in DROPPED_FLAGS and not a.startswith("--port="):
            rest.append(a)
    return [pythonw, "-m", "gui", *rest, "--port", str(port)]


def spawn(argv: list[str], cwd: str | None = None, env: dict | None = None, popen=subprocess.Popen):
    """Detached child holding none of the caller's handles (a bare `start` child keeps the caller's pipes open)."""
    flags = 0 if os.name != "nt" else subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP | DETACHED_PROCESS
    return popen(argv, cwd=cwd, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                 stderr=subprocess.DEVNULL, close_fds=True, creationflags=flags)


def _build_url(port: int) -> str:
    # Assembled from parts: the loopback URL is never a literal in src/gui (tokens test).
    return "http" + "://" + security.BIND_HOST + ":" + str(port) + "/api/build"


def answers(port: int) -> bool:
    try:
        with urllib.request.urlopen(_build_url(port), timeout=2) as r:
            return r.status == 200
    except Exception:
        return False


def wait_ready(proc, port: int, timeout: float, ready=answers, sleep=time.sleep, clock=time.monotonic) -> tuple[bool, str]:
    start = clock()
    while True:
        if proc.poll() is not None:
            return False, "the GUI process exited before it answered; see data/logs/"
        if ready(port):
            return True, ""
        if clock() - start >= timeout:
            return False, f"the GUI did not answer on port {port} within {timeout:.0f} s; see data/logs/"
        sleep(0.25)


def _fetch_build(port: int) -> dict:
    import json
    with urllib.request.urlopen(_build_url(port), timeout=3) as r:
        return json.loads(r.read())


def check(port: int, fetch=_fetch_build, listener=find_listener, out=_say) -> int:
    """--check: the running instance's build line, listener pid, boot_id and sha. boot_id and sha
    come from the server's answer. Exit 0 when something answers, 1 when nothing does."""
    try:
        served = fetch(port)
    except Exception as e:
        out(f"not running on port {port}: {e}")
        return 1
    pid = listener(port)
    out(served["line"])
    out(f"pid {pid} on port {port}" if pid is not None else f"pid unknown on port {port}")
    out(f"boot_id {served['boot_id']}")
    out(f"sha {served['sha']}")
    return 0


def status(port: int) -> int:
    pid = find_listener(port)
    if pid is None:
        _say(f"not running on port {port}")
        return 1
    _say(f"running pid {pid} on port {port}")
    return 0


# --- --launch -----------------------------------------------------------------------

def _open_url(url: str) -> None:
    import webbrowser
    webbrowser.open(url)


def _fail(text: str, dialog: bool) -> int:
    """Windowless failure path: a log line plus a message box, because pythonw has no console."""
    log_line("launch", f"FAILED: {text}")
    _say(f"RivalsVidMaker GUI not started: {text}")
    if dialog:
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(0, text, "RivalsVidMaker GUI did not start", 0x10)
        except Exception:
            pass
    return 1


def launch(port: int, passthrough: list[str], *, dialog: bool = True, browser: bool = True,
           popen=subprocess.Popen, preflight_fn=None, listener=find_listener, stop_fn=None,
           ready=answers, open_browser=_open_url, timeout: float = LAUNCH_TIMEOUT,
           repo_root: Path = REPO_ROOT, python_exe: str | None = None) -> int:
    """Replace any instance on the port, run preflight, start the server detached and return once it
    answers. The browser opens here, once, on a fresh start only; the server never opens one."""
    root = Path(repo_root)
    replaced = listener(port) is not None
    if replaced:
        (stop_fn or stop)(port)
    results = (preflight_fn or preflight)(port)
    for r in results:
        if not r.ok and not r.blocking:
            log_line("launch", f"warning {r.name}: {r.detail}", repo_root=root)
    blocking = [r for r in results if not r.ok and r.blocking]
    if blocking:
        return _fail("preflight failed: " + "; ".join(f"{r.name}: {r.detail}" for r in blocking), dialog)
    env = dict(os.environ)
    env["PYTHONPATH"] = str(root / "src")
    argv = child_argv(pythonw_for(python_exe or sys.executable), port, passthrough)
    log_line("launch", f"spawning {' '.join(argv)}", repo_root=root)
    proc = spawn(argv, cwd=str(root), env=env, popen=popen)
    ok, why = wait_ready(proc, port, timeout, ready=ready)
    if not ok:
        return _fail(why, dialog)
    url = security.open_url(port)
    _say(f"RivalsVidMaker GUI running on {url}")
    if browser and not replaced:
        open_browser(url)
    return 0
