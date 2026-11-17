"""Compile tab (DESIGN.md sections 7, 8, 9, 10, 11): the pickers, the plan for the next video, and its reel strip.

Every number and row comes from view_model.snapshot(source): the ready characters, the plan's batches with their
clips, and the possible duplicates. Each row carries its view_model testid. build() takes an optional actions dict
("plan", "compile", "keep", "recycle", "keep_both", "drop_one"); a button calls its action when one is given and
does nothing otherwise. The real wiring comes in a later task, so this module imports neither bridge nor jobs.
"""
from __future__ import annotations

from html import escape

from nicegui import ui

from gui import avatars, timefmt, tokens, view_model
from gui.components import reel, tier_chip
from gui.tabs import heading

PAINTS_ROWS = True

READY_MINUTES = 10      # a character is ready with one batch of this much clip time (config min_batch_seconds)
DEFAULT_MINUTES = 15    # the default video length, about fifteen minutes (DESIGN.md section 7)
LENGTH_MINUTES = (10, 15, 20)
NOTHING_TO_CHOOSE = "Pick a character, then press Plan video."
NO_CHARACTER_COPY = (f"Compile needs {READY_MINUTES} minutes of clips for one character. "
                     "Scan for KOs on the Clips tab to count them.")
DUPLICATE_HEADING = "Possible duplicates"
REENCODE_LABEL = "Re-encode even if it exists"
UPLOAD_LABEL = "Upload after compiling"

_BODY = f"font-size:{tokens.SIZE_BODY}px;color:{tokens.TEXT_DIM};"
_UI = f"font-size:{tokens.SIZE_UI}px;"
_ROW = f"padding:{tokens.SPACE_8}px 0;border-bottom:1px solid {tokens.LINE};"
_FADED = "opacity:0.45;"
_NUM = "font-variant-numeric:tabular-nums;"


def _plural(count: int, word: str) -> str:
    return f"{count} {word}" if count == 1 else f"{count} {word}s"


def _ready_names(state: dict) -> list[str]:
    return [c["name"] for c in state["clips"]["characters"] if c.get("ready")]


def closest(state: dict, n: int = 3) -> list[tuple[str, int]]:
    """The n characters not ready yet with the most clip seconds, most first, as (folder, seconds)."""
    rows = [c for c in state["clips"]["characters"] if not c.get("ready")]
    rows.sort(key=lambda c: int(c.get("seconds") or 0), reverse=True)
    return [(c["name"], int(c.get("seconds") or 0)) for c in rows[:n]]


def _closest_row(folder: str, seconds: int) -> None:
    """One near-ready character: its avatar and name, then its progress as M:SS of the ready length."""
    tid = view_model.testid("compile-closest", folder)
    with ui.row().props(f"data-testid={tid}").style(_ROW + "gap:16px;align-items:center;width:100%;flex-wrap:wrap;"):
        ui.html(avatars.name_cell_html(folder))
        ui.label(f"{timefmt.duration(seconds)} of {READY_MINUTES}:00").style(_UI + _NUM + f"color:{tokens.TEXT_DIM};")


def _default_character(ready: list[str], plan: dict | None) -> str:
    if plan and plan.get("character") in ready:
        return plan["character"]
    return ready[0]


def _decisions(plan: dict) -> dict:
    """Every planned clip's decision, keyed by clip name: the dict the compile action receives."""
    return {clip["name"]: clip.get("decision") or "keep"
            for batch in plan.get("batches") or [] for clip in batch.get("clips") or []}


def _match_text(score) -> str:
    return f"Match {round(float(score or 0) * 100)}%"


def _call(actions: dict, key: str, *args) -> None:
    action = actions.get(key)
    if action is not None:
        action(*args)


_OUTLINED = "no-caps outline"
_FILLED = "no-caps unelevated"


def _button(label: str, marker: str, handler, busy: bool, props: str = _OUTLINED):
    button = ui.button(label, on_click=handler).props(props).classes("rvm-button").mark(marker)
    if busy:
        button.props("disable")
    return button.style(_FADED if busy else "")


def _choice_button(label: str, marker: str, handler, busy: bool, chosen: bool):
    """A Keep or Recycle button: the chosen one is filled and pressed, the other outlined and not pressed."""
    props = f'{_FILLED if chosen else _OUTLINED} aria-pressed="{str(chosen).lower()}"'
    return _button(label, marker, handler, busy, props)


