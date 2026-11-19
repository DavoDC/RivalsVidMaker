"""
oldcomp_scan.py - Resumable batch scan of the OldCompilations folder with ko_detect.scan_video.

All logic lives here; scripts/oldcomp.py only parses arguments. Inputs are only read. Every
output path (scan dir, index, state file) passes oldcomp_guard.assert_outside_oldcomp first.
A video whose summary.json already carries the current scanner version is skipped, so a killed
run resumes at the next unfinished video (ko_detect chunk checkpoints resume inside a video).
"""

import json
import os
import time
from collections import Counter
from pathlib import Path

import oldcomp_guard

VIDEO_EXTS = (".mp4", ".mkv", ".mov", ".webm")
MAX_ATTEMPTS = 2


def _atomic_write(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(obj, indent=1, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)


def _read_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def list_videos(root) -> list[Path]:
    return sorted(p for p in Path(root).iterdir() if p.is_file() and p.suffix.lower() in VIDEO_EXTS)


def _row(stem, summary) -> dict:
    return {"stem": stem, "status": "scanned", "scanner_version": summary["scanner_version"],
            "counts": summary["counts"], "minutes": summary["minutes"],
            "seconds": summary["scan_time"], "sec_per_video_min": summary["sec_per_video_min"]}


def scan_all(*, root, meta, state_path, scan_fn, duration_fn, version, only=None, max_videos=None,
             dry_run=False, now_fn=None, log=print) -> dict:
    """Scan every video under root (shortest first). Returns {"plan", "scanned", "skipped", "failed"}."""
    now_fn = now_fn or (lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    scan_root = Path(meta) / "scan"
    index_path = scan_root / "_index.json"
    for out in (scan_root, index_path, state_path):
        oldcomp_guard.assert_outside_oldcomp(out, root)

    plan = []
    for v in list_videos(root):
        if only and only.lower() not in v.stem.lower():
            continue
        plan.append({"stem": v.stem, "path": str(v), "duration": duration_fn(str(v))})
    plan.sort(key=lambda r: r["duration"])
    if max_videos is not None:
        plan = plan[:max_videos]
    res = {"plan": plan, "scanned": 0, "skipped": 0, "failed": []}
    if dry_run:
        return res

    index = _read_json(index_path, {"videos": {}})
    index.setdefault("videos", {})
    for r in plan:
        stem, sdir = r["stem"], scan_root / r["stem"]
        oldcomp_guard.assert_outside_oldcomp(sdir, root)
        done = _read_json(sdir / "summary.json", {})
        if done.get("scanner_version") == version and "counts" in done:
            res["skipped"] += 1
            index["videos"][stem] = _row(stem, done)
            log(f"skip {stem}: already {version}")
            continue
        last_err = None
        for attempt in range(MAX_ATTEMPTS):
            try:
                out = scan_fn(r["path"], checkpoint_dir=str(sdir))
                last_err = None
                break
            except Exception as e:  # noqa: BLE001 - recorded, loop continues
                last_err = f"{type(e).__name__}: {e}"
                log(f"error {stem} attempt {attempt + 1}: {last_err}")
        if last_err is not None:
            res["failed"].append(stem)
            row = {"stem": stem, "status": "failed", "error": last_err}
            index["videos"][stem] = row
            _update_state(state_path, stem, row, now_fn())
            _atomic_write(index_path, index)
            continue
        events = out["events"]
        minutes = out["duration"] / 60.0
        summary = {"stem": stem, "video": r["path"], "scanner_version": out["scanner_version"],
                   "detector": out.get("detector"), "duration": out["duration"], "minutes": round(minutes, 2),
                   "scan_time": round(out["scan_time"], 1),
                   "sec_per_video_min": round(out["scan_time"] / minutes, 2) if minutes else None,
                   "counts": dict(Counter(e["tier"] for e in events)), "events": events}
        _atomic_write(sdir / "summary.json", summary)
        row = _row(stem, summary)
        index["videos"][stem] = row
        _atomic_write(index_path, index)
        _update_state(state_path, stem, {**row, "last_tick_utc": now_fn()}, now_fn())
        res["scanned"] += 1
        log(f"scanned {stem}: {row['minutes']} min, {row['sec_per_video_min']} s/min, {row['counts']}")
    return res


def _update_state(state_path, stem, row, ts) -> None:
    state = _read_json(Path(state_path), {})
    state.setdefault("videos", {})[stem] = row
    state["last_tick_utc"] = ts
    _atomic_write(Path(state_path), state)
