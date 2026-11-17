"""Page shell (tab buttons, lazy panels, ?tab= deep link) and the painted-state check (ui_check).

The page tests run the NiceGUI user simulator (nicegui.testing.user_simulation) from sync
tests. The pytest-asyncio plugin is not installed, so the async simulator is driven with
asyncio.run instead of the user fixture; the simulated page is the same.
"""
import asyncio
import re

import pytest
from nicegui import ui
from nicegui.element_filter import ElementFilter
from nicegui.testing.user_simulation import user_simulation

from gui import __main__ as gui_main
from gui import jobs, shell, tabdefs, theme, ui_check
from gui.sources import FixtureSource

KEYS = ("clips", "compile", "videos", "archive", "activity")


def _recording_builders(calls):
    """One builder per tab key; each appends its key to calls when it runs."""
    def make(key):
        def build(source):
            calls.append(key)
        return build
    return {key: make(key) for key in KEYS}


def _failing_builder(source):
    raise RuntimeError("boom in clips")


async def _open(tab, builders, action=None):
    """Open /?tab=<tab> in the simulator, then return action(user) when given, else None."""
    def root(tab: str = "clips"):
        shell.build_page(FixtureSource("empty"), initial_tab=tab, builders=builders)

    async with user_simulation(root) as user:
        await user.open(f"/?tab={tab}")
        if action is None:
            return None
        return await action(user)


def _visible_panels(user):
    """Map each tab key to whether its panel (marker tab-<key>) is shown."""
    shown = {}
    with user.client:
        for key in KEYS:
            found = list(ElementFilter(marker=f"tab-{key}", only_visible=False))
            shown[key] = any(e.visible for e in found)
    return shown


def _has_marker(user, marker):
    with user.client:
        return bool(list(ElementFilter(marker=marker, only_visible=False)))


def _only(key):
    return {k: (k == key) for k in KEYS}


@pytest.mark.parametrize("key", KEYS)
def test_each_tab_key_in_the_query_opens_its_panel(key):
    calls = []

    async def action(user):
        return _visible_panels(user)

    shown = asyncio.run(_open(key, _recording_builders(calls), action))
    assert shown == _only(key)
    assert calls == [key]


@pytest.mark.parametrize("key", KEYS)
def test_default_tab_modules_paint_without_an_error(key):
    async def action(user):
        return _has_marker(user, f"tab-error-{key}"), _visible_panels(user)

    error, shown = asyncio.run(_open(key, None, action))
    assert not error
    assert shown == _only(key)


def test_only_the_requested_tab_is_built_at_first_paint():
    calls = []
    asyncio.run(_open("compile", _recording_builders(calls)))
    assert calls == ["compile"]


def test_tab_buttons_carry_the_ids_the_debug_surface_clicks():
    # chrome.DEBUG_JS setTab clicks document.getElementById('tab-' + key); the buttons must use those ids.
    async def action(user):
        with user.client:
            buttons = {k: list(ElementFilter(marker=f"nav-{k}", only_visible=False)) for k in KEYS}
            panels = {k: list(ElementFilter(marker=f"tab-{k}", only_visible=False)) for k in KEYS}
        return buttons, panels

    buttons, panels = asyncio.run(_open("clips", _recording_builders([]), action))
    for key in KEYS:
        assert len(buttons[key]) == 1
        assert buttons[key][0]._props["id"] == f"tab-{key}"
        assert buttons[key][0]._props["data-testid"] == f"nav-{key}"
        assert panels[key][0]._props["data-testid"] == f"tab-{key}"
        assert panels[key][0]._props["role"] == "tabpanel"


def test_unknown_tab_falls_back_to_clips():
    async def action(user):
        return _visible_panels(user)

    assert asyncio.run(_open("nope", _recording_builders([]), action)) == _only("clips")


