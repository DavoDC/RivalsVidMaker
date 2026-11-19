"""Tests for ko_ncc (edge-template NCC kill-banner detector) and its wiring into ko_detect.scan_video.

Unit tests use small synthetic templates. The real-bank tests read assets/ko_templates. The real-ffmpeg
tests build a tiny 1080p video with a pasted banner crop; the AWAKENS parity test is skipped when the
compilation is absent (it is only ever read).
"""

import glob
import os
import subprocess

import numpy as np
import pytest
from PIL import Image

import ko_detect
import ko_ncc

RNG = np.random.default_rng(7)


def _crop(h=20, w=60):
    """A random blob image standing in for a tier word crop."""
    g = np.full((h, w), 10, np.uint8)        # flat margin like a real crop, so pasting it adds no new edges
    g[4:-4, 6:-6] = RNG.integers(0, 255, (h - 8, w - 12)).astype(np.uint8)
    return g


@pytest.fixture(scope="module")
def tiny_bank():
    crops = {"TRIPLE": [_crop()], "QUAD": [_crop()]}
    return crops, ko_ncc.build_bank(crops, pad=4)


def _pad_frame(crop, pad=4, noise=0):
    f = np.full((crop.shape[0] + 2 * pad, crop.shape[1] + 2 * pad), 10, np.uint8)
    f[pad:pad + crop.shape[0], pad:pad + crop.shape[1]] = crop
    if noise:
        f = np.clip(f.astype(int) + RNG.integers(-noise, noise, f.shape), 0, 255).astype(np.uint8)
    return f


def test_edge_map_flat_is_zero():
    assert float(ko_ncc.edge_map(np.full((10, 10), 99, np.uint8)).max()) == 0.0


def test_frame_scores_pick_the_right_tier(tiny_bank):
    crops, bank = tiny_bank
    frames = np.stack([_pad_frame(crops["TRIPLE"][0]), _pad_frame(crops["QUAD"][0]),
                       np.full_like(_pad_frame(crops["QUAD"][0]), 10)])
    s = ko_ncc.frame_scores(frames, bank)
    assert s.shape == (3, 2)
    assert s[0, 0] > 0.95 and s[0, 0] - s[0, 1] > 0.2
    assert s[1, 1] > 0.95 and s[1, 1] - s[1, 0] > 0.2
    assert s[2].max() == 0.0          # flat frame: NaN scores are coerced to 0


def test_frame_scores_tolerate_a_small_shift(tiny_bank):
    crops, bank = tiny_bank
    f = np.full((28, 68), 10, np.uint8)
    f[6:26, 3:63] = crops["QUAD"][0]
    assert ko_ncc.frame_scores(f[None], bank)[0, 1] > 0.9


def test_merge_scores_places_chunks_and_clips_overrun():
    a, b = np.ones((3, 2), np.float32), np.full((3, 2), 2, np.float32)
    out = ko_ncc.merge_scores([(0, a), (3, b)], total=5)
    assert out.shape == (5, 2) and out[2, 0] == 1 and out[3, 0] == 2 and out[4, 0] == 2


def _scores(rows):
    return np.array(rows, np.float32)


def test_runs_pick_tier_by_summed_score_and_report_margin():
    s = _scores([[0, 0], [0.6, 0.55], [0.7, 0.9], [0.65, 0.95], [0, 0]])
    runs = ko_ncc.runs_from_scores(s, ["TRIPLE", "QUAD"], fps=10, thr=0.5, min_frames=2, max_gap=1)
    assert len(runs) == 1
    r = runs[0]
    assert r["tier"] == "QUAD" and r["start"] == 1 and r["end"] == 3 and r["peak"] == 3
    assert 0 < r["margin"] < 0.3


def test_runs_bridge_small_gaps_and_drop_short_runs():
    s = _scores([[0.9, 0], [0, 0], [0.9, 0], [0, 0], [0, 0], [0.9, 0], [0, 0], [0, 0]])
    runs = ko_ncc.runs_from_scores(s, ["TRIPLE", "QUAD"], 10, 0.5, 2, 1)
    assert [(r["start"], r["end"]) for r in runs] == [(0, 2)]      # lone frame at 5 is below min_frames


