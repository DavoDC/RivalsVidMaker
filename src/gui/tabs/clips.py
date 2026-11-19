"""Clips tab: what came in, what is scanned, which clips need a decision (spec sections 3 and 9).

Every number and row comes from view_model.snapshot(source): the summary line, the character table, the
Highlights root list and the needs-a-decision panel. Each row carries its view_model testid. build() takes an
optional actions dict ("sort", "scan", "keep", "recycle"); a button calls its action when one is given and does
nothing otherwise. The real wiring comes in a later task, so this module imports neither bridge nor jobs.
"""
from __future__ import annotations

from html import escape

from nicegui import ui

from gui import avatars, timefmt, tokens, view_model
from gui.components import tier_chip
from gui.tabs import heading

PAINTS_ROWS = True

NO_NEW_COPY = "No new clips. Save highlights in game, then press Sort clips."
NO_CHARACTERS_COPY = "No characters yet. Scan for KOs to count the clips in each character folder."
SORT_TIP = "Moves new clips from your Highlights folder into a folder per character. Recent clips stay put so the game still lists them."
SCAN_TIP = "Reads each character folder to count its clips and flag low-value ones. Nothing is moved or deleted."
ROOT_NOTE = "Locked clips stay here because the game lists your newest clips as recent. The rest move on the next Sort."
COLUMN_TIPS = {
    "Character": "The character the clip file name says it is.",
    "Clips": "How many clip files are in this character's folder.",
    "Length": "Total running time of the scanned clips only. Clips not scanned yet are not counted.",
    "Scanned": "How many clips Scan for KOs has read, out of all clips in the folder.",
    "Best": "The best kill streak found in this character's scanned clips.",
    "Date": "The day the game saved the clip.",
    "Time": "The time of day the game saved the clip.",
    "Status": "Held: Sort leaves the clip here. Next sort: Sort moves it into its character folder.",
}
HELD_LABEL = "Held"
SORT_NEXT_LABEL = "Next sort"
UNREADABLE_NOTE = "Sort cannot read this name."
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


def _unreadable_sentence(count: int) -> str:
    return "1 has a name Sort cannot read." if count == 1 else f"{count} have a name Sort cannot read."


def summary_text(summary: dict) -> str:
    """The summary line: new and kept counts in one sentence, then unreadable and decision counts, zeros omitted."""
    new = int(summary.get("new_clips") or 0)
    kept = int(summary.get("protected") or 0)
    unreadable = int(summary.get("unrecognised") or 0)
    decide = int(summary.get("low_value_pending") or 0)
    lead = []
    if new:
        lead.append(f"{new} new in Highlights")
    if kept:
        lead.append(f"{kept} kept for the game's recent list")
    sentences = []
    if lead:
        sentences.append(", ".join(lead) + ".")
    if unreadable:
        sentences.append(_unreadable_sentence(unreadable))
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
        return ""
    return tier_chip.chip_html(tier)


DEFAULT_SORT = ("Length", True)  # same order as the Compile tab's closest list: most clip time first
_NUMERIC = ("Clips", "Length", "Scanned", "Best")
_sort = {"col": DEFAULT_SORT[0], "desc": DEFAULT_SORT[1]}  # shortcut: one local user, one table; per-client state if ever shared


def _seconds(row: dict) -> float:
    seconds = row.get("seconds")
    if isinstance(seconds, (int, float)) and not isinstance(seconds, bool):
        return float(seconds)
    return float(row.get("minutes") or 0) * 60


def _best_rank(row: dict) -> int:
    tier = _best(row.get("tiers") or {})
    return len(_BEST_ORDER) - _BEST_ORDER.index(tier) if tier else 0


def sort_rows(rows: list[dict], col: str, desc: bool) -> list[dict]:
    """Rows ordered by a column; ties fall back to the display name so the order never jumps between polls."""
    keys = {
        "Character": lambda r: avatars.display_name(str(r.get("name") or "")).lower(),
        "Clips": lambda r: int(r.get("clips") or 0),
        "Length": _seconds,
        "Scanned": lambda r: int(r.get("scanned") or 0),
        "Best": _best_rank,
    }
    key = keys.get(col, keys[DEFAULT_SORT[0]])
    by_name = sorted(rows, key=keys["Character"])
    return sorted(by_name, key=key, reverse=desc)


def next_sort(col: str) -> tuple[str, bool]:
    """A click on the active column flips its direction; a new column starts the natural way: numbers most first,
    names A to Z."""
    if col == _sort["col"]:
        return col, not _sort["desc"]
    return col, col in _NUMERIC


