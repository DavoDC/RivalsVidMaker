"""Reel strip (DESIGN.md section 7): one bar per planned video, cut into segments sized by clip length.

QUAD, PENTA and HEXA segments are lit in their tier colour and carry the timestamp they get in the description,
set under them as m:ss. Every other segment is quiet slate. The lit segments light left to right once, about
600 ms in all; reduced motion removes the animation so they show lit at once. Keyframes go through ui.add_css
(a <style> tag inside ui.html is never applied by NiceGUI). Colours come from tokens.py and tier_chip.FILL.
"""
from __future__ import annotations

from html import escape

from nicegui import ui

from gui import timefmt, tokens, view_model
from gui.components import tier_chip

LIGHT_MS = 200   # one lit segment takes this long to light
SWEEP_MS = 400   # lit segments start across this span, left to right; LIGHT_MS + SWEEP_MS is the motion total
BAR_HEIGHT = 28
STAMP_HEIGHT = 20

MOTION_CSS = (
    "@keyframes rvm-reel-light{from{opacity:0.15;}to{opacity:1;}}"
    f".rvm-reel-lit{{animation:rvm-reel-light {LIGHT_MS}ms ease-out both;}}"
    "@media (prefers-reduced-motion: reduce){.rvm-reel-lit{animation:none !important;}}"
)

_QUIET = tokens.LINE
_STAMP = (f"position:absolute;top:0;font-size:{tokens.SIZE_UI}px;font-weight:600;font-stretch:87.5%;"
          f"font-variant-numeric:tabular-nums;color:{tokens.TEXT};white-space:nowrap;")


def segment_percentages(durations) -> list[float]:
    """Each duration as a percentage of the total, so the list sums to 100 (all zero when nothing has length)."""
    values = [max(0.0, float(d or 0)) for d in durations]
    total = sum(values)
    if total <= 0:
        return [0.0 for _ in values]
    return [v * 100.0 / total for v in values]


def bar_html(batch: dict) -> str:
    """One bar as an HTML fragment: the segments, then the timestamp row under the lit ones.

    Segment widths are percentages of the clip total, so the bar fills its column at any width. Each segment
    carries a reel-seg testid for its clip (the plan row keeps the plan-clip testid); lit segments also carry rvm-reel-lit and the sweep delay.
    """
    clips = batch.get("clips") or []
    pcts = segment_percentages([c.get("duration_s") or 0 for c in clips])
    segments, stamps = [], []
    left = 0.0
    for clip, pct in zip(clips, pcts):
        tier = clip.get("tier")
        stamp = timefmt.duration(clip.get("start_s"))
        testid = view_model.testid("reel-seg", clip.get("name"))
        delay = round(left / 100.0 * SWEEP_MS)
        if tier in tier_chip.FILL:
            background = tier_chip.FILL[tier]
            klass = "rvm-reel-seg rvm-reel-lit"
            timing = f"animation-delay:{delay}ms;"
            # past 90% a left offset would push the text out of the bar, so it hangs from the right edge
            place = "right:0;" if left > 90.0 else f"left:{left:.4f}%;"
            stamps.append(f'<span style="{_STAMP}{place}">{stamp}</span>')
        else:
            background = _QUIET
            klass = "rvm-reel-seg"
            timing = ""
        segments.append(
            f'<div class="{klass}" data-testid="{testid}" data-tier="{escape(str(tier or ""))}" '
            f'data-start="{left:.4f}" title="{escape(str(tier or "No kill"))} at {stamp}" '
            f'style="flex:none;width:{pct:.4f}%;height:{BAR_HEIGHT}px;box-sizing:border-box;'
            f'background:{background};border-right:2px solid {tokens.GROUND};'
            f'border-radius:{tokens.RADIUS_CHIP}px;{timing}"></div>')
        left += pct
    bar_testid = view_model.testid("reel-bar", f"batch-{batch.get('number')}")
    return (f'<div style="width:100%;">'
            f'<div class="rvm-reel-bar" data-testid="{bar_testid}" '
            f'style="display:flex;width:100%;height:{BAR_HEIGHT}px;">' + "".join(segments) + "</div>"
            f'<div style="position:relative;width:100%;height:{STAMP_HEIGHT}px;">' + "".join(stamps) + "</div>"
            "</div>")


def motion() -> None:
    """Add the reveal keyframes and the reduced-motion block once for the page being built."""
    ui.add_css(MOTION_CSS)


def render_bar(batch: dict, total=None) -> None:
    """Paint one planned video: its number, its total length at 40 px, then the bar.

    total, when given, is the length shown (the compile tab passes the kept clips' sum); otherwise the batch's."""
    if total is None:
        total = batch.get("duration_s")
    if total is None:
        total = sum(float(c.get("duration_s") or 0) for c in batch.get("clips") or [])
    with ui.row().style("align-items:baseline;gap:16px;width:100%;flex-wrap:wrap;"):
        ui.label(f"Video {int(batch.get('number') or 0)}").style(
            f"font-size:{tokens.SIZE_SECTION}px;font-weight:600;font-stretch:87.5%;")
        ui.label(timefmt.duration(total)).style(
            f"font-size:{tokens.SIZE_REEL}px;font-weight:600;font-stretch:87.5%;"
            "font-variant-numeric:tabular-nums;")
    ui.html(bar_html(batch)).style("width:100%;")
