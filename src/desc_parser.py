"""Parse old-compilation YouTube description text into clips and timestamps.

Pure functions, no file IO. Lines that are not recognised are returned in
"unknown" as raw text, never dropped.
"""
import re
from datetime import datetime

# A whole-line clip filename, optionally numbered ("12. THOR_...mp4").
_FILENAME_LINE = re.compile(r"(?:\d+\.\s*)?([^/:]+?\.mp4)")
# Capture datetime at the end of a name, optional pipeline tier suffix after it.
_CAPTURE = re.compile(r"(\d{4}-\d{2}-\d{2})_(\d{2}-\d{2}-\d{2})(?:_([^.]*))?\.mp4$")
# Standard game name: CHARACTER(_| )NAME_YYYY-MM-DD_...
_STANDARD_PREFIX = re.compile(r"^([A-Z][A-Z ]*?)_\d{4}-\d{2}-\d{2}_")
_KNOWN_HEROES = re.compile(r"(?<![A-Za-z])(SQUIRREL GIRL|SQUIRREL_GIRL|THOR)(?![A-Za-z])")
_TIER_TOKEN = re.compile(r"(DOUBLE|TRIPLE|QUAD|PENTA|HEXA)\d*", re.IGNORECASE)
_TS = r"\d+:\d{2}(?::\d{2})?"
# "1:43 - Quadra!", "1:36 - 1:45 = Quad Kill", "1:02:03 - Outro"
_TIMESTAMP_LINE = re.compile(
    rf"^(?P<start>{_TS})\s*-\s*(?:(?P<end>{_TS})\s*=?\s*)?(?P<label>.*)$"
)
_VIDEO_LIST_HEADER = re.compile(r"^\s*Video List:\s*$", re.IGNORECASE)


def _to_seconds(stamp):
    parts = [int(p) for p in stamp.split(":")]
    total = 0
    for p in parts:
        total = total * 60 + p
    return total


def _parse_capture(name):
    m = _CAPTURE.search(name)
    if not m:
        return None, None
    dt = datetime.strptime(f"{m.group(1)}_{m.group(2)}", "%Y-%m-%d_%H-%M-%S")
    return dt, m.group(3)


def _character(name):
    m = _STANDARD_PREFIX.match(name)
    if m:
        return m.group(1)
    h = _KNOWN_HEROES.search(name)
    return h.group(1) if h else None


def _tier(name, suffix):
    tokens = re.split(r"[_ ]", name.rsplit(".mp4", 1)[0])
    if suffix:
        tokens += re.split(r"[_ ]", suffix)
    for t in tokens:
        m = _TIER_TOKEN.fullmatch(t)
        if m:
            return m.group(1).upper()
    return None


def _clip(index, name):
    capture_dt, suffix = _parse_capture(name)
    return {
        "index": index,
        "raw_name": name,
        "character": _character(name),
        "tier": _tier(name, suffix),
        "capture_dt": capture_dt,
        "timestamp_s": None,
    }


def parse_description(text):
    """Return {clips, timestamps, format, unknown} for one description text.

    format is "video_list" when a "Video List:" header precedes the clip
    names, "timestamps" when timestamp lines or a clip-name list appear
    otherwise, and "none" when neither does.
    """
    clips, timestamps, unknown = [], [], []
    saw_video_list = False
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if _VIDEO_LIST_HEADER.match(line):
            saw_video_list = True
            continue
        fm = _FILENAME_LINE.fullmatch(line)
        if fm:
            clips.append(_clip(len(clips) + 1, fm.group(1)))
            continue
        tm = _TIMESTAMP_LINE.match(line)
        if tm:
            end = tm.group("end")
            timestamps.append({
                "timestamp_s": _to_seconds(tm.group("start")),
                "end_s": _to_seconds(end) if end else None,
                "label": tm.group("label").strip(),
                "raw": line,
            })
            continue
        unknown.append(line)
    if not clips and not timestamps:
        fmt = "none"
    elif saw_video_list and clips:
        fmt = "video_list"
    else:
        fmt = "timestamps"
    return {"clips": clips, "timestamps": timestamps, "format": fmt, "unknown": unknown}
