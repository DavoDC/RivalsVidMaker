"""Tests for the fast long-scan profile of ko_ncc (hybrid lanes: CPU workers plus optional NVDEC workers).

Pure functions are tested directly; scan_video wiring is tested with a faked decode (no ffmpeg, no GPU).
The profile: -skip_frame noref, -skip_loop_filter all, balanced auto chunks, 10 fps, 4 CPU + 3 NVDEC workers,
NVDEC optional with a silent all-CPU fallback, and a per-chunk CPU fallback when an NVDEC decode fails.
"""

import numpy as np
import pytest

import ko_detect
import ko_ncc
from tests.test_ko_ncc import scored_once  # noqa: F401  (fixture reused)


# ---- pure helpers ----

def test_split_lanes_puts_nvdec_chunks_last_in_worker_proportion():
    assert ko_ncc.split_lanes(7, 4, 3) == ["cpu"] * 4 + ["nvdec"] * 3
    assert ko_ncc.split_lanes(14, 4, 3) == ["cpu"] * 8 + ["nvdec"] * 6


def test_split_lanes_without_nvdec_is_all_cpu():
    assert ko_ncc.split_lanes(5, 8, 0) == ["cpu"] * 5
    assert ko_ncc.split_lanes(0, 4, 3) == []
    assert ko_ncc.split_lanes(3, 0, 0) == ["cpu"] * 3


def test_split_lanes_never_exceeds_chunk_count():
    assert len(ko_ncc.split_lanes(2, 4, 3)) == 2


def test_chunk_len_auto_is_one_equal_chunk_per_worker():
    assert ko_ncc.chunk_len(130.0, 7) == 19.0                  # ceil(130 / 7)
    assert ko_ncc.chunk_len(7200.0, 7) == 1029.0
    assert ko_ncc.chunk_len(0.4, 7) == 1.0                     # never below 1 s
    assert ko_ncc.chunk_len(100.0, 0) == 100.0                 # zero workers counts as one


def test_chunk_len_numeric_is_used_as_is():
    assert ko_ncc.chunk_len(7200.0, 7, 60) == 60.0


def test_fast_profile_constants_match_the_benched_candidate():
    p = ko_ncc.FAST
    assert (p["fps"], p["cpu_workers"], p["nvdec_workers"], p["ffmpeg_threads"]) == (10, 4, 3, 1)
    assert p["skip_frame"] == "noref" and p["decoder_args"] == ["-skip_loop_filter", "all"]
    assert p["chunk_secs"] == "auto"


def test_decode_fast_command_flags_precede_input(monkeypatch):
    seen = {}

    class Done:
        returncode = 0
        stdout = b""
        stderr = b""

    monkeypatch.setattr(ko_ncc.subprocess, "run", lambda cmd, **kw: seen.setdefault("cmd", cmd) and Done())
    frames = ko_ncc.decode_fast("ffmpeg", "v.mp4", 3.0, 20.0, 10, (10, 10, 0, 0))
    cmd = seen["cmd"]
    i_in = cmd.index("-i")
    assert cmd[cmd.index("-skip_frame") + 1] == "noref" and cmd.index("-skip_frame") < i_in
    assert cmd[cmd.index("-skip_loop_filter") + 1] == "all" and cmd.index("-skip_loop_filter") < i_in
    assert cmd[cmd.index("-threads") + 1] == "1" and cmd.index("-threads") < i_in
    assert "fps=10,crop=10:10:0:0,format=gray" in cmd
    assert frames.shape == (0, 10, 10)


def test_nvdec_command_crop_order_is_top_bottom_left_right():
    cmd = ko_ncc.nvdec_cmd("ffmpeg", "v.mp4", 5.0, 30.0, 10, (116, 48, 1700, 500), (1920, 1080))
    assert cmd[cmd.index("-c:v") + 1] == "h264_cuvid"
    # top=500, bottom=1080-500-48=532, left=1700, right=1920-1700-116=104
    assert cmd[cmd.index("-crop") + 1] == "500x532x1700x104"
    assert cmd.index("-c:v") < cmd.index("-crop") < cmd.index("-i")       # decoder options sit before the input
    assert "fps=10,format=gray" in cmd                                     # crop is done in hardware
    assert cmd[cmd.index("-ss") + 1] == "5.000" and cmd[cmd.index("-t") + 1] == "30.000"


