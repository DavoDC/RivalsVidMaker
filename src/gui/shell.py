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
import time
from collections.abc import Callable

from nicegui import ui

from gui import build_info, chrome, jobs, last_tab, tabdefs, tokens, view_model

_log = logging.getLogger("rvm.gui")
ACTION_TABS = ("clips", "compile", "videos")  # the tabs whose build() takes an actions dict
POLL_SECONDS = 1.0     # how often a page with a job runner checks the job signature
REPAINT_SECONDS = 2.0  # least gap between repaints when only a running job's progress changed
CLOCK = time.monotonic  # module-level so tests can replace the throttle clock


def job_signature(source) -> tuple | None:
    """What a page repaints on: (running id, state, done, newest history id, newest history state).

    None when the source has no runner. Reads only the runner, never source.read(), because a
    real read scans the library on disk.
    """
    runner = getattr(source, "runner", None)
    if runner is None:
        return None
    current = runner.current()
    if current is None:
        running = (None, None, None)
    else:
        running = (current.get("id"), current.get("state"), int(current.get("done") or 0))
    history = runner.history()
    newest = (history[0].get("id"), history[0].get("state")) if history else (None, None)
    return running + newest


def _structure(sig: tuple) -> tuple:
    """The signature without the running job's done count."""
    return (sig[0], sig[1], sig[3], sig[4])


PAST = {  # the past-tense verb a finished job toasts (docs/DESIGN.md section 8)
    "sort": "Sorted clips.", "scan": "Scanned for KOs.", "compile": "Compiled video.",
    "upload": "Uploaded to YouTube.", "cleanup": "Cleaned up.", "uncompile": "Restored clips.",
    "sign_in": "Signed in to YouTube.",
}


def finish_toast(prev: tuple | None, sig: tuple | None, record: dict | None) -> tuple[str, str] | None:
    """The toast for a job that just finished, failed or was cancelled, else None.

    prev, sig: job signatures before and after the change. record: the newest history record.
    Only a new newest history id or state toasts, and only when the record is that same job.
    """
    if prev is None or sig is None or sig[3] is None:
        return None
    if (sig[3], sig[4]) == (prev[3], prev[4]):
        return None
    state = sig[4]
    if state not in (jobs.DONE, jobs.FAILED, jobs.CANCELLED):
        return None
    if not record or record.get("id") != sig[3]:
        return None
    kind = record.get("kind")
    title = record.get("title") or ""
    if state == jobs.DONE:
        if kind == "recycle_clip":
            name = title[len("Recycle "):] if title.startswith("Recycle ") else title
            return f'Recycled "{name}".', "positive"
        if kind in PAST:
            return PAST[kind], "positive"
        return f"{title} finished.", "positive"
    if state == jobs.FAILED:
        error = record.get("error") or ""
        return (f"{title} failed: {error}" if error else f"{title} failed."), "negative"
    return f"{title} was cancelled.", "info"


class Poller:
    """Repaints when the job signature changes. A start, finish or failure repaints on the next
    tick; a progress-only change repaints at most once per REPAINT_SECONDS. The signature is
    re-read on every tick, so a held-back change lands on a later tick without another change."""

    def __init__(self, signature_fn: Callable[[], tuple], repaint_fn: Callable[[], None],
                 clock: Callable[[], float] | None = None,
                 on_change: Callable[[tuple, tuple], None] | None = None):
        self._signature_fn = signature_fn
        self._repaint_fn = repaint_fn
        self._clock = clock
        self._on_change = on_change
        self._last = signature_fn()  # the page was painted from this signature
        self._last_paint: float | None = None

    def _now(self) -> float:
        return self._clock() if self._clock is not None else CLOCK()

    def tick(self) -> bool:
        """Repaint if the page is stale. True when a repaint ran."""
        sig = self._signature_fn()
        if sig == self._last:
            return False
        now = self._now()
        structural = _structure(sig) != _structure(self._last)
        due = self._last_paint is None or now - self._last_paint >= REPAINT_SECONDS
        if not (structural or due):
            return False
        if structural and self._on_change is not None:
            self._on_change(self._last, sig)
        self._last = sig
        self._last_paint = now
        self._repaint_fn()
        return True


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