def _clip_row(clip: dict, actions: dict, busy: bool) -> None:
    """One planned clip: name, start, length and tier word; Keep and Recycle (low-value clips) show the decision."""
    tier = clip.get("tier")
    name = str(clip.get("name") or "")
    decision = str(clip.get("decision") or "keep")
    with ui.row().props(f'data-testid={clip["testid"]}').style(
            _ROW + "gap:16px;align-items:center;width:100%;flex-wrap:wrap;"):
        ui.label(name).style(_UI + "font-weight:600;" + _NUM)
        ui.label(f"Starts {timefmt.duration(clip.get('start_s'))}").style(_UI + _NUM + f"color:{tokens.TEXT_DIM};")
        ui.label(f"Length {timefmt.duration(clip.get('duration_s'))}").style(_UI + _NUM + f"color:{tokens.TEXT_DIM};")
        ui.label(str(tier) if tier else "No kill").style(_UI + f"color:{tokens.TEXT};")
        if tier in tier_chip.FILL:
            ui.label(decision.capitalize()).style(_UI + f"color:{tokens.TEXT_DIM};")
        else:
            _choice_button("Keep", f"keep-{clip['testid']}", lambda n=name: _call(actions, "keep", n),
                           busy, decision != "recycle")
            _choice_button("Recycle", f"recycle-{clip['testid']}", lambda n=name: _call(actions, "recycle", n),
                           busy, decision == "recycle")


def _duplicate_row(dup: dict, actions: dict, busy: bool) -> None:
    a = str(dup.get("a") or "")
    b = str(dup.get("b") or "")
    tid = view_model.testid("plan-dup", f"{a}|{b}")
    with ui.row().props(f"data-testid={tid}").style(_ROW + "gap:16px;align-items:center;width:100%;flex-wrap:wrap;"):
        ui.label(a).style(_UI + _NUM + "font-weight:600;")
        ui.label(b).style(_UI + _NUM)
        ui.label(_match_text(dup.get("score"))).style(_UI + _NUM + f"color:{tokens.TEXT_DIM};")
        _button("Keep both", f"keep-both-{tid}", lambda: _call(actions, "keep_both", a, b), busy)
        _button("Drop one", f"drop-one-{tid}", lambda: _call(actions, "drop_one", a, b), busy)


def build(source, actions=None) -> None:
    actions = actions or {}
    state = view_model.snapshot(source)
    plan = state["compile"]["plan"]
    job = state["job"]
    busy = job is not None
    heading("Compile")
    if busy:
        ui.label(f'Busy: "{job.get("title") or "a job"}"').style(_UI + f"color:{tokens.TEXT_DIM};")
    ready = _ready_names(state)
    if not ready:
        ui.label(NO_CHARACTER_COPY).style(_BODY)
        for folder, seconds in closest(state):
            _closest_row(folder, seconds)
        return

    with ui.row().style("align-items:flex-end;gap:16px;width:100%;flex-wrap:wrap;"):
        character = ui.select(options=ready, value=_default_character(ready, plan), label="Character") \
            .props("dark").mark("compile-character").style("min-width:200px;")
        length = ui.select(options={m * 60: f"{m} minutes" for m in LENGTH_MINUTES},
                           value=DEFAULT_MINUTES * 60, label="Length") \
            .props("dark").mark("compile-length").style("min-width:160px;")
        reencode = ui.checkbox(REENCODE_LABEL, value=False).mark("compile-reencode")
        if busy:
            for picker in (character, length, reencode):
                picker.props("disable").style(_FADED)
        _button("Plan video", "plan-video",
                lambda: _call(actions, "plan", character.value, int(length.value), bool(reencode.value)),
                busy)

    if plan is None:
        ui.label(NOTHING_TO_CHOOSE).style(_BODY)
        return

    batches = plan.get("batches") or []
    clip_count = sum(len(batch.get("clips") or []) for batch in batches)
    with ui.row().style("justify-content:space-between;align-items:center;width:100%;gap:16px;flex-wrap:wrap;"):
        ui.label(f"Plan for {plan.get('character') or 'no character'}: {_plural(len(batches), 'video')}, "
                 f"{_plural(clip_count, 'clip')}.").style(_BODY)
        with ui.row().style("align-items:center;gap:16px;flex-wrap:wrap;"):
            upload = ui.checkbox(UPLOAD_LABEL, value=True).mark("compile-upload")
            if busy:
                upload.props("disable").style(_FADED)
            _button("Compile video", "compile-video",
                    lambda: _call(actions, "compile", plan.get("nonce"), _decisions(plan), bool(upload.value)), busy)

    reel.motion()
    for batch in batches:
        reel.render_bar(batch)
        for clip in batch.get("clips") or []:
            _clip_row(clip, actions, busy)

    duplicates = plan.get("duplicates") or []
    if duplicates:
        ui.label(DUPLICATE_HEADING).style(
            f"font-size:{tokens.SIZE_SECTION}px;font-weight:600;font-stretch:87.5%;margin-top:{tokens.SPACE_24}px;")
        for dup in duplicates:
            _duplicate_row(dup, actions, busy)
