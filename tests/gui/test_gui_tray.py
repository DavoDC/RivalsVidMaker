"""The tray icon: Open, Reload and Quit from a Windows tray icon hosted in the GUI process.

Nothing here imports pystray for real or creates an icon. The fake pystray records MenuItem arguments,
the open and reload callbacks are swapped for recorders so no browser opens and no trigger file is
written under data/, and the mutex test uses its own name so a running real tray is never touched.
"""
import sys
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest

from gui import last_tab, tray

REPO_ROOT = Path(__file__).resolve().parents[2]
MAIN_SRC = REPO_ROOT / "src" / "gui" / "__main__.py"


class FakeMenuItem:
    def __init__(self, text, action, **kwargs):
        self.text = text
        self.action = action
        self.kwargs = kwargs


FAKE_PYSTRAY = SimpleNamespace(MenuItem=FakeMenuItem)


class Clock:
    def __init__(self, now=0.0):
        self.now = now

    def __call__(self):
        return self.now


@pytest.fixture(autouse=True)
def _reset_open_debounce(monkeypatch):
    monkeypatch.setattr(tray, "_last_open", None)


@pytest.fixture(autouse=True)
def _fresh_last_tab():
    last_tab.reset()
    yield
    last_tab.reset()


def test_enabled_is_false_for_a_fixture_and_for_env_zero(monkeypatch):
    monkeypatch.setenv("RVM_GUI_TRAY", "1")
    assert tray.enabled(None) is True
    assert tray.enabled("busy_refused") is False
    monkeypatch.setenv("RVM_GUI_TRAY", "0")
    assert tray.enabled(None) is False


def test_menu_labels_are_open_reload_quit_and_never_stop():
    items = tray.menu_items(8765, lambda: None)
    labels = [label for label, _cb in items]
    assert labels == ["Open RivalsVidMaker", "Reload", "Quit"]
    assert not any("Stop" in label for label in labels)


def test_app_url_is_loopback_with_the_port():
    assert tray.app_url(8765) == "http://localhost:8765/"


def test_app_url_with_a_tab_adds_the_tab_query():
    assert tray.app_url(8000, "videos") == "http://localhost:8000/?tab=videos"
    assert tray.app_url(8000) == "http://localhost:8000/"


def test_open_item_opens_the_remembered_tab_at_click_time(monkeypatch):
    opened = []
    monkeypatch.setattr(tray, "open_once", lambda url, **kw: opened.append(url))
    open_cb = tray.menu_items(8000, lambda: None)[0][1]
    last_tab.remember("videos")
    open_cb()
    last_tab.reset()
    open_cb()
    assert opened == ["http://localhost:8000/?tab=videos", "http://localhost:8000/"]


def test_double_click_item_opens_the_remembered_tab_at_click_time(monkeypatch):
    opened = []
    monkeypatch.setattr(tray, "open_once", lambda url, **kw: opened.append(url))
    items = tray.build_menu_items(FAKE_PYSTRAY, 8000, lambda: None)
    default = [item for item in items if item.kwargs.get("default") is True][0]
    last_tab.remember("archive")
    default.action(None, None)  # first click only arms
    default.action(None, None)  # second click, back to back, lands inside the 0.75 s window
    assert opened == ["http://localhost:8000/?tab=archive"]


def test_open_once_opens_once_for_two_calls_0_2_seconds_apart():
    opened = []
    clock = Clock(10.0)
    assert tray.open_once("http://127.0.0.1:1/", opener=opened.append, clock=clock) is True
    clock.now = 10.2
    assert tray.open_once("http://127.0.0.1:1/", opener=opened.append, clock=clock) is False
    assert opened == ["http://127.0.0.1:1/"]


def test_open_once_opens_twice_for_two_calls_2_seconds_apart():
    opened = []
    clock = Clock(10.0)
    tray.open_once("http://127.0.0.1:1/", opener=opened.append, clock=clock)
    clock.now = 12.0
    tray.open_once("http://127.0.0.1:1/", opener=opened.append, clock=clock)
    assert len(opened) == 2


