"""Compile tab (DESIGN.md sections 7, 8, 9, 10, 11): the pickers, the reel strip, the plan rows and the duplicates.

Tab tests run the NiceGUI user simulator from sync tests with asyncio.run, as the clips tests do. Every row
carries a view_model testid; the reel segments carry their clip's testid too. Nothing here imports bridge or jobs.
"""
import asyncio
import inspect
import re

import pytest
from nicegui import ui
from nicegui.element_filter import ElementFilter
from nicegui.testing.user_simulation import user_simulation

from gui import timefmt, tokens, view_model
from gui.components import reel
from gui.sources import FixtureSource
from gui.tabs import compile as compile_tab

SCENARIOS = ("ready", "plan", "encoding", "empty", "fresh_intake")
PLAN_SCENARIOS = ("plan", "encoding")
TESTID = re.compile(r'data-testid="([^"]+)"')
ROW_PREFIXES = ("plan-clip-", "plan-dup-")
BAD_CHARS = (chr(0x00B7), chr(0x2013), chr(0x2014))
LIT = ("QUAD", "PENTA", "HEXA")
NOTHING_TO_CHOOSE = "Pick a character, then press Plan video."
NO_CHARACTER_COPY = "Compile needs 10 minutes of clips for one character. Scan for KOs on the Clips tab to count them."


class _Source(FixtureSource):
    """A fixture scenario with one change applied to its data (a fresh copy per read)."""

    def __init__(self, name, change):
        super().__init__(name)
        self._change = change

    def read(self):
        data = super().read()
        self._change(data)
        return data


def _no_job_source(name):
    def change(data):
        data["job"] = None
    return _Source(name, change)


def _plan(name):
    return view_model.snapshot(FixtureSource(name))["compile"]["plan"]


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


def _click(marker, source, actions):
    """Click the element with marker inside a simulated page."""
    def root():
        compile_tab.build(source, actions)

    async def run():
        async with user_simulation(root) as user:
            await user.open("/")
            user.find(marker=marker).click()

    asyncio.run(run())


def _segments(html):
    return re.findall(r'<div class="rvm-reel-seg[^"]*"[^>]*>', html)


def _attr(tag, name):
    m = re.search(r'\b%s="([^"]*)"' % re.escape(name), tag)
    return m.group(1) if m else None


def _style_value(tag, prop):
    m = re.search(r"(?:^|;|\")\s*%s:\s*([^;\"]+)" % re.escape(prop), tag)
    return m.group(1).strip() if m else None


# ---- reel: pure percentages ----------------------------------------------------------------------

def test_match_text_shows_a_similarity_of_one_as_100_percent():
    assert compile_tab._match_text(1.0) == "Match 100%"


def test_segment_percentages_are_proportional_and_sum_to_100():
    durations = [300, 312, 300]
    pcts = reel.segment_percentages(durations)
    total = sum(durations)
    assert len(pcts) == 3
    for pct, d in zip(pcts, durations):
        assert abs(pct - d * 100 / total) <= 0.1
    assert abs(sum(pcts) - 100) <= 0.1


def test_segment_percentages_single_segment_fills_the_bar():
    assert reel.segment_percentages([600]) == pytest.approx([100.0])


def test_segment_percentages_with_no_length_are_all_zero():
    assert reel.segment_percentages([]) == []
    assert reel.segment_percentages([0, 0]) == [0.0, 0.0]


# ---- reel: markup --------------------------------------------------------------------------------

def test_bar_segment_widths_follow_the_clip_durations_in_the_plan():
    batch = _plan("plan")["batches"][0]
    segs = _segments(reel.bar_html(batch))
    assert len(segs) == len(batch["clips"])
    widths = [float(_style_value(tag, "width").rstrip("%")) for tag in segs]
    total = sum(c["duration_s"] for c in batch["clips"])
    for width, clip in zip(widths, batch["clips"]):
        assert abs(width - clip["duration_s"] * 100 / total) <= 0.1
    assert abs(sum(widths) - 100) <= 0.1


