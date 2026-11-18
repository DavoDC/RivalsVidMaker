"""Clips tab (DESIGN.md sections 4, 5, 8, 9, 11): summary line, actions, character table, root list and the
needs-a-decision panel. Rows carry the view_model testids; Keep and Recycle call the injected actions.

Tab tests run the NiceGUI user simulator from sync tests with asyncio.run, as the archive and activity tests
do. Nothing here writes outside tmp_path and nothing imports bridge or jobs.
"""
import asyncio
import inspect
import re

import pytest
from nicegui import ui
from nicegui.element_filter import ElementFilter
from nicegui.testing.user_simulation import user_simulation

from gui import avatars, fixtures, tokens, view_model
from gui.sources import FixtureSource
from gui.tabs import clips

SCENARIOS = ("fresh_intake", "needs_decision", "scanning", "empty")
TESTID = re.compile(r'data-testid="([^"]+)"')
ROW_PREFIXES = ("clip-char-", "clip-root-", "lowvalue-")
BAD_CHARS = (chr(0x00B7), chr(0x2013), chr(0x2014))


class _Source(FixtureSource):
    """A fixture scenario with one change applied to its data (a fresh copy per read)."""

    def __init__(self, name, change):
        super().__init__(name)
        self._change = change

    def read(self):
        data = super().read()
        self._change(data)
        return data


def _render(builder, source, actions=None):
    """Run the tab inside a simulated page. Returns (html, testids, labels, buttons) for the page."""
    def root():
        builder(source, actions)

    async def run():
        async with user_simulation(root) as user:
            await user.open("/")
            with user.client:
                elements = list(ElementFilter(only_visible=False))
                html = "\n".join(e.content for e in elements if isinstance(e, ui.html))
                labels = [e.text for e in elements if isinstance(e, ui.label)]
                props = [e._props.get("data-testid") for e in elements]
                buttons = [e for e in elements if isinstance(e, ui.button)]
            return html, [p for p in props if p], labels, buttons

    return asyncio.run(run())


def _state_ids(source):
    snap = view_model.snapshot(source)["clips"]
    ids = set()
    for key in ("characters", "unsorted", "low_value"):
        ids |= {row["testid"] for row in snap[key]}
    return ids


def _click(marker, source, actions):
    """Click the button with marker inside a simulated page."""
    def root():
        clips.build(source, actions)

    async def run():
        async with user_simulation(root) as user:
            await user.open("/")
            user.find(marker=marker).click()

    asyncio.run(run())


def _with_job(title="Scan BLACK WIDOW clips", scenario="empty"):
    def change(data):
        data["job"] = fixtures.job("scan", title, "scanning", 3, 6, "clips")
    return _Source(scenario, change)


def _page_elements(builder, source, actions=None):
    """The live NiceGUI elements of the tab in a simulated page (the tree, for structure checks)."""
    def root():
        builder(source, actions)

    async def run():
        async with user_simulation(root) as user:
            await user.open("/")
            with user.client:
                return list(ElementFilter(only_visible=False))

    return asyncio.run(run())


# ---- painted rows match the view model ---------------------------------------------------------

@pytest.mark.parametrize("scenario", SCENARIOS)
def test_painted_clip_rows_equal_the_view_model_testids(scenario):
    html, props, _labels, _buttons = _render(clips.build, FixtureSource(scenario))
    painted = {t for t in props + TESTID.findall(html) if t.startswith(ROW_PREFIXES)}
    assert painted == _state_ids(FixtureSource(scenario))


@pytest.mark.parametrize("scenario", SCENARIOS)
def test_no_middle_dot_or_dash_in_any_rendered_text(scenario):
    html, _props, labels, _buttons = _render(clips.build, FixtureSource(scenario))
    text = html + "\n".join(labels)
    for ch in BAD_CHARS:
        assert ch not in text


