# copied from a sibling local GUI kit (hot_reload.py)
"""Poor-man's autoreload for the GUI: watches src/*.py and restarts the whole
process in place (os.execv) so ANY change takes effect without closing and
reopening the app.

Two ways a restart triggers:

  - Explicit signal (preferred for a deliberate multi-file build): create
    data/.cache/reload.trigger and the next poll restarts immediately (after a
    syntax check).
  - Passive fallback: once the watched file set has gone quiet for
    DEBOUNCE_SECONDS (long by design), it restarts on its own.

Either way, before restarting every .py file must compile (check_syntax()). A
syntax error means "not ready yet": the watcher logs a warning and keeps the old
process running. A running job defers the restart (BUSY_CHECK, set by the
launcher to JobRunner.busy). A green test run does not prove the live GUI
survived an edit; check the page after a risky change.

Standard library only. On by default; --no-watch turns it off.
"""

import logging
import os
import sys
import threading
import time

log = logging.getLogger(__name__)

POLL_SECONDS = 1.0
# Very long on purpose: a build can run for a long time between saves with zero
# risk of an unwanted mid-build restart; the explicit trigger is the fast path.
DEBOUNCE_SECONDS = 3600.0

# Touch this file to reload immediately (checked every poll, consumed on read).
# Lives in data/.cache (gitignored) next to the other GUI-local state.
TRIGGER_PATH = os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "..", "data", ".cache", "reload.trigger"))

# Set on os.environ right before a self-restart; inherited by the re-exec'd process.
RESTART_ENV_VAR = "AM_GUI_HOT_RELOAD_RESTART"


def snapshot(watch_dir: str, extra_files: list = None) -> dict:
    """Return {path: mtime} for every .py file under watch_dir, plus any extra_files."""
    snap = {}
    for root, _dirs, files in os.walk(watch_dir):
        for name in files:
            if name.endswith(".py"):
                path = os.path.join(root, name)
                try:
                    snap[path] = os.path.getmtime(path)
                except OSError:
                    pass
    for path in (extra_files or []):
        try:
            snap[path] = os.path.getmtime(path)
        except OSError:
            pass
    return snap


def check_syntax(watch_dir: str) -> tuple:
    """Compile-check every .py file under watch_dir in memory (no bytecode written).
    Returns (True, None) if all compile, else (False, "path: error")."""
    for root, _dirs, files in os.walk(watch_dir):
        for name in files:
            if name.endswith(".py"):
                path = os.path.join(root, name)
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        source = f.read()
                    compile(source, path, "exec")
                except SyntaxError as e:
                    return False, f"{path}: {e}"
                except OSError:
                    pass
    return True, None


def restart_argv(argv: list) -> list:
    """The server command again, in module form so package imports resolve the same way."""
    return [sys.executable, "-m", "gui", *argv]


def _restart():
    os.environ[RESTART_ENV_VAR] = "1"
    os.execv(sys.executable, restart_argv(sys.argv[1:]))


BUSY_CHECK = None  # set by the launcher: callable returning True while a job runs


def _is_busy(busy=None) -> bool:
    fn = busy or BUSY_CHECK
    try:
        return bool(fn()) if fn else False
    except Exception:
        return False


def _check_trigger(watch_dir: str, trigger_path: str, busy=None) -> bool:
    """If trigger_path exists, consume it and restart after a syntax check. A running
    job leaves the trigger in place so it fires after the job ends. Returns True when
    it handled a trigger, so the caller skips the debounce logic for this poll."""
    if not os.path.exists(trigger_path):
        return False
    if _is_busy(busy):
        log.info("Reload trigger deferred: a job is running")
        return True
    try:
        os.remove(trigger_path)
    except OSError:
        pass
    ok, error = check_syntax(watch_dir)
    if not ok:
        log.warning("Reload triggered but not restarting - syntax error: %s", error)
        return True
    log.info("Reload triggered explicitly (%s) - restarting the GUI", trigger_path)
    _restart()
    return True  # unreachable after a real restart; kept for clarity and tests


def watch_loop(
    watch_dir: str,
    poll_interval: float = POLL_SECONDS,
    extra_files: list = None,
    debounce_seconds: float = DEBOUNCE_SECONDS,
    trigger_path: str = None,
):
    """Poll watch_dir (+ extra_files) forever. Restarts on an explicit trigger, or after the
    file set has been quiet for debounce_seconds; both gated by a syntax check. Does not
    return: os.execv replaces the process."""
    trigger_path = trigger_path or TRIGGER_PATH
    baseline = snapshot(watch_dir, extra_files)
    previous = baseline
    stable_since = None
    while True:
        time.sleep(poll_interval)

        if _check_trigger(watch_dir, trigger_path):
            continue

        current = snapshot(watch_dir, extra_files)

        if current == baseline:
            stable_since = None
            previous = current
            continue

        if current != previous:
            # still actively changing: reset the quiet-period timer
            stable_since = time.time()
            previous = current
            continue

        if stable_since is None or (time.time() - stable_since) < debounce_seconds:
            continue

        if _is_busy():
            continue
        ok, error = check_syntax(watch_dir)
        if not ok:
            log.warning("Change detected but not restarting - syntax error: %s", error)
            continue

        log.info("Code change detected under %s - restarting the GUI", watch_dir)
        _restart()


def start_watcher(
    watch_dir: str,
    poll_interval: float = POLL_SECONDS,
    extra_files: list = None,
) -> threading.Thread:
    """Start the file watcher in a background daemon thread."""
    t = threading.Thread(
        target=watch_loop, args=(watch_dir, poll_interval, extra_files), daemon=True
    )
    t.start()
    log.info("Hot-reload watcher started for %s (+ %d extra file(s))", watch_dir, len(extra_files or []))
    return t
