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

from gui import build_info, chrome, jobs, tabdefs, tokens, view_model

_log = logging.getLogger("rvm.gui")
ACTION_TABS = ("clips", "compile", "videos")  # the tabs whose build() takes an actions dict


def _default_builder(key: str) -> Callable:
    return importlib.import_module(f"gui.tabs.{key}").build


def _phase_word(phase) -> str:
    text = str(phase or "").strip()
    return text[:1].upper() + text[1:] if text else "Working"


def header_state(job: dict | None, last_failed: bool) -> tuple[str, str]:
    """The header state word and dot kind (docs/DESIGN.md section 4).

    job: the snapshot's running job (view_model._job) or None. A running job wins; a failed last
    job reads Error until the next start; otherwise Idle. A job reads its capitalised phase word,
    plus the integer percent when the total is known and above zero.
    """
    if job:
        word = _phase_word(job.get("phase"))
        done, total = job.get("done"), job.get("total")
        if done is not None and total:
            word += f" {min(100, int(100 * done / total))}%"
        return word, "working"
    if last_failed:
        return "Error", "error"
    return "Idle", "idle"


def _header_from_source(source) -> tuple[str, str]:
    snap = view_model.snapshot(source)
    history = snap["activity"]["jobs"]
    last_failed = bool(history) and history[0]["result"] == jobs.FAILED
    return header_state(snap["job"], last_failed)


def _sync_url(key: str) -> None:
    try:
        ui.run_javascript(f"history.replaceState(null,'','/?tab={key}');")
    except RuntimeError:  # no client connected (for example during a simulated test run)
        pass


def build_page(source, *, initial_tab: str | None = None, state_word: str | None = None,
               state_kind: str | None = None, updated_seconds: float | None = None,
               builders: dict[str, Callable] | None = None,
               actions: Callable[[str], dict] | None = None) -> None:
    """Paint the whole page for one source.

    source: a Source (fixture or real); .fixture, the snapshot's job and activity, and each tab's build(source) are read.
    initial_tab: the ?tab= value; anything not in tabdefs.KEYS opens the default tab.
    state_word, state_kind: the header state word and dot kind (chrome.header_html). Left None, both come
    from header_state() on the same snapshot the page paints: the running job, else a failed last job.
    updated_seconds: seconds since the last state update for the footer; None shows "not updated yet".
    builders: optional {key: build(source)} overriding tabs/<key>.py; used by tests.
    actions: optional key -> action dict. clips, compile and videos are built with build(source, actions(key));
    archive and activity, and every tab when actions is None, are built with build(source).
    """
    active = initial_tab if initial_tab in tabdefs.KEYS else tabdefs.DEFAULT
    overrides = builders or {}
    if state_word is None:
        state_word, state_kind = _header_from_source(source)
    state_kind = state_kind or "idle"
    panels: dict[str, ui.element] = {}
    buttons: dict[str, ui.element] = {}
    built: set[str] = set()

    ui.add_head_html(chrome.head_html())
    # One content column: header, banner, tabs, panels and footer all span it, capped at
    # 1280 px (docs/DESIGN.md section 11). Without it each piece shrink-wraps its content.
    root = ui.column().style("width:100%;max-width:1280px;margin:0 auto;padding:16px 24px 0;"
                             "box-sizing:border-box;gap:0;align-items:stretch;")
    root.mark("page-root")
    with root:
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
                    if actions is not None and key in ACTION_TABS:
                        build(source, actions(key))
                    else:
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
            ).style(f"gap:0;padding:{tokens.SPACE_24}px;align-items:stretch;")
            panel.mark(f"tab-{key}")
            panel.set_visibility(key == active)
            panels[key] = panel

        paint(active)

        ui.html(chrome.footer_html(build_info.line(), build_info.STARTED_AT, updated_seconds))