def test_nvdec_command_clamps_a_roi_past_the_frame_edge():
    cmd = ko_ncc.nvdec_cmd("ffmpeg", "v.mp4", 0.0, 10.0, 10, (116, 48, 1808, 500), (1920, 1080))
    assert cmd[cmd.index("-crop") + 1] == "500x532x1804x0"                 # x 1808 -> 1920-116, right edge 0
    cmd = ko_ncc.nvdec_cmd("ffmpeg", "v.mp4", 0.0, 10.0, 10, (116, 48, -4, -2), (1920, 1080))
    assert cmd[cmd.index("-crop") + 1].startswith("0x")                    # negative y clamps to 0


def test_nvdec_crop_with_odd_edges_is_refused():
    assert ko_ncc.nvdec_crop_ok((116, 48, 1804, 500), (1920, 1080)) is True
    assert ko_ncc.nvdec_crop_ok((117, 48, 1803, 500), (1920, 1080)) is False


# ---- GPU detection: no NVIDIA means silently no NVDEC ----

class _Run:
    def __init__(self, rc=0, out=b"", err=b""):
        self.returncode, self.stdout, self.stderr = rc, out, err


def test_nvdec_unavailable_when_decoder_not_listed(monkeypatch):
    ko_ncc.nvdec_available.cache_clear()
    monkeypatch.setattr(ko_ncc.subprocess, "run", lambda cmd, **kw: _Run(0, b" V..... h264  H.264\n"))
    assert ko_ncc.nvdec_available("ffmpeg-no-cuvid") is False


def test_nvdec_unavailable_when_probe_decode_fails(monkeypatch):
    ko_ncc.nvdec_available.cache_clear()

    def fake_run(cmd, **kw):
        if "-decoders" in cmd:
            return _Run(0, b" V..... h264_cuvid  Nvidia CUVID H264 decoder\n")
        return _Run(1, b"", b"CUDA_ERROR_NO_DEVICE")                    # decoder exists, no GPU present

    monkeypatch.setattr(ko_ncc.subprocess, "run", fake_run)
    assert ko_ncc.nvdec_available("ffmpeg-no-gpu") is False


def test_nvdec_unavailable_when_ffmpeg_missing_or_hangs(monkeypatch):
    ko_ncc.nvdec_available.cache_clear()

    def boom(cmd, **kw):
        raise FileNotFoundError(cmd[0])

    monkeypatch.setattr(ko_ncc.subprocess, "run", boom)
    assert ko_ncc.nvdec_available("nope") is False


def test_nvdec_available_when_listed_and_probe_decodes(monkeypatch):
    ko_ncc.nvdec_available.cache_clear()

    def fake_run(cmd, **kw):
        if "-decoders" in cmd:
            return _Run(0, b" V..... h264_cuvid  Nvidia CUVID H264 decoder\n")
        return _Run(0, b"h264-bytes")

    monkeypatch.setattr(ko_ncc.subprocess, "run", fake_run)
    assert ko_ncc.nvdec_available("ffmpeg-with-gpu") is True
    ko_ncc.nvdec_available.cache_clear()


# ---- scan_video wiring ----

