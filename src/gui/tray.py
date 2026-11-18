"""A Windows tray icon for the GUI process: Open, Reload and Quit once the browser tab is closed.

The GUI runs windowless, so this icon is the only visible handle on it. It shows the plain app mark
(gui.icon.render) and the header state word in its tooltip. A named mutex lets only one process show
an icon: a hot reload starts the new process before the old one exits, so the new one retries the
lock for LOCK_RETRY_SECONDS. pystray is imported lazily inside _run, so the helpers below run
without it; the icon runs on a daemon thread and never blocks the server.
"""
from __future__ import annotations

import os
import sys
import threading
import time
import webbrowser
from pathlib import Path

from gui import hot_reload, icon, last_tab, launcher

LOCK_NAME = "Local" + chr(92) + "RivalsVidMakerTray"
LOCK_RETRY_SECONDS = 8.0
LOCK_RETRY_STEP_SECONDS = 0.5
POLL_SECONDS = 5.0
TITLE_MAX = 127
OPEN_LABEL = "Open RivalsVidMaker"
RELOAD_LABEL = "Reload"
QUIT_LABEL = "Quit"
DOUBLE_CLICK_WINDOW_SECONDS = 0.75
OPEN_DEBOUNCE_SECONDS = 1.0
BUSY_NOTE = "A job is running. Quit when it finishes."
ERROR_ALREADY_EXISTS = 183

_open_lock = threading.Lock()
_last_open = None  # monotonic time of the last open that went through


def enabled(fixture) -> bool:
    """False when RVM_GUI_TRAY is 0 or the server runs a fixture (a canned, test-only run)."""
    return os.environ.get("RVM_GUI_TRAY", "1").strip() != "0" and not fixture


def acquire_lock(name: str = LOCK_NAME):
    """Hold the named mutex. None when another process holds it (ERROR_ALREADY_EXISTS) or it cannot be
    created; off Windows there is no mutex, so a plain object stands in for the handle."""
    if sys.platform != "win32":
        return object()
    import ctypes
    from ctypes import wintypes
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateMutexW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
    kernel32.CreateMutexW.restype = wintypes.HANDLE
    handle = kernel32.CreateMutexW(None, False, name)
    if not handle:
        return None
    if ctypes.get_last_error() == ERROR_ALREADY_EXISTS:
        kernel32.CloseHandle(handle)  # we opened the other process's mutex; give it back
        return None
    return handle


def release_lock(handle) -> None:
    if handle is None or sys.platform != "win32":
        return
    import ctypes
    ctypes.WinDLL("kernel32").CloseHandle(handle)


def _acquire_with_retry(name: str = LOCK_NAME, seconds: float = LOCK_RETRY_SECONDS):
    deadline = time.monotonic() + seconds
    while True:
        handle = acquire_lock(name)
        if handle is not None or time.monotonic() >= deadline:
            return handle
        time.sleep(LOCK_RETRY_STEP_SECONDS)


def app_url(port: int, tab: str | None = None) -> str:
    if tab is None:
        return f"http://127.0.0.1:{port}/"
    return f"http://127.0.0.1:{port}/?tab={tab}"


def open_once(url: str, opener=None, clock=time.monotonic) -> bool:
    """Open url unless an open went through within OPEN_DEBOUNCE_SECONDS, so a burst opens one tab.
    True when this call opened it."""
    global _last_open
    with _open_lock:
        now = clock()
        if _last_open is not None and now - _last_open < OPEN_DEBOUNCE_SECONDS:
            return False
        _last_open = now
    (opener or webbrowser.open)(url)
    return True


def make_double_click_handler(url_fn, window: float = DOUBLE_CLICK_WINDOW_SECONDS,
                              clock=time.monotonic, opener=None):
    """A zero-argument handler: the second click within window opens url_fn(); a first click only arms."""
    armed = {"at": None}

    def handler():
        now = clock()
        at = armed["at"]
        if at is not None and now - at <= window:
            armed["at"] = None
            open_once(url_fn(), opener=opener, clock=clock)
            return
        armed["at"] = now

    return handler


def request_reload(path=None) -> None:
    """Touch the hot-reload trigger so the watcher restarts the app when it is idle."""
    trigger = Path(path or hot_reload.TRIGGER_PATH)
    trigger.parent.mkdir(parents=True, exist_ok=True)
    trigger.touch()


def quit_or_note(is_busy, shutdown, notify) -> bool:
    """Quit when idle (True); while a job runs, tell the user and keep running (False)."""
    if is_busy():
        notify(BUSY_NOTE)
        return False
    shutdown()
    return True


def tooltip(state_word: str) -> str:
    return f"RivalsVidMaker: {state_word}"[:TITLE_MAX]


def menu_action(cb):
    """pystray inspects the callback's arity, so every action takes (icon, item)."""
    return lambda icon_, item: cb()


def menu_items(port: int, quit_cb) -> list:
    """The visible menu as (label, callback) pairs: Open, Reload, Quit."""
    return [
        (OPEN_LABEL, lambda: open_once(app_url(port, last_tab.get()))),
        (RELOAD_LABEL, lambda: request_reload()),
        (QUIT_LABEL, quit_cb),
    ]


def build_menu_items(pystray, port: int, quit_cb) -> list:
    """pystray MenuItems: the three visible items, then a hidden default so a double left click opens."""
    items = [pystray.MenuItem(label, menu_action(cb)) for label, cb in menu_items(port, quit_cb)]
    double = make_double_click_handler(lambda: app_url(port, last_tab.get()))
    items.append(pystray.MenuItem("", menu_action(double), default=True, visible=False))
    return items


def _poll(ti, state_word) -> None:
    """Refresh the tooltip every POLL_SECONDS. Never raises: a failed read keeps the old tooltip."""
    while True:
        time.sleep(POLL_SECONDS)
        try:
            ti.title = tooltip(state_word())
        except Exception:
            pass


def _run(port, is_busy, shutdown, state_word) -> None:
    handle = _acquire_with_retry()
    if handle is None:
        launcher.log_line("tray", "another process holds the tray icon; this one shows none")
        return
    try:
        try:
            import pystray
        except ImportError as exc:
            launcher.log_line("tray", f"pystray is not installed, no tray icon: {exc}")
            return
        ti = None

        def quit_cb():
            if quit_or_note(is_busy, shutdown, lambda m: ti.notify(m, "RivalsVidMaker")):
                ti.stop()  # remove the icon now, not when Windows notices the dead process

        menu = pystray.Menu(*build_menu_items(pystray, port, quit_cb))
        ti = pystray.Icon("RivalsVidMaker", icon.render(64), tooltip(state_word()), menu)
        threading.Thread(target=_poll, args=(ti, state_word), name="rvm-tray-poll", daemon=True).start()
        launcher.log_line("tray", f"icon up for port {port}")
        ti.run()
    except Exception as exc:
        launcher.log_line("tray", f"tray stopped: {exc}")
    finally:
        release_lock(handle)


def start(port: int, *, is_busy, shutdown, state_word, fixture=None):
    """Run the tray on a daemon thread and return it; None when the tray is disabled."""
    if not enabled(fixture):
        return None
    thread = threading.Thread(target=_run, args=(port, is_busy, shutdown, state_word),
                              name="rvm-tray", daemon=True)
    thread.start()
    return thread
