"""Videos tab (DESIGN.md sections 8, 9, 11 and 12): one row per output folder grouped by stage, the sign-in card,
the clean-up plan and Danger mode's Restore clips.

Every row and notice comes from view_model.snapshot(source): folders from ["videos"]["folders"], the plan from
["videos"]["cleanup_plan"], the sign-in notices from ["notices"]. Each row carries its view_model testid. build()
takes an optional actions dict ("upload", "mark_live", "plan_cleanup", "apply_cleanup", "sign_in", "restore"); a
button calls its action when one is given and does nothing otherwise. While a job runs every action button is
disabled and the tab says which job it is. The real wiring comes in a later task, so this module imports neither
bridge nor jobs.
"""
from __future__ import annotations

from urllib.parse import urlsplit, urlunsplit

from nicegui import ui

from gui import tokens, view_model
from gui.components import plan_list
from gui.tabs import heading

PAINTS_ROWS = True

EMPTY_COPY = "No videos yet. Compile one on the Compile tab."
CLEANED_NOTE = "Cleaned up. Clips moved to the archive."
SIGN_IN_LABEL = "Sign in to YouTube again"
RESTORE_LABEL = "Restore clips"
DANGER_LABEL = "Danger mode"
OPEN_LABEL = "Open on YouTube"
UPLOAD_LABEL = "Upload to YouTube"
MARK_LIVE_LABEL = "Mark as live"
CLEAN_UP_LABEL = "Clean up"
QUAD_LABEL = "QUAD or better"
STAGE_ORDER = ("encoded", "uploaded", "live", "cleaned_partly")
_STAGE_RANK = {stage: rank for rank, stage in enumerate(STAGE_ORDER)}
RESTORABLE = ("live", "cleaned_partly")

_BODY = f"font-size:{tokens.SIZE_BODY}px;color:{tokens.TEXT_DIM};"
_UI = f"font-size:{tokens.SIZE_UI}px;"
_NUM = "font-variant-numeric:tabular-nums;"
_DIM = f"color:{tokens.TEXT_DIM};"
_ROW = f"padding:{tokens.SPACE_8}px 0;border-bottom:1px solid {tokens.LINE};"
_CARD = (f"gap:8px;width:100%;background:{tokens.PANEL};border:1px solid {tokens.LINE};"
         f"border-radius:{tokens.RADIUS_PANEL}px;padding:{tokens.SPACE_16}px;")
_FADED = "opacity:0.45;"


def _plural(count: int, word: str) -> str:
    return f"{count} {word}" if count == 1 else f"{count} {word}s"


def _https(url) -> str:
    """The link target: the stored URL with an https scheme added when it has none (urllib, so no literal URL)."""
    text = str(url or "").strip()
    parts = urlsplit(text)
    if parts.scheme or not text:
        return text
    _, netloc, path, query, fragment = urlsplit("//" + text)
    return urlunsplit(("https", netloc, path, query, fragment))


def _call(actions: dict, key: str, *args) -> None:
    action = actions.get(key)
    if action is not None:
        action(*args)


def _button(label: str, marker: str, handler, busy: bool):
    button = ui.button(label, on_click=handler).props("no-caps outline").classes("rvm-button").mark(marker)
    if busy:
        button.disable()
    return button.style(_FADED if busy else "")


def _open_link(folder: dict) -> None:
    if folder.get("video_url"):
        ui.link(OPEN_LABEL, _https(folder["video_url"]), new_tab=True).mark(f"open-{folder['slug']}") \
            .style(_UI + f"color:{tokens.TEXT};")


def _stage_actions(folder: dict, actions: dict, busy: bool) -> None:
    slug = folder["slug"]
    stage = folder["stage"]
    if stage == "encoded":
        _button(UPLOAD_LABEL, f"upload-{slug}", lambda: _call(actions, "upload", slug), busy)
    elif stage == "uploaded":
        _open_link(folder)
        _button(MARK_LIVE_LABEL, f"mark-live-{slug}", lambda: _call(actions, "mark_live", slug), busy)
    elif stage == "live":
        _open_link(folder)
        _button(CLEAN_UP_LABEL, f"clean-up-{slug}", lambda: _call(actions, "plan_cleanup", slug), busy)
    else:
        ui.label(CLEANED_NOTE).style(_UI + _DIM)


