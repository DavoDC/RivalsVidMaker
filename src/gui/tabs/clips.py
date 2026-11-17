"""Clips tab: what came in, what is scanned, which clips need a decision (spec sections 3 and 9).

Every number and row comes from view_model.snapshot(source): the summary line, the character table, the
Highlights root list and the needs-a-decision panel. Each row carries its view_model testid. build() takes an
optional actions dict ("sort", "scan", "keep", "recycle"); a button calls its action when one is given and does
nothing otherwise. The real wiring comes in a later task, so this module imports neither bridge nor jobs.
"""
from __future__ import annotations

from html import escape

from nicegui import ui

from gui import timefmt, tokens, view_model
from gui.components import tier_chip
from gui.tabs import heading

PAINTS_ROWS = True

NO_NEW_COPY = "No new clips. Save highlights in game, then press Sort clips."
NO_CHARACTERS_COPY = "No characters yet. Scan for KOs to count the clips in each character folder."
ROOT_NOTE = "kept: in the game's recent list"
DECISION_HEADING = "Needs a decision"
ROOT_HEADING = "In Highlights root"

_BEST_ORDER = ("HEXA", "PENTA", "QUAD")
_BODY = f"font-size:{tokens.SIZE_BODY}px;color:{tokens.TEXT_DIM};"
_TABLE = (f"width:100%;border-collapse:collapse;font-size:{tokens.SIZE_UI}px;"
          f"font-variant-numeric:tabular-nums;")
_TH = (f"text-align:left;color:{tokens.TEXT_DIM};font-weight:600;padding:{tokens.SPACE_8}px 0;"
       f"border-bottom:1px solid {tokens.LINE};")
_TH_NUM = (f"text-align:right;color:{tokens.TEXT_DIM};font-weight:600;padding:{tokens.SPACE_8}px 12px;"
           f"border-bottom:1px solid {tokens.LINE};")
_TD = f"padding:{tokens.SPACE_8}px 0;border-bottom:1px solid {tokens.LINE};"
_TD_NUM = f"padding:{tokens.SPACE_8}px 12px;text-align:right;font-weight:400;border-bottom:1px solid {tokens.LINE};"
_ROW = f"padding:{tokens.SPACE_8}px 0;border-bottom:1px solid {tokens.LINE};"
# Inline, not a <style> tag in ui.html: NiceGUI never applied that tag, so the panel stacked at 1440.
# Side by side when the column fits 640 + 24 + 320 px (1440 yes, 1024 no), stacked below that (flex wrap, no JS).
_LAYOUT_ROW = "display:flex;flex-wrap:wrap;gap:24px;align-items:flex-start;width:100%;"
_LAYOUT_MAIN = "flex:2 1 640px;min-width:0;"
_LAYOUT_PANEL = "flex:1 1 320px;min-width:320px;"
_FADED = "opacity:0.45;"


def _decision_sentence(count: int) -> str:
    return "1 clip needs a decision." if count == 1 else f"{count} clips need a decision."


def summary_text(summary: dict) -> str:
    """The summary line: new and kept counts in one sentence, the decision count after it, zeros omitted."""
    new = int(summary.get("new_clips") or 0)
    kept = int(summary.get("protected") or 0)
    decide = int(summary.get("low_value_pending") or 0)
    lead = []
    if new:
        lead.append(f"{new} new in Highlights")
    if kept:
        lead.append(f"{kept} kept for the game's recent list")
    sentences = []
    if lead:
        sentences.append(", ".join(lead) + ".")
    if decide:
        sentences.append(_decision_sentence(decide))
    return " ".join(sentences) if sentences else NO_NEW_COPY


def _duration(row: dict) -> str:
    """Clip time as m:ss, or h:mm:ss past an hour (DESIGN 12). Exact seconds when the row has them, else minutes."""
    seconds = row.get("seconds")
    if isinstance(seconds, (int, float)) and not isinstance(seconds, bool):
        return timefmt.duration(round(seconds))
    return timefmt.duration(round(float(row.get("minutes") or 0) * 60))


def _best(tiers: dict) -> str | None:
    for tier in _BEST_ORDER:
        if tiers.get(tier):
            return tier
    return None


def _best_cell(tiers: dict) -> str:
    tier = _best(tiers)
    if tier is None:
        return f'<span style="color:{tokens.TEXT_DIM};">None</span>'
    return tier_chip.chip_html(tier)


