"""Tab actions: each key on a tab calls one bridge function and shows the result as a toast.

Actions(runner, config) is the real wiring. A key calls bridge.* and, on success, shows a positive
toast and goes back to its tab. A refused, busy or failed action shows its text as a negative toast
and changes nothing. A plan made on the compile or videos tab is held here under the nonce the
bridge issued; held_plans() returns it so WiredSource can add it to the snapshot.

FixtureActions is the stand-in for a --fixture run: every key toasts that nothing is written.
This module must not import the engine (tests/gui/test_gui_seam.py), so the cleanup fates are
named by their string values, which cleanup.py defines.
"""
from __future__ import annotations

import copy
import functools

from nicegui import ui

from gui import bridge, jobs

TAB_ACTIONS = {
    "clips": ("sort", "scan", "keep", "recycle"),
    "compile": ("plan", "compile", "keep", "recycle", "keep_both", "drop_one"),
    "videos": ("upload", "mark_live", "plan_cleanup", "apply_cleanup", "sign_in", "restore"),
}
STALE = "This plan is no longer valid. Make the plan again."
NO_PLAN = "No plan is held. Make a plan first."
FIXTURE_TEXT = "Fixture: nothing is written."
# cleanup.py FATE_RECYCLE, FATE_RECYCLE_VIDEO, FATE_RECYCLE_FOLDER, by value
REMOVING_FATES = ("recycle", "recycle_video", "recycle_folder")
KEEP_FATE = "keep"
MB = 1024 * 1024


def _toast(text: str, kind: str = "positive") -> None:
    ui.notify(text, type=kind)


def _go(path: str) -> None:
    ui.navigate.to(path)


