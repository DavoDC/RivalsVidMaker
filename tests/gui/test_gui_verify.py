"""verify (one PASS or FAIL line with per-step timings), the capture bad-text scanner and the
DOM checks that capture applies to every visit. No browser, no server: steps are faked."""
import json
import re

import pytest

from gui import capture, verify

SUMMARY = re.compile(r"^\[(PASS|FAIL)\] ")


# ---- run_steps: every step runs, one summary line -------------------------------------------

def test_run_steps_passes_with_timed_summary():
    code, line = verify.run_steps([("pytest", lambda: 0), ("ui_check", lambda: 0)])
    assert code == 0
    assert re.fullmatch(r"\[PASS\] pytest \(\d+s\) \+ ui_check \(\d+s\)", line)


def test_run_steps_runs_every_step_after_a_failure():
    ran = []

    def failing():
        ran.append("pytest")
        return 1

    def passing():
        ran.append("capture")
        return 0

    code, line = verify.run_steps([("pytest", failing), ("capture", passing)])
    assert ran == ["pytest", "capture"]
    assert code == 1
    assert line == "[FAIL] pytest=1"


def test_run_steps_treats_a_crashing_step_as_failed():
    def boom():
        raise RuntimeError("no browser")

    code, line = verify.run_steps([("capture", boom)])
    assert code == 1
    assert line == "[FAIL] capture=error"


# ---- main: exit code and the one printed line ------------------------------------------------

@pytest.mark.parametrize("pytest_code,expected_exit", [(0, 0), (1, 1)])
def test_main_exit_code_follows_the_failing_step(monkeypatch, capsys, pytest_code, expected_exit):
    monkeypatch.setattr(verify, "_pytest", lambda: pytest_code)
    monkeypatch.setattr(verify, "_ui_check", lambda: 0)
    monkeypatch.setattr(verify, "_capture", lambda *a, **k: 0)
    assert verify.main(["--fast"]) == expected_exit
    lines = [l for l in capsys.readouterr().out.splitlines() if SUMMARY.match(l)]
    assert len(lines) == 1
    assert lines[0].startswith("[PASS] " if expected_exit == 0 else "[FAIL] pytest=1")


def test_fast_mode_skips_the_full_capture_matrix(monkeypatch):
    seen = []
    monkeypatch.setattr(verify, "_pytest", lambda: 0)
    monkeypatch.setattr(verify, "_ui_check", lambda: 0)
    monkeypatch.setattr(verify, "_capture", lambda fast: seen.append(fast) or 0)
    verify.main(["--fast"])
    verify.main([])
    assert seen == [True, False]


# ---- bad-text scanner: each forbidden string is flagged, clean text passes ---------------------

@pytest.mark.parametrize("bad", ["[app-error] boom", "undefined", "NaN", "Traceback (most recent call last)"])
def test_scanner_flags_each_forbidden_string_in_visible_text(bad):
    assert capture.bad_text_problems(f"Clips\n{bad}\n", "") != []


def test_scanner_flags_app_error_and_traceback_in_console():
    assert capture.bad_text_problems("Clips", "[app-error] uncaught: x") != []
    assert capture.bad_text_problems("Clips", "Traceback (most recent call last)") != []


def test_scanner_passes_clean_text():
    text = "Clips 12 ready\nTHOR 9 KO 2 DOUBLE\nNancy 3 nan-free words"
    assert capture.bad_text_problems(text, "log: tab ready") == []


def test_scanner_ignores_words_that_only_contain_a_forbidden_string():
    assert capture.bad_text_problems("Nancy and undefinedness are not bad words here", "") == []


# ---- DOM checks applied to each visit -------------------------------------------------------

GOOD_DOM = ('<html><div id="error-banner" hidden></div>'
            '<div data-testid="build-line">abc1234 9:36am</div>'
            '<button data-testid="nav-clips" aria-selected="true">Clips</button>'
            '<section data-testid="tab-clips" data-content-len="42"></section>'
            '<div data-hscroll="no"></div></html>')


def test_clean_visit_has_no_problems():
    assert capture.verify_dom("clips", GOOD_DOM, "", 1440, None) == []


def test_visit_without_a_build_line_fails():
    dom = GOOD_DOM.replace("abc1234 9:36am", "")
    assert any("build line" in p for p in capture.verify_dom("clips", dom, "", 1440, None))