def test_runs_empty_scores():
    assert ko_ncc.runs_from_scores(np.zeros((0, 2), np.float32), ["TRIPLE", "QUAD"], 10, 0.5, 2, 1) == []


def test_timeline_labels_run_frames_only():
    runs = [{"start": 2, "end": 3, "tier": "QUAD", "peak": 2, "frames": 2, "margin": 1.0}]
    tl = ko_ncc.timeline_from_runs(runs, total=5, fps=2)
    assert tl == [(0.0, None), (0.5, None), (1.0, "QUAD"), (1.5, "QUAD"), (2.0, None)]


def test_load_real_bank_has_tier_words():
    raw = ko_ncc.load_raw_bank()
    assert {"TRIPLE", "QUAD"} <= set(raw["crops"])
    assert all(len(v) for v in raw["crops"].values())
    assert len(raw["frac"]) == 4 and raw["size"][0] > raw["size"][1]


def test_plan_1080p_uses_bank_unscaled_and_other_sizes_rescale():
    raw = ko_ncc.load_raw_bank()
    p = ko_ncc.plan(1920, 1080, raw)
    w, h = raw["size"]
    assert p["crop"][:2] == (w + 8, h + 8)
    p720 = ko_ncc.plan(1280, 720, raw)
    assert abs(p720["crop"][0] - (w * 2 / 3 + 8)) <= 2 and p720["scale"] == pytest.approx(2 / 3)


@pytest.mark.parametrize("size", [(640, 480), (320, 180), (0, 0), (1080, 1920)])
def test_plan_unsupported_sizes_raise_value_error_subclass(size):
    with pytest.raises(ko_ncc.UnsupportedSize):
        ko_ncc.plan(*size, ko_ncc.load_raw_bank())


# ---- scan_video wiring (decode faked) ----

def _fake_decode_factory(raw, hit_start, hit_end, tier, fps=ko_ncc.FPS):
    plan = ko_ncc.plan(1920, 1080, raw)
    cw, ch = plan["crop"][:2]
    blank = np.full((ch, cw), 10, np.uint8)
    crop = raw["crops"][tier][0]
    banner = blank.copy()
    banner[4:4 + crop.shape[0], 4:4 + crop.shape[1]] = crop

    def decode(ffmpeg, video, start, length, fps_, crop_box):
        n = int(length * fps_)
        frames = np.stack([banner if hit_start <= start + i / fps_ < hit_end else blank for i in range(n)])
        return frames, [(0.5, 40.0)]
    return decode


def test_scan_video_ncc_returns_scan_shape_and_event(tmp_path, monkeypatch):
    raw = ko_ncc.load_raw_bank()
    monkeypatch.setattr(ko_ncc, "decode", _fake_decode_factory(raw, 70.0, 72.0, "QUAD"))
    res = ko_detect.scan_video("fake.mp4", checkpoint_dir=str(tmp_path / "s"), duration=130.0,
                               size=(1920, 1080), detector="ncc")
    assert res["scanner_version"] == ko_detect.SCANNER_VERSION
    assert res["detector"] == "ncc"
    assert [(e["tier"]) for e in res["events"]] == ["QUAD"]
    assert 69.9 <= res["events"][0]["ts"] <= 70.5
    assert all(len(p) == 2 for p in res["timeline"])
    assert any(t == "QUAD" for _, t in res["timeline"])
    assert (0.5, 40.0) in [tuple(s) for s in res["scenes"]]
    for k in ("video", "duration", "fps", "chunks", "chunks_reused", "scan_time"):
        assert k in res


def test_scan_video_ncc_resumes_from_checkpoints(tmp_path, monkeypatch):
    raw = ko_ncc.load_raw_bank()
    monkeypatch.setattr(ko_ncc, "decode", _fake_decode_factory(raw, 5.0, 7.0, "TRIPLE"))
    kw = dict(checkpoint_dir=str(tmp_path / "s"), duration=130.0, size=(1920, 1080), detector="ncc")
    ko_detect.scan_video("fake.mp4", **kw)
    monkeypatch.setattr(ko_ncc, "decode", lambda *a, **k: (_ for _ in ()).throw(AssertionError("redecoded")))
    res = ko_detect.scan_video("fake.mp4", **kw)
    assert res["chunks_reused"] == res["chunks"] > 1 and res["events"][0]["tier"] == "TRIPLE"