def test_only_quad_penta_hexa_segments_use_tier_tokens():
    token_for = {"QUAD": tokens.TIER_QUAD, "PENTA": tokens.TIER_PENTA, "HEXA": tokens.TIER_HEXA}
    tier_hexes = {tokens.TIER_QUAD, tokens.TIER_PENTA, tokens.TIER_HEXA,
                  tokens.TIER_LOW_1, tokens.TIER_LOW_2, tokens.TIER_LOW_3}
    seen_lit = 0
    for name in PLAN_SCENARIOS:
        for batch in _plan(name)["batches"]:
            for tag in _segments(reel.bar_html(batch)):
                tier = _attr(tag, "data-tier")
                background = _style_value(tag, "background")
                if tier in LIT:
                    seen_lit += 1
                    assert background == token_for[tier]
                    assert "rvm-reel-lit" in tag
                else:
                    assert background == tokens.LINE, f"{tier} should be quiet slate"
                    assert not any(hexa in tag for hexa in tier_hexes)
                    assert "rvm-reel-lit" not in tag
    assert seen_lit >= 3


def test_kept_low_tiers_are_slate_not_their_tier_colour():
    batch = _plan("plan")["batches"][0]
    tags = {_attr(t, "data-tier"): t for t in _segments(reel.bar_html(batch))}
    assert _style_value(tags["KO"], "background") == tokens.LINE
    assert tokens.TIER_LOW_1 not in tags["KO"]


def test_lit_segments_carry_the_description_timestamp_under_them():
    batch = _plan("plan")["batches"][0]
    html = reel.bar_html(batch)
    for clip in batch["clips"]:
        stamp = timefmt.duration(clip["start_s"])
        if clip["tier"] in LIT:
            assert f">{stamp}</span>" in html
        else:
            assert f">{stamp}</span>" not in html


def test_reel_bar_with_no_lit_segment_has_no_timestamps():
    batch = _plan("plan")["batches"][1]
    html = reel.bar_html(batch)
    assert "rvm-reel-lit" not in html
    assert "rvm-reel-stamp" not in html


# ---- reel: motion --------------------------------------------------------------------------------

def test_reveal_css_is_added_once_per_build_with_a_reduced_motion_block(monkeypatch):
    added = []
    monkeypatch.setattr(ui, "add_css", lambda content, *a, **k: added.append(content))
    _render(compile_tab.build, FixtureSource("plan"))
    assert len(added) == 1
    css = added[0]
    assert "@keyframes" in css
    assert "@media (prefers-reduced-motion: reduce)" in css
    block = css.split("@media (prefers-reduced-motion: reduce)", 1)[1]
    assert re.search(r"animation:\s*none\s*!important", block)


def test_lit_segments_light_left_to_right_once_within_600ms():
    batch = _plan("plan")["batches"][0]
    lit = [t for t in _segments(reel.bar_html(batch)) if "rvm-reel-lit" in t]
    assert len(lit) == 2  # QUAD and PENTA in batch 1; the KO between them stays quiet
    starts = [float(_attr(t, "data-start")) for t in lit]
    delays = [int(re.search(r"animation-delay:(\d+)ms", t).group(1)) for t in lit]
    assert starts == sorted(starts)
    assert delays == sorted(delays)
    assert max(delays) + reel.LIGHT_MS <= 600
    assert reel.LIGHT_MS + reel.SWEEP_MS == 600


def test_no_style_or_script_tag_in_any_ui_html_content():
    for name in SCENARIOS:
        html, _props, _labels, _buttons = _render(compile_tab.build, FixtureSource(name))
        assert "<style" not in html.lower(), name
        assert "<script" not in html.lower(), name


# ---- painted rows match the view model -----------------------------------------------------------

