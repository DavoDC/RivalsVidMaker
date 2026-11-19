"""Tests for format_check: parse yt-dlp -F tables, pick the best video format, compare with local files.

Every test injects a fake runner, so no test touches the network, runs yt-dlp or ffprobe, or writes
into a real OldCompilations folder. The -F fixture is the real output for iViRKtsnKu0 (no download).
"""

import json
from types import SimpleNamespace

import pytest

import format_check
from format_check import (
    FormatCheckError,
    compare,
    fetch_formats,
    parse_format_table,
    parse_local_probe,
    pick_best,
    probe_local,
    run_formats,
    run_process,
)
from oldcomp_guard import OldCompViolation

FIXTURE_TEXT = """[youtube] Extracting URL: https://www.youtube.com/watch?v=iViRKtsnKu0
[info] Available formats for iViRKtsnKu0:
ID  EXT   RESOLUTION FPS CH |   FILESIZE   TBR PROTO | VCODEC          VBR ACODEC      ABR ASR MORE INFO
---------------------------------------------------------------------------------------------------------------------
sb3 mhtml 48x27        0    |                  mhtml | images                                  storyboard
sb0 mhtml 320x180      0    |                  mhtml | images                                  storyboard
233 mp4   audio only        |                  m3u8  | audio only          unknown             [en] Default, high
139 m4a   audio only      2 |    3.49MiB   49k https | audio only          mp4a.40.5   49k 22k [en] low, m4a_dash
140 m4a   audio only      2 |    9.26MiB  129k https | audio only          mp4a.40.2  129k 44k [en] medium, m4a_dash
243 webm  640x360     30    |   31.54MiB  441k https | vp9            441k video only          360p, webm_dash
605 mp4   640x360     30    | ~145.03MiB 2028k m3u8  | vp09.00.21.08 2028k video only
18  mp4   640x360     30  2 |  41.29MiB  577k https | avc1.42001E         mp4a.40.2       44k [en] 360p
136 mp4   1280x720    30    |  120.01MiB 1678k https | avc1.64001F   1678k video only          720p, mp4_dash
298 mp4   1280x720    60    |  190.94MiB 2669k https | avc1.640020   2669k video only          720p60, mp4_dash
312 mp4   1920x1080   60    | ~482.26MiB 6742k m3u8  | avc1.64002A   6742k video only
299 mp4   1920x1080   60    |  304.71MiB 4260k https | avc1.64002A   4260k video only          1080p60, mp4_dash
"""


def result(stdout="", returncode=0, stderr=""):
    return SimpleNamespace(stdout=stdout, returncode=returncode, stderr=stderr)


def fixture_text():
    return FIXTURE_TEXT


def row(fid, width, height, fps, tbr, vcodec="avc1.64002A", protocol="https"):
    return {
        "format_id": fid, "ext": "mp4", "width": width, "height": height, "fps": fps,
        "tbr_kbps": tbr, "protocol": protocol, "vcodec": vcodec, "video_only": True,
    }


# ---- parse_format_table ----------------------------------------------------------------------

def test_parse_reads_real_video_rows_and_skips_headers_and_chatter():
    rows = parse_format_table(fixture_text())
    by_id = {r["format_id"]: r for r in rows}
    assert "ID" not in by_id and "sb3" in by_id  # header skipped, storyboard row present
    p299 = by_id["299"]
    assert (p299["width"], p299["height"], p299["fps"]) == (1920, 1080, 60)
    assert p299["tbr_kbps"] == 4260
    assert p299["protocol"] == "https"
    assert p299["vcodec"] == "avc1.64002A"
    assert p299["video_only"] is True


def test_parse_keeps_hls_protocol_and_audio_rows_without_resolution():
    by_id = {r["format_id"]: r for r in parse_format_table(fixture_text())}
    assert by_id["312"]["protocol"] == "m3u8"
    assert by_id["312"]["tbr_kbps"] == 6742
    assert by_id["140"]["width"] is None and by_id["140"]["height"] is None
    assert by_id["18"]["video_only"] is False  # combined audio+video format


def test_parse_ignores_lines_that_are_not_table_rows():
    assert parse_format_table("[youtube] hello\n[info] Available formats\n") == []


# ---- pick_best -------------------------------------------------------------------------------

def test_pick_best_prefers_hls_1080p60_by_bitrate_on_real_fixture():
    best = pick_best(parse_format_table(fixture_text()))
    assert best["format_id"] == "312"
    assert best["height"] == 1080 and best["tbr_kbps"] == 6742


def test_pick_best_codec_filter_drops_other_codecs():
    rows = parse_format_table(fixture_text())
    assert pick_best(rows, codec_prefix="avc1")["format_id"] == "312"
    assert pick_best(rows, codec_prefix="av01") is None


def test_pick_best_resolution_beats_bitrate():
    rows = [row("a", 1920, 1080, 60, 3000), row("b", 1280, 720, 60, 9000)]
    assert pick_best(rows)["format_id"] == "a"


