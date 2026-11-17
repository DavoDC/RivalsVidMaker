"""Pure view model (design plan section 6): a Source payload to the /state.json contract.

snapshot() reads one Source and returns plain dicts; testid() gives each row a stable DOM id.
No writes and no engine imports: this module only shapes data that sources.py already read.
"""
from __future__ import annotations

import re
import zlib

from gui import build_info

SCHEMA = 1
POLL_INTERVAL = 2  # seconds between /state.json polls
# Kinds that stop between clips; stopping an encode or upload mid-run is past the first version.
CANCELLABLE_KINDS = frozenset({"scan", "cleanup"})


def testid(kind: str, name) -> str:
    """kind, slug of name, then the low 24 bits of crc32 of the full name as 6 hex digits.

    The slug keeps ids readable; the crc of the untruncated name keeps names that slug alike apart.
    """
    raw = str(name)
    slug = re.sub(r"[^A-Za-z0-9]+", "-", raw).strip("-").lower()[:48]
    return f"{kind}-{slug}-{zlib.crc32(raw.encode('utf-8')) & 0xFFFFFF:06x}"


def stage_of(row: dict) -> str:
    """First match wins: live, cleaned_partly, uploaded, else encoded."""
    if row.get("youtube_confirmed"):
        return "live"
    if not row.get("has_video") and (row.get("has_clips_dir") or row.get("has_desc")):
        return "cleaned_partly"
    if row.get("video_url"):
        return "uploaded"
    return "encoded"


def _job(job: dict | None) -> dict | None:
    if not job:
        return None
    return {
        "id": job.get("id"),
        "kind": job.get("kind"),
        "title": job.get("title"),
        "phase": job.get("phase"),
        "done": job.get("done"),
        "total": job.get("total"),
        "unit": job.get("unit"),
        "eta_s": job.get("eta_s", job.get("eta")),
        "started_at": job.get("started_at"),
        "cancellable": job.get("kind") in CANCELLABLE_KINDS,
    }


def _summary(data: dict, rows: list[dict]) -> dict:
    unsorted = data.get("unsorted") or []
    protected = sum(1 for clip in unsorted if clip.get("protected"))
    stages = [(stage_of(r), bool(r.get("has_video")), bool(r.get("has_clips_dir"))) for r in rows]
    return {
        "new_clips": len(unsorted) - protected,
        "unsorted": len(unsorted),
        "protected": protected,
        "low_value_pending": len(data.get("low_value") or []),
        "ready_characters": sum(1 for c in data.get("characters") or [] if c.get("ready")),
        "videos_to_upload": sum(1 for s, video, _ in stages if s == "encoded" and video),
        "videos_to_confirm": sum(1 for s, _, _ in stages if s == "uploaded"),
        "videos_to_clean": sum(1 for s, video, clips_dir in stages
                               if s == "live" and (video or clips_dir)),
    }


def _folder(row: dict) -> dict:
    slug = row.get("slug")
    return {
        "testid": testid("video", slug),
        "slug": slug,
        "character": row.get("character"),
        "months": row.get("months"),
        "has_video": bool(row.get("has_video")),
        "has_desc": bool(row.get("has_desc")),
        "clips": row.get("clips", 0),
        "quad_plus": row.get("quad_plus", 0),
        "stage": stage_of(row),
        "video_url": row.get("video_url"),
        "confirmed_at": row.get("confirmed_at"),
    }


def _activity(rec: dict) -> dict:
    """A fixture activity row or a JobRunner history record (state, finished_at, id)."""
    kind = rec.get("kind")
    started = rec.get("started_at")
    ident = rec.get("id") or f"{kind}-{rec.get('title')}-{started}"
    return {
        "testid": testid("job", ident),
        "kind": kind,
        "title": rec.get("title"),
        "result": rec.get("result", rec.get("state")),
        "started_at": started,
        "ended_at": rec.get("ended_at", rec.get("finished_at")),
        "error": rec.get("error"),
        "log_path": rec.get("log_path"),
    }