@pytest.mark.parametrize("scenario", PLAN_SCENARIOS)
def test_painted_plan_rows_equal_the_view_model_testids(scenario):
    html, props, _labels, _buttons = _render(compile_tab.build, FixtureSource(scenario))
    painted = {t for t in props + TESTID.findall(html) if t.startswith(ROW_PREFIXES)}
    plan = _plan(scenario)
    expected = {view_model.testid("plan-clip", c["name"]) for b in plan["batches"] for c in b["clips"]}
    expected |= {view_model.testid("plan-dup", f"{d['a']}|{d['b']}") for d in plan["duplicates"]}
    assert painted == expected


@pytest.mark.parametrize("scenario", SCENARIOS)
def test_no_dash_or_middle_dot_in_any_rendered_text(scenario):
    html, _props, labels, _buttons = _render(compile_tab.build, FixtureSource(scenario))
    text = html + "\n".join(labels)
    for ch in BAD_CHARS:
        assert ch not in text


@pytest.mark.parametrize("scenario", SCENARIOS)
def test_every_button_has_no_caps(scenario):
    _html, _props, _labels, buttons = _render(compile_tab.build, FixtureSource(scenario))
    for button in buttons:
        assert "no-caps" in button._props


def test_module_paints_rows_and_imports_neither_bridge_nor_jobs():
    assert compile_tab.PAINTS_ROWS is True
    for module in (compile_tab, reel):
        source = inspect.getsource(module)
        assert "import bridge" not in source and "from gui import bridge" not in source
        assert "import jobs" not in source and "from gui import jobs" not in source


# ---- pickers -------------------------------------------------------------------------------------

def _marked(elements, marker):
    return [e for e in elements if marker in (getattr(e, "_markers", None) or [])]


def test_character_picker_lists_only_ready_characters():
    elements = _page_elements(compile_tab.build, FixtureSource("ready"))
    pickers = [e for e in _marked(elements, "compile-character") if isinstance(e, ui.select)]
    assert len(pickers) == 1
    ready = [c["name"] for c in view_model.snapshot(FixtureSource("ready"))["clips"]["characters"] if c["ready"]]
    assert list(pickers[0].options) == ready
    assert "SQUIRREL GIRL" not in pickers[0].options


def test_pickers_use_the_dark_field_style_so_their_labels_read_on_the_ground():
    elements = _page_elements(compile_tab.build, FixtureSource("ready"))
    for marker in ("compile-character", "compile-length"):
        picker = next(e for e in _marked(elements, marker) if isinstance(e, ui.select))
        assert "dark" in picker._props, f"{marker} needs the dark prop to read on the dark ground"


def test_plan_video_calls_plan_with_character_length_and_reencode_flag():
    calls = []
    _click("plan-video", _no_job_source("ready"),
           {"plan": lambda *args: calls.append(("plan",) + args)})
    assert calls == [("plan", "THOR", 900, False)]


def test_plan_video_with_reencode_checked_passes_true():
    calls = []

    def root():
        compile_tab.build(_no_job_source("ready"), {"plan": lambda *a: calls.append(a)})

    async def run():
        async with user_simulation(root) as user:
            await user.open("/")
            box = next(iter(user.find(marker="compile-reencode").elements))
            box.set_value(True)
            user.find(marker="plan-video").click()

    asyncio.run(run())
    assert calls == [("THOR", 900, True)]


# ---- empty states --------------------------------------------------------------------------------

def test_no_plan_names_the_next_action():
    _html, _props, labels, _buttons = _render(compile_tab.build, _no_job_source("ready"))
    assert NOTHING_TO_CHOOSE in labels


def test_no_ready_character_says_how_many_minutes_and_points_to_clips():
    html, _props, labels, buttons = _render(compile_tab.build, FixtureSource("empty"))
    assert NO_CHARACTER_COPY in labels
    assert not any(b.text == "Plan video" for b in buttons)


def _clip_row(name, seconds, ready=False):
    return {"name": name, "clips": 1, "minutes": round(seconds / 60, 1), "seconds": seconds,
            "scanned": 1, "unscanned": 0, "tiers": {}, "ready": ready}