def test_ambiguous_event_falls_back_to_ocr(tmp_path, monkeypatch):
    raw = ko_ncc.load_raw_bank()
    monkeypatch.setattr(ko_ncc, "decode", _fake_decode_factory(raw, 20.0, 22.0, "QUAD"))
    monkeypatch.setattr(ko_ncc, "AMBIG_MARGIN", 1.1)           # every event counts as ambiguous

    class OneFrame:
        scenes = []
        def __iter__(self):
            yield b"\0" * 10

    res = ko_detect.scan_video("fake.mp4", checkpoint_dir=str(tmp_path / "s"), duration=60.0,
                               size=(1920, 1080), detector="ncc",
                               runner=lambda *a: OneFrame(), ocr_fn=lambda d, w, h: "PENTA")
    assert [e["tier"] for e in res["events"]] == ["PENTA"]


def test_unsupported_size_falls_back_to_ocr_with_log(tmp_path, caplog):
    seen = []

    class Dec:
        scenes = []
        def __iter__(self):
            yield b"\0" * (ko_detect.roi_geometry(640, 480)[0] * ko_detect.roi_geometry(640, 480)[1] * 3)

    with caplog.at_level("INFO"):
        res = ko_detect.scan_video("fake.mp4", checkpoint_dir=str(tmp_path / "s"), duration=1.0, size=(640, 480),
                                   chunk_secs=10, overlap_secs=0, fps=1, workers=1, detector="ncc",
                                   runner=lambda *a: Dec(), ocr_fn=lambda d, w, h: seen.append(1))
    assert res["detector"] == "ocr" and seen
    assert any("falling back to OCR" in r.message for r in caplog.records)


def test_detector_ocr_is_reachable():
    assert ko_detect.SCANNER_VERSION != "long-scan-2"


# ---- real ffmpeg ----

def _ffmpeg_ok():
    return os.path.exists(ko_detect.FFMPEG)


@pytest.mark.skipif(not _ffmpeg_ok(), reason="ffmpeg missing")
def test_real_ffmpeg_synthetic_banner(tmp_path):
    raw = ko_ncc.load_raw_bank()
    w, h = raw["size"]
    x, y = round(raw["frac"][0] * 1920), round(raw["frac"][1] * 1080)
    blank = Image.new("RGB", (1920, 1080), (30, 30, 30))
    banner = blank.copy()
    banner.paste(Image.fromarray(raw["crops"]["QUAD"][0]).convert("RGB"), (x, y))
    blank.save(tmp_path / "b.png")
    banner.save(tmp_path / "q.png")
    out = tmp_path / "v.mp4"
    cmd = [ko_detect.FFMPEG, "-y", "-loglevel", "error",
           "-loop", "1", "-t", "2", "-i", str(tmp_path / "b.png"),
           "-loop", "1", "-t", "3", "-i", str(tmp_path / "q.png"),
           "-loop", "1", "-t", "2", "-i", str(tmp_path / "b.png"),
           "-filter_complex", "concat=n=3:v=1:a=0,fps=30,format=yuv420p", "-c:v", "libx264", "-crf", "18", str(out)]
    subprocess.run(cmd, check=True)
    res = ko_detect.scan_video(str(out), checkpoint_dir=str(tmp_path / "scan"), detector="ncc")
    assert [e["tier"] for e in res["events"]] == ["QUAD"]
    assert 1.8 <= res["events"][0]["ts"] <= 2.6


AWAKENS = glob.glob(r"C:\Users\David\Videos\MarvelRivals\OldCompilations\2026-03-17_THOR AWAKENS*")


@pytest.mark.skipif(not (AWAKENS and _ffmpeg_ok()), reason="AWAKENS compilation absent")
@pytest.mark.parametrize("start,expect", [(95.0, 107.75), (235.0, 247.0)])
def test_awakens_window_quad_parity(start, expect):
    runs = ko_ncc.scan_range(AWAKENS[0], start, 15.0, ko_detect.FFMPEG, (1920, 1080))
    quads = [r for r in runs if r["tier"] == "QUAD"]
    assert quads, runs
    assert any(r["t_start"] - 1.5 <= expect <= r["t_end"] + 1.5 for r in quads), quads
