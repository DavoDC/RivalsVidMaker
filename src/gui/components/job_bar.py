"""Job bar: the current job with its progress, ETA and a Stop button (spec sections 7 and 9).

render(job) takes the snapshot "job" dict (view_model._job). With no job it says so. Stop is rendered
only when the job is cancellable: an absent button, not a disabled one (spec section 7). Its
click calls on_stop, a no-op by default; the real cancel wiring comes with the job actions.
The bar fill is the one animated element on the page, and it only takes the working colour.
"""
from __future__ import annotations

import math
from collections.abc import Callable
from html import escape

from nicegui import ui

from gui import tokens


def progress_fraction(job: dict) -> float:
    total = job.get("total") or 0
    done = job.get("done") or 0
    if total <= 0:
        return 0.0
    return min(1.0, max(0.0, done / total))


def progress_text(job: dict) -> str:
    total = job.get("total")
    if not total:
        return ""
    unit = job.get("unit") or ""
    return f"{int(job.get('done') or 0)} of {int(total)} {unit}".rstrip()


def eta_text(job: dict) -> str:
    eta = job.get("eta_s")
    if eta is None:
        return "Estimating time left" if job.get("done") else "Starting"
    seconds = max(0, int(eta))
    if seconds < 60:
        return f"About {seconds} s left"
    return f"About {math.ceil(seconds / 60)} min left"


def phase_word(job: dict) -> str:
    phase = str(job.get("phase") or "").strip()
    return phase[:1].upper() + phase[1:]


def bar_html(job: dict) -> str:
    percent = round(progress_fraction(job) * 100)
    title = escape(str(job.get("title") or "Working"))
    word = phase_word(job)
    phase = (f'<span data-part="phase" style="color:{tokens.TEXT_DIM};margin-right:{tokens.SPACE_16}px;">'
             f'{escape(word)}</span>') if word else ""
    # Track spans the panel width up to 640 px; count and ETA are two elements with a 16 px gap (DESIGN 8).
    track = (f"width:100%;max-width:640px;height:{tokens.SPACE_8}px;background:{tokens.LINE};"
             f"border-radius:{tokens.RADIUS_CHIP}px;overflow:hidden;margin:{tokens.SPACE_8}px 0;")
    fill = (f"height:100%;width:{percent}%;background:{tokens.WORKING};")
    meta = (f'<div style="display:flex;gap:{tokens.SPACE_16}px;font-size:{tokens.SIZE_UI}px;'
            f'color:{tokens.TEXT_DIM};font-variant-numeric:tabular-nums;">'
            f'<span data-part="count">{escape(progress_text(job))}</span>'
            f'<span data-part="eta">{escape(eta_text(job))}</span></div>')
    return (
        f'<div style="font-size:{tokens.SIZE_BODY}px;color:{tokens.TEXT};">{phase}{title}</div>'
        f'<div role="progressbar" aria-label="{title}" aria-valuemin="0" aria-valuemax="100" '
        f'aria-valuenow="{percent}" style="{track}"><div style="{fill}"></div></div>'
        f'{meta}'
    )


def render(job: dict | None, on_stop: Callable[[], None] | None = None) -> None:
    """Paint the job bar into the current container."""
    if not job:
        ui.label("No job is running.").style(
            f"font-size:{tokens.SIZE_UI}px;color:{tokens.TEXT_DIM};")
        return

    def stop() -> None:
        if on_stop is not None:
            on_stop()

    with ui.row().props('data-testid=current-job role=group aria-label="Current job"').style(
            f"align-items:center;gap:{tokens.SPACE_16}px;width:100%;"):
        with ui.column().style("flex:1;gap:0;min-width:0;"):
            ui.html(bar_html(job)).style("width:100%;")
        if job.get("cancellable"):
            ui.button("Stop", on_click=stop).classes("rvm-button").mark("stop-current-job").props(
                'data-testid=stop-current-job')