@pytest.mark.parametrize("scenario", SCENARIOS)
def test_every_button_has_no_caps(scenario):
    _html, _props, _labels, buttons = _render(clips.build, FixtureSource(scenario))
    assert buttons, "the tab paints at least the two action buttons"
    for button in buttons:
        assert "no-caps" in button._props


# ---- summary line -----------------------------------------------------------------------------

def test_summary_names_new_protected_and_decision_counts_omitting_zeros():
    summary = {"new_clips": 2, "protected": 1, "low_value_pending": 0}
    assert clips.summary_text(summary) == "2 new in Highlights, 1 kept for the game's recent list."


def test_summary_singular_decision_and_all_zero_copy():
    assert clips.summary_text({"new_clips": 1, "protected": 0, "low_value_pending": 1}) == (
        "1 new in Highlights. 1 clip needs a decision.")
    assert clips.summary_text({"new_clips": 0, "protected": 0, "low_value_pending": 0}) == (
        "No new clips. Save highlights in game, then press Sort clips.")


def test_empty_scenario_shows_the_empty_copy():
    html, _props, labels, _buttons = _render(clips.build, FixtureSource("empty"))
    assert "No new clips. Save highlights in game, then press Sort clips." in labels


# ---- busy state -------------------------------------------------------------------------------

def test_busy_disables_both_buttons_and_names_the_job():
    _html, _props, labels, buttons = _render(clips.build, _with_job())
    assert buttons, "action buttons are painted"
    for button in buttons:
        assert button._props.get("disable"), f"{button._props} should be disabled while a job runs"
    assert 'Busy: "Scan BLACK WIDOW clips"' in labels


def test_busy_disables_all_four_buttons_and_fades_them():
    elements = _page_elements(clips.build, _with_job(scenario="needs_decision"))
    buttons = [e for e in elements if isinstance(e, ui.button)]
    assert {b.text for b in buttons} >= {"Sort clips", "Scan for KOs", "Keep", "Recycle"}
    for button in buttons:
        assert button._props.get("disable"), f"{button.text} should be disabled while a job runs"
        assert "0.45" in str(button._style), f"{button.text} should be faded while a job runs"


def test_idle_buttons_are_not_faded():
    def no_job(data):
        data["job"] = None
    elements = _page_elements(clips.build, _Source("needs_decision", no_job))
    buttons = [e for e in elements if isinstance(e, ui.button)]
    assert buttons
    for button in buttons:
        assert "0.45" not in str(button._style)


def test_decision_character_tier_and_buttons_share_one_row():
    row = view_model.snapshot(FixtureSource("needs_decision"))["clips"]["low_value"][0]
    elements = _page_elements(clips.build, FixtureSource("needs_decision"))
    keep = next(e for e in elements if isinstance(e, ui.button) and e.text == "Keep")
    line = keep.parent_slot.parent
    texts = {e.text for e in line.descendants() if isinstance(e, ui.label)}
    buttons = {e.text for e in line.descendants() if isinstance(e, ui.button)}
    assert buttons == {"Keep", "Recycle"}
    assert row["character"] in texts
    assert (row.get("tier_or_none") or "No kill") in texts
    assert f'"{row["name"]}"' not in texts


def test_summary_and_buttons_share_one_space_between_row():
    elements = _page_elements(clips.build, FixtureSource("needs_decision"))
    sort = next(e for e in elements if isinstance(e, ui.button) and e.text == "Sort clips")
    bar = sort.parent_slot.parent.parent_slot.parent
    assert "space-between" in str(bar._style)
    texts = {e.text for e in bar.descendants() if isinstance(e, ui.label)}
    assert summary_text_for("needs_decision") in texts


def summary_text_for(scenario):
    return clips.summary_text(view_model.snapshot(FixtureSource(scenario))["summary"])


def test_idle_leaves_the_buttons_enabled_and_shows_no_busy_label():
    _html, _props, labels, buttons = _render(clips.build, FixtureSource("fresh_intake"))
    assert buttons
    for button in buttons:
        assert not button._props.get("disable")
    assert not any(text.startswith("Busy:") for text in labels)