def test_failing_builder_paints_error_and_other_tabs_still_open():
    calls = []
    builders = _recording_builders(calls)
    builders["clips"] = _failing_builder

    async def action(user):
        error_painted = _has_marker(user, "tab-error-clips")
        clips_at_first = _visible_panels(user)["clips"]
        user.find(marker="nav-compile").click()
        return error_painted, clips_at_first, _visible_panels(user)

    error_painted, clips_at_first, after = asyncio.run(_open("clips", builders, action))
    assert error_painted
    assert clips_at_first
    assert after == _only("compile")
    assert "compile" in calls


def test_clicking_a_tab_builds_it_once_and_hides_the_others():
    calls = []

    async def action(user):
        user.find(marker="nav-videos").click()
        user.find(marker="nav-videos").click()
        return _visible_panels(user)

    shown = asyncio.run(_open("clips", _recording_builders(calls), action))
    assert shown == _only("videos")
    assert calls == ["clips", "videos"]


def test_tab_keys_and_labels_match_the_design_table():
    assert tuple(key for key, _label in tabdefs.TABS) == KEYS
    assert [label for _key, label in tabdefs.TABS] == ["Clips", "Compile", "Videos", "Archive", "Activity"]


# ---- one content column: 100% wide, capped at 1280 px (docs/DESIGN.md section 11) ----

def test_page_root_column_is_full_width_capped_at_1280():
    async def action(user):
        with user.client:
            return list(ElementFilter(marker="page-root", only_visible=False))

    roots = asyncio.run(_open("clips", _recording_builders([]), action))
    assert len(roots) == 1
    assert roots[0]._style["width"] == "100%"
    assert roots[0]._style["max-width"] == "1280px"
    # NiceGUI columns default to align-items:flex-start, which shrink-wraps each child to its content
    assert roots[0]._style["align-items"] == "stretch"
    # centred, 24 px side gutters, header 16 px from the top (docs/DESIGN.md section 11)
    assert roots[0]._style["margin"] == "0 auto"
    assert roots[0]._style["padding"] == "16px 24px 0"


def test_each_tab_panel_stretches_to_the_content_column():
    async def action(user):
        with user.client:
            return {k: list(ElementFilter(marker=f"tab-{k}", only_visible=False)) for k in KEYS}

    panels = asyncio.run(_open("clips", _recording_builders([]), action))
    for key in KEYS:
        assert len(panels[key]) == 1
        assert panels[key][0]._style["align-items"] == "stretch"


def test_shared_css_gives_table_cells_horizontal_padding_and_full_width_tables():
    css = theme.HEAD_CSS
    assert "table{width:100%;}" in css
    assert "table th,table td{padding-left:12px !important;padding-right:12px !important;}" in css


def test_shared_css_removes_the_nicegui_wrapper_padding_so_the_header_sits_16px_down():
    # NiceGUI's .nicegui-content adds 1rem padding and gap; the root column owns the spacing now
    assert ".nicegui-content{padding:0 !important;gap:0 !important;}" in theme.HEAD_CSS


def test_shared_css_header_is_one_row_with_the_state_pushed_right():
    assert ".rvm-header{display:flex;align-items:center;justify-content:space-between;" in theme.HEAD_CSS


# ---- ui_check: painted testids against the state rows, both ways ----

def _state(character_ids, folder_ids):
    return {"clips": {"characters": [{"testid": t} for t in character_ids]},
            "videos": {"folders": [{"testid": t} for t in folder_ids]}}


def test_ui_check_passes_when_painted_rows_match_state():
    state_ids = ui_check.state_row_ids(_state(["clip-char-thor-aaaaaa"], ["video-thor-vid1-bbbbbb"]))
    painted = {"clip-char-thor-aaaaaa", "video-thor-vid1-bbbbbb"}
    assert ui_check.problems(state_ids, painted) == []


