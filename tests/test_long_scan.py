"""Tests for ko_detect.scan_video: chunked ROI pipe, OCR pool, checkpoint and resume.

The fakes stand in for ffmpeg and Tesseract so no real video OCR is needed. One test
generates a tiny synthetic video with ffmpeg lavfi (skipped when ffmpeg is missing) to
exercise the real ffmpeg runner.
"""

import json
import os
import subprocess
from pathlib import Path

import pytest

import ko_detect
import winproc

W, H = 40, 20
GEOM = ko_detect.roi_geometry(W, H)
FRAME_BYTES = GEOM[0] * GEOM[1]
FPS = 4


class FakeDecode:
    """Iterable of fake ROI frames. First 4 bytes carry the global grid index."""

    def __init__(self, first_idx, count, scenes):
        self._first = first_idx
        self._count = count
        self.scenes = scenes

    def __iter__(self):
        for i in range(self._count):
            idx = self._first + i
            yield idx.to_bytes(4, "big") + b"\0" * (FRAME_BYTES - 4)


def make_runner(calls=None, fail_on_chunk_start=None, scenes_at=None):
    def runner(video, start, length, geom, fps):
        if calls is not None:
            calls.append(start)
        if fail_on_chunk_start is not None and start >= fail_on_chunk_start:
            raise KeyboardInterrupt("simulated kill")
        scenes = [(t - start, s) for t, s in (scenes_at or []) if start <= t < start + length]
        return FakeDecode(round(start * fps), round(length * fps), scenes)
    return runner


def make_ocr(tier_by_secs):
    """tier_by_secs: {seconds: tier}; the banner is visible for 1.0 s from that time."""
    def ocr(data, w, h):
        idx = int.from_bytes(data[:4], "big")
        t = idx / FPS
        for start, tier in tier_by_secs.items():
            if start <= t < start + 1.0:
                return tier
        return None
    return ocr


def scan(tmp_path, tiers, duration=25.0, **kw):
    kw.setdefault("runner", make_runner())
    return ko_detect.scan_video(
        "fake.mp4", checkpoint_dir=str(tmp_path / "scan"), ocr_fn=make_ocr(tiers),
        duration=duration, size=(W, H), chunk_secs=10, overlap_secs=2, fps=FPS, workers=3, **kw,
    )


def chunk_files(tmp_path):
    d = tmp_path / "scan"
    return {p.name: p.read_bytes() for p in sorted(d.glob("chunk_*.json"))}


def test_roi_geometry_matches_crop_banner():
    from PIL import Image
    for w, h in ((1920, 1080), (2560, 1440), (40, 20)):
        cw, ch, x, y = ko_detect.roi_geometry(w, h)
        assert Image.new("L", (w, h)).crop((x, y, x + cw, y + ch)).size == ko_detect.crop_banner(Image.new("L", (w, h))).size
        assert x == int(w * ko_detect.CROP_X)


def test_every_grid_sample_appears_once_in_the_timeline(tmp_path):
    result = scan(tmp_path, {})
    times = [t for t, _ in result["timeline"]]
    assert times == [i / FPS for i in range(100)]
    assert all(tier is None for _, tier in result["timeline"])
    assert result["events"] == []


def test_checkpoint_has_one_file_per_chunk_and_no_tmp_left(tmp_path):
    scan(tmp_path, {})
    names = sorted(os.listdir(tmp_path / "scan"))
    assert [n for n in names if n.startswith("chunk_")] == ["chunk_0000.json", "chunk_0001.json", "chunk_0002.json"]
    assert not [n for n in names if n.endswith(".tmp")]


def test_no_22_second_cap_and_no_early_exit(tmp_path):
    result = scan(tmp_path, {3.0: "KO", 24.0: "QUAD"})
    assert [(e["ts"], e["tier"]) for e in result["events"]] == [(3.0, "KO"), (24.0, "QUAD")]


def test_banner_straddling_a_chunk_boundary_is_one_event(tmp_path):
    result = scan(tmp_path, {9.5: "DOUBLE"})
    assert [(e["ts"], e["tier"]) for e in result["events"]] == [(9.5, "DOUBLE")]


def test_cooldown_and_rank_rules_match_scan_clip(tmp_path, monkeypatch):
    tiers = {6.0: "KO", 7.0: "DOUBLE", 12.0: "TRIPLE", 18.0: "QUAD", 24.0: "KO"}
    long_result = scan(tmp_path, tiers)
    ocr = make_ocr(tiers)
    monkeypatch.setattr(ko_detect, "ocr_tier", lambda path: ocr(int(path).to_bytes(4, "big"), 0, 0))
    frames = [(i / FPS, str(i)) for i in range(100)]
    clip = ko_detect._scan_frames(frames, False, stop_early=False)
    assert long_result["events"][: len(clip["events"])] == clip["events"]