def test_pick_best_bitrate_breaks_ties_within_a_resolution():
    rows = [row("a", 1920, 1080, 60, 4000), row("b", 1920, 1080, 60, 6000)]
    assert pick_best(rows)["format_id"] == "b"


def test_pick_best_ignores_storyboards_and_audio():
    rows = parse_format_table(fixture_text())
    assert pick_best([r for r in rows if r["format_id"].startswith(("sb", "139", "140"))]) is None


# ---- parse_local_probe -----------------------------------------------------------------------

def probe_json(**stream):
    base = {"codec_type": "video", "codec_name": "h264", "width": 1920, "height": 1080,
            "r_frame_rate": "60/1", "bit_rate": "4254000"}
    base.update(stream)
    return json.dumps({"streams": [{"codec_type": "audio", "codec_name": "aac"}, base]})


def test_parse_local_probe_reads_video_stream():
    info = parse_local_probe(probe_json())
    assert info == {"codec": "h264", "width": 1920, "height": 1080, "fps": 60.0, "vbitrate_kbps": 4254.0}


def test_parse_local_probe_missing_bitrate_is_none():
    info = parse_local_probe(probe_json(bit_rate=None))
    assert info["vbitrate_kbps"] is None


def test_parse_local_probe_without_video_stream_raises():
    with pytest.raises(FormatCheckError):
        parse_local_probe(json.dumps({"streams": [{"codec_type": "audio"}]}))


# ---- compare ---------------------------------------------------------------------------------

LOCAL = {"codec": "h264", "width": 1920, "height": 1080, "fps": 60.0, "vbitrate_kbps": 4254.0}


def test_compare_same_quality_is_not_flagged():
    out = compare(LOCAL, row("299", 1920, 1080, 60, 4260))
    assert out == {"flagged": False, "reasons": [], "unknown": []}


def test_compare_higher_bitrate_over_15_percent_is_flagged():
    out = compare(LOCAL, row("312", 1920, 1080, 60, 6742))
    assert out["flagged"] is True and out["reasons"] == ["bitrate"]


def test_compare_exactly_15_percent_is_not_flagged():
    local = dict(LOCAL, vbitrate_kbps=4000.0)
    assert compare(local, row("x", 1920, 1080, 60, 4600))["flagged"] is False
    assert compare(local, row("x", 1920, 1080, 60, 4601))["flagged"] is True


def test_compare_higher_resolution_is_flagged():
    out = compare(LOCAL, row("x", 2560, 1440, 60, 4000))
    assert out["flagged"] is True and out["reasons"] == ["resolution"]


def test_compare_higher_fps_is_flagged():
    out = compare(LOCAL, row("x", 1920, 1080, 120, 4000))
    assert out["flagged"] is True and out["reasons"] == ["fps"]


def test_compare_unknown_local_bitrate_is_reported_not_guessed():
    out = compare(dict(LOCAL, vbitrate_kbps=None), row("x", 1920, 1080, 60, 9000))
    assert out["flagged"] is False and out["unknown"] == ["bitrate"]


# ---- fetch_formats and run_process -----------------------------------------------------------

def test_fetch_formats_runs_F_only_with_js_runtime_and_no_download():
    calls = []

    def runner(args):
        calls.append(args)
        return result(stdout=fixture_text())

    text = fetch_formats("iViRKtsnKu0", runner, yt_dlp="yt-dlp.exe", js_runtime="node")
    assert "1920x1080" in text
    args = calls[0]
    assert "-F" in args and "--js-runtimes" in args and "node" in args
    assert not any(a in args for a in ("-f", "-o", "--output", "--skip-download", "-x"))


def test_fetch_formats_omits_js_runtime_flag_when_none():
    calls = []
    fetch_formats("iViRKtsnKu0", lambda a: calls.append(a) or result(stdout="x"), yt_dlp="y", js_runtime=None)
    assert "--js-runtimes" not in calls[0]


def test_fetch_formats_nonzero_exit_raises():
    with pytest.raises(FormatCheckError):
        fetch_formats("iViRKtsnKu0", lambda a: result(returncode=1, stderr="boom"), yt_dlp="y")


def test_run_process_hides_console_window(monkeypatch):
    seen = {}

    def fake_run(args, **kwargs):
        seen.update(kwargs)
        return result()

    monkeypatch.setattr(format_check.subprocess, "run", fake_run)
    run_process(["x"])
    assert seen["creationflags"] == format_check.winproc.NO_WINDOW


# ---- run_formats (orchestration, writes formats.json) ----------------------------------------

def make_pairs(tmp_path, n):
    oldcomp = tmp_path / "OldCompilations"
    oldcomp.mkdir()
    pairs = []
    for i in range(n):
        name = f"video_{i}.mp4"
        pairs.append({"youtube_id": f"id{i:02d}xxxxxxx", "filename": name, "local_path": oldcomp / name})
    return oldcomp, pairs


def fake_runner_factory(local_json, fail_ids=(), calls=None):
    def runner(args):
        if calls is not None:
            calls.append(args)
        if args[0] == "ffprobe_exe":
            return result(stdout=local_json)
        vid = args[-1].split("v=")[-1]
        if any(f in vid for f in fail_ids):
            return result(returncode=1, stderr="unavailable")
        return result(stdout=fixture_text())
    return runner