def _th(label: str, style: str, right: bool = False, sort: tuple[str, bool] | None = None) -> str:
    """A header cell whose hover box (styled in theme.py, .rvm-tip) explains the column. With sort it is also a
    button: click or Enter sorts by the column, and the active column shows an arrow and aria-sort."""
    cls = "rvm-tip rvm-tip-r" if right else "rvm-tip"
    extra, arrow = "", ""
    if sort is not None:
        cls += " rvm-sortable"
        active = sort[0] == label
        state = ("descending" if sort[1] else "ascending") if active else "none"
        fire = "this.dispatchEvent(new CustomEvent('rvm_sort',{detail:'" + label + "',bubbles:true}))"
        keys = "if(event.key==='Enter'||event.key===' '){event.preventDefault();" + fire + "}"
        extra = (f' role="columnheader" tabindex="0" aria-sort="{state}" onclick="{fire}" onkeydown="{keys}"')
        mark = ("▼" if sort[1] else "▲") if active else ""
        arrow = f'<span class="rvm-sort-mark" aria-hidden="true">{mark}</span>'
    return f'<th class="{cls}" data-tip="{escape(COLUMN_TIPS[label])}" style="{style}"{extra}>{label}{arrow}</th>'


def _partial_hint(clips: int, scanned: int) -> str:
    """Length counts scanned clips only, so a folder with unscanned clips says so beside the number."""
    if scanned >= clips:
        return ""
    return f'<div style="color:{tokens.TEXT_DIM};font-weight:400;">{clips - scanned} unscanned</div>'


def table_html(rows: list[dict], sort: tuple[str, bool] | None = None) -> str:
    """The character table: Character, Clips, Length, Scanned and Best; one row per character with its testid.
    Rows follow sort (column, descending), by default Length most first; headers are click targets."""
    sort = sort or DEFAULT_SORT
    body = []
    for row in sort_rows(rows, *sort):
        clips = int(row.get("clips") or 0)
        scanned = int(row.get("scanned") or 0)
        folder = str(row.get("name") or "")
        body.append(
            f'<tr data-testid="{row["testid"]}">'
            f'<td style="{_TD}">{avatars.name_cell_html(folder)}</td>'
            f'<td style="{_TD_NUM}">{clips}</td>'
            f'<td style="{_TD_NUM}">{_duration(row)}{_partial_hint(clips, scanned)}</td>'
            f'<td style="{_TD_NUM}">{scanned} of {clips}</td>'
            f'<td style="{_TD}">{_best_cell(row.get("tiers") or {})}</td>'
            "</tr>")
    return (f'<table style="{_TABLE}"><thead><tr>'
            + _th('Character', _TH, sort=sort)
            + _th('Clips', _TH_NUM, right=True, sort=sort)
            + _th('Length', _TH_NUM, right=True, sort=sort)
            + _th('Scanned', _TH_NUM, right=True, sort=sort)
            + _th('Best', _TH, sort=sort)
            + "</tr></thead><tbody>" + "".join(body) + "</tbody></table>")


_LOCK_SVG = ('<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" '
             'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
             '<rect x="5" y="11" width="14" height="10" rx="2"/><path d="M8 11V7a4 4 0 0 1 8 0v4"/></svg>')


def _status_cell(row: dict) -> str:
    """Held rows get a lock and the word Held; clips Sort will move say Next sort; unreadable names stay blank."""
    if row.get("protected"):
        return (f'<span style="display:inline-flex;align-items:center;gap:{tokens.SPACE_8}px;color:{tokens.TEXT};'
                f'font-weight:600;">{_LOCK_SVG}{HELD_LABEL}</span>')
    if row.get("character"):
        return f'<span style="color:{tokens.TEXT_DIM};">{SORT_NEXT_LABEL}</span>'
    return ""


def _root_html(rows: list[dict]) -> str:
    """The root list as a table: character (avatar and display name), capture date, capture time. The file name
    is hover text on each row. A row with no character shows its file name with the unreadable note and empty
    date and time cells. One dim kept line leads the table when any row is protected."""
    td = _TD + f"padding-right:{tokens.SPACE_32}px;"
    th = _TH + f"padding-right:{tokens.SPACE_32}px;"
    body = []
    for row in rows:
        name = escape(str(row.get("name") or ""))
        if row.get("character"):
            first = avatars.name_cell_html(str(row["character"]))
            date = escape(str(row.get("date") or ""))
            time = escape(str(row.get("time") or ""))
        else:
            first = f'<div>{name}</div><div style="color:{tokens.TEXT_DIM};">{UNREADABLE_NOTE}</div>'
            date = time = ""
        body.append(f'<tr data-testid="{row["testid"]}" title="{name}">'
                    f'<td style="{td}">{first}</td>'
                    f'<td style="{td}">{date}</td>'
                    f'<td style="{td}">{time}</td>'
                    f'<td style="{td}">{_status_cell(row)}</td>'
                    "</tr>")
    kept = (f'<div style="color:{tokens.TEXT_DIM};padding-bottom:{tokens.SPACE_8}px;">{ROOT_NOTE}</div>'
            if any(row.get("protected") for row in rows) else "")
    table = (f'<table style="{_TABLE.replace("width:100%", "width:auto")}"><thead><tr>'
             + _th('Character', th)
             + _th('Date', th)
             + _th('Time', th)
             + _th('Status', th)
             + "</tr></thead><tbody>" + "".join(body) + "</tbody></table>")
    return '<div style="width:100%;">' + kept + table + "</div>"