def test_build_line_must_start_with_a_seven_character_sha():
    old_style = GOOD_DOM.replace("abc1234 9:36am", "RivalsVidMaker abc1234 17/11/2026")
    assert any("build line" in p for p in capture.verify_dom("clips", old_style, "", 1440, None))


def test_visit_with_an_empty_tab_fails():
    dom = GOOD_DOM.replace('data-content-len="42"', 'data-content-len="0"')
    assert any("is empty" in p for p in capture.verify_dom("clips", dom, "", 1440, None))


def test_visit_whose_tab_was_not_selected_fails():
    dom = GOOD_DOM.replace('aria-selected="true"', 'aria-selected="false"')
    assert any("was not selected" in p for p in capture.verify_dom("clips", dom, "", 1440, None))


def test_visible_error_banner_fails():
    dom = GOOD_DOM.replace('id="error-banner" hidden', 'id="error-banner"')
    assert any("error banner is visible" in p for p in capture.verify_dom("clips", dom, "", 1440, None))


def test_fixture_run_without_the_fixture_banner_fails():
    assert any("FIXTURE banner" in p for p in capture.verify_dom("clips", GOOD_DOM, "", 1440, "ready"))


# ---- matrix constants ----------------------------------------------------------------------

def test_tab_url_uses_the_server_deep_link_route():
    # The server routes /tab/<key>; ?tab= is only written by the page after load.
    assert capture.tab_url("http://127.0.0.1:8476", "compile") == "http://127.0.0.1:8476/tab/compile"


def test_capture_matrix_is_every_tab_scenario_and_both_widths():
    from gui import fixtures, tabdefs
    assert capture.TABS == tabdefs.KEYS
    assert capture.SCENARIOS == tuple(fixtures.SCENARIOS)
    assert capture.WIDTHS == (1024, 1440)


# ---- ui_check scope: only tabs whose module sets PAINTS_ROWS are compared -----------------------

class _FakeModule:
    def __init__(self, paints=None):
        if paints is not None:
            self.PAINTS_ROWS = paints


@pytest.mark.parametrize("testid,tab", [
    ("clip-char-thor-1", "clips"), ("clip-root-x", "clips"), ("lowvalue-x", "clips"),
    ("plan-clip-x", "compile"), ("video-thor-1", "videos"), ("fate-x", "videos"),
    ("archive-x", "archive"), ("job-x", "activity"), ("nav-clips", None), ("header", None),
])
def test_tab_of_maps_each_row_prefix_to_its_tab(testid, tab):
    assert verify.tab_of(testid) == tab


def test_opted_in_tabs_keeps_only_modules_that_set_paints_rows_true():
    modules = {"clips": _FakeModule(True), "compile": _FakeModule(None), "videos": _FakeModule(False),
               "archive": _FakeModule(None), "activity": _FakeModule(None)}
    assert verify.opted_in_tabs(lambda name: modules[name.rsplit(".", 1)[-1]]) == ["clips"]


class _FakeBrowser:
    def visit(self, url, png, width, tab):
        return "", "", True  # nothing painted


STATE = {"clips": {"rows": [{"testid": "clip-char-thor-1"}]},
         "compile": {"rows": [{"testid": "plan-clip-x-2"}]}}


@pytest.fixture
def state_server(monkeypatch):
    body = json.dumps(STATE).encode()

    class _Resp:
        def read(self):
            return body

    monkeypatch.setattr(capture.urllib.request, "urlopen", lambda *a, **k: _Resp())


def test_flagged_tab_with_missing_rows_fails(state_server, tmp_path):
    probs = capture.painted_problems(_FakeBrowser(), "http://x", ["clips"], tmp_path, 1440,
                                     keep=verify.keep_for(["clips"]))
    assert probs == ["missing on page: clip-char-thor-1"]


def test_unflagged_tab_rows_are_skipped(state_server, tmp_path):
    probs = capture.painted_problems(_FakeBrowser(), "http://x", ["clips"], tmp_path, 1440,
                                     keep=verify.keep_for(["clips"]))
    assert not any("plan-clip" in p for p in probs)


def test_no_opted_in_tabs_reports_zero_and_passes(monkeypatch, capsys):
    monkeypatch.setattr(verify, "opted_in_tabs", lambda: [])
    monkeypatch.setattr(capture, "find_chrome", lambda: pytest.fail("chrome must not start"))
    assert verify._ui_check() == 0
    assert "ui_check: 0 tabs painted" in capsys.readouterr().out
