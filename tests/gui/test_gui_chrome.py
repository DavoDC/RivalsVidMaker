"""Page head and chrome (docs/DESIGN.md): theme.py and chrome.py."""
import re
from pathlib import Path

from gui import build_info, chrome, security, theme, timefmt, tokens

ROOT = Path(__file__).resolve().parents[2]
GUI_FILES = [ROOT / "src" / "gui" / "theme.py", ROOT / "src" / "gui" / "chrome.py"]
HEX_LITERAL = re.compile(r"#[0-9a-fA-F]{6}\b")
DASHES = (chr(0x2014), chr(0x2013))
MIDDLE_DOT = chr(0x00B7)
STARTED = "2026-11-17T14:14:00+00:00"


def test_head_html_has_reduced_motion_rule():
    assert "prefers-reduced-motion" in theme.HEAD_HTML


def test_head_html_has_tabular_figures():
    assert "font-variant-numeric: tabular-nums" in theme.HEAD_HTML


def test_head_html_uses_bahnschrift_stack():
    assert "Bahnschrift" in theme.HEAD_HTML
    assert 'Bahnschrift, "Segoe UI Variable", "Segoe UI", sans-serif' in theme.HEAD_HTML


def test_head_html_dims_disabled_buttons_past_quasar_opacity():
    # NiceGUI imports Quasar's .q-btn.disabled{opacity:.7 !important} into the quasar_importants layer. A layered
    # !important beats any unlayered one whatever its specificity, and for !important the EARLIEST declared layer
    # wins, so the rule lives in the first layer, theme (live probe: computed 0.7 when unlayered).
    assert "@layer theme{.q-btn.disabled,.q-btn[disabled]{opacity:0.6 !important;}}" in theme.HEAD_HTML
    assert "opacity:0.45" not in theme.HEAD_HTML


def test_head_html_app_title_is_the_tab_heading_size_and_tabs_the_section_size():
    assert ".rvm-title{font-size:26px;" in theme.HEAD_HTML
    assert ".rvm-tab{font:inherit;font-size:20px;" in theme.HEAD_HTML


def test_head_html_has_visible_focus_ring():
    assert ":focus-visible" in theme.HEAD_HTML
    assert "outline" in theme.HEAD_HTML


def test_head_html_has_no_unfilled_placeholders():
    assert not re.search(r"@@[A-Z0-9_]+@@", theme.HEAD_HTML)


def test_head_html_takes_colours_from_tokens():
    assert tokens.GROUND in theme.HEAD_HTML
    assert tokens.TEXT in theme.HEAD_HTML


def test_error_js_reports_with_app_error_tag():
    assert "[app-error]" in chrome.ERROR_JS


def test_error_js_posts_to_log_route():
    assert "/__log" in chrome.ERROR_JS


def test_head_html_fills_token_into_error_js_as_json_string():
    head = chrome.head_html()
    assert "__TOKEN__" not in head
    assert '"' + security.TOKEN + '"' in head


def test_quit_js_posts_to_quit_route_with_the_token_header():
    assert "/__quit" in chrome.QUIT_JS
    assert "X-RVM-Token" in chrome.QUIT_JS


def test_quit_js_uses_document_delegation_not_an_inline_handler():
    assert "closest('#rvm-quit')" in chrome.QUIT_JS
    assert "onclick" not in chrome.head_html()


def test_head_html_carries_quit_script_with_the_token_filled():
    head = chrome.head_html()
    assert "/__quit" in head
    assert "closest('#rvm-quit')" in head
    assert "__TOKEN__" not in head
    assert '"' + security.TOKEN + '"' in head


def test_quit_js_states_the_three_outcomes():
    js = chrome.QUIT_JS
    assert "RivalsVidMaker stopped. You can close this tab." in js
    assert "'Busy: '" in js and "'. Quit when it finishes.'" in js
    assert "Quit failed. Try again." in js


def test_quit_js_escapes_the_job_title_with_textcontent():
    assert "textContent" in chrome.QUIT_JS
    assert "innerHTML" not in chrome.QUIT_JS


def test_theme_has_toast_rule():
    assert "#rvm-toast" in theme.HEAD_HTML


def test_error_js_sends_rvm_token_header():
    assert "X-RVM-Token" in chrome.ERROR_JS
    assert "X-AM-Token" not in chrome.ERROR_JS


def test_debug_script_exposes_the_named_surface():
    js = chrome.DEBUG_JS
    assert "window.__debug" in js
    for name in ("version", "state", "setTab", "forceStatus", "help"):
        assert re.search(rf"\b{name}\s*:", js), name


def test_debug_forcestatus_writes_the_header_state():
    assert "rvm-state" in chrome.DEBUG_JS
    assert "rvm-dot" in chrome.DEBUG_JS


def test_footer_contains_build_info_line():
    html = chrome.footer_html(build_info.line(), STARTED, 180)
    assert build_info.line() in html


def test_footer_shows_start_time_with_display_stamp():
    html = chrome.footer_html("RivalsVidMaker abc1234 17/11/2026", STARTED, 180)
    assert timefmt.stamp(STARTED) in html
    assert "17/11/2026 2:14pm" in html


def test_footer_shows_relative_update_age():
    assert "updated 3m ago" in chrome.footer_html("line", STARTED, 180)


def test_footer_without_an_update_yet_says_so():
    assert "not updated yet" in chrome.footer_html("line", STARTED, None)


def test_footer_joins_fields_without_middle_dot():
    assert MIDDLE_DOT not in chrome.footer_html("line", STARTED, 180)


def test_footer_escapes_the_line():
    html = chrome.footer_html("<b>x</b>", STARTED, 0)
    assert "<b>x</b>" not in html
    assert "&lt;b&gt;" in html


def test_fixture_banner_absent_outside_fixture_mode():
    assert chrome.fixture_banner_html(None) == ""


def test_fixture_banner_names_the_scenario():
    html = chrome.fixture_banner_html("plan")
    assert "FIXTURE plan" in html
    assert 'data-testid="fixture-banner"' in html


def test_header_has_title_live_state_and_quit():
    html = chrome.header_html("Idle", "idle")
    assert "RivalsVidMaker" in html
    assert 'aria-live="polite"' in html
    assert "Idle" in html
    assert ">Quit<" in html


def test_header_state_word_is_escaped():
    html = chrome.header_html("<img src=x>", "error")
    assert "<img" not in html
    assert "&lt;img" in html


def test_header_state_kind_is_carried_as_data_attribute():
    assert 'data-kind="working"' in chrome.header_html("Scanning THOR 12 of 40", "working")


def test_body_html_has_error_banner_and_footer():
    html = chrome.body_html("Idle", "idle", None, STARTED, 5)
    assert 'id="error-banner"' in html
    assert 'data-testid="build-footer"' in html
    assert "updated 5s ago" in html


def test_chrome_and_theme_have_no_hex_colour_literal():
    hits = []
    for path in GUI_FILES:
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if HEX_LITERAL.search(line):
                hits.append(f"{path.name}:{n}")
    assert not hits, hits


def test_chrome_and_theme_have_no_em_or_en_dash():
    hits = [path.name for path in GUI_FILES
            if any(dash in path.read_text(encoding="utf-8") for dash in DASHES)]
    assert not hits, hits


def test_copied_files_carry_the_sibling_kit_marker_only():
    for path in GUI_FILES:
        first = path.read_text(encoding="utf-8").splitlines()[0]
        assert first.startswith("# copied from a sibling local GUI kit (") and first.endswith(")")
        assert "/" not in first and "\\" not in first
