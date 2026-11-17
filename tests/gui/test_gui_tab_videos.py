"""Videos tab (DESIGN.md sections 8, 9, 11, 12): one row per output folder grouped by stage, the sign-in card,
the clean-up plan list and Danger mode's Restore clips.

Tab tests run the NiceGUI user simulator from sync tests with asyncio.run, as the compile and clips tests do.
Every row carries its view_model testid. Nothing here imports bridge or jobs.
"""
import asyncio
import inspect
import re

import pytest
from nicegui import ui
from nicegui.element_filter import ElementFilter
from nicegui.testing.user_simulation import user_simulation

from gui import fixtures, tokens, view_model
from gui.components import plan_list
from gui.sources import FixtureSource
from gui.tabs import videos as videos_tab

SCENARIOS = ("awaiting_live", "cleanup_plan", "upload_failed", "empty")
ROW_PREFIX = "video-"
FATE_PREFIX = "fate-"
BAD_CHARS = (chr(0x00B7), chr(0x2013), chr(0x2014))
EMPTY_COPY = "No videos yet. Compile one on the Compile tab."
CLEANED_NOTE = "Cleaned up. Clips moved to the archive."
SIGN_IN_LABEL = "Sign in to YouTube again"
RESTORE_LABEL = "Restore clips"
APPLY_TEXT = "Remove 2 files, 1.6 GB"
CLEAN_UP_LABEL = "Clean up"
MARK_LIVE_LABEL = "Mark as live"
UPLOAD_LABEL = "Upload to YouTube"


class _Source(FixtureSource):
    """A fixture scenario with one change applied to its data (a fresh copy per read)."""

    def __init__(self, name, change):
        super().__init__(name)
        self._change = change

    def read(self):
        data = super().read()
        self._change(data)
        return data


def _with_folders(folders):
    def change(data):
        data["output_folders"] = folders
        data["job"] = None
    return _Source("empty", change)


def _no_job(name):
    def change(data):
        data["job"] = None
    return _Source(name, change)


def _recorder(*keys):
    calls = []

    def make(key):
        return lambda *args: calls.append((key, *args))

    return {k: make(k) for k in keys}, calls


# -- user simulator steps: each takes the simulated user, run in order inside the page ----------------

def _press(marker):
    return lambda user: user.find(marker=marker).click()


def _set(marker, value):
    return lambda user: setattr(next(iter(user.find(marker=marker).elements)), "value", value)


def _steps(*fns):
    def run(user):
        for fn in fns:
            fn(user)
    return run


def _session(source, actions=None, steps=None):
    """Open the tab in a simulated page, run steps(user) inside it, and return the live elements."""
    def root():
        videos_tab.build(source, actions)

    async def run():
        async with user_simulation(root) as user:
            await user.open("/")
            if steps is not None:
                steps(user)
            with user.client:
                return list(ElementFilter(only_visible=False))

    return asyncio.run(run())


def _render(source, actions=None):
    """(ui.html content, testids, label texts, buttons) for one open of the tab."""
    elements = _session(source, actions)
    html = "\n".join(e.content for e in elements if isinstance(e, ui.html))
    labels = [e.text for e in elements if isinstance(e, ui.label)]
    props = [e._props.get("data-testid") for e in elements]
    buttons = [e for e in elements if isinstance(e, ui.button)]
    return html, [p for p in props if p], labels, buttons


def _by_marker(elements, marker):
    return [e for e in elements if marker in (getattr(e, "_markers", None) or [])]


def _button_texts(elements):
    return [b.text for b in elements if isinstance(b, ui.button)]


# ---- stage rows ----------------------------------------------------------------------------------

def test_awaiting_live_shows_mark_as_live_and_no_clean_up():
    texts = _button_texts(_session(_no_job("awaiting_live")))
    assert MARK_LIVE_LABEL in texts
    assert CLEAN_UP_LABEL not in texts


def test_clean_up_appears_on_a_live_row_and_not_on_an_uploaded_row():
    texts = _button_texts(_session(_no_job("cleanup_plan")))
    assert CLEAN_UP_LABEL in texts
    assert MARK_LIVE_LABEL not in texts


def test_encoded_row_offers_upload_and_calls_upload_with_slug():
    actions, calls = _recorder("upload")
    source = _with_folders([fixtures.folder("zed_vid1", 1, character="ZED", clips=2)])
    elements = _session(source, actions, steps=_press("upload-zed_vid1"))
    assert UPLOAD_LABEL in _button_texts(elements)
    assert calls == [("upload", "zed_vid1")]


def test_uploaded_row_mark_live_calls_mark_live_with_slug():
    actions, calls = _recorder("mark_live")
    _session(_no_job("awaiting_live"), actions, steps=_press("mark-live-thor_vid1"))
    assert calls == [("mark_live", "thor_vid1")]


