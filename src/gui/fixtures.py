"""Scenario catalogue (design plan section 11): every fixture state as plain data.

Each scenario has the same keys as the RealSource payload (see sources.py).
Names are invented: in-game character names, made-up dates, no paths,
no channel ids, no person names. Timestamps are fixed so tests are stable.
"""
from copy import deepcopy

GENERATED_AT = "2026-11-17T09:00:00+00:00"
STALE_AT = "2026-11-10T09:00:00+00:00"
STARTED_AT = "2026-11-17T08:55:00+00:00"

TIERS = ("KO", "DOUBLE", "TRIPLE", "QUAD", "PENTA", "HEXA")


def tiers(**counts) -> dict:
    unknown = set(counts) - set(TIERS)
    if unknown:
        raise ValueError(f"unknown tier(s): {sorted(unknown)}")
    return {t: counts.get(t, 0) for t in TIERS}


def character(name, clips, minutes, scanned=None, tier_counts=None, ready=False) -> dict:
    scanned = clips if scanned is None else scanned
    return {
        "name": name,
        "clips": clips,
        "minutes": minutes,
        "scanned": scanned,
        "unscanned": clips - scanned,
        "tiers": tiers(**(tier_counts or {})),
        "ready": ready,
    }


def job(kind, title, phase, done, total, unit, eta_s=None) -> dict:
    return {
        "id": f"{kind}-fixture",
        "kind": kind,
        "title": title,
        "phase": phase,
        "done": done,
        "total": total,
        "unit": unit,
        "eta_s": eta_s,
        "started_at": STARTED_AT,
    }


def activity(kind, title, result, error=None) -> dict:
    return {
        "kind": kind,
        "title": title,
        "result": result,
        "started_at": STARTED_AT,
        "ended_at": None if result == "interrupted" else GENERATED_AT,
        "error": error,
        "log_path": None,
    }


def folder(slug, video_count, youtube_confirmed=False, confirmed_at=None, *, character=None,
           has_desc=False, clips=0, quad_plus=0, has_clips_dir=False, video_url=None) -> dict:
    """One output-folder row. Defaults match RealSource on an empty folder."""
    return {
        "slug": slug,
        "character": character if character is not None else slug.split("_", 1)[0].upper(),
        "months": None,
        "video_count": video_count,
        "has_video": video_count > 0,
        "has_desc": has_desc,
        "clips": clips,
        "quad_plus": quad_plus,
        "has_clips_dir": has_clips_dir,
        "video_url": video_url,
        "youtube_confirmed": youtube_confirmed,
        "confirmed_at": confirmed_at,
    }


def clip(name, **extra) -> dict:
    return {"name": name, **extra}


BASE = {
    "fixture": None,
    "generated_at": GENERATED_AT,
    "stale": False,
    "config_problems": [],
    "job": None,
    "unsorted": [],
    "characters": [],
    "low_value": [],
    "compile_plan": None,
    "output_folders": [],
    "cleanup_plan": None,
    "archive": {"total": 0, "by_character": []},
    "activity": [],
    "notices": [],
}


def _scenario(name, **over) -> dict:
    data = deepcopy(BASE)
    data["fixture"] = name
    data.update(over)
    return data


_THOR = character("THOR", 12, 150.0, scanned=12, tier_counts={"KO": 9, "DOUBLE": 2, "QUAD": 1}, ready=True)
_IRON = character("IRON MAN", 8, 96.0, scanned=8, tier_counts={"KO": 6, "TRIPLE": 1}, ready=True)
_SQUIRREL = character("SQUIRREL GIRL", 5, 22.5, scanned=5, tier_counts={"KO": 4})
_WIDOW = character("BLACK WIDOW", 6, 40.0, scanned=3, tier_counts={"KO": 2})

_UNSORTED = [
    clip("THOR_2026-07-10_20-14-03.mp4", protected=False),
    clip("IRON_MAN_2026-07-10_21-02-44.mp4", protected=False),
    clip("BLACK_WIDOW_2026-07-11_09-30-10.mp4", protected=True),
]

_LOW_VALUE = [
    {"name": "SQUIRREL_GIRL_2026-07-02_11-00-00.mp4", "character": "SQUIRREL GIRL",
     "tier_or_none": None, "size_mb": 4.2},
    {"name": "BLACK_WIDOW_2026-07-03_18-45-12.mp4", "character": "BLACK WIDOW",
     "tier_or_none": "KO", "size_mb": 6.8},
]

_PLAN = {
    "nonce": "fixture-plan-nonce",
    "character": "THOR",
    "target_s": 900,
    "batches": [
        {"number": 1, "duration_s": 912, "clips": [
            {"name": "THOR_2026-07-01_10-00-00.mp4", "start_s": 0, "duration_s": 300,
             "tier": "QUAD", "decision": "keep"},
            {"name": "THOR_2026-07-01_10-05-00.mp4", "start_s": 300, "duration_s": 312,
             "tier": "KO", "decision": "keep"},
            {"name": "THOR_2026-07-02_19-40-21.mp4", "start_s": 612, "duration_s": 300,
             "tier": "PENTA", "decision": "keep"},
        ]},
        {"number": 2, "duration_s": 600, "clips": [
            {"name": "THOR_2026-07-04_12-00-00.mp4", "start_s": 0, "duration_s": 600,
             "tier": "DOUBLE", "decision": "keep"},
        ]},
    ],
    "duplicates": [
        {"a": "THOR_2026-07-01_10-05-00.mp4", "b": "THOR_2026-07-01_10-05-30.mp4", "score": 0.97},
    ],
}

