"""Archive and Activity tabs (spec sections 3 and 10): row testids, empty copy, tier chips, job bar.

Rows carry the view_model testids exactly; the painted set matches the state rows the way ui_check
compares them. No pre element anywhere; Stop is absent (not disabled) unless the job is cancellable.
Tab tests run the NiceGUI user simulator from sync tests with asyncio.run, as tests/gui/test_gui_shell.py
does. Nothing here writes outside tmp_path.
"""
import asyncio
import re

import pytest
from nicegui import ui
from nicegui.element_filter import ElementFilter
from nicegui.testing.user_simulation import user_simulation

from gui import avatars, fixtures, tokens, ui_check, view_model
from gui.components import job_bar, tier_chip
from gui.sources import FixtureSource
from gui.tabs import activity, archive

SCENARIOS = tuple(fixtures.SCENARIOS)
TESTID = re.compile(r'data-testid="([^"]+)"')


class _Source(FixtureSource):
    """A fixture scenario with one change applied to its data (a fresh copy per read)."""

    def __init__(self, name, change):
        super().__init__(name)
        self._change = change

    def read(self):
        data = super().read()
        self._change(data)
        return data


def _render(builder, source, marker=None):
    """Run builder(source) inside a simulated page. Returns the HTML of every ui.html element and the
    testids of every element that has one, plus the elements carrying marker when given."""
    def root():
        builder(source)

    async def run():
        async with user_simulation(root) as user:
            await user.open("/")
            with user.client:
                elements = list(ElementFilter(only_visible=False))
                html = "\n".join(e.content for e in elements if isinstance(e, ui.html))
                html += "\n" + "\n".join(e.text for e in elements if isinstance(e, ui.label))
                props = [e._props.get("data-testid") for e in elements]
                found = (list(ElementFilter(marker=marker, only_visible=False)) if marker else [])
            return html, [p for p in props if p], len(found)

    return asyncio.run(run())


def _state_rows(source, prefix):
    state = view_model.snapshot(source)
    ids = ui_check.state_row_ids(state)
    return {t for t in ids if t.startswith(prefix)}


def _ui_rows(html, prefix):
    return {t for t in TESTID.findall(html) if t.startswith(prefix)}


# ---- tier chips -------------------------------------------------------------------------------

@pytest.mark.parametrize("tier,token", [("QUAD", tokens.TIER_QUAD), ("PENTA", tokens.TIER_PENTA),
                                        ("HEXA", tokens.TIER_HEXA)])
def test_chip_for_a_kept_tier_uses_its_ramp_colour_and_the_tier_word(tier, token):
    chip = tier_chip.chip_html(tier, 3)
    assert f"{tier} 3" in chip
    assert token in chip
    assert tokens.ON_TIER in chip


@pytest.mark.parametrize("tier", ["KO", "DOUBLE", "TRIPLE", "NONE", ""])
def test_chip_refuses_tiers_below_quad(tier):
    with pytest.raises(ValueError):
        tier_chip.chip_html(tier, 1)


def test_chip_without_a_count_is_the_word_alone():
    assert ">QUAD</span>" in tier_chip.chip_html("QUAD")


# ---- job bar text -----------------------------------------------------------------------------

def test_job_bar_progress_text_and_fraction_clamp_to_the_bar():
    job = {"done": 3, "total": 9, "unit": "steps"}
    assert job_bar.progress_text(job) == "3 of 9 steps"
    assert job_bar.progress_fraction(job) == pytest.approx(3 / 9)
    assert job_bar.progress_fraction({"done": 12, "total": 9}) == 1.0
    assert job_bar.progress_fraction({"done": -2, "total": 9}) == 0.0
    assert job_bar.progress_fraction({"done": 1, "total": None}) == 0.0


def test_job_bar_eta_says_starting_until_the_first_signal():
    assert job_bar.eta_text({"done": None, "total": 9, "eta_s": None}) == "Starting"
    assert job_bar.eta_text({"done": 0, "total": 9, "eta_s": None}) == "Starting"