def test_open_on_youtube_link_opens_in_a_new_tab_with_https_added():
    source = _with_folders([fixtures.folder(
        "thor_vid1", 1, character="THOR", clips=3, quad_plus=1, has_clips_dir=True, has_desc=True,
        video_url="fixture.test/watch?v=up1")])
    links = [e for e in _session(source) if isinstance(e, ui.link)]
    assert [link._props.get("href") for link in links] == ["https://fixture.test/watch?v=up1"]
    assert links[0]._props.get("target") == "_blank"


def test_open_link_keeps_an_https_url_as_it_is():
    source = _with_folders([fixtures.folder("thor_vid1", 1, clips=3, video_url="https://fixture.test/watch?v=up1")])
    links = [e for e in _session(source) if isinstance(e, ui.link)]
    assert links and links[0]._props.get("href") == "https://fixture.test/watch?v=up1"


def test_live_row_clean_up_calls_plan_cleanup_with_slug():
    actions, calls = _recorder("plan_cleanup")
    _session(_no_job("cleanup_plan"), actions, steps=_press("clean-up-thor_vid1"))
    assert calls == [("plan_cleanup", "thor_vid1")]


def test_cleaned_partly_row_shows_the_note_and_no_buttons():
    source = _with_folders([fixtures.folder("bee_vid1", 0, has_clips_dir=True, has_desc=True, clips=1)])
    _html, _props, labels, buttons = _render(source)
    assert CLEANED_NOTE in labels
    assert buttons == []


def test_rows_group_by_stage_in_encoded_uploaded_live_cleaned_order():
    folders = [
        fixtures.folder("aye_vid1", 1, youtube_confirmed=True, character="AYE", clips=1),
        fixtures.folder("bee_vid1", 0, has_clips_dir=True, has_desc=True, character="BEE", clips=1),
        fixtures.folder("cee_vid1", 1, character="CEE", clips=1, video_url="fixture.test/watch?v=c"),
        fixtures.folder("zed_vid1", 1, character="ZED", clips=1),
    ]
    _html, props, _labels, _buttons = _render(_with_folders(folders))
    rows = [p for p in props if p.startswith(ROW_PREFIX)]
    expected = [view_model.testid("video", s) for s in ("zed_vid1", "cee_vid1", "aye_vid1", "bee_vid1")]
    assert rows == expected


def test_each_row_paints_its_view_model_testid():
    _html, props, _labels, _buttons = _render(_no_job("awaiting_live"))
    painted = {p for p in props if p.startswith(ROW_PREFIX)}
    expected = {f["testid"] for f in view_model.snapshot(FixtureSource("awaiting_live"))["videos"]["folders"]}
    assert painted == expected


def test_numbers_are_separate_labels_with_clips_and_quad_or_better():
    _html, _props, labels, _buttons = _render(_no_job("cleanup_plan"))
    assert "3 clips" in labels
    assert "1 QUAD or better" in labels
    assert not any(BAD_CHARS[0] in text for text in labels)


def test_character_label_uses_the_same_font_size_token_as_the_counts():
    source = _with_folders([fixtures.folder("zed_vid1", 1, character="ZED", clips=2)])
    elements = _session(source)
    character = next(e for e in elements if isinstance(e, ui.label) and e.text == "ZED")
    counts = next(e for e in elements if isinstance(e, ui.label) and e.text == "2 clips")
    assert character._style.get("font-size") == counts._style.get("font-size") == f"{tokens.SIZE_UI}px"
    assert character._style.get("color") == tokens.TEXT_DIM


def test_numbers_use_tabular_figures_and_a_16_px_gap():
    elements = _session(_no_job("cleanup_plan"))
    counts = [e for e in elements if isinstance(e, ui.label) and e.text == "3 clips"]
    assert counts
    assert "tabular-nums" in str(counts[0]._style)
    row = counts[0].parent_slot.parent
    assert row._style.get("gap") == "16px"


# ---- sign-in card --------------------------------------------------------------------------------

def test_auth_error_notice_shows_its_text_and_a_sign_in_button_above_the_rows():
    actions, calls = _recorder("sign_in")
    elements = _session(_no_job("upload_failed"), actions, steps=_press("sign-in"))
    labels = [e.text for e in elements if isinstance(e, ui.label)]
    notice = fixtures.SCENARIOS["upload_failed"]["notices"][0]["text"]
    assert notice in labels
    assert SIGN_IN_LABEL in _button_texts(elements)
    sign_in = _by_marker(elements, "sign-in")[0]
    first_row = next(e for e in elements if e._props.get("data-testid", "").startswith(ROW_PREFIX))
    assert elements.index(sign_in) < elements.index(first_row)
    assert calls == [("sign_in",)]