def _with_characters(rows):
    def change(data):
        data["characters"] = rows
    return _Source("empty", change)


def test_closest_returns_top_three_by_seconds_and_skips_ready_characters():
    state = {"clips": {"characters": [
        _clip_row("A", 100), _clip_row("B", 900, ready=True), _clip_row("C", 400),
        _clip_row("D", 700), _clip_row("E", 300), _clip_row("F", 500),
    ]}}
    assert compile_tab.closest(state) == [("D", 700), ("F", 500), ("C", 400)]


def test_closest_with_no_clips_is_empty():
    assert compile_tab.closest({"clips": {"characters": []}}) == []


def test_closest_on_the_ready_fixture_carries_seconds():
    rows = compile_tab.closest(view_model.snapshot(FixtureSource("ready")))
    assert rows and all(seconds > 0 for _name, seconds in rows)


def test_ready_fraction_is_the_share_of_the_ready_length_capped_at_one():
    assert compile_tab.ready_fraction(300) == 0.5
    assert compile_tab.ready_fraction(1350) == 1.0
    assert compile_tab.ready_fraction(0) == 0.0


def test_progress_bar_fill_is_the_share_and_the_value_is_capped_at_the_ready_length():
    bar = compile_tab.progress_bar_html(540)
    assert "width:90.0%" in bar
    assert 'aria-valuenow="540"' in bar
    assert 'aria-valuemax="600"' in bar
    full = compile_tab.progress_bar_html(1350)
    assert "width:100.0%" in full
    assert 'aria-valuenow="600"' in full


def test_progress_track_keeps_a_fixed_width_so_flex_rows_cannot_collapse_it():
    track = compile_tab.progress_bar_html(540).split('style="', 1)[1].split('"', 1)[0]
    assert "width:240px" in track
    assert "max-width:100%" in track
    assert "flex:none" in track


def test_character_options_map_folders_to_display_names_in_order():
    assert compile_tab.character_options(["HELA", "SQUIRREL_GIRL"]) == {"HELA": "Hela", "SQUIRREL_GIRL": "Squirrel Girl"}
    assert list(compile_tab.character_options(["SQUIRREL_GIRL", "HELA"])) == ["SQUIRREL_GIRL", "HELA"]


def test_empty_state_lists_closest_characters_as_progress():
    source = _with_characters([_clip_row("SQUIRREL GIRL", 1350), _clip_row("BLACK WIDOW", 400),
                               _clip_row("IRON MAN", 540), _clip_row("HULK", 60)])
    html, props, labels, _buttons = _render(compile_tab.build, source)
    assert NO_CHARACTER_COPY in labels
    ready_text = f"of {compile_tab.READY_MINUTES}:00"
    progress = [text for text in labels if text.endswith(ready_text)]
    assert progress == ["22:30 of 10:00", "9:00 of 10:00", "6:40 of 10:00"]
    assert "Squirrel Girl" in html and "Black Widow" in html and "Iron Man" in html
    assert "Hulk" not in html
    assert html.count('role="progressbar"') == 3
    assert view_model.testid("compile-closest", "SQUIRREL GIRL") in props


def test_closest_name_cells_sit_in_a_fixed_width_box():
    source = _with_characters([_clip_row("SQUIRREL GIRL", 1350), _clip_row("BLACK WIDOW", 400),
                               _clip_row("IRON MAN", 540), _clip_row("HULK", 60)])
    html, _props, _labels, _buttons = _render(compile_tab.build, source)
    assert html.count("width:220px;flex:none;") == 3


def test_no_closest_list_when_there_are_no_clips():
    _html, props, labels, _buttons = _render(compile_tab.build, FixtureSource("empty"))
    assert not any(text.endswith(f"of {compile_tab.READY_MINUTES}:00") for text in labels)
    assert not any(p.startswith("compile-closest-") for p in props)


# ---- plan rows and actions -----------------------------------------------------------------------