def test_resume_after_kill_gives_byte_identical_chunk_files(tmp_path):
    tiers = {3.0: "KO", 8.0: "DOUBLE", 14.0: "TRIPLE", 21.0: "QUAD"}
    clean_dir = tmp_path / "clean"
    clean_dir.mkdir()
    clean = scan(clean_dir, tiers)
    clean_files = chunk_files(clean_dir)

    with pytest.raises(KeyboardInterrupt):
        scan(tmp_path, tiers, runner=make_runner(fail_on_chunk_start=20))
    partial = chunk_files(tmp_path)
    assert sorted(partial) == ["chunk_0000.json", "chunk_0001.json"]
    (tmp_path / "scan" / "chunk_0002.json.tmp").write_text("garbage from a killed write")

    calls = []
    resumed = scan(tmp_path, tiers, runner=make_runner(calls=calls))
    assert calls == [20.0]
    assert chunk_files(tmp_path) == clean_files
    assert resumed["events"] == clean["events"]
    assert resumed["timeline"] == clean["timeline"]
    assert resumed["chunks_reused"] == 2


def test_stale_scanner_version_chunk_is_rescanned(tmp_path):
    scan(tmp_path, {})
    path = tmp_path / "scan" / "chunk_0001.json"
    data = json.loads(path.read_text())
    data["scanner_version"] = "old"
    path.write_text(json.dumps(data))
    calls = []
    scan(tmp_path, {}, runner=make_runner(calls=calls))
    assert calls == [10.0]


def test_chunk_with_different_parameters_is_rescanned(tmp_path):
    scan(tmp_path, {})
    calls = []
    ko_detect.scan_video(
        "fake.mp4", checkpoint_dir=str(tmp_path / "scan"), ocr_fn=make_ocr({}), duration=25.0,
        size=(W, H), chunk_secs=10, overlap_secs=3, fps=FPS, workers=2, runner=make_runner(calls=calls),
    )
    assert calls == [0.0, 10.0, 20.0]


def test_resume_false_rescans_everything(tmp_path):
    scan(tmp_path, {})
    calls = []
    scan(tmp_path, {}, runner=make_runner(calls=calls), resume=False)
    assert calls == [0.0, 10.0, 20.0]


def test_progress_callback_reports_every_chunk(tmp_path):
    seen = []
    scan(tmp_path, {}, progress=lambda done, total, info: seen.append((done, total, info["reused"])))
    assert seen == [(1, 3, False), (2, 3, False), (3, 3, False)]
    seen.clear()
    scan(tmp_path, {}, progress=lambda done, total, info: seen.append((done, total, info["reused"])))
    assert seen == [(1, 3, True), (2, 3, True), (3, 3, True)]


def test_scene_scores_are_recorded_with_video_time(tmp_path):
    result = scan(tmp_path, {}, runner=make_runner(scenes_at=[(12.5, 40.0), (1.0, 6.0)]))
    assert (12.5, 40.0) in [tuple(s) for s in result["scenes"]]
    assert (1.0, 6.0) in [tuple(s) for s in result["scenes"]]


def test_scene_scores_in_overlap_are_not_duplicated(tmp_path):
    result = scan(tmp_path, {}, runner=make_runner(scenes_at=[(10.5, 40.0)]))
    assert [tuple(s) for s in result["scenes"]].count((10.5, 40.0)) == 1


def test_ocr_exception_propagates_and_leaves_no_partial_chunk(tmp_path):
    def bad_ocr(data, w, h):
        raise RuntimeError("tesseract died")
    with pytest.raises(RuntimeError):
        ko_detect.scan_video(
            "fake.mp4", checkpoint_dir=str(tmp_path / "scan"), ocr_fn=bad_ocr, duration=25.0,
            size=(W, H), chunk_secs=10, overlap_secs=2, fps=FPS, workers=2, runner=make_runner(),
        )
    assert chunk_files(tmp_path) == {}


def test_missing_frames_raise_instead_of_checkpointing_a_gap(tmp_path):
    def short_runner(video, start, length, geom, fps):
        return FakeDecode(round(start * fps), 3, [])
    with pytest.raises(RuntimeError, match="frames"):
        scan(tmp_path, {}, runner=short_runner)
    assert chunk_files(tmp_path) == {}


def test_scan_clip_default_paths_untouched():
    assert ko_detect.SCAN_STOP_SECS == 22
    assert ko_detect.POST_KO_SILENCE_SECS == 16


# -- real ffmpeg on a tiny synthetic video -------------------------------------

def _ffmpeg():
    return ko_detect.FFMPEG if Path(ko_detect.FFMPEG).exists() else None