def test_job_bar_eta_before_a_rate_exists_and_after():
    assert job_bar.eta_text({"done": 2, "total": 9, "eta_s": None}) == "Estimating time left"
    assert job_bar.eta_text({"done": 2, "total": 9, "eta_s": 240}) == "About 4 min left"
    assert job_bar.eta_text({"done": 2, "total": 9, "eta_s": 40}) == "About 40 s left"


# ---- archive rows -----------------------------------------------------------------------------

def test_archive_table_rows_carry_the_view_model_testids_and_name_each_character():
    source = FixtureSource("huge_archive")
    rows = view_model.snapshot(source)["archive"]["by_character"]
    html = archive.table_html(rows)
    assert _ui_rows(html, "archive-") == {r["testid"] for r in rows}
    assert "Archive Group 0001</div>" in html
    assert "ARCHIVE GROUP 0001" not in html


def test_archive_chips_only_for_quad_penta_hexa():
    rows = [{"testid": "archive-thor-000001", "name": "THOR", "count": 9,
             "tiers": {"KO": 4, "DOUBLE": 2, "TRIPLE": 1, "QUAD": 1, "PENTA": 1, "HEXA": 0}}]
    html = archive.table_html(rows)
    assert 'data-tier="QUAD" ' in html and ">QUAD 1</span>" in html
    assert 'data-tier="PENTA" ' in html and ">PENTA 1</span>" in html
    assert 'data-tier="HEXA"' not in html  # a zero count gets no chip
    for low in ("KO", "DOUBLE", "TRIPLE"):
        assert f'data-tier="{low}"' not in html
        assert f">{low}" not in html


def test_archive_names_from_data_are_escaped_not_markup():
    rows = [{"testid": "archive-x-000000", "name": "<b>bold</b>", "count": 1,
             "tiers": {"QUAD": 1}}]
    html = archive.table_html(rows)
    assert "&lt;b&gt;bold&lt;/b&gt;" in html
    assert "<b>bold</b>" not in html


def test_archive_character_cell_shows_the_display_name_not_the_folder_name(monkeypatch, tmp_path):
    monkeypatch.setattr(avatars, "ASSET_DIR", tmp_path)  # no portrait, so the initials badge shows
    rows = [{"testid": "archive-thor-000001", "name": "THOR", "count": 1, "tiers": {"QUAD": 1}}]
    html = archive.table_html(rows)
    assert "Thor</div>" in html
    assert ">THOR<" not in html


def test_archive_empty_copy_names_the_next_action():
    html, _props, _n = _render(archive.build, FixtureSource("empty"))
    assert archive.EMPTY_COPY in html
    assert "Clean up" in archive.EMPTY_COPY


def test_archive_copy_says_quad_or_better_with_tier_words_upper_case():
    html, _props, _n = _render(archive.build, FixtureSource("empty"))
    assert "QUAD or better" in archive.EMPTY_COPY
    assert "Quad" not in archive.EMPTY_COPY
    assert "QUAD or better" in html and "Quad" not in html
    full_html, _props, _n = _render(archive.build, FixtureSource("huge_archive"))
    assert "kept for a best-of. QUAD or better only." in full_html
    assert "Quad" not in full_html


@pytest.mark.parametrize("scenario", SCENARIOS)
def test_archive_painted_rows_match_the_state_rows(scenario):
    source = FixtureSource(scenario)
    html, props, _n = _render(archive.build, source)
    painted = {t for t in props + TESTID.findall(html) if t.startswith("archive-")}
    assert painted == _state_rows(FixtureSource(scenario), "archive-")


# ---- activity rows ----------------------------------------------------------------------------

def _job_source(**job_fields):
    def change(data):
        data["job"] = {**fixtures.job("compile", "Encode THOR batch 1", "encoding", 3, 9, "steps",
                                      eta_s=240), **job_fields}
    return _Source("encoding", change)


