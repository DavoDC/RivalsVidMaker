"""Page shell (tab buttons, lazy panels, ?tab= deep link) and the painted-state check (ui_check).

The page tests run the NiceGUI user simulator (nicegui.testing.user_simulation) from sync
tests. The pytest-asyncio plugin is not installed, so the async simulator is driven with
asyncio.run instead of the user fixture; the simulated page is the same.
"""
import asyncio

import pytest
from nicegui.element_filter import ElementFilter
from nicegui.testing.user_simulation import user_simulation

from gui import shell, tabdefs, ui_check
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