def _finish_notifier(source) -> Callable[[tuple, tuple], None]:
    """Poller on_change: toast a finished job. No client (a unit test) means no toast."""
    def on_change(prev: tuple, sig: tuple) -> None:
        history = source.runner.history()
        toast = finish_toast(prev, sig, history[0] if history else None)
        if toast is None:
            return
        text, kind = toast
        try:
            ui.notify(text, type=kind)
        except RuntimeError:  # no client connected (for example during a simulated test run)
            pass
    return on_change


def _register_repaint(repaint: Callable[[], None]) -> None:
    """Keep the page's repaint on its client so wiring actions can refresh the page in place."""
    try:
        ui.context.client.rvm_repaint = repaint
    except (RuntimeError, AttributeError):  # no client context (for example in a unit test)
        pass


def build_page(source, *, initial_tab: str | None = None, state_word: str | None = None,
               state_kind: str | None = None,
               builders: dict[str, Callable] | None = None,
               actions: Callable[[str], dict] | None = None) -> None:
    """Paint the whole page for one source.

    source: a Source (fixture or real); .fixture, the snapshot's job and activity, and each tab's build(source) are read.
    initial_tab: the ?tab= value; anything not in tabdefs.KEYS opens the default tab.
    state_word, state_kind: the header state word and dot kind (chrome.header_html). Left None, both come
    from header_state() on the same snapshot the page paints: the running job, else a failed last job.
    builders: optional {key: build(source)} overriding tabs/<key>.py; used by tests.
    actions: optional key -> action dict. clips, compile and videos are built with build(source, actions(key));
    archive and activity, and every tab when actions is None, are built with build(source).
    """
    active = initial_tab if initial_tab in tabdefs.KEYS else tabdefs.DEFAULT
    last_tab.remember(active)
    overrides = builders or {}
    if state_word is None:
        state_word, state_kind = _header_from_source(source)
    state_kind = state_kind or "idle"
    panels: dict[str, ui.element] = {}
    buttons: dict[str, ui.element] = {}
    built: set[str] = set()
    current = active  # the visible tab; show() keeps it in step

    ui.add_head_html(chrome.head_html())
    # One content column: header, banner, tabs, panels and footer all span it, capped at
    # 1280 px (docs/DESIGN.md section 11). Without it each piece shrink-wraps its content.
    root = ui.column().style("width:100%;max-width:1280px;margin:0 auto;padding:0 24px 0;"
                             "box-sizing:border-box;gap:0;align-items:stretch;")
    root.mark("page-root")
    with root:
        # Same markup as chrome.body_html's error banner; the footer must sit below the panels,
        # so the pieces are placed one by one.
        ui.html('<div id="error-banner" role="alert" data-testid="error-banner" hidden></div>')
        header = ui.html(chrome.header_html(state_word, state_kind))
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
            nonlocal current
            current = key
            last_tab.remember(key)
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
                    f'aria-selected={"true" if key == active else "false"} onmousedown="event.preventDefault()"')
                button.mark(f"nav-{key}")
                with button:
                    ui.html(tabdefs.label_of(key))
                button.on("click", lambda _e=None, k=key: switch(k))
                buttons[key] = button

        for key in tabdefs.KEYS:
            panel = ui.column().props(
                f'id=panel-{key} role=tabpanel data-testid=tab-{key} aria-labelledby=tab-{key}'
            ).style(f"gap:0;padding:{tokens.SPACE_16}px {tokens.SPACE_24}px {tokens.SPACE_24}px;align-items:stretch;")
            panel.mark(f"tab-{key}")
            panel.set_visibility(key == active)
            panels[key] = panel

        def repaint() -> None:
            # Stale tabs clear now; the visible one repaints at once, the others when shown.
            built.clear()
            for panel in panels.values():
                panel.clear()
            header.set_content(chrome.header_html(*_header_from_source(source)))
            paint(current)

        _register_repaint(repaint)
        paint(active)

        ui.html(chrome.footer_html(build_info.short(), build_info.line(), build_info.STARTED_AT))

        if job_signature(source) is not None:  # only a page with a job runner can go stale
            poller = Poller(lambda: job_signature(source), repaint, on_change=_finish_notifier(source))
            ui.timer(POLL_SECONDS, poller.tick)
