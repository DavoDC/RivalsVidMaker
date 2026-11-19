"""
format_check.py - Compare the best YouTube video format of each old compilation with its local file.

For each video, `yt-dlp -F` lists the formats (no download), the best video format is picked by
resolution then bitrate, and the local file is read with ffprobe (read-only). A row is flagged when
YouTube offers a higher resolution, a higher fps, or a video bitrate more than 15 percent above local.
Output is written to the meta folder only, and every output path passes assert_outside_oldcomp first.
All external tools run through an injected runner, so tests never touch the network.
"""

import json
import re
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

import winproc
from oldcomp_guard import assert_outside_oldcomp

REPO_ROOT = Path(__file__).resolve().parents[1]
YT_DLP = REPO_ROOT / "dependencies" / "yt-dlp.exe"
FFPROBE = REPO_ROOT / "dependencies" / "ffmpeg" / "ffprobe.exe"
WATCH_URL = "https://www.youtube.com/watch?v={}"
BITRATE_THRESHOLD_PCT = 15
PAUSE_S = 2.0
MAX_CONSECUTIVE_FAILURES = 3
PROCESS_TIMEOUT_S = 300

TBR_RE = re.compile(r"^(\d+(?:\.\d+)?)k$")
RES_RE = re.compile(r"(\d+)x(\d+)")


class FormatCheckError(Exception):
    """yt-dlp or ffprobe failed, or printed or read something that is not in the expected shape."""


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


# ---- yt-dlp -F table -------------------------------------------------------------------------

def parse_format_table(text):
    """
    Parse `yt-dlp -F` output into rows. Each row has format_id, ext, width, height, fps, tbr_kbps,
    protocol, vcodec and video_only. Header, [youtube] and [info] lines are skipped.
    Audio rows have width and height None; storyboards have protocol 'mhtml'.
    """
    rows = []
    for line in text.splitlines():
        parts = line.split("|")
        if len(parts) < 3:
            continue
        head = parts[0].split()
        if len(head) < 2 or head[0] == "ID" or head[0].startswith(("[", "-")):
            continue
        res = RES_RE.search(parts[0])
        fps = None
        if res:
            after = parts[0][res.end():].split()
            fps = int(after[0]) if after and after[0].isdigit() else None
        mid = parts[1].split()
        tbr = None
        for tok in mid:
            m = TBR_RE.match(tok)
            if m:
                tbr = int(round(float(m.group(1))))
                break
        tail = parts[2].split()
        rows.append({
            "format_id": head[0],
            "ext": head[1],
            "width": int(res.group(1)) if res else None,
            "height": int(res.group(2)) if res else None,
            "fps": fps,
            "tbr_kbps": tbr,
            "protocol": mid[-1] if mid else None,
            "vcodec": tail[0] if tail else None,
            "video_only": "video only" in parts[2],
        })
    return rows


def _is_video(row):
    return (row["width"] is not None and row["height"] is not None
            and row["protocol"] != "mhtml" and row["vcodec"] not in (None, "images", "audio"))


def pick_best(rows, codec_prefix=None):
    """Highest resolution, then highest bitrate, among video rows (optionally one codec family)."""
    candidates = [r for r in rows if _is_video(r)]
    if codec_prefix:
        candidates = [r for r in candidates if (r["vcodec"] or "").startswith(codec_prefix)]
    if not candidates:
        return None
    return max(candidates, key=lambda r: (r["height"], r["width"], r["tbr_kbps"] or 0))


def fetch_formats(video_id, runner, *, yt_dlp=YT_DLP, js_runtime="node"):
    """Run `yt-dlp -F` for one video and return its stdout. Never downloads."""
    args = [str(yt_dlp), "-F", "--no-playlist"]
    if js_runtime:
        args += ["--js-runtimes", js_runtime]
    args.append(WATCH_URL.format(video_id))
    res = runner(args)
    if res.returncode != 0:
        raise FormatCheckError(f"yt-dlp -F exit {res.returncode} for {video_id}: {res.stderr.strip()[-200:]}")
    return res.stdout


# ---- local file (ffprobe, read-only) ---------------------------------------------------------

def parse_local_probe(text):
    """Video stream facts from `ffprobe -of json`: codec, width, height, fps and video bitrate in kbps."""
    streams = json.loads(text).get("streams", [])
    video = next((s for s in streams if s.get("codec_type") == "video"), None)
    if video is None:
        raise FormatCheckError("ffprobe found no video stream")
    fps = None
    rate = video.get("r_frame_rate") or ""
    if "/" in rate:
        num, den = rate.split("/", 1)
        if den not in ("", "0") and num.isdigit() and den.isdigit():
            fps = int(num) / int(den)
    bit = video.get("bit_rate")
    return {
        "codec": video.get("codec_name"),
        "width": video.get("width"),
        "height": video.get("height"),
        "fps": fps,
        "vbitrate_kbps": float(bit) / 1000 if bit not in (None, "", "N/A") else None,
    }