def test_double_click_handler_opens_on_the_second_click_within_the_window_only():
    opened = []
    clock = Clock(10.0)
    handler = tray.make_double_click_handler(lambda: "http://127.0.0.1:1/", window=0.75,
                                             clock=clock, opener=opened.append)
    handler()  # first click: nothing opens
    assert opened == []
    clock.now = 10.5  # second click inside 0.75 s
    handler()
    assert opened == ["http://127.0.0.1:1/"]

    handler()  # a lone click much later is a first click again
    clock.now = 13.0
    handler()
    assert opened == ["http://127.0.0.1:1/"]  # no second open: the 2.5 s gap is too long


def test_request_reload_creates_parent_dirs_and_touches_the_trigger(tmp_path):
    trigger = tmp_path / "data" / ".cache" / "reload.trigger"
    tray.request_reload(trigger)
    assert trigger.exists()


def test_quit_busy_notifies_and_does_not_shut_down():
    notes, shut = [], []
    result = tray.quit_or_note(lambda: True, lambda: shut.append(1), notes.append)
    assert result is False
    assert notes == [tray.BUSY_NOTE]
    assert shut == []


def test_quit_idle_shuts_down_and_says_nothing():
    notes, shut = [], []
    result = tray.quit_or_note(lambda: False, lambda: shut.append(1), notes.append)
    assert result is True
    assert shut == [1]
    assert notes == []


def test_tooltip_is_the_state_word_and_cuts_to_127_characters():
    assert tray.tooltip("Idle") == "RivalsVidMaker: Idle"
    assert len(tray.tooltip("x" * 300)) == tray.TITLE_MAX == 127


def test_build_menu_items_gives_three_visible_items_and_one_hidden_default(monkeypatch):
    monkeypatch.setattr(tray, "open_once", lambda url, **kw: None)
    items = tray.build_menu_items(FAKE_PYSTRAY, 8765, lambda: None)
    visible = [item for item in items if item.kwargs.get("visible", True)]
    hidden = [item for item in items if item.kwargs.get("visible") is False]
    assert [item.text for item in visible] == ["Open RivalsVidMaker", "Reload", "Quit"]
    assert len(hidden) == 1
    assert hidden[0].kwargs.get("default") is True


def test_menu_action_callbacks_take_icon_and_item(monkeypatch):
    calls = []
    monkeypatch.setattr(tray, "open_once", lambda url, **kw: calls.append(("open", url)))
    monkeypatch.setattr(tray, "request_reload", lambda path=None: calls.append(("reload",)))
    quits = []
    items = tray.build_menu_items(FAKE_PYSTRAY, 8765, lambda: quits.append(1))
    for item in items:
        item.action(None, None)  # pystray calls every action with (icon, item)
    assert ("open", "http://localhost:8765/") in calls
    assert ("reload",) in calls
    assert quits == [1]


def test_start_returns_none_when_disabled(monkeypatch):
    monkeypatch.setenv("RVM_GUI_TRAY", "1")
    assert tray.start(8765, is_busy=lambda: False, shutdown=lambda: None,
                      state_word=lambda: "Idle", fixture="busy_refused") is None
    monkeypatch.setenv("RVM_GUI_TRAY", "0")
    assert tray.start(8765, is_busy=lambda: False, shutdown=lambda: None,
                      state_word=lambda: "Idle") is None


def test_serve_starts_the_tray_after_register_quit():
    text = MAIN_SRC.read_text(encoding="utf-8")
    assert "tray.start(" in text
    assert text.index("tray.start(") > text.index("state_api.register_quit(")


@pytest.mark.skipif(sys.platform != "win32", reason="named mutex is Windows only")
def test_acquire_lock_is_exclusive_on_windows_and_released_after():
    name = "Local\\RivalsVidMakerTrayTest-" + uuid.uuid4().hex  # never the real tray name
    first = tray.acquire_lock(name)
    assert first is not None
    assert tray.acquire_lock(name) is None
    tray.release_lock(first)
    again = tray.acquire_lock(name)
    assert again is not None
    tray.release_lock(again)


@pytest.mark.skipif(sys.platform == "win32", reason="non-Windows path only")
def test_acquire_lock_off_windows_always_returns_a_handle():
    assert tray.acquire_lock(tray.LOCK_NAME) is not None


def test_tray_urls_never_use_the_127_literal():
    # webapp standard: URLs David's browser opens say localhost, never 127.0.0.1
    import inspect
    assert "127.0.0.1" not in inspect.getsource(tray.app_url)
    assert tray.app_url(1, "clips").startswith("http://localhost:")