def test_ui_check_fails_on_a_missing_row():
    state_ids = ui_check.state_row_ids(_state(["clip-char-thor-aaaaaa"], ["video-thor-vid1-bbbbbb"]))
    problems = ui_check.problems(state_ids, {"clip-char-thor-aaaaaa"})
    assert any("missing" in p and "video-thor-vid1-bbbbbb" in p for p in problems)


def test_ui_check_fails_on_an_extra_painted_row():
    state_ids = ui_check.state_row_ids(_state(["clip-char-thor-aaaaaa"], []))
    problems = ui_check.problems(state_ids, {"clip-char-thor-aaaaaa", "video-ghost-000000"})
    assert any("unexpected" in p and "video-ghost-000000" in p for p in problems)


def test_ui_check_ignores_shell_testids_that_are_not_rows():
    html = ('<button data-testid="nav-clips"></button><div data-testid="header"></div>'
            '<div data-testid="clip-char-thor-aaaaaa"></div>')
    painted = ui_check.painted_rows(ui_check.extract_testids(html))
    assert painted == {"clip-char-thor-aaaaaa"}


def test_ui_check_exit_code_follows_failures():
    assert ui_check.exit_code([]) == 0
    assert ui_check.exit_code(["missing row"]) == 1


# ---- header state word: from the running job, Error after a failure (docs/DESIGN.md section 4) ----

def test_header_state_is_idle_without_a_job():
    assert shell.header_state(None, False) == ("Idle", "idle")


def test_header_state_shows_the_phase_word_and_integer_percent_when_total_is_known():
    assert shell.header_state({"phase": "encoding", "done": 3, "total": 9}, False) == ("Encoding 33%", "working")
    assert shell.header_state({"phase": "encoding", "done": 9, "total": 9}, False) == ("Encoding 100%", "working")


def test_header_state_has_the_phase_word_alone_when_total_is_unknown_or_zero():
    assert shell.header_state({"phase": "encoding", "done": 3, "total": None}, False) == ("Encoding", "working")
    assert shell.header_state({"phase": "encoding", "done": 0, "total": 0}, False) == ("Encoding", "working")


def test_header_state_says_working_when_the_job_has_no_phase():
    assert shell.header_state({"phase": None, "done": None, "total": None}, False) == ("Working", "working")


def test_header_state_is_error_after_a_failed_job():
    assert shell.header_state(None, True) == ("Error", "error")


def test_a_running_job_outranks_an_earlier_failure():
    assert shell.header_state({"phase": "encoding", "done": 3, "total": 9}, True) == ("Encoding 33%", "working")


_HEADER_STATE_SPAN = re.compile(r'<span id="rvm-state"[^>]*data-kind="([^"]*)">([^<]*)</span>')


def _default_page_header(source, runner):
    """Paint the page builder that python -m gui serves; return the header (word, kind) it painted."""
    def root():
        gui_main._default_builder(source, runner, None)

    async def action(user):
        with user.client:
            for el in ElementFilter(kind=ui.html, only_visible=False):
                match = _HEADER_STATE_SPAN.search(el.content or "")
                if match:
                    return match.group(2), match.group(1)
        return None

    async def run():
        async with user_simulation(root) as user:
            await user.open("/")
            return await action(user)

    return asyncio.run(run())


def test_default_page_header_says_idle_with_no_job(tmp_path):
    runner = jobs.JobRunner(tmp_path / "jobs.json")
    assert _default_page_header(gui_main.WiredSource(FixtureSource("empty"), runner), runner) == ("Idle", "idle")


def test_default_page_header_shows_the_encoding_fixture_job_as_working(tmp_path):
    runner = jobs.JobRunner(tmp_path / "jobs.json")
    header = _default_page_header(gui_main.WiredSource(FixtureSource("encoding"), runner), runner)
    assert header == ("Encoding 33%", "working")