# ---- character table --------------------------------------------------------------------------

def test_table_rows_carry_testids_and_the_five_columns():
    rows = view_model.snapshot(FixtureSource("needs_decision"))["clips"]["characters"]
    html = clips.table_html(rows)
    assert {t for t in TESTID.findall(html) if t.startswith("clip-char-")} == {r["testid"] for r in rows}
    for heading in ("Character", "Clips", "Length", "Scanned", "Best"):
        assert f">{heading}</th>" in html


def test_table_header_says_length_not_minutes():
    html = clips.table_html([])
    assert ">Length</th>" in html
    assert ">Minutes<" not in html


def test_table_minutes_scanned_and_best_cells():
    row = {"testid": "clip-char-thor-000001", "name": "THOR", "clips": 31, "minutes": 18.6667,
           "scanned": 31, "unscanned": 0, "tiers": {"KO": 20, "QUAD": 3, "PENTA": 1, "HEXA": 0}}
    html = clips.table_html([row])
    assert ">18:40</td>" in html
    assert ">31 of 31</td>" in html
    assert 'data-tier="PENTA"' in html
    assert 'data-tier="QUAD"' not in html  # the highest kept tier is the one shown
    assert ">None</span>" not in html


def test_minutes_cell_uses_exact_seconds_when_the_row_has_them():
    row = {"testid": "clip-char-thor-000006", "name": "THOR", "clips": 2, "minutes": 1.3,
           "seconds": 80, "scanned": 2, "unscanned": 0, "tiers": {}}
    html = clips.table_html([row])
    assert ">1:20</td>" in html          # 80 s, not the 1:18 that 1.3 minutes would give


def test_minutes_cell_falls_back_to_minutes_without_seconds():
    row = {"testid": "clip-char-thor-000007", "name": "THOR", "clips": 2, "minutes": 1.5,
           "scanned": 2, "unscanned": 0, "tiers": {}}
    html = clips.table_html([row])
    assert ">1:30</td>" in html


def test_minutes_past_an_hour_read_as_hours_minutes_seconds():
    row = {"testid": "clip-char-thor-000005", "name": "THOR", "clips": 90, "minutes": 150,
           "scanned": 90, "unscanned": 0, "tiers": {}}
    html = clips.table_html([row])
    assert ">2:30:00</td>" in html
    assert ">150:00</td>" not in html


def test_table_and_root_list_fill_their_column():
    table = [e for e in _page_elements(clips.build, FixtureSource("needs_decision"))
             if isinstance(e, ui.html) and "<table" in e.content]
    roots = [e for e in _page_elements(clips.build, FixtureSource("fresh_intake"))
             if isinstance(e, ui.html) and "clip-root-" in e.content]
    assert table and roots
    assert "width:100%" in table[0].content
    for element in table + roots:
        assert element._style.get("width") == "100%"
    assert "width:100%" in clips._root_html(view_model.snapshot(FixtureSource("fresh_intake"))["clips"]["unsorted"])


def test_table_best_is_a_dim_dash_when_no_quad_or_better():
    row = {"testid": "clip-char-x-000002", "name": "SQUIRREL GIRL", "clips": 12, "minutes": 7.0833,
           "scanned": 10, "unscanned": 2, "tiers": {"KO": 9, "DOUBLE": 2}}
    html = clips.table_html([row])
    assert ">7:05</td>" in html
    assert ">10 of 12</td>" in html
    assert "None" not in html and "data-tier" not in html
    assert f'color:{tokens.TEXT_DIM};">-</span>' in html


