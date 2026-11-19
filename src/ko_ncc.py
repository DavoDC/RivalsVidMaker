"""
ko_ncc.py - Fast kill-banner tier detector: edge-template normalised cross-correlation.

Instead of OCR on every sampled frame, only the small tier-word box (TRIPLE, QUAD, ...) is decoded
by ffmpeg, turned into a Sobel edge map and matched against a bank of word crops
(assets/ko_templates). Runs of hit frames become events and the tier is the one with the largest
summed score over the run. The caller (ko_detect.scan_video) may still run OCR on the rare run whose
best two tier scores are close (AMBIG_MARGIN).

The bank was cut at 1080p. Other 16:9 sizes rescale the templates; other aspect ratios or tiny frames
raise UnsupportedSize so the caller can fall back to OCR instead of failing.

Pure numpy + cv2; ffmpeg only inside decode().
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from pathlib import Path

import cv2
import numpy as np

import winproc

BANK_DIR = Path(__file__).resolve().parent.parent / "assets" / "ko_templates"

FPS = 15               # banners last about 2.5 s; 15 fps is half the cost of 30 with no recall loss
PAD = 4                # px of slack around the box so a small position shift still matches
THR = 0.5              # best-tier NCC score that counts a frame as a hit
MIN_FRAMES = 2         # hit frames needed for a run to count as an event
MAX_GAP = 1            # missed frames bridged inside one run
AMBIG_MARGIN = 0.10    # (best - second) / best summed score below this: ask OCR about the run
CHUNK_SECS = 60
SCENE_KEEP_MIN = 5.0   # scdet scores below this are noise (same as ko_detect.SCENE_KEEP_MIN)
MIN_HEIGHT = 360       # below this the word is too small to match

_SCENE_RE = re.compile(r"lavfi\.scd\.score:\s*([0-9.]+),\s*lavfi\.scd\.time:\s*([0-9.]+)")
_ASPECT = 16 / 9


class UnsupportedSize(ValueError):
    """The frame size cannot use the template bank (not 16:9, or too small)."""


# ── Scoring ───────────────────────────────────────────────────────────────────

def edge_map(gray: np.ndarray) -> np.ndarray:
    """Sobel gradient magnitude, float32, same shape. A flat image maps to all zeros."""
    g = gray.astype(np.float32)
    gx = cv2.Sobel(g, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(g, cv2.CV_32F, 0, 1, ksize=3)
    return cv2.magnitude(gx, gy)


def build_bank(crops_by_tier: dict[str, list[np.ndarray]], pad: int = PAD) -> dict:
    tiers = list(crops_by_tier)
    return {"tiers": tiers, "pad": pad,
            "templates": [[edge_map(c) for c in crops_by_tier[t]] for t in tiers]}


def frame_scores(frames: np.ndarray, bank: dict) -> np.ndarray:
    """(N, n_tiers): best TM_CCOEFF_NORMED of each frame's edge map against each tier's templates."""
    out = np.zeros((len(frames), len(bank["tiers"])), np.float32)
    for i, fr in enumerate(frames):
        e = edge_map(fr)
        for j, tpls in enumerate(bank["templates"]):
            best = 0.0
            for t in tpls:
                r = cv2.matchTemplate(e, t, cv2.TM_CCOEFF_NORMED)
                m = float(np.nan_to_num(r, nan=0.0, posinf=0.0, neginf=0.0).max())
                if m > best:
                    best = m
            out[i, j] = best
    return out


def merge_scores(parts: list[tuple[int, np.ndarray]], total: int) -> np.ndarray:
    """Place per-chunk score blocks at their global frame index (chunks never overlap)."""
    width = parts[0][1].shape[1]
    out = np.zeros((total, width), np.float32)
    for first, blk in parts:
        n = max(0, min(len(blk), total - first))
        out[first:first + n] = blk[:n]
    return out


def runs_from_scores(scores: np.ndarray, tiers: list[str], fps: float, thr: float = THR,
                     min_frames: int = MIN_FRAMES, max_gap: int = MAX_GAP) -> list[dict]:
    """
    Runs of frames whose best tier score >= thr (gaps up to max_gap bridged), each with at least
    min_frames hits. Run: {"start", "end", "peak" (frame indices), "tier" (largest summed score),
    "frames", "margin" ((best - second) / best of the summed scores, 1.0 with one tier)}.
    """
    if not len(scores):
        return []
    hit = scores.max(axis=1) >= thr
    spans, start, last = [], None, None
    for i in np.flatnonzero(hit):
        i = int(i)
        if start is None:
            start = last = i
        elif i - last - 1 <= max_gap:
            last = i
        else:
            spans.append((start, last))
            start = last = i
    if start is not None:
        spans.append((start, last))
    runs = []
    for a, b in spans:
        if int(hit[a:b + 1].sum()) < min_frames:
            continue
        seg = scores[a:b + 1]
        sums = np.where(hit[a:b + 1, None], seg, 0.0).sum(axis=0)
        k = int(sums.argmax())
        srt = np.sort(sums)[::-1]
        runs.append({"start": a, "end": b, "peak": a + int(seg[:, k].argmax()), "tier": tiers[k],
                     "frames": b - a + 1,
                     "margin": float((srt[0] - srt[1]) / srt[0]) if len(srt) > 1 and srt[0] > 0 else 1.0})
    return runs


def timeline_from_runs(runs: list[dict], total: int, fps: float) -> list[tuple[float, str | None]]:
    """One (t, tier_or_None) sample per frame; frames inside a run carry the run's tier."""
    tier: list[str | None] = [None] * total
    for r in runs:
        for i in range(r["start"], min(r["end"] + 1, total)):
            tier[i] = r["tier"]
    return [(i / fps, tier[i]) for i in range(total)]