def test_activity_rows_carry_the_view_model_testids():
    source = FixtureSource("interrupted")
    jobs = view_model.snapshot(source)["activity"]["jobs"]
    html = activity.table_html(jobs)
    assert _ui_rows(html, "job-") == {j["testid"] for j in jobs}
    assert "Interrupted" in html


@pytest.mark.parametrize("scenario", SCENARIOS)
def test_activity_painted_rows_match_the_state_rows(scenario):
    html, props, _n = _render(activity.build, FixtureSource(scenario))
    painted = {t for t in props + TESTID.findall(html) if t.startswith("job-")}
    assert painted == _state_rows(FixtureSource(scenario), "job-")


def test_activity_failed_row_shows_the_error_as_escaped_text():
    def change(data):
        data["activity"] = [fixtures.activity("upload", "Upload thor_vid1", "failed", error="<auth>")]
    jobs = view_model.snapshot(_Source("empty", change))["activity"]["jobs"]
    html = activity.table_html(jobs)
    assert "Failed" in html
    assert "&lt;auth&gt;" in html
    assert "<auth>" not in html


def test_activity_summary_shows_under_the_result_word_escaped():
    def change(data):
        data["activity"] = [{**fixtures.activity("sort", "Sort clips", "done"),
                             "summary": "Sorted <b>3</b> clips."}]
    jobs = view_model.snapshot(_Source("empty", change))["activity"]["jobs"]
    html = activity.table_html(jobs)
    assert "Sorted &lt;b&gt;3&lt;/b&gt; clips." in html
    assert "<b>3</b>" not in html
    assert html.index("Done") < html.index("Sorted &lt;b&gt;")


@pytest.mark.parametrize("summary", [None, ""])
def test_activity_without_a_summary_renders_no_summary_line(summary):
    def change(data):
        data["activity"] = [{**fixtures.activity("sort", "Sort clips", "done"), "summary": summary}]
    jobs = view_model.snapshot(_Source("empty", change))["activity"]["jobs"]
    html = activity.table_html(jobs)
    assert f'<div style="color:{tokens.TEXT_DIM};">' not in html


def test_activity_log_path_becomes_a_file_link(tmp_path):
    log = tmp_path / "gui_2026-11-17.log"
    log.write_text("", encoding="utf-8")

    def change(data):
        data["activity"] = [{**fixtures.activity("scan", "Scan THOR clips", "done"),
                             "log_path": str(log)}]
    jobs = view_model.snapshot(_Source("empty", change))["activity"]["jobs"]
    html = activity.table_html(jobs)
    assert 'href="file:///' in html
    assert "Open log" in html


def test_result_word_is_regular_weight_and_failed_keeps_the_error_colour():
    done = activity._result_cell({"result": "done"})
    failed = activity._result_cell({"result": "failed"})
    assert "font-weight:600" not in done
    assert f"color:{tokens.ERROR};" in failed


def test_log_cell_without_a_log_reads_no_log_not_a_dash():
    html = activity._log_cell(None)
    assert "No log" in html
    assert ">-<" not in html


def test_activity_empty_copy_names_the_next_action():
    html, _props, _n = _render(activity.build, FixtureSource("empty"))
    assert activity.EMPTY_COPY in html
    assert "No jobs have run yet" in activity.EMPTY_COPY


# ---- Stop: absent, not disabled, unless the job is cancellable ---------------------------------

def test_stop_is_shown_for_a_cancellable_running_job():
    _html, _props, found = _render(activity.build, FixtureSource("scanning"), marker="stop-current-job")
    assert found == 1


def test_stop_is_absent_when_no_job_runs():
    _html, _props, found = _render(activity.build, FixtureSource("empty"), marker="stop-current-job")
    assert found == 0