def test_table_shows_display_names_not_folder_names(monkeypatch, tmp_path):
    monkeypatch.setattr(avatars, "ASSET_DIR", tmp_path)  # no local portraits: the initials badge shows
    row = {"testid": "clip-char-x-000010", "name": "DOCTOR_STRANGE", "clips": 3, "minutes": 1.0,
           "scanned": 3, "unscanned": 0, "tiers": {}}
    html = clips.table_html([row])
    assert "Doctor Strange" in html
    assert "DOCTOR_STRANGE" not in html
    assert ">DS</span>" in html  # no portrait file in the repo, so the initials badge
    assert 'display:flex;align-items:center;gap:8px;' in html


def test_table_name_cell_is_the_shared_avatars_name_cell(monkeypatch, tmp_path):
    monkeypatch.setattr(avatars, "ASSET_DIR", tmp_path)
    row = {"testid": "clip-char-x-000011", "name": "SQUIRREL_GIRL", "clips": 1, "minutes": 0.5,
           "scanned": 1, "unscanned": 0, "tiers": {}}
    assert avatars.name_cell_html("SQUIRREL_GIRL") in clips.table_html([row])


def test_table_numeric_cells_are_right_aligned_with_12px_padding_and_regular_weight():
    row = {"testid": "clip-char-x-000003", "name": "IRON MAN", "clips": 8, "minutes": 1.0,
           "scanned": 8, "unscanned": 0, "tiers": {}}
    html = clips.table_html([row])
    assert "text-align:right" in html
    assert "padding:8px 12px;" in html
    assert "font-weight:700" not in html and "font-weight:bold" not in html


def test_table_names_from_data_are_escaped():
    row = {"testid": "clip-char-x-000004", "name": "<i>x</i>", "clips": 1, "minutes": 0,
           "scanned": 1, "unscanned": 0, "tiers": {}}
    html = clips.table_html([row])
    assert "&lt;i&gt;x&lt;/i&gt;" in html
    assert "<i>x</i>" not in html


# ---- root list and decision panel ------------------------------------------------------------

def test_root_list_marks_protected_rows_with_one_kept_line_above_the_rows():
    html, _props, _labels, _buttons = _render(clips.build, FixtureSource("fresh_intake"))
    assert "Kept in place: the game lists these as recent clips." in html
    assert html.count(clips.ROOT_NOTE) == 1
    assert "kept: in the game's recent list" not in html


def test_root_list_kept_line_appears_once_for_two_protected_rows():
    rows = [
        {"testid": "clip-root-a", "name": "THOR_2026-11-18_00-42-48.mp4", "protected": True, "recognised": True,
         "character": "THOR", "date": "18/11/2026", "time": "12:42am"},
        {"testid": "clip-root-b", "name": "THOR_2026-11-18_00-50-01.mp4", "protected": True, "recognised": True,
         "character": "THOR", "date": "18/11/2026", "time": "12:50am"},
    ]
    html = clips._root_html(rows)
    assert html.count(clips.ROOT_NOTE) == 1
    assert html.index(clips.ROOT_NOTE) < html.index('data-testid="clip-root-a"')


def test_root_list_names_have_no_quotes_around_them():
    rows = [{"testid": "clip-root-a", "name": "THOR_2026-11-18_00-42-48.mp4", "protected": False, "recognised": True,
             "character": "THOR", "date": "18/11/2026", "time": "12:42am"}]
    html = clips._root_html(rows)
    assert "&quot;" not in html and ">&quot;" not in html and '>"' not in html
    assert 'title="THOR_2026-11-18_00-42-48.mp4"' in html


def test_decision_panel_is_absent_when_low_value_is_empty():
    html, props, labels, _buttons = _render(clips.build, FixtureSource("fresh_intake"))
    assert "Needs a decision" not in labels
    assert not any(t.startswith("lowvalue-") for t in props + TESTID.findall(html))


def test_decision_panel_rows_show_name_character_and_tier_or_none():
    html, _props, labels, _buttons = _render(clips.build, FixtureSource("needs_decision"))
    assert "Needs a decision" in labels
    assert "No kill" in html or "No kill" in labels
    assert "KO" in html or "KO" in labels


