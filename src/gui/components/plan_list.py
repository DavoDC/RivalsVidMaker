"""Clean-up plan list (DESIGN.md sections 8, 9 and 12): every file in the plan grouped by its fate, with a count
and a summed size per group, then the "Also recycle the video" checkbox and the apply button.

build(plan, actions, busy) takes the snapshot "videos"."cleanup_plan" dict (nonce, slug, items, totals). Each item
row carries its view_model testid. The apply button calls actions["apply_cleanup"](nonce, recycle_video) and does
nothing when no handler is given. Nothing moves while the plan is shown: only the apply button changes files.
The apply button is never the default focus (no autofocus), and it is disabled when the plan archives and recycles nothing.
"""
from __future__ import annotations

from nicegui import ui

from gui import tokens

GB_MB = 1024  # sizes switch from MB to GB at one gigabyte
FATE_WORDS = {"remove": "Remove", "keep": "Keep", "archive": "Archive", "recycle_video": "Recycle video",
              "recycle": "Recycle", "remove_empty_folder": "Remove empty folder", "restore": "Restore",
              "recycle_folder": "Recycle folder"}
RECYCLE_LABEL = "Also recycle the video"
HEADING_PREFIX = "Clean up plan for"

_UI = f"font-size:{tokens.SIZE_UI}px;"
_NUM = "font-variant-numeric:tabular-nums;"
_DIM = f"color:{tokens.TEXT_DIM};"
_ROW = f"padding:{tokens.SPACE_8}px 0;border-bottom:1px solid {tokens.LINE};"
_FADED = "opacity:0.45;"


def size_text(mb) -> str:
    """Megabytes as whole KB under 1 MB, MB with one decimal, or GB with one decimal from one gigabyte up."""
    value = float(mb or 0)
    if round(value, 1) >= GB_MB:
        return f"{value / GB_MB:.1f} GB"
    kilobytes = round(value * 1024)
    if kilobytes < 1024:
        return f"{kilobytes} KB"
    return f"{value:.1f} MB"


def _plural(count: int, word: str) -> str:
    return f"{count} {word}" if count == 1 else f"{count} {word}s"


def totals_text(totals: dict) -> str:
    """The apply button text: "Archive 2 clips, recycle 1 file, 1.6 GB"; "Nothing to clean up" when both counts are 0."""
    archive = int(totals.get("archive_count") or 0)
    recycle = int(totals.get("recycle_count") or 0)
    if archive + recycle == 0:
        return "Nothing to clean up"
    parts = []
    if archive:
        parts.append(f"Archive {_plural(archive, 'clip')}")
    if recycle:
        parts.append(f"{'recycle' if archive else 'Recycle'} {_plural(recycle, 'file')}")
    parts.append(size_text(totals.get("move_mb")))
    return ", ".join(parts)


def groups(items: list[dict]) -> list[dict]:
    """Items grouped by fate, in the order each fate first appears, with the count and summed size per group."""
    order: list[str] = []
    by_fate: dict[str, dict] = {}
    for item in items:
        fate = str(item.get("fate") or "keep")
        if fate not in by_fate:
            by_fate[fate] = {"fate": fate, "count": 0, "size_mb": 0.0, "items": []}
            order.append(fate)
        group = by_fate[fate]
        group["count"] += 1
        group["size_mb"] += float(item.get("size_mb") or 0)
        group["items"].append(item)
    return [by_fate[fate] for fate in order]


def _fate_word(fate: str) -> str:
    return FATE_WORDS.get(fate, fate.capitalize())


def _call(actions: dict, key: str, *args) -> None:
    action = actions.get(key)
    if action is not None:
        action(*args)


def _item_row(item: dict) -> None:
    with ui.row().props(f"data-testid={item['testid']}").style(_ROW + "gap:16px;align-items:center;width:100%;"):
        ui.label(str(item.get("name") or "")).style(_UI + _NUM)
        ui.label(size_text(item.get("size_mb"))).style(_UI + _NUM + _DIM)


def build(plan: dict, actions=None, busy: bool = False) -> None:
    actions = actions or {}
    totals = plan.get("totals") or {}
    ui.label(f"{HEADING_PREFIX} {plan.get('slug') or 'this video'}").style(
        f"font-size:{tokens.SIZE_SECTION}px;font-weight:600;font-stretch:87.5%;margin-top:{tokens.SPACE_24}px;"
        f"margin-bottom:{tokens.SPACE_8}px;")
    for group in groups(plan.get("items") or []):
        with ui.column().style("gap:4px;width:100%;"):
            with ui.row().style("gap:16px;align-items:baseline;width:100%;flex-wrap:wrap;"):
                ui.label(_fate_word(group["fate"])).style(_UI + "font-weight:600;")
                ui.label(_plural(group["count"], "file")).style(_UI + _NUM + _DIM)
                ui.label(size_text(group["size_mb"])).style(_UI + _NUM + _DIM)
            for item in group["items"]:
                _item_row(item)

    nonce = plan.get("nonce")
    moves = int(totals.get("archive_count") or 0) + int(totals.get("recycle_count") or 0)
    with ui.row().style("align-items:center;justify-content:space-between;gap:16px;width:100%;flex-wrap:wrap;"):
        recycle = ui.checkbox(RECYCLE_LABEL, value=False).props("dense") \
            .style("padding-left:0;").mark("cleanup-recycle")
        apply = ui.button(totals_text(totals),
                          on_click=lambda: _call(actions, "apply_cleanup", nonce, bool(recycle.value))) \
            .props("no-caps outline").classes("rvm-button").mark("apply-cleanup")
        if busy or moves == 0:
            apply.disable()
        if busy:
            recycle.props("disable")
            recycle.style(_FADED)
        apply.style(_FADED if busy else "")