def test_no_sign_in_card_without_an_auth_error_notice():
    assert SIGN_IN_LABEL not in _button_texts(_session(_no_job("awaiting_live")))


# ---- clean-up plan ------------------------------------------------------------------------------

def test_plan_apply_text_is_built_from_the_totals():
    assert APPLY_TEXT in _button_texts(_session(_no_job("cleanup_plan")))


def test_apply_calls_apply_cleanup_with_nonce_and_unticked_recycle():
    actions, calls = _recorder("apply_cleanup")
    _session(_no_job("cleanup_plan"), actions, steps=_press("apply-cleanup"))
    assert calls == [("apply_cleanup", "fixture-cleanup-nonce", False)]


def test_apply_passes_the_recycle_checkbox_value():
    actions, calls = _recorder("apply_cleanup")
    _session(_no_job("cleanup_plan"), actions,
             steps=_steps(_set("cleanup-recycle", True), _press("apply-cleanup")))
    assert calls == [("apply_cleanup", "fixture-cleanup-nonce", True)]


def test_recycle_checkbox_is_labelled_and_off_by_default():
    boxes = _by_marker(_session(_no_job("cleanup_plan")), "cleanup-recycle")
    assert len(boxes) == 1
    assert boxes[0].text == "Also recycle the video"
    assert not boxes[0].value


def test_recycle_checkbox_is_dense_with_no_left_padding_so_its_box_meets_the_content_edge():
    box = _by_marker(_session(_no_job("cleanup_plan")), "cleanup-recycle")[0]
    assert "dense" in box._props
    assert box._style.get("padding-left") == "0"


def test_plan_heading_has_8_px_space_below_it_before_the_first_fate_group():
    elements = _session(_no_job("cleanup_plan"))
    heading = next(e for e in elements if isinstance(e, ui.label) and e.text.startswith(plan_list.HEADING_PREFIX))
    assert heading._style.get("margin-bottom") == f"{tokens.SPACE_8}px"


def test_fate_groups_show_counts_and_sizes():
    items = fixtures.SCENARIOS["cleanup_plan"]["cleanup_plan"]["items"]
    groups = plan_list.groups(items)
    assert [(g["fate"], g["count"]) for g in groups] == [("remove", 2), ("keep", 1)]
    assert groups[0]["size_mb"] == pytest.approx(1602.5)
    labels = [e.text for e in _session(_no_job("cleanup_plan")) if isinstance(e, ui.label)]
    assert "2 files" in labels
    assert "1 file" in labels


def test_plan_items_paint_their_view_model_testids():
    _html, props, _labels, _buttons = _render(_no_job("cleanup_plan"))
    painted = {p for p in props if p.startswith(FATE_PREFIX)}
    plan = view_model.snapshot(FixtureSource("cleanup_plan"))["videos"]["cleanup_plan"]
    assert painted == {item["testid"] for item in plan["items"]}


def test_no_plan_section_without_a_cleanup_plan():
    elements = _session(_no_job("awaiting_live"))
    assert not [e for e in elements if e._props.get("data-testid", "").startswith(FATE_PREFIX)]
    assert APPLY_TEXT not in _button_texts(elements)


@pytest.mark.parametrize("mb, text", [
    (0, "0 KB"),
    (None, "0 KB"),
    (0.01, "10 KB"),
    (0.01171875, "12 KB"),
    (0.5, "512 KB"),
    (1.0, "1.0 MB"),
    (0.9999, "1.0 MB"),
    (812.4, "812.4 MB"),
    (1023.94, "1023.9 MB"),
    (1024, "1.0 GB"),
    (1602.5, "1.6 GB"),
])
def test_size_text_shows_kb_then_mb_then_gb_by_band(mb, text):
    assert plan_list.size_text(mb) == text


def test_size_text_never_shows_a_kilobyte_size_as_zero_point_zero_mb():
    for mb in (0.0001, 0.01, 0.5, 0.9):
        assert "MB" not in plan_list.size_text(mb)


def test_totals_text_names_the_count_and_the_size():
    assert plan_list.totals_text({"remove_count": 2, "remove_mb": 1602.5}) == APPLY_TEXT
    assert plan_list.totals_text({"remove_count": 1, "remove_mb": 3.0}) == "Remove 1 file, 3.0 MB"


# ---- Danger mode and Restore clips --------------------------------------------------------------

def test_restore_is_absent_with_danger_mode_off():
    elements = _session(_no_job("cleanup_plan"))
    assert RESTORE_LABEL not in _button_texts(elements)
    assert not _by_marker(elements, "restore-thor_vid1")


