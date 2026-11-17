"""Activity table (task 49): times stay on one line with a full-stamp hover, the Job column takes 40%,
and a sign-in error reads as plain words instead of a Python repr."""
import re

from gui import timefmt
from gui.tabs import activity

REPR = ("RefreshError: ('deleted_client: The OAuth client was deleted.', {'error': 'deleted_client', "
        "'error_description': 'The OAuth client was deleted.'})")
DELETED = ("YouTube sign-in failed: the Google OAuth client was deleted. Make a new client secret in "
           "Google Cloud, then sign in again.")
EXPIRED = "YouTube sign-in expired. Sign in again."


def _job(**fields):
    base = {"testid": "job-test-000001", "kind": "upload", "title": "Upload thor_vid1",
            "result": "done", "summary": None, "error": None,
            "started_at": "2020-01-05T00:07:00", "ended_at": "2020-01-05T00:30:00", "log_path": None}
    return {**base, **fields}


# ---- error words -------------------------------------------------------------------------------

def test_error_words_deleted_client_gives_the_sign_in_sentence():
    assert activity.error_words(REPR) == DELETED


def test_error_words_invalid_grant_gives_the_expired_sentence():
    text = "RefreshError: ('invalid_grant: Token has been expired or revoked.', {'error': 'invalid_grant'})"
    assert activity.error_words(text) == EXPIRED


def test_error_words_tuple_repr_keeps_the_name_and_first_quoted_message():
    assert activity.error_words("ValueError: ('bad thing', {'a': 1})") == "ValueError: bad thing"


def test_error_words_plain_one_line_error_is_unchanged():
    assert activity.error_words("Upload failed: file is locked") == "Upload failed: file is locked"


def test_error_words_keeps_only_the_first_line():
    assert activity.error_words("Disk full\nTraceback (most recent call last):") == "Disk full"


def test_error_words_cuts_to_200_characters():
    assert len(activity.error_words("x" * 300)) == 200


# ---- activity table ----------------------------------------------------------------------------

def test_deleted_client_error_renders_the_sentence_and_no_python_repr():
    html = activity.table_html([_job(result="failed", error=REPR)])
    assert DELETED in html
    assert "deleted_client" not in html
    assert "{" not in html


def test_invalid_grant_error_renders_the_expired_sentence():
    html = activity.table_html([_job(result="failed", error="invalid_grant: revoked")])
    assert EXPIRED in html
    assert "invalid_grant" not in html


def test_started_and_ended_cells_are_short_nowrap_with_the_full_stamp_as_title():
    html = activity.table_html([_job()])
    started = re.search(r'<td style="([^"]*)" title="05/01/2020 12:07am">5 Jan 2020</td>', html)
    ended = re.search(r'<td style="([^"]*)" title="05/01/2020 12:30am">5 Jan 2020</td>', html)
    assert started and "white-space:nowrap;" in started.group(1)
    assert ended and "white-space:nowrap;" in ended.group(1)


def test_log_cell_is_nowrap(tmp_path):
    log = tmp_path / "gui.log"
    log.write_text("", encoding="utf-8")
    html = activity.table_html([_job(log_path=str(log))])
    cell = re.search(r'<td style="([^"]*)"><a href="file:', html)
    assert cell and "white-space:nowrap;" in cell.group(1)


def test_job_header_and_cell_are_forty_percent_and_other_columns_have_no_width():
    html = activity.table_html([_job()])
    assert re.search(r'<th style="[^"]*width:40%;[^"]*">Job</th>', html)
    assert re.search(r'<td style="[^"]*width:40%;[^"]*">Upload thor_vid1</td>', html)
    for column in ("Result", "Started", "Ended", "Log"):
        assert not re.search(rf'<th style="[^"]*width[^"]*">{column}</th>', html)