def _restore_controls(slot, folder: dict, actions: dict, busy: bool) -> None:
    """A text field and a Restore clips button that stays disabled until the field equals the folder slug."""
    slug = folder["slug"]
    with slot:
        field = ui.input(placeholder=slug).props("dark").mark(f"restore-input-{slug}") \
            .style("min-width:200px;")
        restore = ui.button(RESTORE_LABEL,
                            on_click=lambda: _restore_if_typed(field, slug, actions)) \
            .props("no-caps outline").classes("rvm-button").mark(f"restore-{slug}")

        def sync(_event=None) -> None:
            if busy or field.value != slug:
                restore.disable()
                restore.props("disable")
            else:
                restore.enable()
                restore.props(remove="disable")

        field.on_value_change(sync)
        sync()
        restore.style(_FADED if busy else "")


def _restore_if_typed(field, slug: str, actions: dict) -> None:
    if field.value == slug:
        _call(actions, "restore", slug)


def _set_restore(slot, folder: dict, actions: dict, busy: bool, on: bool) -> None:
    slot.clear()
    if on:
        _restore_controls(slot, folder, actions, busy)


def _folder_row(folder: dict, actions: dict, busy: bool, restore_slots: list) -> None:
    with ui.column().props(f"data-testid={folder['testid']}").style(_ROW + "gap:8px;width:100%;"):
        with ui.row().style("gap:16px;align-items:center;width:100%;flex-wrap:wrap;"):
            ui.label(str(folder.get("slug") or "")).style(_UI + "font-weight:600;")
            ui.label(str(folder.get("character") or "")).style(_UI + _DIM)
            ui.label(_plural(int(folder.get("clips") or 0), "clip")).style(_UI + _NUM)
            ui.label(f"{int(folder.get('quad_plus') or 0)} {QUAD_LABEL}").style(_UI + _NUM)
            _stage_actions(folder, actions, busy)
        if folder["stage"] in RESTORABLE:
            slot = ui.row().style("gap:16px;align-items:center;width:100%;flex-wrap:wrap;")
            restore_slots.append((slot, folder))


def build(source, actions=None) -> None:
    actions = actions or {}
    state = view_model.snapshot(source)
    videos = state["videos"]
    job = state["job"]
    busy = job is not None
    heading("Videos")
    if busy:
        ui.label(f'Busy: "{job.get("title") or "a job"}"').style(_UI + _DIM)
    for notice in state["notices"]:
        if notice.get("kind") == "auth_error":
            with ui.column().style(_CARD).mark("sign-in-card"):
                ui.label(str(notice.get("text") or "")).style(_UI + f"color:{tokens.TEXT};")
                _button(SIGN_IN_LABEL, "sign-in", lambda: _call(actions, "sign_in"), busy)

    folders = sorted(videos["folders"], key=lambda f: _STAGE_RANK.get(f["stage"], len(STAGE_ORDER)))
    plan = videos["cleanup_plan"]
    if not folders and plan is None:
        ui.label(EMPTY_COPY).style(_BODY)
        return

    restore_slots: list = []
    if folders:
        with ui.row().style("justify-content:flex-end;align-items:center;width:100%;"):
            danger = ui.switch(DANGER_LABEL, value=False).mark("danger-mode")
        for folder in folders:
            _folder_row(folder, actions, busy, restore_slots)

        def toggle(event) -> None:
            for slot, folder in restore_slots:
                _set_restore(slot, folder, actions, busy, bool(event.value))

        danger.on_value_change(toggle)

    if plan is not None:
        plan_list.build(plan, actions, busy)