_CLEANUP = {
    "nonce": "fixture-cleanup-nonce",
    "slug": "thor_vid1",
    "items": [
        {"name": "thor_vid1_part1.mp4", "fate": "remove", "size_mb": 812.4},
        {"name": "thor_vid1_part2.mp4", "fate": "remove", "size_mb": 790.1},
        {"name": "thor_vid1_description.txt", "fate": "keep", "size_mb": 0.01},
    ],
    "totals": {"remove_count": 2, "remove_mb": 1602.5},
}

_HUGE_ARCHIVE = [
    {"name": f"ARCHIVE GROUP {i:04d}", "count": 1 + i % 7, "tiers": tiers(KO=i % 5)}
    for i in range(1, 2401)
]

_LONG = (
    "THE VERY LONG NAMED CHARACTER OF THE NORTHERN PROVINCE "
    "WITH A SECOND HALF THAT KEEPS GOING PAST ANY SANE WIDTH"
)

SCENARIOS = {
    "empty": _scenario("empty"),
    "fresh_intake": _scenario("fresh_intake", unsorted=_UNSORTED,
                              activity=[activity("sort", "Sort unsorted clips", "done")]),
    "needs_decision": _scenario("needs_decision", unsorted=_UNSORTED[:1], low_value=_LOW_VALUE,
                                characters=[_THOR, _IRON],
                                job=job("recycle_clip", "Recycle a low-value clip", "recycling", 1, 2, "clips"),
                                activity=[activity("recycle_clip", "Recycle SQUIRREL GIRL clip", "done")]),
    "ready": _scenario("ready", characters=[_THOR, _IRON, _SQUIRREL],
                       output_folders=[folder("thor_vid2", 0, character="THOR", has_desc=True,
                                              clips=2, quad_plus=1, has_clips_dir=True)],
                       job=job("uncompile", "Uncompile thor_vid2", "restoring", 2, 5, "clips")),
    "plan": _scenario("plan", characters=[_THOR, _IRON], compile_plan=_PLAN),
    "scanning": _scenario("scanning", characters=[_THOR, _WIDOW],
                          job=job("scan", "Scan BLACK WIDOW clips", "scanning", 3, 6, "clips"),
                          activity=[activity("scan", "Scan THOR clips", "done")]),
    "encoding": _scenario("encoding", characters=[_THOR], compile_plan=_PLAN,
                          job=job("compile", "Encode THOR batch 1", "encoding", 3, 9, "steps", eta_s=240)),
    "upload_failed": _scenario(
        "upload_failed",
        output_folders=[folder("thor_vid1", 1, character="THOR", has_desc=True, clips=3,
                               quad_plus=1, has_clips_dir=True)],
        job=job("upload", "Retry upload thor_vid1", "uploading", 0, 1, "videos"),
        notices=[{"kind": "auth_error",
                  "text": "Sign-in for the video host expired. Sign in again, then retry the upload."}],
        activity=[activity("upload", "Upload thor_vid1", "failed", error="auth expired")],
    ),
    "awaiting_live": _scenario(
        "awaiting_live",
        output_folders=[folder("thor_vid1", 1, youtube_confirmed=False, character="THOR", has_desc=True,
                               clips=3, quad_plus=1, has_clips_dir=True,
                               video_url="fixture.test/watch?v=up1")],
        activity=[activity("upload", "Upload thor_vid1", "uploaded")],
    ),
    "cleanup_plan": _scenario("cleanup_plan", cleanup_plan=_CLEANUP,
                              output_folders=[folder("thor_vid1", 2, True, "2026-07-05T10:00:00+00:00",
                                                     character="THOR", has_desc=True, clips=3, quad_plus=1,
                                                     has_clips_dir=True,
                                                     video_url="fixture.test/watch?v=live1")],
                              job=job("cleanup", "Clean up thor_vid1", "removing", 0, 2, "files"),
                              activity=[activity("cleanup", "Clean up thor_vid1", "done")]),
    "huge_archive": _scenario("huge_archive", characters=[_THOR],
                              archive={"total": 4200, "by_character": _HUGE_ARCHIVE}),
    "long_names": _scenario(
        "long_names",
        characters=[character(_LONG, 3, 12.0, scanned=2, tier_counts={"KO": 1})],
        unsorted=[clip(_LONG.replace(" ", "_") + "_2026-07-12_07-07-07.mp4", protected=False)],
        output_folders=[folder("the_very_long_named_character_vid1", 1)],
    ),
    "stale": _scenario("stale", generated_at=STALE_AT, stale=True,
                       characters=[_THOR, _IRON]),
    "config_broken": _scenario("config_broken",
                               config_problems=["ffmpeg not found", "tesseract not found"]),
    "busy_refused": _scenario(
        "busy_refused",
        job=job("sort", "Sort unsorted clips", "sorting", 1, 3, "clips"),
        unsorted=_UNSORTED,
        notices=[{"kind": "toast", "text": "A job is already running. Wait for it to finish."}],
    ),
    "interrupted": _scenario(
        "interrupted",
        characters=[_THOR],
        activity=[activity("compile", "Encode THOR batch 1", "interrupted"),
                  activity("uncompile", "Uncompile thor_vid2", "interrupted")],
    ),
}


def scenario(name: str) -> dict:
    """A deep copy of one scenario. Raises KeyError for an unknown name."""
    return deepcopy(SCENARIOS[name])
