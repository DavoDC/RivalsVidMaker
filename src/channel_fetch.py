"""
channel_fetch.py - Inventory the old compilations against the YouTube channel, and fetch their descriptions.

Read-only on OldCompilations: the local folder is only listed (names, sizes, ffprobe durations).
Every output goes to the meta folder, and every output path passes assert_outside_oldcomp first.
All external tools run through an injected runner, so tests never touch the network.
"""

import json
import os
import re
import subprocess
import time
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

import winproc
from oldcomp_guard import assert_outside_oldcomp

REPO_ROOT = Path(__file__).resolve().parents[1]
YT_DLP = REPO_ROOT / "dependencies" / "yt-dlp.exe"
OLDCOMP_ROOT = Path(r"C:\Users\David\Videos\MarvelRivals\OldCompilations")
OLDCOMP_META_DEFAULT = Path(r"C:\Users\David\Videos\MarvelRivals\OldCompilationsMeta")
CHANNEL_URL = "https://www.youtube.com/@dave369_/videos"

PRINT_FORMAT = "%(id)s\t%(title)s\t%(duration)s"
DURATION_TOLERANCE_S = 2.0
PAUSE_S = 2.0
MAX_CONSECUTIVE_FAILURES = 3
PROCESS_TIMEOUT_S = 600
DATE_PREFIX = re.compile(r"^\d{4}-\d{2}-\d{2}_")


class ChannelListError(Exception):
    """yt-dlp could not list the channel, or printed a line that is not in the expected shape."""


class FetchError(Exception):
    """yt-dlp did not produce an info.json for one video."""


class ProbeError(Exception):
    """ffprobe could not read the duration of a local file."""


def run_process(args):
    """Default runner: run a command, capture its output, and keep the console window hidden."""
    return subprocess.run(
        args,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        creationflags=winproc.NO_WINDOW,
        timeout=PROCESS_TIMEOUT_S,
    )


def _guard(path):
    assert_outside_oldcomp(path, OLDCOMP_ROOT)


def _write_bytes(path, data: bytes):
    """Write through a temp file and os.replace, so a crash never leaves a half-written output."""
    path = Path(path)
    _guard(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)


def _write_json(path, data):
    _write_bytes(path, (json.dumps(data, indent=2, ensure_ascii=False) + "\n").encode("utf-8"))


# ---- channel listing -------------------------------------------------------------------------

def list_channel(channel_url, runner, yt_dlp=YT_DLP):
    """Return [{id, title, duration}] for every video on the channel, from a flat playlist listing."""
    res = runner([str(yt_dlp), "--flat-playlist", "--print", PRINT_FORMAT, channel_url])
    if res.returncode != 0:
        raise ChannelListError(f"yt-dlp exit {res.returncode}: {res.stderr.strip()[-300:]}")
    rows = []
    for line in res.stdout.splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        if len(parts) < 3 or not parts[0].strip():
            raise ChannelListError(f"unexpected listing line: {line[:120]!r}")
        raw_duration = parts[-1].strip()
        rows.append({
            "id": parts[0].strip(),
            "title": "\t".join(parts[1:-1]),
            "duration": None if raw_duration in ("", "NA", "None") else float(raw_duration),
        })
    return rows


# ---- title matching --------------------------------------------------------------------------

def normalise_title(text: str) -> str:
    """
    Compare-ready form of a title: leading YYYY-MM-DD_ removed, NFKC (full-width pipe becomes |),
    casefolded, emoji and punctuation turned into spaces, combining marks and joiners dropped,
    whitespace collapsed.
    """
    folded = unicodedata.normalize("NFKC", DATE_PREFIX.sub("", text, count=1)).casefold()
    out = []
    for ch in folded:
        cat = unicodedata.category(ch)
        if cat in ("Mn", "Me", "Cf"):
            continue  # variation selectors, skin tones, zero-width joiners
        out.append(ch if cat[0] in "LN" else " ")
    return " ".join("".join(out).split())


def match_local(local_stems, channel_rows, local_durations=None):
    """
    Match local file stems to channel rows by normalised title, with the date prefix removed.

    When a local duration is supplied, a row whose duration is known must be within
    DURATION_TOLERANCE_S of it. A channel row is used at most once. Returns (matched, unmatched).
    """
    durations = local_durations or {}
    used = set()
    matched, unmatched = [], []
    for stem in local_stems:
        key = normalise_title(stem)
        same_title = [r for r in channel_rows if normalise_title(r["title"]) == key]
        if not same_title:
            unmatched.append({"stem": stem, "reason": "no title match"})
            continue
        free = [r for r in same_title if r["id"] not in used]
        if not free:
            unmatched.append({"stem": stem, "reason": "channel row already matched"})
            continue
        local_d = durations.get(stem)
        if local_d is not None:
            free = [r for r in free if r["duration"] is None or abs(r["duration"] - local_d) <= DURATION_TOLERANCE_S]
            if not free:
                unmatched.append({"stem": stem, "reason": "no candidate within duration tolerance"})
                continue
        if len(free) > 1:
            unmatched.append({"stem": stem, "reason": "ambiguous"})
            continue
        row = free[0]
        used.add(row["id"])
        matched.append({"stem": stem, "youtube_id": row["id"], "title": row["title"], "duration": row["duration"]})
    return matched, unmatched