def probe_local(path, runner, *, ffprobe=FFPROBE):
    """Read the video stream of a local file with ffprobe. Nothing is written."""
    res = runner([
        str(ffprobe), "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=codec_type,codec_name,width,height,r_frame_rate,bit_rate",
        "-of", "json", str(path),
    ])
    if res.returncode != 0:
        raise FormatCheckError(f"ffprobe exit {res.returncode} for {Path(path).name}")
    return parse_local_probe(res.stdout)


# ---- comparison ------------------------------------------------------------------------------

def compare(local, remote, threshold_pct=BITRATE_THRESHOLD_PCT):
    """
    Flag when the remote best format beats the local file on resolution, fps, or video bitrate.
    Bitrate counts only when it is more than threshold_pct above local (integer arithmetic, so an
    exact 15 percent is not flagged). Facts missing on either side go to 'unknown', never guessed.
    """
    reasons, unknown = [], []
    if remote["height"] > local["height"] or remote["width"] > local["width"]:
        reasons.append("resolution")
    if local.get("fps") is None or remote.get("fps") is None:
        unknown.append("fps")
    elif remote["fps"] > local["fps"]:
        reasons.append("fps")
    if local.get("vbitrate_kbps") is None or remote.get("tbr_kbps") is None:
        unknown.append("bitrate")
    elif remote["tbr_kbps"] * 100 > local["vbitrate_kbps"] * (100 + threshold_pct):
        reasons.append("bitrate")
    return {"flagged": bool(reasons), "reasons": reasons, "unknown": unknown}


# ---- orchestration ---------------------------------------------------------------------------

def run_formats(pairs, out_path, *, oldcomp_root, runner=run_process, yt_dlp=YT_DLP, ffprobe=FFPROBE,
                js_runtime="node", sleep=time.sleep, pause=PAUSE_S, meta=None,
                max_consecutive_failures=MAX_CONSECUTIVE_FAILURES):
    """
    For each {youtube_id, filename, local_path} run `yt-dlp -F` (paced) and probe the local file.
    Writes one row per id to out_path, including partial results when the run stops early.
    Stops with FormatCheckError after max_consecutive_failures failed ids in a row.
    """
    out_path = Path(out_path)
    assert_outside_oldcomp(out_path, oldcomp_root)
    rows, failures, made_call = [], 0, False
    summary = {"count": 0, "failed_count": 0, "flagged_count": 0}

    def finish():
        flagged = sum(1 for r in rows if r.get("comparison", {}).get("flagged"))
        failed = sum(1 for r in rows if "error" in r)
        summary.update(count=len(rows), failed_count=failed, flagged_count=flagged)
        doc = dict(meta or {})
        doc.update({
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "js_runtime": js_runtime,
            "threshold_pct": BITRATE_THRESHOLD_PCT,
            "count": len(rows), "failed_count": failed, "flagged_count": flagged,
            "rows": rows,
        })
        out_path.write_text(json.dumps(doc, indent=2), encoding="utf-8")

    try:
        for pair in pairs:
            row = {"youtube_id": pair["youtube_id"], "filename": pair["filename"]}
            rows.append(row)
            if made_call:
                sleep(pause)
            made_call = True
            try:
                text = fetch_formats(pair["youtube_id"], runner, yt_dlp=yt_dlp, js_runtime=js_runtime)
                failures = 0
            except FormatCheckError as exc:
                row["error"] = str(exc)
                failures += 1
                if failures >= max_consecutive_failures:
                    raise FormatCheckError(
                        f"stopped after {failures} consecutive failures; last: {exc}") from exc
                continue
            formats = parse_format_table(text)
            best = pick_best(formats)
            row["best_avc1"] = pick_best(formats, codec_prefix="avc1")
            row["best"] = best
            if pair.get("local_path") is None:
                row["local"] = None
                if best is None:
                    row["error"] = "no video format listed"
                continue
            try:
                local = probe_local(pair["local_path"], runner, ffprobe=ffprobe)
            except FormatCheckError as exc:
                row["error"] = str(exc)
                continue
            row["local"] = local
            if best is None:
                row["error"] = "no video format listed"
            else:
                row["comparison"] = compare(local, best)
    finally:
        finish()
    summary["path"] = str(out_path)
    return summary
