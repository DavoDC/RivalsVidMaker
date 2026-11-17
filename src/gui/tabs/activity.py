"""Activity tab: the current job with its ETA and Stop, the recent jobs and each job's log file (spec section 3).

Rows come from view_model (activity.jobs, newest first); each row carries its testid. Raw log text never
reaches the page (spec section 7): a row links the log file and shows only the job's own result.
"""
from __future__ import annotations

from html import escape
from pathlib import Path

from nicegui import ui

from gui import timefmt, tokens, view_model
from gui.components import job_bar
from gui.tabs import heading

PAINTS_ROWS = True

EMPTY_COPY = ("No jobs have run yet. Sort, scan, compile or upload from the other tabs and each run "
              "is listed here.")
INTERRUPTED_NOTE = "The app stopped while this job was running."

RESULT_WORDS = {"done": "Done", "failed": "Failed", "cancelled": "Cancelled",
                "interrupted": "Interrupted", "running": "Running"}

_TABLE = (f"width:100%;border-collapse:collapse;font-size:{tokens.SIZE_UI}px;"
          f"font-variant-numeric:tabular-nums;")
_TH = (f"text-align:left;color:{tokens.TEXT_DIM};font-weight:600;padding:{tokens.SPACE_8}px 0;"
       f"border-bottom:1px solid {tokens.LINE};")
_TD = (f"vertical-align:top;padding:{tokens.SPACE_8}px {tokens.SPACE_8}px {tokens.SPACE_8}px 0;"
       f"border-bottom:1px solid {tokens.LINE};")


def _result_cell(job: dict) -> str:
    result = str(job.get("result") or "")
    word = RESULT_WORDS.get(result, result.capitalize() or "-")
    colour = tokens.ERROR if result == "failed" else tokens.TEXT
    parts = [f'<span style="color:{colour};font-weight:600;">{escape(word)}</span>']
    if result == "interrupted":
        parts.append(f'<div style="color:{tokens.TEXT_DIM};">{escape(INTERRUPTED_NOTE)}</div>')
    summary = str(job.get("summary") or "").strip()
    if summary:
        parts.append(f'<div style="color:{tokens.TEXT_DIM};">{escape(summary)}</div>')
    return "".join(parts)


def _log_cell(log_path) -> str:
    if not log_path:
        return f'<span style="color:{tokens.TEXT_DIM};">-</span>'
    try:
        href = Path(str(log_path)).as_uri()
    except ValueError:  # a relative path has no file URI; show its name without a link
        return f'<span style="color:{tokens.TEXT_DIM};">{escape(Path(str(log_path)).name)}</span>'
    return f'<a href="{escape(href, quote=True)}" style="color:{tokens.TEXT};">Open log</a>'


def table_html(jobs: list[dict]) -> str:
    """The recent jobs table: one row per job with its view_model testid, newest first as given."""
    body = []
    for job in jobs:
        title = escape(str(job.get("title") or job.get("kind") or "-"))
        error = job.get("error")
        error_line = (f'<div style="color:{tokens.ERROR};">{escape(str(error))}</div>' if error else "")
        body.append(
            f'<tr data-testid="{job["testid"]}">'
            f'<td style="{_TD}">{title}{error_line}</td>'
            f'<td style="{_TD}">{_result_cell(job)}</td>'
            f'<td style="{_TD}">{escape(timefmt.stamp(job.get("started_at")))}</td>'
            f'<td style="{_TD}">{escape(timefmt.stamp(job.get("ended_at")))}</td>'
            f'<td style="{_TD}">{_log_cell(job.get("log_path"))}</td>'
            "</tr>")
    return (f'<table style="{_TABLE}"><thead><tr>'
            f'<th style="{_TH}">Job</th><th style="{_TH}">Result</th>'
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