# ---- descriptions ----------------------------------------------------------------------------

def _video_folder(video_id, out_dir):
    return Path(out_dir) / video_id


def fetch_description(video_id, out_dir, runner, yt_dlp=YT_DLP):
    """
    Make out_dir/<id>/description.txt. Returns "skipped" if it already exists, "fetched" otherwise.

    yt-dlp writes <id>.info.json (its own name for the info file). If that file is already
    there, the description is built from it without a network call.
    """
    folder = _video_folder(video_id, out_dir)
    description = folder / "description.txt"
    _guard(description)
    if description.exists():
        return "skipped"
    info = folder / f"{video_id}.info.json"
    if not info.exists():
        template = str(folder / "%(id)s")
        res = runner([
            str(yt_dlp), "--skip-download", "--write-info-json", "--no-playlist",
            "-o", template, f"https://www.youtube.com/watch?v={video_id}",
        ])
        if not info.exists():
            raise FetchError(f"{video_id}: yt-dlp exit {res.returncode}: {res.stderr.strip()[-300:]}")
    data = json.loads(info.read_text(encoding="utf-8"))
    _write_bytes(description, (data.get("description") or "").encode("utf-8"))
    return "fetched"


def fetch_all(video_ids, out_dir, runner, yt_dlp=YT_DLP, sleep=time.sleep, pause=PAUSE_S):
    """
    Fetch every id, resumably. Pauses `pause` seconds after each network call that has more ids
    after it. Stops after MAX_CONSECUTIVE_FAILURES failures in a row (a success resets the count).
    """
    summary = {"fetched": [], "skipped": [], "failed": [], "stopped": False}
    calls = 0

    def counting_runner(args):
        nonlocal calls
        calls += 1
        return runner(args)

    consecutive = 0
    ids = list(video_ids)
    for index, video_id in enumerate(ids):
        before = calls
        try:
            status = fetch_description(video_id, out_dir, counting_runner, yt_dlp=yt_dlp)
        except FetchError:
            summary["failed"].append(video_id)
            consecutive += 1
            if consecutive >= MAX_CONSECUTIVE_FAILURES:
                summary["stopped"] = True
                break
        else:
            consecutive = 0
            summary["skipped" if status == "skipped" else "fetched"].append(video_id)
        if calls > before and index < len(ids) - 1:
            sleep(pause)
    return summary


# ---- inventory -------------------------------------------------------------------------------

def probe_duration(path, ffprobe, runner):
    """Duration in seconds of a local file, read by ffprobe (read-only)."""
    res = runner([
        str(ffprobe), "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", str(path),
    ])
    if res.returncode != 0:
        raise ProbeError(f"ffprobe exit {res.returncode} for {Path(path).name}")
    return float(res.stdout.strip())


def run_inventory(local_dir, meta_dir, *, runner=run_process, yt_dlp=YT_DLP, ffprobe=None,
                  channel_url=CHANNEL_URL):
    """
    List the local .mp4 files, list the channel, match them, and write meta_dir/channel_index.json
    and meta_dir/source.json. local_dir is never written. Durations are probed only when ffprobe is given.
    """
    local_dir = Path(local_dir)
    meta_dir = Path(meta_dir)
    _guard(meta_dir)
    files = sorted(p for p in local_dir.iterdir() if p.is_file() and p.suffix.lower() == ".mp4")
    local_durations = {}
    if ffprobe is not None:
        for f in files:
            local_durations[f.stem] = probe_duration(f, ffprobe, runner)
    rows = list_channel(channel_url, runner, yt_dlp=yt_dlp)
    matched, unmatched = match_local([f.stem for f in files], rows, local_durations=local_durations or None)

    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    _write_json(meta_dir / "channel_index.json", {
        "channel_url": channel_url, "fetched_at": now, "count": len(rows), "rows": rows,
    })
    by_stem = {m["stem"]: m for m in matched}
    by_stem.update({u["stem"]: u for u in unmatched})
    videos = []
    for f in files:
        status = by_stem[f.stem]
        videos.append({
            "stem": f.stem,
            "filename": f.name,
            "bytes": f.stat().st_size,
            "duration_s": local_durations.get(f.stem),
            "youtube_id": status.get("youtube_id"),
            "channel_title": status.get("title"),
            "reason": status.get("reason"),
        })
    summary = {
        "local_dir": str(local_dir),
        "generated_at": now,
        "channel_count": len(rows),
        "local_count": len(files),
        "matched_count": len(matched),
        "unmatched_count": len(unmatched),
        "videos": videos,
    }
    _write_json(meta_dir / "source.json", summary)
    return summary