def _factory(raw, hit_start, hit_end, tier, log):
    """Fakes for decode_fast / decode_nvdec (frames only) and legacy decode (frames, scenes); log records each call."""
    plan = ko_ncc.plan(1920, 1080, raw)
    cw, ch = plan["crop"][:2]
    blank = np.full((ch, cw), 10, np.uint8)
    crop = raw["crops"][tier][0]
    banner = blank.copy()
    banner[4:4 + crop.shape[0], 4:4 + crop.shape[1]] = crop

    def frames(start, length, fps):
        n = int(length * fps)
        return np.stack([banner if hit_start <= start + i / fps < hit_end else blank for i in range(n)])

    def fast(ffmpeg, video, start, length, fps, crop_box, *a, **k):
        log.append(("cpu", round(start, 3)))
        return frames(start, length, fps)

    def nv(ffmpeg, video, start, length, fps, crop_box, size, *a, **k):
        log.append(("nvdec", round(start, 3)))
        return frames(start, length, fps)

    def legacy(ffmpeg, video, start, length, fps, crop_box, *a, **k):
        log.append(("legacy", round(start, 3)))
        return frames(start, length, fps), [(0.5, 40.0)]
    return fast, nv, legacy


@pytest.fixture
def lanes_env(monkeypatch, scored_once):  # noqa: F811
    raw = ko_ncc.load_raw_bank()
    log = []
    fast, nv, legacy = _factory(raw, 70.0, 72.0, "QUAD", log)
    monkeypatch.setattr(ko_ncc, "decode_fast", fast)
    monkeypatch.setattr(ko_ncc, "decode_nvdec", nv)
    monkeypatch.setattr(ko_ncc, "decode", legacy)
    return monkeypatch, log, (fast, nv, legacy)


def _scan(tmp_path, **kw):
    return ko_detect.scan_video("fake.mp4", checkpoint_dir=str(tmp_path / "s"), duration=130.0,
                                size=(1920, 1080), detector="ncc", **kw)


def test_default_scan_without_nvidia_is_all_cpu_and_finds_the_event(tmp_path, lanes_env):
    mp, log, _ = lanes_env
    ko_ncc.nvdec_available.cache_clear()
    mp.setattr(ko_ncc, "nvdec_available", lambda ffmpeg: False)
    res = _scan(tmp_path)
    assert [e["tier"] for e in res["events"]] == ["QUAD"] and 69.9 <= res["events"][0]["ts"] <= 70.6
    assert {k for k, _ in log} == {"cpu"}
    assert res["fps"] == 10 and res["detector"] == "ncc"


def test_all_cpu_fallback_uses_eight_workers(tmp_path, lanes_env):
    mp, log, _ = lanes_env
    mp.setattr(ko_ncc, "nvdec_available", lambda ffmpeg: False)
    sizes = []
    real_pool = ko_detect.ThreadPoolExecutor

    class Rec(real_pool):
        def __init__(self, max_workers=None, *a, **k):
            sizes.append(max_workers)
            super().__init__(max_workers, *a, **k)

    mp.setattr(ko_detect, "ThreadPoolExecutor", Rec)
    res = _scan(tmp_path)
    assert sizes[0] == 8 and res["chunks"] == 8                     # ceil(130 / 8) = 17 s chunks, one per worker


def test_hybrid_scan_runs_four_cpu_and_three_nvdec_chunks_balanced(tmp_path, lanes_env):
    mp, log, _ = lanes_env
    mp.setattr(ko_ncc, "nvdec_available", lambda ffmpeg: True)
    res = _scan(tmp_path)
    assert res["chunks"] == 7                                        # ceil(130 / 7) = 19 s chunks
    lane_by_start = dict((s, k) for k, s in log)
    assert sorted(k for k, _ in log).count("cpu") == 4 and sorted(k for k, _ in log).count("nvdec") == 3
    assert [lane_by_start[s] for s in sorted(lane_by_start)] == ["cpu"] * 4 + ["nvdec"] * 3
    assert [e["tier"] for e in res["events"]] == ["QUAD"]


def test_nvdec_decode_failure_falls_back_to_cpu_per_chunk_without_error(tmp_path, lanes_env):
    mp, log, (fast, nv, legacy) = lanes_env
    mp.setattr(ko_ncc, "nvdec_available", lambda ffmpeg: True)

    def broken(*a, **k):
        raise RuntimeError("ffmpeg nvdec failed")

    mp.setattr(ko_ncc, "decode_nvdec", broken)
    res = _scan(tmp_path)
    assert res["chunks"] == 7 and {k for k, _ in log} == {"cpu"}    # all 7 chunks decoded, on the CPU
    assert [e["tier"] for e in res["events"]] == ["QUAD"]