def table_html(rows: list[dict]) -> str:
    """The character table: Character, Clips, Minutes, Scanned and Best; one row per character with its testid."""
    body = []
    for row in rows:
        clips = int(row.get("clips") or 0)
        scanned = int(row.get("scanned") or 0)
        body.append(
            f'<tr data-testid="{row["testid"]}">'
            f'<td style="{_TD}">{escape(str(row.get("name") or ""))}</td>'
            f'<td style="{_TD_NUM}">{clips}</td>'
            f'<td style="{_TD_NUM}">{_duration(row)}</td>'
            f'<td style="{_TD_NUM}">{scanned} of {clips}</td>'
            f'<td style="{_TD}">{_best_cell(row.get("tiers") or {})}</td>'
            "</tr>")
    return (f'<table style="{_TABLE}"><thead><tr>'
            f'<th style="{_TH}">Character</th>'
            f'<th style="{_TH_NUM}">Clips</th>'
            f'<th style="{_TH_NUM}">Minutes</th>'
            f'<th style="{_TH_NUM}">Scanned</th>'
            f'<th style="{_TH}">Best</th>'
            "</tr></thead><tbody>" + "".join(body) + "</tbody></table>")


def _root_html(rows: list[dict]) -> str:
    items = []
    for row in rows:
        note = (f'<div style="color:{tokens.TEXT_DIM};">{ROOT_NOTE}</div>' if row.get("protected") else "")
        items.append(f'<div data-testid="{row["testid"]}" style="{_ROW}">'
                     f'<div>"{escape(str(row.get("name") or ""))}"</div>{note}</div>')
    return '<div style="width:100%;">' + "".join(items) + "</div>"


def _call(actions: dict, key: str, *args) -> None:
    action = actions.get(key)
    if action is not None:
        action(*args)


def _decision_row(row: dict, actions: dict, busy: bool) -> None:
    """Two lines: the quoted name, then character, tier and the Keep and Recycle buttons in one row."""
    tier = row.get("tier_or_none")
    faded = _FADED if busy else ""
    with ui.column().props(f'data-testid={row["testid"]}').style(_ROW + "gap:4px;width:100%;"):
        ui.label(f'"{row.get("name") or ""}"').style(f"font-size:{tokens.SIZE_UI}px;font-weight:600;")
        with ui.row().style("gap:16px;align-items:center;width:100%;flex-wrap:wrap;"):
            ui.label(str(row.get("character") or "")).style(_BODY)
            ui.label(str(tier) if tier else "No kill").style(f"font-size:{tokens.SIZE_UI}px;color:{tokens.TEXT};")
            keep = ui.button("Keep", on_click=lambda n=row.get("name"): _call(actions, "keep", n)) \
                .props("no-caps outline").classes("rvm-button").mark(f"keep-{row['testid']}")
            recycle = ui.button("Recycle", on_click=lambda n=row.get("name"): _call(actions, "recycle", n)) \
                .props("no-caps outline").classes("rvm-button").mark(f"recycle-{row['testid']}")
            for button in (keep, recycle):
                if busy:
                    button.props("disable")
                button.style(faded)


def build(source, actions=None) -> None:
    actions = actions or {}
    state = view_model.snapshot(source)
    clips_state = state["clips"]
    job = state["job"]
    heading("Clips")
    busy = job is not None
    with ui.row().style("justify-content:space-between;align-items:flex-start;width:100%;gap:16px;flex-wrap:wrap;"):
        with ui.column().style("gap:4px;"):
            ui.label(summary_text(state["summary"])).style(_BODY)
            if busy:
                ui.label(f'Busy: "{job.get("title") or "a job"}"').style(
                    f"font-size:{tokens.SIZE_UI}px;color:{tokens.TEXT_DIM};")
        with ui.row().style("align-items:center;justify-content:flex-end;gap:8px;flex-wrap:wrap;"):
            sort = ui.button("Sort clips", on_click=lambda: _call(actions, "sort")).props("no-caps outline")
            scan = ui.button("Scan for KOs", on_click=lambda: _call(actions, "scan")).props("no-caps outline")
            for button, marker in ((sort, "sort-clips"), (scan, "scan-kos")):
                button.mark(marker).classes("rvm-button").style(_FADED if busy else "")
                if busy:
                    button.props("disable")
    with ui.element("div").classes("rvm-clips").style(_LAYOUT_ROW):
        with ui.column().classes("rvm-clips-main").style(_LAYOUT_MAIN + "gap:8px;"):
            characters = clips_state["characters"]
            if characters:
                ui.html(table_html(characters)).style("width:100%;")
            else:
                ui.label(NO_CHARACTERS_COPY).style(_BODY)
            roots = clips_state["unsorted"]
            if roots:
                ui.label(ROOT_HEADING).style(
                    f"font-size:{tokens.SIZE_SECTION}px;font-weight:600;font-stretch:87.5%;margin-top:{tokens.SPACE_24}px;")
                ui.html(_root_html(roots)).style("width:100%;")
        decisions = clips_state["low_value"]
        if decisions:
            with ui.column().classes("rvm-clips-panel").style(
                    _LAYOUT_PANEL + f"gap:8px;border:1px solid {tokens.LINE};border-radius:{tokens.RADIUS_PANEL}px;"
                    f"padding:{tokens.SPACE_16}px;"):
                ui.label(DECISION_HEADING).style(
                    f"font-size:{tokens.SIZE_SECTION}px;font-weight:600;font-stretch:87.5%;")
                for row in decisions:
                    _decision_row(row, actions, busy)