def _plan_clip(clip: dict) -> dict:
    return {
        "testid": testid("plan-clip", clip.get("name")),
        "name": clip.get("name"),
        "start_s": clip.get("start_s"),
        "duration_s": clip.get("duration_s"),
        "tier": clip.get("tier"),
        "decision": clip.get("decision"),
    }


def _compile(plan: dict | None) -> dict:
    if not plan:
        return {"plan": None}
    return {"plan": {
        "nonce": plan.get("nonce"),
        "character": plan.get("character"),
        "target_s": plan.get("target_s"),
        "batches": [{"number": b.get("number"), "duration_s": b.get("duration_s"),
                     "clips": [_plan_clip(c) for c in b.get("clips") or []]}
                    for b in plan.get("batches") or []],
        "duplicates": [{"a": d.get("a"), "b": d.get("b"), "score": d.get("score")}
                       for d in plan.get("duplicates") or []],
    }}


def _cleanup(plan: dict | None) -> dict | None:
    if not plan:
        return None
    return {
        "nonce": plan.get("nonce"),
        "slug": plan.get("slug"),
        "items": [{"testid": testid("fate", i.get("name")), "name": i.get("name"),
                   "fate": i.get("fate"), "size_mb": i.get("size_mb")}
                  for i in plan.get("items") or []],
        "totals": dict(plan.get("totals") or {}),
    }


def snapshot(source, job: dict | None = None, plans: dict | None = None, history=()) -> dict:
    """The /state.json payload for one read of source.

    job: a running JobRunner record; when given it replaces the source's job.
    plans: optional {"compile_plan": ..., "cleanup_plan": ...}; a key present replaces that source plan.
    history: JobRunner history records (newest first); when given they replace the source's activity.
    """
    data = source.read()
    rows = data.get("output_folders") or []
    plan_of = plans or {}
    archive = data.get("archive") or {}
    activity_src = history or data.get("activity") or []
    return {
        "schema": SCHEMA,
        "generated_at": data.get("generated_at"),
        "stale": bool(data.get("stale")),
        "poll_interval": POLL_INTERVAL,
        "boot_id": build_info.BOOT_ID,
        "build": build_info.line(),
        "fixture": data.get("fixture"),
        "job": _job(job if job is not None else data.get("job")),
        "summary": _summary(data, rows),
        "clips": {
            "characters": [{
                "testid": testid("clip-char", c.get("name")),
                "name": c.get("name"),
                "clips": c.get("clips"),
                "minutes": c.get("minutes"),
                "seconds": c.get("seconds"),
                "scanned": c.get("scanned"),
                "unscanned": c.get("unscanned"),
                "tiers": dict(c.get("tiers") or {}),
                "ready": bool(c.get("ready")),
            } for c in data.get("characters") or []],
            "unsorted": [{
                "testid": testid("clip-root", c.get("name")),
                "name": c.get("name"),
                "protected": bool(c.get("protected")),
            } for c in data.get("unsorted") or []],
            "low_value": [{
                "testid": testid("lowvalue", c.get("name")),
                "name": c.get("name"),
                "character": c.get("character"),
                "tier_or_none": c.get("tier_or_none"),
                "size_mb": c.get("size_mb"),
            } for c in data.get("low_value") or []],
        },
        "compile": _compile(plan_of["compile_plan"] if "compile_plan" in plan_of
                            else data.get("compile_plan")),
        "videos": {
            "folders": [_folder(r) for r in rows],
            "cleanup_plan": _cleanup(plan_of["cleanup_plan"] if "cleanup_plan" in plan_of
                                     else data.get("cleanup_plan")),
        },
        "archive": {
            "total": archive.get("total", 0),
            "by_character": [{
                "testid": testid("archive", r.get("name")),
                "name": r.get("name"),
                "count": r.get("count"),
                "tiers": dict(r.get("tiers") or {}),
            } for r in archive.get("by_character") or []],
        },
        "activity": {"jobs": [_activity(r) for r in activity_src]},
        "config_problems": [str(p) for p in data.get("config_problems") or []],
        "notices": [dict(n) for n in data.get("notices") or [] if isinstance(n, dict)],
    }