@pytest.mark.skipif(_ffmpeg() is None, reason="ffmpeg not available")
def test_real_ffmpeg_runner_on_synthetic_video(tmp_path):
    video = tmp_path / "synthetic.mp4"
    subprocess.run(
        [_ffmpeg(), "-y", "-loglevel", "error",
         "-f", "lavfi", "-i", "color=c=black:s=640x360:r=30:d=10",
         "-f", "lavfi", "-i", "color=c=white:s=640x360:r=30:d=10",
         "-filter_complex", "[0:v][1:v]concat=n=2:v=1:a=0[v]", "-map", "[v]",
         "-pix_fmt", "yuv420p", str(video)],
        check=True, creationflags=winproc.NO_WINDOW,
    )

    def bright_ocr(data, w, h):
        return "QUAD" if sum(data) / len(data) > 128 else None

    result = ko_detect.scan_video(
        str(video), checkpoint_dir=str(tmp_path / "scan"), ocr_fn=bright_ocr,
        chunk_secs=8, overlap_secs=2, fps=4, workers=2,
    )
    assert abs(result["duration"] - 20.0) < 0.2
    assert len(result["timeline"]) in (80, 79)
    assert [e["tier"] for e in result["events"]] == ["QUAD"]
    assert abs(result["events"][0]["ts"] - 10.0) <= 0.5
    peak = max(result["scenes"], key=lambda s: s[1])
    assert abs(peak[0] - 10.0) <= 0.5


# -- full-range gray and the TRIPLE-triggered rescan ---------------------------

@pytest.mark.skipif(_ffmpeg() is None, reason="ffmpeg not available")
def test_real_ffmpeg_roi_matches_png_pil_gray_for_coloured_banner(tmp_path):
    """The pipe must give the same luma as PNG then PIL convert('L') (what crop_banner OCRs)."""
    from PIL import Image
    video = tmp_path / "colour.mp4"
    subprocess.run(
        [_ffmpeg(), "-y", "-loglevel", "error", "-f", "lavfi", "-i", "color=c=0xf0a020:s=640x360:r=30:d=2",
         "-pix_fmt", "yuv420p", str(video)],
        check=True, creationflags=winproc.NO_WINDOW,
    )
    png = tmp_path / "f.png"
    subprocess.run([_ffmpeg(), "-y", "-loglevel", "error", "-i", str(video), "-frames:v", "1", str(png)],
                   check=True, creationflags=winproc.NO_WINDOW)
    want = ko_detect.crop_banner(Image.open(png)).convert("L").getpixel((5, 5))
    geom = ko_detect.roi_geometry(640, 360)
    frame = next(iter(ko_detect._ffmpeg_runner(str(video), 0.0, 1.0, geom, 2)))
    got = ko_detect._roi_to_gray(frame, geom[0], geom[1]).getpixel((5, 5))
    assert abs(got - want) <= 2


def rescan_runner(log):
    def runner(video, start, length, geom, fps):
        log.append((start, length, fps))
        return FakeDecode(round(start * fps), round(length * fps), [])
    return runner


def test_triple_triggers_local_high_fps_rescan_that_finds_quad(tmp_path):
    log = []
    # base grid sees TRIPLE at 12.0; the QUAD banner lasts 0.25 s at 15.5 and only the rescan grid can see it
    def ocr(data, w, h):
        t = int.from_bytes(data[:4], "big") / ko_detect.RESCAN_FPS if len(log) and log[-1][2] == ko_detect.RESCAN_FPS \
            else int.from_bytes(data[:4], "big") / FPS
        if 12.0 <= t < 12.5:
            return "TRIPLE"
        if 15.5 <= t < 15.75 and log[-1][2] == ko_detect.RESCAN_FPS:
            return "QUAD"
        return None
    # rescan frames carry idx = round(start*fps)+i, so t = idx / RESCAN_FPS is video time
    res = ko_detect.scan_video(
        "fake.mp4", checkpoint_dir=str(tmp_path / "scan"), ocr_fn=ocr, duration=25.0, size=(W, H),
        chunk_secs=10, overlap_secs=2, fps=FPS, workers=1, runner=rescan_runner(log))
    rescans = [c for c in log if c[2] == ko_detect.RESCAN_FPS]
    assert rescans and rescans[0][0] == pytest.approx(12.0, abs=1.0)
    assert rescans[0][1] == ko_detect.RESCAN_SECS
    assert [e["tier"] for e in res["events"]] == ["TRIPLE", "QUAD"]


def test_no_rescan_without_triple(tmp_path):
    log = []
    ko_detect.scan_video(
        "fake.mp4", checkpoint_dir=str(tmp_path / "scan"), ocr_fn=make_ocr({3.0: "DOUBLE"}), duration=25.0,
        size=(W, H), chunk_secs=10, overlap_secs=2, fps=FPS, workers=2, runner=rescan_runner(log))
    assert not [c for c in log if c[2] == ko_detect.RESCAN_FPS]