def test_keep_calls_the_injected_action_with_the_clip_name():
    source = FixtureSource("needs_decision")
    row = view_model.snapshot(source)["clips"]["low_value"][0]
    calls = []
    _click(f"keep-{row['testid']}", FixtureSource("needs_decision"),
           {"keep": lambda name: calls.append(("keep", name))})
    assert calls == [("keep", row["name"])]


def test_recycle_calls_the_injected_action_with_the_clip_name():
    source = FixtureSource("needs_decision")
    row = view_model.snapshot(source)["clips"]["low_value"][1]
    calls = []
    _click(f"recycle-{row['testid']}", FixtureSource("needs_decision"),
           {"recycle": lambda name: calls.append(("recycle", name))})
    assert calls == [("recycle", row["name"])]


def test_decision_buttons_do_nothing_without_actions():
    source = FixtureSource("needs_decision")
    row = view_model.snapshot(source)["clips"]["low_value"][0]
    _click(f"keep-{row['testid']}", FixtureSource("needs_decision"), None)


def test_sort_and_scan_call_their_actions_when_given():
    calls = []
    actions = {"sort": lambda: calls.append("sort"), "scan": lambda: calls.append("scan")}
    _click("sort-clips", FixtureSource("fresh_intake"), actions)
    _click("scan-kos", FixtureSource("fresh_intake"), actions)
    assert calls == ["sort", "scan"]


def test_action_buttons_without_actions_are_no_ops():
    _click("sort-clips", FixtureSource("fresh_intake"), None)
    _click("scan-kos", FixtureSource("fresh_intake"), None)


# ---- layout: side by side at 1440 and up, stacked below (flex wrap, no JS) ---------------------

def _styles_by_class(source):
    """Inline style dict of every element carrying an rvm-clips* class, keyed by that class."""
    def root():
        clips.build(source, None)

    async def run():
        async with user_simulation(root) as user:
            await user.open("/")
            with user.client:
                found = {}
                for e in ElementFilter(only_visible=False):
                    for cls in e._classes:
                        if cls.startswith("rvm-clips"):
                            found[cls] = dict(e._style)
                return found

    return asyncio.run(run())


def test_panel_sits_beside_the_table_at_1440_and_stacks_at_1024():
    # Inline styles, not a <style> tag in ui.html: NiceGUI never applied that tag, so the panel stacked.
    styles = _styles_by_class(FixtureSource("needs_decision"))
    assert styles["rvm-clips"].get("display") == "flex"
    assert styles["rvm-clips"].get("flex-wrap") == "wrap"
    assert styles["rvm-clips-main"].get("flex") == "2 1 640px"
    assert styles["rvm-clips-panel"].get("flex") == "1 1 320px"
    html, _props, _labels, _buttons = _render(clips.build, FixtureSource("needs_decision"))
    assert "<style" not in html.lower() and "<script" not in html.lower()


def test_no_max_width_1439_media_query_remains():
    source = inspect.getsource(clips)
    assert "max-width:1439px" not in source
    assert "1439" not in source


# ---- loose clips Sort cannot read -----------------------------------------------------------

def test_summary_names_unrecognised_clips_singular_and_plural():
    one = {"new_clips": 1, "protected": 0, "low_value_pending": 0, "unrecognised": 1}
    two = {"new_clips": 1, "protected": 0, "low_value_pending": 0, "unrecognised": 2}
    assert clips.summary_text(one) == "1 new in Highlights. 1 has a name Sort cannot read."
    assert clips.summary_text(two) == "1 new in Highlights. 2 have a name Sort cannot read."


def test_summary_with_only_unrecognised_clips_is_just_that_sentence():
    only = {"new_clips": 0, "protected": 0, "low_value_pending": 0, "unrecognised": 2}
    assert clips.summary_text(only) == "2 have a name Sort cannot read."