def test_nvdec_false_disables_the_lane_even_when_a_gpu_exists(tmp_path, lanes_env):
    mp, log, _ = lanes_env
    mp.setattr(ko_ncc, "nvdec_available", lambda ffmpeg: True)
    _scan(tmp_path, nvdec=False)
    assert {k for k, _ in log} == {"cpu"}


def test_odd_roi_geometry_skips_the_nvdec_lane(tmp_path, lanes_env):
    mp, log, _ = lanes_env
    mp.setattr(ko_ncc, "nvdec_available", lambda ffmpeg: True)
    mp.setattr(ko_ncc, "nvdec_crop_ok", lambda crop, size: False)
    _scan(tmp_path)
    assert {k for k, _ in log} == {"cpu"}


def test_fast_scan_records_no_scenes_and_with_scenes_restores_the_legacy_path(tmp_path, lanes_env):
    mp, log, _ = lanes_env
    mp.setattr(ko_ncc, "nvdec_available", lambda ffmpeg: True)
    fast_res = _scan(tmp_path)
    assert fast_res["scenes"] == []                                  # documented loss: no scdet on the fast lanes
    log.clear()
    res = ko_detect.scan_video("fake.mp4", checkpoint_dir=str(tmp_path / "s2"), duration=130.0,
                               size=(1920, 1080), detector="ncc", with_scenes=True)
    assert {k for k, _ in log} == {"legacy"} and res["fps"] == 15
    assert res["chunks"] == 3                                        # 60 s chunks
    assert (0.5, 40.0) in [tuple(s) for s in res["scenes"]]
    assert [e["tier"] for e in res["events"]] == ["QUAD"]


def test_fast_scan_resumes_from_checkpoints_across_lanes(tmp_path, lanes_env):
    mp, log, _ = lanes_env
    mp.setattr(ko_ncc, "nvdec_available", lambda ffmpeg: True)
    _scan(tmp_path)

    def nope(*a, **k):
        raise AssertionError("redecoded")

    for name in ("decode_fast", "decode_nvdec", "decode"):
        mp.setattr(ko_ncc, name, nope)
    res = _scan(tmp_path)
    assert res["chunks_reused"] == res["chunks"] == 7 and res["events"][0]["tier"] == "QUAD"


def test_fast_checkpoint_is_not_reused_by_the_legacy_profile(tmp_path, lanes_env):
    mp, log, _ = lanes_env
    mp.setattr(ko_ncc, "nvdec_available", lambda ffmpeg: False)
    _scan(tmp_path)
    log.clear()
    res = _scan(tmp_path, with_scenes=True)
    assert res["chunks_reused"] == 0 and {k for k, _ in log} == {"legacy"}


def test_scanner_version_bumped_for_the_fast_profile():
    assert ko_detect.SCANNER_VERSION not in ("long-scan-2", "long-scan-3")


# ---- events are stamped at the run's PEAK frame (David 2026-11-20), both profiles ----

def _scores(rows):
    return np.array(rows, np.float32)


def test_peak_timeline_marks_only_the_peak_frame_of_each_run():
    tiers = ["TRIPLE", "QUAD"]
    s = _scores([[0, 0], [.9, .1], [.8, .2], [.1, .9], [.2, .95], [.1, .8], [0, 0]])
    runs = ko_ncc.runs_from_scores(s, tiers, fps=1)
    assert len(runs) == 1 and runs[0]["tier"] == "QUAD" and runs[0]["peak"] == 4
    tl = ko_ncc.peak_timeline(runs, total=len(s), fps=1)
    assert [(t, k) for t, k in tl if k] == [(4.0, "QUAD")] and len(tl) == len(s)


