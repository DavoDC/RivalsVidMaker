"""Activity tab: the current job with its ETA and Stop, the recent jobs and each job's log file (spec section 3).

Rows come from view_model (activity.jobs, newest first); each row carries its testid. Raw log text never
reaches the page (spec section 7): a row links the log file and shows only the job's own result.
"""
from __future__ import annotations

import re
from html import escape
from pathlib import Path

from nicegui import ui

from gui import state_api, timefmt, tokens, view_model
from gui.components import job_bar
from gui.tabs import heading

PAINTS_ROWS = True

EMPTY_COPY = ("No jobs have run yet. Sort, scan, compile or upload from the other tabs and each run "
              "is listed here.")
INTERRUPTED_NOTE = "The app stopped while this job was running."

RESULT_WORDS = {"done": "Done", "failed": "Failed", "cancelled": "Cancelled",
                "interrupted": "Interrupted", "running": "Running"}
NO_LOG = "No log"

_TABLE = (f"width:100%;border-collapse:collapse;font-size:{tokens.SIZE_UI}px;"
          f"font-variant-numeric:tabular-nums;")
_TH = (f"text-align:left;color:{tokens.TEXT_DIM};font-weight:600;padding:{tokens.SPACE_8}px 0;"
       f"border-bottom:1px solid {tokens.LINE};")
_TD = (f"vertical-align:top;padding:{tokens.SPACE_8}px {tokens.SPACE_8}px {tokens.SPACE_8}px 0;"
       f"border-bottom:1px solid {tokens.LINE};")
_TD_NOWRAP = _TD + "white-space:nowrap;"

DELETED_CLIENT_WORDS = ("YouTube sign-in failed: the Google OAuth client was deleted. Make a new client secret "
                        "in Google Cloud, then sign in again.")
EXPIRED_WORDS = "YouTube sign-in expired. Sign in again."
ERROR_MAX = 200
_REPR_ERROR = re.compile(r"^(\w+): \(\s*(['\"])(.*?)\2\s*[,)]")


def error_words(error) -> str:
    """A job error as plain words: known sign-in failures get a sentence, a Python tuple repr keeps its
    name and first message, anything else keeps its first line. Cut to ERROR_MAX characters."""
    text = str(error)
    if "deleted_client" in text:
        return DELETED_CLIENT_WORDS
    if "invalid_grant" in text:
        return EXPIRED_WORDS
    lines = text.strip().splitlines()
    first = lines[0] if lines else ""
    match = _REPR_ERROR.match(first)
    if match:
        first = f"{match.group(1)}: {match.group(3)}"
    return first[:ERROR_MAX]


def _result_cell(job: dict) -> str:
    result = str(job.get("result") or "")
    word = RESULT_WORDS.get(result, result.capitalize() or "-")
    colour = tokens.ERROR if result == "failed" else tokens.TEXT
    parts = [f'<span style="color:{colour};">{escape(word)}</span>']
    if result == "interrupted":
        parts.append(f'<div style="color:{tokens.TEXT_DIM};">{escape(INTERRUPTED_NOTE)}</div>')
    summary = str(job.get("summary") or "").strip()
    if summary:
        parts.append(f'<div style="color:{tokens.TEXT_DIM};">{escape(summary)}</div>')
    return "".join(parts)


def _log_cell(log_path) -> str:
    if not log_path:
        return f'<span style="color:{tokens.TEXT_DIM};">{NO_LOG}</span>'
    name = Path(str(log_path)).name
    if not state_api.LOG_NAME.fullmatch(name):  # not a day log the app serves: name only, no link
        return f'<span style="color:{tokens.TEXT_DIM};">{escape(name)}</span>'
    href = f"/log/{name}"
    return (f'<a href="{escape(href, quote=True)}" target="_blank" rel="noopener" '
            f'style="color:{tokens.TEXT};">Open log</a>')


def _time_cell(value) -> str:
    """A short time that never wraps; hovering shows the full stamp."""
    full = timefmt.stamp(value)
    return (f'<td style="{_TD_NOWRAP}" title="{escape(full, quote=True)}">'
            f"{escape(timefmt.short(value))}</td>")


def table_html(jobs: list[dict]) -> str:
    """The recent jobs table: one row per job with its view_model testid, newest first as given."""
    body = []
    for job in jobs:
        title = escape(str(job.get("title") or job.get("kind") or "-"))
        error = job.get("error")
        error_line = (f'<div style="color:{tokens.ERROR};">{escape(error_words(error))}</div>' if error else "")
        body.append(
            f'<tr data-testid="{job["testid"]}">'
            f'<td style="{_TD}width:40%;">{title}{error_line}</td>'
            f'<td style="{_TD}">{_result_cell(job)}</td>'
            f'{_time_cell(job.get("started_at"))}'
            f'{_time_cell(job.get("ended_at"))}'
            f'<td style="{_TD_NOWRAP}">{_log_cell(job.get("log_path"))}</td>'
            "</tr>")
    return (f'<table style="{_TABLE}"><thead><tr>'
            f'<th style="{_TH}width:40%;">Job</th><th style="{_TH}">Result</th>'
            f'<th style="{_TH}">Started</th><th style="{_TH}">Ended</th><th style="{_TH}">Log</th>'
            "</tr></thead><tbody>" + "".join(body) + "</tbody></table>")


def build(source) -> None:
    state = view_model.snapshot(source)
    jobs = state["activity"]["jobs"]
    heading("Activity")
    job_bar.render(state["job"])
    ui.label("Recent jobs").style(
        f"font-size:{tokens.SIZE_SECTION}px;font-weight:600;font-stretch:87.5%;margin:{tokens.SPACE_24}px 0 {tokens.SPACE_8}px;")
    if not jobs:
        ui.label(EMPTY_COPY).style(f"font-size:{tokens.SIZE_BODY}px;color:{tokens.TEXT_DIM};")
        return
    ui.html(table_html(jobs))