# ── Bank and geometry ─────────────────────────────────────────────────────────

_raw_cache: dict[str, dict] = {}


def bank_signature(bank_dir: Path | str | None = None) -> str:
    """Short hash of templates.json; part of the checkpoint meta so a new bank invalidates old scores."""
    p = Path(bank_dir or BANK_DIR) / "templates.json"
    return hashlib.sha1(p.read_bytes()).hexdigest()[:12]


def load_raw_bank(bank_dir: Path | str | None = None) -> dict:
    """{"crops": {tier: [gray uint8]}, "frac": [x, y, w, h] of the box in the frame, "size": (w, h), "frame_h"}."""
    base = Path(bank_dir or BANK_DIR)
    key = str(base)
    if key in _raw_cache:
        return _raw_cache[key]
    tj = json.loads((base / "templates.json").read_text(encoding="utf-8"))
    crops: dict[str, list[np.ndarray]] = {}
    for t in tj["templates"]:
        img = cv2.imread(str(base / t["file"]), cv2.IMREAD_GRAYSCALE)
        if img is None:
            raise FileNotFoundError(f"template image missing: {base / t['file']}")
        crops.setdefault(t["tier"], []).append(img)
    if not crops:
        raise ValueError(f"no templates in {base}")
    hs = [c.shape[0] for v in crops.values() for c in v]
    ws = [c.shape[1] for v in crops.values() for c in v]
    raw = {"crops": crops, "frac": tj["templates"][0]["box_frame_frac_xywh"],
           "size": (max(ws), max(hs)), "frame_h": tj["frame_size"][1]}
    _raw_cache[key] = raw
    return raw