def test_compile_video_calls_compile_with_nonce_and_decisions():
    plan = _plan("plan")
    decisions = {c["name"]: c["decision"] for b in plan["batches"] for c in b["clips"]}
    calls = []
    _click("compile-video", FixtureSource("plan"),
           {"compile": lambda nonce, decided, upload: calls.append((nonce, decided, upload))})
    assert calls == [("fixture-plan-nonce", decisions, True)]


def test_upload_checkbox_is_labelled_and_ticked_by_default():
    elements = _page_elements(compile_tab.build, FixtureSource("plan"))
    boxes = [e for e in _marked(elements, "compile-upload") if isinstance(e, ui.checkbox)]
    assert len(boxes) == 1
    assert boxes[0].text == compile_tab.UPLOAD_LABEL == "Upload after compiling"
    assert boxes[0].value is True


def test_unticking_upload_then_compiling_calls_compile_with_false():
    calls = []

    def root():
        compile_tab.build(FixtureSource("plan"), {"compile": lambda *a: calls.append(a)})

    async def run():
        async with user_simulation(root) as user:
            await user.open("/")
            box = next(iter(user.find(marker="compile-upload").elements))
            box.set_value(False)
            user.find(marker="compile-video").click()

    asyncio.run(run())
    assert [args[2] for args in calls] == [False]


def test_upload_checkbox_is_disabled_and_faded_while_busy():
    elements = _page_elements(compile_tab.build, FixtureSource("encoding"))
    box = next(e for e in _marked(elements, "compile-upload") if isinstance(e, ui.checkbox))
    assert box._props.get("disable")
    assert "0.45" in str(box._style)


def test_keep_and_recycle_appear_only_on_low_value_clips():
    plan = _plan("plan")
    elements = _page_elements(compile_tab.build, FixtureSource("plan"))
    marks = {m for e in elements if isinstance(e, ui.button) for m in (getattr(e, "_markers", None) or [])}
    for batch in plan["batches"]:
        for clip in batch["clips"]:
            tid = view_model.testid("plan-clip", clip["name"])
            if clip["tier"] in LIT:
                assert f"keep-{tid}" not in marks and f"recycle-{tid}" not in marks
            else:
                assert f"keep-{tid}" in marks and f"recycle-{tid}" in marks


def test_keep_and_recycle_call_actions_with_the_clip_name():
    plan = _plan("plan")
    low = next(c for b in plan["batches"] for c in b["clips"] if c["tier"] not in LIT)
    tid = view_model.testid("plan-clip", low["name"])
    calls = []
    actions = {"keep": lambda n: calls.append(("keep", n)), "recycle": lambda n: calls.append(("recycle", n))}
    _click(f"keep-{tid}", FixtureSource("plan"), actions)
    _click(f"recycle-{tid}", FixtureSource("plan"), actions)
    assert calls == [("keep", low["name"]), ("recycle", low["name"])]


def test_duplicate_pair_offers_keep_both_and_drop_one():
    dup = _plan("plan")["duplicates"][0]
    tid = view_model.testid("plan-dup", f"{dup['a']}|{dup['b']}")
    calls = []
    actions = {"keep_both": lambda a, b: calls.append(("keep_both", a, b)),
               "drop_one": lambda a, b: calls.append(("drop_one", a, b))}
    _click(f"keep-both-{tid}", FixtureSource("plan"), actions)
    _click(f"drop-one-{tid}", FixtureSource("plan"), actions)
    assert calls == [("keep_both", dup["a"], dup["b"]), ("drop_one", dup["a"], dup["b"])]


def test_plan_actions_do_nothing_without_handlers():
    plan = _plan("plan")
    low = next(c for b in plan["batches"] for c in b["clips"] if c["tier"] not in LIT)
    tid = view_model.testid("plan-clip", low["name"])
    _click("compile-video", FixtureSource("plan"), None)
    _click("plan-video", FixtureSource("ready"), None)
    _click(f"keep-{tid}", FixtureSource("plan"), None)