def test_stop_is_absent_for_an_encode_job_that_cannot_be_cancelled():
    # Encode cancel is past MVP: the view model marks only scan and cleanup cancellable.
    for source in (_job_source(cancellable=False), FixtureSource("encoding")):
        html, _props, found = _render(activity.build, source, marker="stop-current-job")
        assert found == 0
        assert "disabled" not in html.lower()


def test_stop_click_calls_the_passed_in_callable():
    calls = []

    def root():
        job_bar.render({"id": "scan-1", "title": "Scan THOR clips", "done": 1, "total": 2, "unit": "clips",
                        "eta_s": None, "cancellable": True}, on_stop=lambda: calls.append("stop"))

    async def run():
        async with user_simulation(root) as user:
            await user.open("/")
            user.find(marker="stop-current-job").click()

    asyncio.run(run())
    assert calls == ["stop"]


def test_stop_defaults_to_a_no_op_when_no_callable_is_passed():
    def root():
        job_bar.render({"id": "scan-1", "title": "Scan THOR clips", "done": 1, "total": 2, "unit": "clips",
                        "eta_s": None, "cancellable": True})

    async def run():
        async with user_simulation(root) as user:
            await user.open("/")
            user.find(marker="stop-current-job").click()

    asyncio.run(run())


# ---- shape: no raw output, rows opted in -------------------------------------------------------

@pytest.mark.parametrize("scenario", SCENARIOS)
@pytest.mark.parametrize("builder", [archive.build, activity.build])
def test_no_pre_element_on_either_tab(scenario, builder):
    html, _props, _n = _render(builder, FixtureSource(scenario))
    assert not re.search(r"<\s*pre[\s>]", html, re.IGNORECASE)


def test_both_tabs_opt_in_to_the_painted_row_check():
    assert archive.PAINTS_ROWS is True
    assert activity.PAINTS_ROWS is True


# ---- job bar layout (DESIGN.md sections 5 and 8, task 27b) -------------------------------------

BAR_JOB = {"id": "enc-1", "title": "Encode THOR batch 1", "phase": "encoding", "done": 3, "total": 9,
           "unit": "steps", "eta_s": 240, "cancellable": False}
BAD_BAR_CHARS = (chr(0x00B7), chr(0x2014), chr(0x2013))


def test_job_bar_has_no_middle_dot_or_dash_in_any_state():
    states = (BAR_JOB, {**BAR_JOB, "done": None, "eta_s": None},
              {**BAR_JOB, "phase": None, "total": None}, {**BAR_JOB, "eta_s": 40})
    for job in states:
        html = job_bar.bar_html(job)
        for ch in BAD_BAR_CHARS:
            assert ch not in html


def test_job_bar_count_and_eta_are_separate_elements_with_a_16px_gap():
    html = job_bar.bar_html(BAR_JOB)
    assert f"gap:{tokens.SPACE_16}px" in html
    assert re.search(r'data-part="count"[^>]*>3 of 9 steps</span>', html)
    assert re.search(r'data-part="eta"[^>]*>About 4 min left</span>', html)
    assert ">3 of 9 steps</span><span data-part=\"eta\"" in html


def test_track_spans_the_panel_width_with_a_640px_maximum():
    html = job_bar.bar_html(BAR_JOB)
    track = re.search(r'role="progressbar"[^>]*style="([^"]*)"', html).group(1)
    assert "width:100%" in track
    assert "max-width:640px" in track


def test_done_none_renders_starting_for_the_eta():
    html = job_bar.bar_html({**BAR_JOB, "done": None, "eta_s": None})
    assert re.search(r'data-part="eta"[^>]*>Starting</span>', html)


def test_phase_word_is_shown_before_the_title_when_the_phase_is_set():
    html = job_bar.bar_html(BAR_JOB)
    assert "Encoding" in html
    assert html.index("Encoding") < html.index("Encode THOR batch 1")
    assert "Encoding" not in job_bar.bar_html({**BAR_JOB, "phase": None})