def test_run_formats_writes_table_and_paces_calls(tmp_path):
    oldcomp, pairs = make_pairs(tmp_path, 3)
    meta = tmp_path / "meta"
    meta.mkdir()
    sleeps = []
    calls = []
    summary = run_formats(
        pairs, meta / "formats.json", oldcomp_root=oldcomp,
        runner=fake_runner_factory(probe_json(), calls=calls), yt_dlp="yt", ffprobe="ffprobe_exe",
        js_runtime="node", sleep=sleeps.append, pause=2.0,
    )
    data = json.loads((meta / "formats.json").read_text(encoding="utf-8"))
    assert len(data["rows"]) == 3
    first = data["rows"][0]
    assert first["best"]["format_id"] == "312"
    assert first["comparison"]["flagged"] is True
    assert first["local"]["height"] == 1080
    assert summary["flagged_count"] == 3
    assert sleeps == [2.0, 2.0]  # paced between ids, not before the first


def test_run_formats_records_failed_id_and_continues(tmp_path):
    oldcomp, pairs = make_pairs(tmp_path, 3)
    meta = tmp_path / "meta"
    meta.mkdir()
    run_formats(pairs, meta / "formats.json", oldcomp_root=oldcomp,
                runner=fake_runner_factory(probe_json(), fail_ids=("id01",)), yt_dlp="yt",
                ffprobe="ffprobe_exe", js_runtime="node", sleep=lambda s: None, pause=0)
    rows = {r["youtube_id"]: r for r in json.loads((meta / "formats.json").read_text(encoding="utf-8"))["rows"]}
    assert "error" in rows["id01xxxxxxx"]
    assert rows["id02xxxxxxx"]["best"]["format_id"] == "312"


def test_run_formats_stops_after_three_consecutive_failures(tmp_path):
    oldcomp, pairs = make_pairs(tmp_path, 5)
    meta = tmp_path / "meta"
    meta.mkdir()
    calls = []
    with pytest.raises(FormatCheckError):
        run_formats(pairs, meta / "formats.json", oldcomp_root=oldcomp,
                    runner=fake_runner_factory(probe_json(), fail_ids=("id",), calls=calls),
                    yt_dlp="yt", ffprobe="ffprobe_exe", js_runtime="node", sleep=lambda s: None, pause=0)
    fcalls = [c for c in calls if "-F" in c]
    assert len(fcalls) == 3


def test_probe_local_asks_ffprobe_for_fields_the_parser_needs(tmp_path):
    # Fake ffprobe that returns only the keys named in -show_entries, as real ffprobe does.
    full = {"codec_type": "video", "codec_name": "h264", "width": 1920, "height": 1080,
            "r_frame_rate": "60/1", "bit_rate": "4254000"}
    calls = []

    def runner(args):
        calls.append(args)
        entries = args[args.index("-show_entries") + 1]
        wanted = entries.split("=", 1)[1].split(",")
        return result(stdout=json.dumps({"streams": [{k: v for k, v in full.items() if k in wanted}]}))

    info = probe_local(tmp_path / "x.mp4", runner, ffprobe="fp")
    assert info["height"] == 1080 and info["vbitrate_kbps"] == 4254.0
    assert info["codec"] == "h264" and info["fps"] == 60.0
    assert str(tmp_path / "x.mp4") in calls[0]


def test_run_formats_channel_only_id_gets_formats_but_no_local_probe(tmp_path):
    oldcomp, pairs = make_pairs(tmp_path, 1)
    pairs.append({"youtube_id": "TL2dmvkKv98", "filename": None, "local_path": None})
    meta = tmp_path / "meta"
    meta.mkdir()
    calls = []
    run_formats(pairs, meta / "formats.json", oldcomp_root=oldcomp,
                runner=fake_runner_factory(probe_json(), calls=calls), yt_dlp="yt",
                ffprobe="ffprobe_exe", js_runtime="node", sleep=lambda s: None, pause=0)
    rows = {r["youtube_id"]: r for r in json.loads((meta / "formats.json").read_text(encoding="utf-8"))["rows"]}
    extra = rows["TL2dmvkKv98"]
    assert extra["best"]["format_id"] == "312"
    assert extra["local"] is None and "comparison" not in extra
    assert sum(1 for c in calls if c[0] == "ffprobe_exe") == 1  # only the local file is probed


def test_run_formats_refuses_output_inside_oldcomp(tmp_path):
    oldcomp, pairs = make_pairs(tmp_path, 1)
    with pytest.raises(OldCompViolation):
        run_formats(pairs, oldcomp / "formats.json", oldcomp_root=oldcomp,
                    runner=fake_runner_factory(probe_json()), yt_dlp="yt", ffprobe="ffprobe_exe",
                    js_runtime="node", sleep=lambda s: None, pause=0)
    assert not (oldcomp / "formats.json").exists()