# ---- busy state ----------------------------------------------------------------------------------

def test_busy_disables_every_button_and_fades_them():
    elements = _page_elements(compile_tab.build, FixtureSource("encoding"))
    buttons = [e for e in elements if isinstance(e, ui.button)]
    assert buttons
    assert {"Compile video"} <= {b.text for b in buttons}
    for button in buttons:
        assert button._props.get("disable"), f"{button.text} should be disabled while a job runs"
        assert "0.45" in str(button._style), f"{button.text} should be faded while a job runs"


def test_busy_names_the_running_job():
    _html, _props, labels, _buttons = _render(compile_tab.build, FixtureSource("encoding"))
    assert 'Busy: "Encode THOR batch 1"' in labels


def test_idle_buttons_are_enabled_and_not_faded():
    elements = _page_elements(compile_tab.build, _no_job_source("plan"))
    buttons = [e for e in elements if isinstance(e, ui.button)]
    assert buttons
    for button in buttons:
        assert not button._props.get("disable")
        assert "0.45" not in str(button._style)


# ---- layout inputs -------------------------------------------------------------------------------

def test_reel_strip_fills_its_column():
    html, _props, _labels, _buttons = _render(compile_tab.build, FixtureSource("plan"))
    assert "width:100%" in html


# ---- plan length and count leave out dropped clips -----------------------------------------------

def _deciding(name, clip_name, decision, only_first_batch=False):
    """A fixture source whose named clip carries the decision; optionally the plan keeps only batch one."""
    def change(data):
        plan = data["compile_plan"]
        if only_first_batch:
            plan["batches"] = plan["batches"][:1]
        for batch in plan["batches"]:
            for clip in batch["clips"]:
                if clip["name"] == clip_name:
                    clip["decision"] = decision
    return _Source(name, change)


def test_kept_clips_leaves_out_drop_and_recycle_and_keeps_missing_decisions():
    clips = [{"name": "a", "decision": "keep"}, {"name": "b", "decision": "drop"},
             {"name": "c", "decision": "recycle"}, {"name": "d"}]
    assert [c["name"] for c in compile_tab.kept_clips({"clips": clips})] == ["a", "d"]


def test_plan_line_counts_only_the_kept_clips():
    plan = _plan("plan")
    batch = plan["batches"][0]
    source = _deciding("plan", batch["clips"][0]["name"], "drop", only_first_batch=True)
    _html, _props, labels, _buttons = _render(compile_tab.build, source)
    assert f"Plan for {plan['character']}: 1 video, 2 clips." in labels


def test_render_bar_total_wins_over_the_batch_duration():
    batch = {"number": 1, "duration_s": 130, "clips": []}
    _html, _props, labels, _buttons = _render(lambda s, a: reel.render_bar(batch, 100), FixtureSource("plan"))
    assert timefmt.duration(100) in labels
    assert timefmt.duration(130) not in labels


def test_batch_length_label_sums_only_the_kept_clips():
    batch = _plan("plan")["batches"][0]
    dropped = batch["clips"][0]
    kept = sum(c["duration_s"] for c in batch["clips"] if c["name"] != dropped["name"])
    _html, _props, labels, _buttons = _render(compile_tab.build, _deciding("plan", dropped["name"], "drop"))
    assert timefmt.duration(kept) in labels
    assert timefmt.duration(batch["duration_s"]) not in labels


# ---- stamps at the right edge ---------------------------------------------------------

def _batch_with_lit_clip_at(percent):
    """Two clips: a KO of percent seconds, then a HEXA that starts at percent of the bar."""
    return {"number": 1, "clips": [
        {"name": "THOR_a.mp4", "start_s": 0, "duration_s": percent, "tier": "KO"},
        {"name": "THOR_b.mp4", "start_s": percent, "duration_s": 100 - percent, "tier": "HEXA"},
    ]}


