# copied from a sibling local GUI kit (main.py)
"""Page shell: chrome, the tab bar and one panel per tab, built lazily on first show.

build_page(...) is the one entry point; the launcher calls it inside its page function.
Tab buttons carry id tab-<key> (chrome.DEBUG_JS setTab clicks them) and data-testid nav-<key>.
Panels carry data-testid tab-<key> and role=tabpanel. A builder that raises paints
tab-error-<key> in its panel; the other tabs still open. ?tab= is kept in step with the
URL with history.replaceState when the user switches tabs.
"""
from __future__ import annotations

import importlib
import logging
from collections.abc import Callable

from nicegui import ui

from gui import build_info, chrome, tabdefs, tokens

_log = logging.getLogger("rvm.gui")


def _default_builder(key: str) -> Callable:
    return importlib.import_module(f"gui.tabs.{key}").build


def _sync_url(key: str) -> None:
    try:
        ui.run_javascript(f"history.replaceState(null,'','/?tab={key}');")
    except RuntimeError:  # no client connected (for example during a simulated test run)
        pass


def build_page(source, *, initial_tab: str | None = None, state_word: str = "Idle",
               state_kind: str = "idle", updated_seconds: float | None = None,
               builders: dict[str, Callable] | None = None) -> None:
    """Paint the whole page for one source.

    source: a Source (fixture or real); only .fixture and each tab's build(source) are read.
    initial_tab: the ?tab= value; anything not in tabdefs.KEYS opens the default tab.
    state_word, state_kind: the header state word and dot kind (chrome.header_html).
    updated_seconds: seconds since the last state update for the footer; None shows "not updated yet".
    builders: optional {key: build(source)} overriding tabs/<key>.py; used by tests.
    """
    active = initial_tab if initial_tab in tabdefs.KEYS else tabdefs.DEFAULT
    overrides = builders or {}
    panels: dict[str, ui.element] = {}
    buttons: dict[str, ui.element] = {}
    built: set[str] = set()

    ui.add_head_html(chrome.head_html())
    # Same markup as chrome.body_html's error banner; the footer must sit below the panels,
    # so the pieces are placed one by one.
    ui.html('<div id="error-banner" role="alert" data-testid="error-banner" hidden></div>')
    ui.html(chrome.header_html(state_word, state_kind))
    ui.html(chrome.fixture_banner_html(source.fixture))

    def paint(key: str) -> None:
        if key in built:
            return
        built.add(key)
        with panels[key]:
            try:
                build = overrides.get(key) or _default_builder(key)
                build(source)
            except Exception as e:  # a broken tab must not kill the page
                _log.exception("tab build failed: %s", key)
                ui.label(f"This tab failed to build: {e}").props(
                    f'data-testid=tab-error-{key} role=alert').mark(f"tab-error-{key}")

    def show(key: str) -> None:
        for k, panel in panels.items():
            panel.set_visibility(k == key)
        for k, button in buttons.items():
            button.props(f'aria-selected={"true" if k == key else "false"}')
        paint(key)

    def switch(key: str) -> None:
        show(key)
        _sync_url(key)

    with ui.element("div").classes("rvm-tabs").props('role=tablist aria-label="Sections"'):
        for key in tabdefs.KEYS:
            button = ui.element("button").classes("rvm-tab").props(
                f'id=tab-{key} type=button role=tab data-testid=nav-{key} aria-controls=panel-{key} '
                f'aria-selected={"true" if key == active else "false"}')
            button.mark(f"nav-{key}")
            with button:
                ui.html(tabdefs.label_of(key))
            button.on("click", lambda _e=None, k=key: switch(k))
            buttons[key] = button

    for key in tabdefs.KEYS:
        panel = ui.column().props(
            f'id=panel-{key} role=tabpanel data-testid=tab-{key} aria-labelledby=tab-{key}'
        ).style(f"gap:0;padding:{tokens.SPACE_24}px;")
        panel.mark(f"tab-{key}")
        panel.set_visibility(key == active)
        panels[key] = panel

    paint(active)

    ui.html(chrome.footer_html(build_info.line(), build_info.STARTED_AT, updated_seconds))