def plan(width: int, height: int, raw: dict | None = None, pad: int = PAD) -> dict:
    """
    {"bank", "crop": (cw, ch, x, y), "scale"} for a frame size, rescaling the 1080p templates when
    the frame is another 16:9 size. Raises UnsupportedSize for anything the bank cannot serve.
    """
    raw = raw or load_raw_bank()
    if width <= 0 or height < MIN_HEIGHT:
        raise UnsupportedSize(f"{width}x{height} is too small for the template bank")
    if abs(width / height - _ASPECT) > 0.02 * _ASPECT:
        raise UnsupportedSize(f"{width}x{height} is not 16:9")
    scale = height / raw["frame_h"]
    if abs(scale - 1.0) < 1e-6:
        crops = raw["crops"]
        tw, th = raw["size"]
    else:
        crops = {t: [cv2.resize(c, (max(1, round(c.shape[1] * scale)), max(1, round(c.shape[0] * scale))),
                                interpolation=cv2.INTER_AREA) for c in v] for t, v in raw["crops"].items()}
        tw = max(c.shape[1] for v in crops.values() for c in v)
        th = max(c.shape[0] for v in crops.values() for c in v)
    bx, by = round(raw["frac"][0] * width), round(raw["frac"][1] * height)
    cw, ch = tw + 2 * pad, th + 2 * pad
    if bx + tw > width + 2 or by + th > height + 2 or cw > width or ch > height:
        raise UnsupportedSize(f"banner box falls outside a {width}x{height} frame")
    # The box hugs the right edge, so the padded crop is clamped into the frame (as ffmpeg crop does);
    # the template then sits at the crop's far edge and still fits.
    x, y = min(max(0, bx - pad), width - cw), min(max(0, by - pad), height - ch)
    return {"bank": build_bank(crops, pad), "crop": (cw, ch, x, y), "scale": scale}


# ── Decode ────────────────────────────────────────────────────────────────────

def decode(ffmpeg: str, video: str, start: float, length: float, fps: int,
           crop: tuple[int, int, int, int]) -> tuple[np.ndarray, list[tuple[float, float]]]:
    """
    (frames (N, ch, cw) uint8 gray, scenes [(t_from_start, score)]) for [start, start+length).
    A scdet branch on the downscaled full frame rides along so the scene peaks used for clip
    boundaries need no second decode.
    """
    cw, ch, x, y = crop
    graph = (f"[0:v]split=2[a][b];[a]fps={fps},crop={cw}:{ch}:{x}:{y},format=gray[roi];"
             f"[b]scale=320:-2,scdet=threshold=0[sc]")
    cmd = [ffmpeg, "-hide_banner", "-nostats", "-loglevel", "info", "-nostdin",
           "-ss", f"{start:.3f}", "-t", f"{length:.3f}", "-i", video, "-an", "-sn",
           "-filter_complex", graph,
           "-map", "[roi]", "-f", "rawvideo", "-pix_fmt", "gray", "pipe:1",
           "-map", "[sc]", "-f", "null", "-"]
    r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, creationflags=winproc.NO_WINDOW)
    err = r.stderr.decode("utf-8", "replace")
    if r.returncode != 0:
        raise RuntimeError(f"ffmpeg failed at {start}s ({r.returncode}): " + " | ".join(err.splitlines()[-5:]))
    frames = np.frombuffer(r.stdout, dtype=np.uint8)
    frames = frames[: len(frames) // (cw * ch) * (cw * ch)].reshape(-1, ch, cw)
    scenes = [(float(m.group(2)), float(m.group(1))) for m in _SCENE_RE.finditer(err)
              if float(m.group(1)) >= SCENE_KEEP_MIN]
    return frames, scenes


def scan_range(video: str, start: float, length: float, ffmpeg: str, size: tuple[int, int],
               fps: int = FPS, raw: dict | None = None) -> list[dict]:
    """Runs found in one window of a video, with absolute t_start / t_end / t_peak seconds added."""
    p = plan(size[0], size[1], raw)
    frames, _ = decode(ffmpeg, video, start, length, fps, p["crop"])
    runs = runs_from_scores(frame_scores(frames, p["bank"]), p["bank"]["tiers"], fps)
    for r in runs:
        r["t_start"], r["t_end"], r["t_peak"] = (start + r[k] / fps for k in ("start", "end", "peak"))
    return runs