def _guarded(fn):
    """Run one action. A Busy, Refused, FolderNotConfirmed or engine error becomes a negative toast."""
    @functools.wraps(fn)
    def run(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except jobs.Busy as e:
            _toast(f"{e.running_title} is still running. Wait for it to finish, then try again.", "negative")
        except Exception as e:
            _toast(str(e) or "Something went wrong.", "negative")
    return run


def _size(path) -> int:
    try:
        return path.stat().st_size
    except OSError:
        return 0


def _held_compile(token: str, plan, reencode: bool) -> dict:
    """The compile plan as view_model._compile reads it, with every clip's decision set to keep."""
    return {
        "nonce": token,
        "character": plan.character,
        "target_s": float(plan.target_s),
        "reencode": reencode,
        "batches": [{"number": b.number, "duration_s": b.duration_s,
                     "clips": [{"name": c.name, "start_s": c.start_s, "duration_s": c.duration_s,
                                "tier": c.tier, "decision": "keep"} for c in b.clips]}
                    for b in plan.batches],
        "duplicates": [{"a": d.a, "b": d.b, "score": d.score} for d in plan.duplicates],
    }


def _clips_by_name(held: dict) -> dict:
    return {c["name"]: c for b in held["batches"] for c in b["clips"]}


def _decisions(held: dict) -> dict:
    return {name: c["decision"] for name, c in _clips_by_name(held).items()}


def _held_cleanup(token: str, plan, slug: str) -> dict:
    """The cleanup plan as view_model._cleanup reads it. Skipped files are listed as keep."""
    items = [{"name": a.path.name, "fate": a.fate, "bytes": _size(a.path)} for a in plan.actions]
    items += [{"name": name, "fate": KEEP_FATE, "bytes": 0} for name in plan.skipped]
    removing = [i for i in items if i["fate"] in REMOVING_FATES]
    for i in items:
        i["size_mb"] = round(i.pop("bytes") / MB, 2)
    return {
        "nonce": token,
        "slug": slug,
        "include_video": plan.include_video,
        "items": items,
        "totals": {"remove_count": len(removing),
                   "remove_mb": round(sum(i["size_mb"] for i in removing), 2)},
    }


class Actions:
    """The real tab actions. bridge.* does the work; this class shows the result and holds the plans."""

    def __init__(self, runner, config):
        self.runner = runner
        self.config = config
        self._held: dict = {}

    def held_plans(self) -> dict:
        return copy.deepcopy(self._held)

    def for_tab(self, tab: str) -> dict:
        table = {
            "clips": {"sort": self._sort, "scan": self._scan,
                      "keep": self._clip_keep, "recycle": self._clip_recycle},
            "compile": {"plan": self._plan, "compile": self._compile, "keep": self._keep,
                        "recycle": self._recycle, "keep_both": self._keep_both, "drop_one": self._drop_one},
            "videos": {"upload": self._upload, "mark_live": self._mark_live,
                       "plan_cleanup": self._plan_cleanup, "apply_cleanup": self._apply_cleanup,
                       "sign_in": self._sign_in, "restore": self._restore},
        }
        return {name: _guarded(fn) for name, fn in table[tab].items()}

    # clips tab

    def _sort(self) -> None:
        bridge.sort(self.runner, self.config)
        _toast("Sorting clips.")
        _go("/tab/clips")

    def _scan(self) -> None:
        bridge.scan(self.runner, self.config)
        _toast("Scanning for KOs.")
        _go("/tab/clips")

    def _clip_keep(self, name: str) -> None:
        _toast(f'Kept "{name}".')

    def _clip_recycle(self, name: str) -> None:
        matches = [p for p in self.config.clips_path.rglob("*") if p.is_file() and p.name == name]
        if not matches:
            _toast(f'No clip named "{name}" in the clips folder.', "negative")
            return
        if len(matches) > 1:
            _toast(f'"{name}" matches more than one file in the clips folder, so nothing was recycled.',
                   "negative")
            return
        bridge.recycle_clip(self.runner, self.config, matches[0])
        _toast(f'Recycling "{name}".')
        _go("/tab/clips")

    # compile tab

    def _plan(self, character: str, length_s, reencode) -> None:
        token, plan = bridge.plan_compile(self.config, character, float(length_s))
        self._held["compile_plan"] = _held_compile(token, plan, bool(reencode))
        _toast(f"Planned video for {character}.")
        _go("/tab/compile")

    def _compile(self, nonce: str, decisions: dict) -> None:
        held = self._held.get("compile_plan")
        if held is None or held["nonce"] != nonce:
            raise bridge.Refused(STALE)
        # The held decisions are the source of truth: the page shows them, so they win over the page's values.
        merged = dict(decisions or {})
        merged.update(_decisions(held))
        bridge.compile(self.runner, self.config, nonce, clips=merged, extra=0, force=held["reencode"])
        self._held.pop("compile_plan", None)
        _toast("Compiling video.")
        _go("/tab/compile")

    def _decide(self, changes: dict) -> None:
        held = self._held.get("compile_plan")
        if held is None:
            raise bridge.Refused(NO_PLAN)
        clips = _clips_by_name(held)
        for name in changes:
            if name not in clips:
                raise bridge.Refused(f'"{name}" is not in this plan.')
        for name, decision in changes.items():
            clips[name]["decision"] = decision

    def _keep(self, name: str) -> None:
        self._decide({name: "keep"})
        _toast(f'Will keep "{name}".')
        _go("/tab/compile")

    def _recycle(self, name: str) -> None:
        self._decide({name: "recycle"})
        _toast(f'Will recycle "{name}".')
        _go("/tab/compile")

    def _keep_both(self, a: str, b: str) -> None:
        self._decide({a: "keep", b: "keep"})
        _toast(f'Will keep both "{a}" and "{b}".')
        _go("/tab/compile")

    def _drop_one(self, a: str, b: str) -> None:
        # In a duplicate pair the second clip is the one dropped; the first is kept.
        self._decide({b: "recycle"})
        _toast(f'Will recycle "{b}".')
        _go("/tab/compile")

    # videos tab

    def _folder(self, slug: str):
        return self.config.output_path / slug

    def _upload(self, slug: str) -> None:
        bridge.upload(self.runner, self.config, self._folder(slug))
        _toast("Uploading to YouTube.")
        _go("/tab/videos")

    def _mark_live(self, slug: str) -> None:
        bridge.mark_live(self.runner, self.config, slug)
        _toast("Marked as live.")
        _go("/tab/videos")

    def _sign_in(self) -> None:
        bridge.sign_in(self.runner, self.config)
        _toast("Signing in to YouTube.")

    def _replan(self, slug: str, include_video: bool) -> None:
        token, plan = bridge.plan_cleanup(self.config, self._folder(slug), include_video=include_video)
        self._held["cleanup_plan"] = _held_cleanup(token, plan, slug)
        _go("/tab/videos")

    def _plan_cleanup(self, slug: str) -> None:
        self._replan(slug, False)
        _toast(f"Planned cleanup for {slug}. Review it, then apply.")

    def _apply_cleanup(self, token: str, recycle_video: bool) -> None:
        held = self._held.get("cleanup_plan")
        if held is None or held["nonce"] != token:
            raise bridge.Refused(STALE)
        if bool(recycle_video) != held["include_video"]:
            # The box and the plan disagree: plan again with the box's value, and apply nothing yet.
            self._replan(held["slug"], bool(recycle_video))
            _toast("The plan was updated for the box you set. Review it, then apply.")
            return
        bridge.cleanup(self.runner, self.config, token)
        self._held.pop("cleanup_plan", None)
        _toast(f"Cleaning up {held['slug']}.")
        _go("/tab/videos")

    def _restore(self, slug: str) -> None:
        token, _plan = bridge.plan_uncompile(self.config, self._folder(slug))
        bridge.uncompile(self.runner, self.config, token)
        _toast(f"Restoring clips for {slug}.")
        _go("/tab/videos")


class FixtureActions:
    """Stand-in for a --fixture run: every key toasts that nothing is written and never calls the bridge."""

    def held_plans(self) -> dict:
        return {}

    def for_tab(self, tab: str) -> dict:
        return {name: self._stand_in for name in TAB_ACTIONS[tab]}

    def _stand_in(self, *_args, **_kwargs) -> None:
        _toast(FIXTURE_TEXT, "info")