def _stamp_style(html, text):
    match = re.search(r'<span style="([^"]*)">%s</span>' % re.escape(text), html)
    assert match, f"no stamp {text} in the bar"
    return match.group(1)


def test_stamp_past_ninety_percent_anchors_to_the_right_edge():
    html = reel.bar_html(_batch_with_lit_clip_at(95))
    style = _stamp_style(html, timefmt.duration(95))
    assert "right:0;" in style
    assert "left:" not in style


def test_stamp_at_or_under_ninety_percent_keeps_its_left_offset():
    for percent in (50, 90):
        html = reel.bar_html(_batch_with_lit_clip_at(percent))
        style = _stamp_style(html, timefmt.duration(percent))
        assert f"left:{percent:.4f}%;" in style
        assert "right:0;" not in style


# ---- decision word and pressed buttons ------------------------------------------------

def _decide(name, decision):
    def change(data):
        for batch in data["compile_plan"]["batches"]:
            for clip in batch["clips"]:
                if clip["name"] == name:
                    clip["decision"] = decision
    return _Source("plan", change)


def _low_clip(plan):
    return next(c for b in plan["batches"] for c in b["clips"] if c["tier"] not in LIT)


def _marked_button(elements, marker):
    return next(e for e in _marked(elements, marker) if isinstance(e, ui.button))


def test_rows_with_keep_and_recycle_buttons_drop_the_decision_word():
    labels = _render(compile_tab.build, FixtureSource("plan"))[2]
    lit = sum(1 for b in _plan("plan")["batches"] for c in b["clips"] if c["tier"] in LIT)
    assert labels.count("Keep") == lit
    assert "Recycle" not in labels


def test_dropped_clip_shows_left_out_and_neither_button_pressed():
    low = _low_clip(_plan("plan"))
    tid = view_model.testid("plan-clip", low["name"])
    source = _decide(low["name"], "drop")
    elements = _page_elements(compile_tab.build, source)
    assert str(_marked_button(elements, f"keep-{tid}")._props.get("aria-pressed")).lower() == "false"
    assert str(_marked_button(elements, f"recycle-{tid}")._props.get("aria-pressed")).lower() == "false"
    assert "Left out" in _render(compile_tab.build, source)[2]


def _resolve(a, b, resolution):
    def change(data):
        for dup in data["compile_plan"]["duplicates"]:
            if (dup["a"], dup["b"]) == (a, b):
                dup["resolution"] = resolution
    return _Source("plan", change)


@pytest.mark.parametrize("resolution,pressed", (("keep_both", "keep-both"), ("drop_one", "drop-one"), (None, None)))
def test_settled_pair_shows_its_choice_as_the_pressed_button(resolution, pressed):
    dup = _plan("plan")["duplicates"][0]
    tid = view_model.testid("plan-dup", f"{dup['a']}|{dup['b']}")
    elements = _page_elements(compile_tab.build, _resolve(dup["a"], dup["b"], resolution))
    for name in ("keep-both", "drop-one"):
        button = _marked_button(elements, f"{name}-{tid}")
        chosen = name == pressed
        assert str(button._props.get("aria-pressed")).lower() == ("true" if chosen else "false")
        assert ("unelevated" in button._props) == chosen


@pytest.mark.parametrize("decision", ("keep", "recycle"))
def test_chosen_button_is_filled_and_pressed_and_the_other_stays_outlined(decision):
    low = _low_clip(_plan("plan"))
    tid = view_model.testid("plan-clip", low["name"])
    elements = _page_elements(compile_tab.build, _decide(low["name"], decision))
    keep = _marked_button(elements, f"keep-{tid}")
    recycle = _marked_button(elements, f"recycle-{tid}")
    chosen, other = (keep, recycle) if decision == "keep" else (recycle, keep)
    assert "unelevated" in chosen._props and "outline" not in chosen._props
    assert str(chosen._props.get("aria-pressed")).lower() == "true"
    assert "outline" in other._props and "unelevated" not in other._props
    assert str(other._props.get("aria-pressed")).lower() == "false"