def test_root_list_marks_unrecognised_rows_with_the_unreadable_note():
    rows = [
        {"testid": "clip-root-x", "name": "random.mp4", "protected": False, "recognised": False,
         "character": None, "date": None, "time": None},
        {"testid": "clip-root-y", "name": "junk.mp4", "protected": True, "recognised": False,
         "character": None, "date": None, "time": None},
        {"testid": "clip-root-z", "name": "THOR_2026-11-18_00-42-48.mp4", "protected": False, "recognised": True,
         "character": "THOR", "date": "18/11/2026", "time": "12:42am"},
    ]
    html = clips._root_html(rows)
    assert html.count(clips.UNREADABLE_NOTE) == 2
    assert "Sort cannot read this name." in html
    assert html.count(clips.ROOT_NOTE) == 1
    assert html.index(clips.ROOT_NOTE) < html.index('data-testid="clip-root-x"')  # the kept line leads the list
    junk = html.split('data-testid="clip-root-y"')[1].split('data-testid="clip-root-z"')[0]
    assert clips.UNREADABLE_NOTE in junk
    recognised = html.split('data-testid="clip-root-z"')[1]
    assert clips.UNREADABLE_NOTE not in recognised


def _root_row(testid, name, **over):
    row = {"testid": testid, "name": name, "protected": False, "recognised": True,
           "character": "THOR", "date": "18/11/2026", "time": "12:42am"}
    row.update(over)
    return row


def test_root_list_is_a_table_with_character_date_and_time_headers():
    html = clips._root_html([_root_row("clip-root-a", "THOR_2026-11-18_00-42-48.mp4")])
    assert "<table" in html
    for head in ("Character", "Date", "Time"):
        assert f">{head}</th>" in html


def test_root_row_shows_avatar_name_capture_date_and_time_with_the_file_name_on_hover(monkeypatch, tmp_path):
    monkeypatch.setattr(avatars, "ASSET_DIR", tmp_path)  # no local portraits: the initials badge shows
    name = "THOR_2026-11-18_00-42-48.mp4"
    html = clips._root_html([_root_row("clip-root-a", name)])
    row = html.split('data-testid="clip-root-a"')[1].split("</tr>")[0]
    assert avatars.name_cell_html("THOR") in row
    assert ">18/11/2026</td>" in row
    assert ">12:42am</td>" in row
    assert f'title="{name}"' in row
    assert html.count(name) == 1  # the raw file name is hover text only


def test_root_row_without_a_character_shows_the_name_and_note_and_empty_date_and_time(monkeypatch, tmp_path):
    monkeypatch.setattr(avatars, "ASSET_DIR", tmp_path)
    html = clips._root_html([_root_row("clip-root-x", "random.mp4", recognised=False,
                                       character=None, date=None, time=None)])
    row = html.split('data-testid="clip-root-x"')[1].split("</tr>")[0]
    cells = row.split("<td")[1:]
    assert len(cells) == 3
    assert ">random.mp4<" in cells[0] and clips.UNREADABLE_NOTE in cells[0]
    for cell in cells[1:]:
        assert cell.split(">", 1)[1].split("</td>")[0] == ""
    assert 'title="random.mp4"' in row


def test_root_list_escapes_the_file_name_in_the_cell_and_the_title():
    name = '<b>x".mp4'
    html = clips._root_html([_root_row("clip-root-q", name, recognised=False, character=None, date=None, time=None)])
    assert "<b>x" not in html
    assert 'title="&lt;b&gt;x&quot;.mp4"' in html


def test_root_list_kept_line_sits_above_the_table_only_when_a_row_is_protected():
    html = clips._root_html([_root_row("clip-root-a", "THOR_2026-11-18_00-42-48.mp4", protected=True)])
    assert html.find(clips.ROOT_NOTE) != -1 and html.find(clips.ROOT_NOTE) < html.find("<table")
    plain = clips._root_html([_root_row("clip-root-a", "THOR_2026-11-18_00-42-48.mp4")])
    assert clips.ROOT_NOTE not in plain