def test_single_tier_run_keeps_tier_and_count_and_lands_inside_the_run():
    s = _scores([[0, 0], [0, .7], [0, .9], [0, .6], [0, 0]])
    runs = ko_ncc.runs_from_scores(s, ["TRIPLE", "QUAD"], fps=1)
    ev = ko_detect._events_from_samples(ko_ncc.peak_timeline(runs, len(s), 1))
    assert [e["tier"] for e in ev] == ["QUAD"] and runs[0]["start"] <= ev[0]["ts"] <= runs[0]["end"]


def _banner_fake(raw, segments):
    """segments [(t0, t1, tier)]: frames inside a segment show that tier's banner, others are blank."""
    cw, ch = ko_ncc.plan(1920, 1080, raw)["crop"][:2]
    blank = np.full((ch, cw), 10, np.uint8)
    banners = {}
    for tier in {s[2] for s in segments}:
        b, c = blank.copy(), raw["crops"][tier][0]
        b[4:4 + c.shape[0], 4:4 + c.shape[1]] = c
        banners[tier] = b

    def frames(start, length, fps):
        out = []
        for i in range(int(length * fps)):
            t = start + i / fps
            out.append(next((banners[k] for a, b, k in segments if a <= t < b), blank))
        return np.stack(out)
    return frames


@pytest.mark.parametrize("with_scenes", [False, True])
def test_chained_triple_to_quad_run_is_stamped_at_the_quad(tmp_path, monkeypatch, scored_once, with_scenes):  # noqa: F811
    raw = ko_ncc.load_raw_bank()
    fr = _banner_fake(raw, [(60.0, 62.0, "TRIPLE"), (62.0, 66.0, "QUAD")])   # back to back: one hit run
    monkeypatch.setattr(ko_ncc, "decode", lambda f, v, s, l, fps, c, *a, **k: (fr(s, l, fps), []))
    monkeypatch.setattr(ko_ncc, "decode_fast", lambda f, v, s, l, fps, c, *a, **k: fr(s, l, fps))
    monkeypatch.setattr(ko_ncc, "nvdec_available", lambda ffmpeg: False)
    res = ko_detect.scan_video("fake.mp4", checkpoint_dir=str(tmp_path / "s"), duration=130.0,
                               size=(1920, 1080), detector="ncc", with_scenes=with_scenes)
    quad = [e for e in res["events"] if e["tier"] == "QUAD"]
    frames = fr(0.0, 130.0, res["fps"])                                      # the same frames the scan decoded
    bank = ko_ncc.plan(1920, 1080, raw)["bank"]
    runs = ko_ncc.runs_from_scores(ko_ncc.frame_scores(frames, bank), bank["tiers"], res["fps"])
    peak_t = [r["peak"] / res["fps"] for r in runs if r["tier"] == "QUAD"][0]
    assert len(quad) == 1 and quad[0]["ts"] == pytest.approx(peak_t, abs=1e-6)  # exactly the run's peak frame
    assert 62.0 <= peak_t <= 66.0 and peak_t != 60.0                         # not the run's first frame


def test_streak_grouping_with_peak_times_keeps_max_gap_semantics():
    from ko_streaks import build_streaks
    # peaks: DOUBLE 1113.0, TRIPLE 1120.5, QUAD 1131.2 -> one streak, start_ts and max_ts are the peaks
    s = build_streaks([{"ts": 1113.0, "tier": "DOUBLE"}, {"ts": 1120.5, "tier": "TRIPLE"}, {"ts": 1131.2, "tier": "QUAD"}])
    assert len(s) == 1 and s[0]["tier"] == "QUAD" and s[0]["max_ts"] == 1131.2 and s[0]["start_ts"] == 1113.0
    # a peak 25.4 s after the previous peak splits, 24.6 s does not (max_gap 25 s is measured peak to peak)
    assert len(build_streaks([{"ts": 100.0, "tier": "TRIPLE"}, {"ts": 124.6, "tier": "QUAD"}])) == 1
    assert len(build_streaks([{"ts": 100.0, "tier": "TRIPLE"}, {"ts": 125.4, "tier": "QUAD"}])) == 2