def test_default_page_header_says_error_after_a_failed_job_then_idle_after_a_clean_one(tmp_path):
    runner = jobs.JobRunner(tmp_path / "jobs.json")

    def boom(ctx):
        raise RuntimeError("disk gone")

    runner.start("scan", "Scan Clips", boom)
    assert runner.wait(5)
    source = gui_main.WiredSource(FixtureSource("empty"), runner)
    assert _default_page_header(source, runner) == ("Error", "error")

    runner.start("scan", "Scan Clips", lambda ctx: None)
    assert runner.wait(5)
    assert _default_page_header(gui_main.WiredSource(FixtureSource("empty"), runner), runner) == ("Idle", "idle")


# ---- actions: clips, compile and videos get their tab's dict; archive and activity get none ----

def _arg_recording_builders(calls):
    """Each builder records the extra arguments it was given after the source."""
    def make(key):
        def build(source, *rest):
            calls.append((key, rest))
        return build
    return {key: make(key) for key in KEYS}


def test_build_page_passes_each_action_tab_its_dict_and_not_archive_or_activity():
    calls = []
    builders = _arg_recording_builders(calls)
    tabs_seen = {}

    def actions(key):
        tabs_seen.setdefault(key, {"for": key})
        return tabs_seen[key]

    async def action(user):
        for key in ("compile", "videos", "archive", "activity"):
            user.find(marker=f"nav-{key}").click()

    async def run():
        def root():
            shell.build_page(FixtureSource("empty"), initial_tab="clips", builders=builders, actions=actions)

        async with user_simulation(root) as user:
            await user.open("/?tab=clips")
            await action(user)

    asyncio.run(run())
    assert ("clips", ({"for": "clips"},)) in calls
    assert ("compile", ({"for": "compile"},)) in calls
    assert ("videos", ({"for": "videos"},)) in calls
    assert ("archive", ()) in calls
    assert ("activity", ()) in calls


def test_make_page_handler_passes_the_actions_to_the_builder(tmp_path):
    calls = []
    source, runner, actions = object(), object(), object()
    handler = gui_main.make_page_handler(source, runner, builder=lambda s, r, tab, a: calls.append((s, r, tab, a)),
                                         actions=actions)
    handler(tab="compile")
    assert calls == [(source, runner, "compile", actions)]


def test_default_builder_hands_the_actions_as_a_key_lookup_to_build_page(monkeypatch):
    import sys
    import types

    seen = {}
    stub = types.ModuleType("gui.shell")
    stub.build_page = lambda source, *, initial_tab=None, actions=None: seen.update(actions=actions)
    monkeypatch.setitem(sys.modules, "gui.shell", stub)

    class Lookup:
        def for_tab(self, key):
            return {"key": key}

    gui_main._default_builder(object(), object(), "clips", Lookup())
    assert seen["actions"]("clips") == {"key": "clips"}


# ----- build_page registers its repaint on the page's client ----------------------------

def test_register_repaint_sets_the_attribute_on_the_client(monkeypatch):
    from types import SimpleNamespace
    client = SimpleNamespace()
    monkeypatch.setattr(shell, "ui", SimpleNamespace(context=SimpleNamespace(client=client)))

    def repaint():
        pass

    shell._register_repaint(repaint)
    assert client.rvm_repaint is repaint


def test_register_repaint_swallows_the_no_context_error(monkeypatch):
    class NoContextUi:
        @property
        def context(self):
            raise RuntimeError("slot stack empty")

    monkeypatch.setattr(shell, "ui", NoContextUi())
    shell._register_repaint(lambda: None)


def test_a_simulated_page_registers_a_repaint_on_its_client():
    seen = {}

    def root():
        shell.build_page(FixtureSource("empty"), initial_tab="clips", builders=_recording_builders([]))

    async def run():
        async with user_simulation(root) as user:
            await user.open("/?tab=clips")
            seen["repaint"] = getattr(user.client, "rvm_repaint", None)

    asyncio.run(run())
    assert callable(seen["repaint"])