def test_danger_mode_is_a_switch_that_starts_off():
    switches = _by_marker(_session(_no_job("cleanup_plan")), "danger-mode")
    assert len(switches) == 1
    assert isinstance(switches[0], ui.switch)
    assert switches[0].value is False


def test_restore_shows_on_live_rows_in_danger_mode_and_starts_disabled():
    elements = _session(_no_job("cleanup_plan"), steps=_set("danger-mode", True))
    restore = _by_marker(elements, "restore-thor_vid1")[0]
    assert restore.text == RESTORE_LABEL
    assert restore._props.get("disable")
    assert not restore.enabled


def test_restore_stays_disabled_until_the_slug_is_typed_then_calls_restore():
    actions, calls = _recorder("restore")
    partial = _steps(_set("danger-mode", True), _set("restore-input-thor_vid1", "thor_vi"),
                     _press("restore-thor_vid1"))
    elements = _session(_no_job("cleanup_plan"), actions, steps=partial)
    assert not _by_marker(elements, "restore-thor_vid1")[0].enabled
    assert calls == []

    full = _steps(_set("danger-mode", True), _set("restore-input-thor_vid1", "thor_vid1"),
                  _press("restore-thor_vid1"))
    elements = _session(_no_job("cleanup_plan"), actions, steps=full)
    assert _by_marker(elements, "restore-thor_vid1")[0].enabled
    assert calls == [("restore", "thor_vid1")]


def test_restore_is_absent_from_rows_that_are_not_live_or_cleaned():
    source = _with_folders([fixtures.folder("thor_vid1", 1, clips=3, video_url="fixture.test/watch?v=u")])
    elements = _session(source, steps=_set("danger-mode", True))
    assert RESTORE_LABEL not in _button_texts(elements)


def test_restore_shows_on_cleaned_partly_rows_in_danger_mode():
    source = _with_folders([fixtures.folder("bee_vid1", 0, has_clips_dir=True, has_desc=True, clips=1)])
    elements = _session(source, steps=_set("danger-mode", True))
    assert _by_marker(elements, "restore-bee_vid1")


# ---- busy, empty and copy -------------------------------------------------------------------------

def test_busy_disables_every_action_button_and_fades_them():
    elements = _session(_Source("cleanup_plan", lambda d: None))
    buttons = [e for e in elements if isinstance(e, ui.button)]
    assert CLEAN_UP_LABEL in [b.text for b in buttons]
    assert APPLY_TEXT in [b.text for b in buttons]
    for button in buttons:
        assert button._props.get("disable"), f"{button.text} should be disabled while a job runs"
        assert "0.45" in str(button._style), f"{button.text} should be faded while a job runs"


def test_busy_names_the_running_job():
    _html, _props, labels, _buttons = _render(_Source("cleanup_plan", lambda d: None))
    assert 'Busy: "Clean up thor_vid1"' in labels


def test_idle_buttons_are_enabled_and_not_faded():
    buttons = [e for e in _session(_no_job("cleanup_plan")) if isinstance(e, ui.button)]
    assert buttons
    for button in buttons:
        assert not button._props.get("disable")
        assert "0.45" not in str(button._style)


def test_destructive_buttons_never_take_default_focus():
    apply = _by_marker(_session(_no_job("cleanup_plan")), "apply-cleanup")[0]
    assert "autofocus" not in apply._props


def test_empty_state_names_the_next_action():
    _html, _props, labels, _buttons = _render(_no_job("empty"))
    assert EMPTY_COPY in labels


def test_no_style_or_script_tag_in_any_ui_html_content():
    for name in SCENARIOS:
        html, _props, _labels, _buttons = _render(_no_job(name))
        assert "<style" not in html.lower(), name
        assert "<script" not in html.lower(), name


@pytest.mark.parametrize("scenario", SCENARIOS)
def test_no_dash_or_middle_dot_in_any_rendered_text(scenario):
    html, _props, labels, _buttons = _render(_no_job(scenario))
    text = html + "\n".join(labels)
    for ch in BAD_CHARS:
        assert ch not in text


@pytest.mark.parametrize("scenario", SCENARIOS)
def test_every_button_has_no_caps(scenario):
    _html, _props, _labels, buttons = _render(_no_job(scenario))
    for button in buttons:
        assert "no-caps" in button._props


def test_module_paints_rows_and_imports_neither_bridge_nor_jobs():
    assert videos_tab.PAINTS_ROWS is True
    for module in (videos_tab, plan_list):
        source = inspect.getsource(module)
        assert "import bridge" not in source and "from gui import bridge" not in source
        assert "import jobs" not in source and "from gui import jobs" not in source