def test_rising_peaks_closer_than_the_cooldown_each_become_an_event():
    # thor4 held-out 262-268 s: QUAD peak 263.2 then PENTA peak 264.5 (1.3 s apart, inside COOLDOWN_SECS) must both be stamped
    tiers = ["TRIPLE", "QUAD", "PENTA", "HEXA"]
    runs = [{"tier": "QUAD", "peak": 2632}, {"tier": "PENTA", "peak": 2645}, {"tier": "HEXA", "peak": 2660}]
    ev = ko_detect._events_from_samples(ko_ncc.peak_timeline(runs, 2700, 10), rise_ignores_cooldown=True)
    assert [e["tier"] for e in ev] == ["QUAD", "PENTA", "HEXA"]
    # a same-tier or lower-tier peak inside the cooldown is still suppressed
    runs = [{"tier": "QUAD", "peak": 100}, {"tier": "QUAD", "peak": 110}, {"tier": "TRIPLE", "peak": 115}]
    ev = ko_detect._events_from_samples(ko_ncc.peak_timeline(runs, 200, 10), rise_ignores_cooldown=True)
    assert [e["tier"] for e in ev] == ["QUAD"]


# ---- reviewer fixes 2026-11-20: truncated decodes are never scored as zeros; a split banner is not a higher tier ----

def _short(fn, drop):
    """Wrap a decode fake so it returns `drop` frames fewer than asked (exit 0, truncated output)."""
    def wrapped(*a, **k):
        out = fn(*a, **k)
        return out[:len(out) - drop] if not isinstance(out, tuple) else (out[0][:len(out[0]) - drop], out[1])
    return wrapped


def test_nvdec_short_output_is_redone_on_the_cpu_lane(tmp_path, lanes_env):
    mp, log, (fast, nv, legacy) = lanes_env
    mp.setattr(ko_ncc, "nvdec_available", lambda ffmpeg: True)
    mp.setattr(ko_ncc, "decode_nvdec", _short(nv, 30))                # 3 s of the chunk missing
    res = _scan(tmp_path)
    assert {k for k, _ in log} == {"cpu", "nvdec"}
    assert sorted(k for k, _ in log).count("cpu") == 4 + 3           # the 3 truncated NVDEC chunks were redone on CPU
    assert [e["tier"] for e in res["events"]] == ["QUAD"]


def test_nvdec_output_within_tolerance_is_accepted(tmp_path, lanes_env):
    mp, log, (fast, nv, legacy) = lanes_env
    mp.setattr(ko_ncc, "nvdec_available", lambda ffmpeg: True)
    mp.setattr(ko_ncc, "decode_nvdec", _short(nv, 2))
    _scan(tmp_path)
    assert sorted(k for k, _ in log).count("cpu") == 4


def test_cpu_short_output_raises(tmp_path, lanes_env):
    mp, log, (fast, nv, legacy) = lanes_env
    mp.setattr(ko_ncc, "nvdec_available", lambda ffmpeg: False)
    mp.setattr(ko_ncc, "decode_fast", _short(fast, 30))
    with pytest.raises(RuntimeError, match="short"):
        _scan(tmp_path)


def test_legacy_short_output_raises(tmp_path, lanes_env):
    mp, log, (fast, nv, legacy) = lanes_env
    mp.setattr(ko_ncc, "decode", _short(legacy, 30))
    with pytest.raises(RuntimeError, match="short"):
        _scan(tmp_path, with_scenes=True)