def _call(actions: dict, key: str, *args) -> None:
    action = actions.get(key)
    if action is not None:
        action(*args)


def _decision_row(row: dict, actions: dict, busy: bool) -> None:
    """Two lines: the character's name cell with the capture time (the file name is hover text), then the tier and
    the Keep and Recycle buttons in one row that does not wrap. A row with no character shows its file name."""
    tier = row.get("tier_or_none")
    faded = _FADED if busy else ""
    name = escape(str(row.get("name") or ""))
    if row.get("character"):
        when = " ".join(part for part in (row.get("date"), row.get("time")) if part)
        span = f'<span style="color:{tokens.TEXT_DIM};">{escape(when)}</span>' if row.get("date") else ""
        first = avatars.name_cell_html(str(row["character"])) + span
    else:
        first = f"<div>{name}</div>"
    with ui.column().props(f'data-testid={row["testid"]}').style(_ROW + "gap:4px;width:100%;"):
        ui.html(f'<div title="{name}" style="display:flex;align-items:center;gap:{tokens.SPACE_8}px;'
                f'flex-wrap:wrap;">{first}</div>').style(f"font-size:{tokens.SIZE_UI}px;font-weight:600;")
        with ui.row().style("gap:16px;align-items:center;width:100%;flex-wrap:nowrap;"):
            ui.label(str(tier) if tier else "No kill").style(f"font-size:{tokens.SIZE_UI}px;color:{tokens.TEXT};")
            keep = ui.button("Keep", on_click=lambda n=row.get("name"): _call(actions, "keep", n)) \
                .props("no-caps outline").classes("rvm-button").mark(f"keep-{row['testid']}")
            recycle = ui.button("Recycle", on_click=lambda n=row.get("name"): _call(actions, "recycle", n)) \
                .props("no-caps outline").classes("rvm-button").mark(f"recycle-{row['testid']}")
            for button in (keep, recycle):
                if busy:
                    button.props("disable")
                button.style(faded)


def _sortable_table(characters: list[dict]) -> None:
    """The character table in its own box; a header click re-sorts it in place without rebuilding the tab."""
    box = ui.column().style("width:100%;gap:0;")

    def draw() -> None:
        box.clear()
        with box:
            html = ui.html(table_html(characters, (_sort["col"], _sort["desc"]))).style("width:100%;")
            html.on("rvm_sort", on_sort, args=["detail"])

    def on_sort(event) -> None:
        col = event.args.get("detail") if isinstance(event.args, dict) else event.args
        if col in _NUMERIC or col == "Character":
            _sort["col"], _sort["desc"] = next_sort(col)
            draw()

    draw()


def build(source, actions=None) -> None:
    actions = actions or {}
    state = view_model.snapshot(source)
    clips_state = state["clips"]
    job = state["job"]
    busy = job is not None
    with ui.row().style("justify-content:space-between;align-items:center;width:100%;gap:16px;flex-wrap:wrap;"):
        heading("Clips")
        with ui.row().style("align-items:center;justify-content:flex-end;gap:8px;flex-wrap:wrap;"):
            sort = ui.button("Sort clips", on_click=lambda: _call(actions, "sort")).props("no-caps outline")
            scan = ui.button("Scan for KOs", on_click=lambda: _call(actions, "scan")).props("no-caps outline")
            for button, marker, tip in ((sort, "sort-clips", SORT_TIP), (scan, "scan-kos", SCAN_TIP)):
                button.tooltip(tip)
                button.mark(marker).classes("rvm-button").style(_FADED if busy else "")
                if busy:
                    button.props("disable")
    with ui.column().style("gap:4px;"):
        ui.label(summary_text(state["summary"])).style(_BODY)
        if busy:
            ui.label(f'Busy: "{job.get("title") or "a job"}"').style(
                f"font-size:{tokens.SIZE_UI}px;color:{tokens.TEXT_DIM};")
    with ui.element("div").classes("rvm-clips").style(_LAYOUT_ROW):
        with ui.column().classes("rvm-clips-main").style(_LAYOUT_MAIN + "gap:8px;"):
            characters = clips_state["characters"]
            if characters:
                _sortable_table(characters)
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