def test_short_checkpoint_is_rescanned_not_reused(tmp_path, lanes_env):
    import json
    mp, log, _ = lanes_env
    mp.setattr(ko_ncc, "nvdec_available", lambda ffmpeg: False)
    _scan(tmp_path)
    ck = tmp_path / "s" / "chunk_0003.json"
    data = json.loads(ck.read_text(encoding="utf-8"))
    data["scores"] = data["scores"][:len(data["scores"]) // 2]
    ck.write_text(json.dumps(data), encoding="utf-8")
    log.clear()
    res = _scan(tmp_path)
    assert res["chunks_reused"] == res["chunks"] - 1 and len(log) == 1


def test_split_banner_misread_one_tier_higher_moments_later_is_not_a_new_event():
    runs = [{"tier": "TRIPLE", "peak": 100}, {"tier": "QUAD", "peak": 103}]      # 0.3 s apart at 10 fps
    ev = ko_detect._events_from_samples(ko_ncc.peak_timeline(runs, 200, 10), rise_ignores_cooldown=True)
    assert [e["tier"] for e in ev] == ["TRIPLE"]
    runs = [{"tier": "TRIPLE", "peak": 100}, {"tier": "QUAD", "peak": 113}]      # legit chain, 1.3 s apart
    ev = ko_detect._events_from_samples(ko_ncc.peak_timeline(runs, 200, 10), rise_ignores_cooldown=True)
    assert [e["tier"] for e in ev] == ["TRIPLE", "QUAD"]


def test_progress_reports_decode_and_score_seconds_per_chunk(tmp_path, lanes_env):
    mp, log, _ = lanes_env
    mp.setattr(ko_ncc, "nvdec_available", lambda ffmpeg: False)
    seen = []
    _scan(tmp_path, progress=lambda done, total, info: seen.append(info))
    assert seen
    for info in seen:
        assert info["decode_secs"] >= 0 and info["score_secs"] >= 0
        assert info["decode_secs"] + info["score_secs"] <= info["secs"] + 1e-6


# ---- weighted lane spans (BL-141): NVDEC lanes get longer chunks so every worker finishes together ----

def _covers(spans, duration):
    assert spans[0][0] == 0
    for (s0, l0, _), (s1, _, _) in zip(spans, spans[1:]):
        assert s0 + l0 == s1
    assert abs(spans[-1][0] + spans[-1][1] - duration) < 1e-9


def test_lane_spans_cover_the_video_contiguously_and_weight_nvdec_longer():
    spans = ko_ncc.lane_spans(903.1, 4, 3)
    _covers(spans, 903.1)
    assert [lane for _, _, lane in spans] == ["cpu"] * 4 + ["nvdec"] * 3
    cpu_len = {l for _, l, lane in spans if lane == "cpu"}
    nv_len = {l for _, l, lane in spans if lane == "nvdec"}
    assert max(cpu_len) < min(nv_len)
    assert min(nv_len) / max(cpu_len) == pytest.approx(ko_ncc.NVDEC_WEIGHT, rel=0.1)


def test_lane_spans_without_nvdec_equal_the_old_equal_chunks():
    spans = ko_ncc.lane_spans(130.0, 8, 0)
    _covers(spans, 130.0)
    assert all(lane == "cpu" for _, _, lane in spans)
    assert [round(l) for _, l, _ in spans[:-1]] == [17.0] * (len(spans) - 1)    # ceil(130 / 8)


def test_lane_spans_tiny_video_is_one_span():
    spans = ko_ncc.lane_spans(0.4, 4, 3)
    assert len(spans) == 1 and spans[0][0] == 0 and abs(spans[0][1] - 0.4) < 1e-9


def test_scan_decodes_the_weighted_spans(tmp_path, lanes_env):
    mp, log, _ = lanes_env
    mp.setattr(ko_ncc, "nvdec_available", lambda ffmpeg: True)
    spans = []
    real_nv = ko_ncc.decode_nvdec
    real_fast = ko_ncc.decode_fast

    def spy_nv(ffmpeg, video, start, length, *a, **k):
        spans.append((start, length, "nvdec")); return real_nv(ffmpeg, video, start, length, *a, **k)

    def spy_fast(ffmpeg, video, start, length, *a, **k):
        spans.append((start, length, "cpu")); return real_fast(ffmpeg, video, start, length, *a, **k)

    mp.setattr(ko_ncc, "decode_nvdec", spy_nv)
    mp.setattr(ko_ncc, "decode_fast", spy_fast)
    _scan(tmp_path)
    assert sorted(spans) == sorted(ko_ncc.lane_spans(130.0, 4, 3))
