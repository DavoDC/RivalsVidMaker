"""Tests for channel_fetch: list the channel, match local stems to it, fetch descriptions, write the inventory.

Every test injects a fake runner, so no test touches the network or runs yt-dlp or ffprobe.
Output folders are under tmp_path, and OLDCOMP_ROOT is pointed at a fake OldCompilations folder.
"""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import channel_fetch
from channel_fetch import (
    FetchError,
    ChannelListError,
    fetch_all,
    fetch_description,
    list_channel,
    match_local,
    normalise_title,
    run_inventory,
    run_process,
)
from oldcomp_guard import OldCompViolation


def result(stdout="", returncode=0, stderr=""):
    return SimpleNamespace(stdout=stdout, returncode=returncode, stderr=stderr)


class FakeRunner:
    """Records every call and answers from a handler(args) -> result."""

    def __init__(self, handler=None):
        self.calls = []
        self.handler = handler or (lambda args: result())

    def __call__(self, args):
        self.calls.append(list(args))
        return self.handler(args)


@pytest.fixture
def fake_root(tmp_path, monkeypatch):
    """A stand-in for Videos\\MarvelRivals. OLDCOMP_ROOT points at its OldCompilations folder."""
    root = tmp_path / "MarvelRivals"
    old = root / "OldCompilations"
    old.mkdir(parents=True)
    monkeypatch.setattr(channel_fetch, "OLDCOMP_ROOT", old)
    return root, old


LIST_STDOUT = (
    "TL2dmvkKv98\tTHOR BRINGS THE HAMMER\t1152\n"
    "iViRKtsnKu0\tTHOR HIGHLIGHTS, MULTIKILLS [FEB-MAY 2025]\t1180.0\n"
    "ASXqiYEaFTA\tTHOR UNLEASHED ⚡ Relentless Multikills (Sep 2025) ｜ Part 4\tNA\n"
)


# ---- list_channel ----------------------------------------------------------------------------

def test_list_channel_builds_flat_playlist_command_and_parses_rows():
    runner = FakeRunner(lambda args: result(LIST_STDOUT))
    rows = list_channel("https://www.youtube.com/@dave369_/videos", runner, yt_dlp="yt-dlp.exe")
    args = runner.calls[0]
    assert args[0] == "yt-dlp.exe"
    assert "--flat-playlist" in args
    assert args[args.index("--print") + 1] == "%(id)s\t%(title)s\t%(duration)s"
    assert args[-1] == "https://www.youtube.com/@dave369_/videos"
    assert [r["id"] for r in rows] == ["TL2dmvkKv98", "iViRKtsnKu0", "ASXqiYEaFTA"]
    assert rows[1] == {"id": "iViRKtsnKu0", "title": "THOR HIGHLIGHTS, MULTIKILLS [FEB-MAY 2025]", "duration": 1180.0}
    assert rows[2]["duration"] is None  # NA means unknown


def test_list_channel_raises_on_nonzero_exit():
    runner = FakeRunner(lambda args: result("", returncode=1, stderr="ERROR: boom"))
    with pytest.raises(ChannelListError):
        list_channel("https://www.youtube.com/@dave369_/videos", runner, yt_dlp="yt-dlp.exe")


def test_list_channel_skips_blank_lines():
    runner = FakeRunner(lambda args: result("\n" + LIST_STDOUT + "\n\n"))
    assert len(list_channel("u", runner, yt_dlp="yt-dlp.exe")) == 3


def test_run_process_hides_console_window(monkeypatch):
    seen = {}

    def fake_run(args, **kwargs):
        seen.update(kwargs)
        return SimpleNamespace(stdout="", returncode=0, stderr="")

    monkeypatch.setattr(channel_fetch.subprocess, "run", fake_run)
    run_process(["yt-dlp.exe", "--version"])
    assert seen["creationflags"] == channel_fetch.winproc.NO_WINDOW
    assert seen["capture_output"] is True


# ---- normalise_title -------------------------------------------------------------------------

def test_normalise_strips_date_prefix_case_and_punctuation():
    assert normalise_title("2025-05-18_THOR HIGHLIGHTS, MULTIKILLS [FEB-MAY 2025]") == normalise_title(
        "thor highlights multikills feb may 2025"
    )


def test_normalise_treats_full_width_pipe_as_ascii_pipe_or_space():
    a = normalise_title("THOR UNLEASHED ｜ Part 4")
    b = normalise_title("THOR UNLEASHED Part 4")
    assert a == b


def test_normalise_drops_emoji_and_variation_selectors():
    assert normalise_title("THOR ⚡ Multikill \U0001f43f️ Highlights") == normalise_title(
        "thor multikill highlights"
    )


def test_normalise_keeps_digits_and_letters_only():
    assert normalise_title("2025-10-01_THOR (Sep 2025)") == "thor sep 2025"


# ---- match_local -----------------------------------------------------------------------------

ROWS = [
    {"id": "iViRKtsnKu0", "title": "THOR HIGHLIGHTS, MULTIKILLS [FEB-MAY 2025]", "duration": 1180.0},
    {"id": "AAAAAAAAAAA", "title": "THOR HIGHLIGHTS, MULTIKILLS [FEB-MAY 2025]", "duration": 1000.0},
    {"id": "ASXqiYEaFTA", "title": "THOR UNLEASHED ⚡ Relentless Multikills (Sep 2025) ｜ Part 4", "duration": 2100.0},
]


def test_match_local_matches_on_title_with_date_prefix_stripped():
    matched, unmatched = match_local(["2025-10-01_THOR UNLEASHED Relentless Multikills (Sep 2025) Part 4"], ROWS[2:])
    assert unmatched == []
    assert matched == [
        {"stem": "2025-10-01_THOR UNLEASHED Relentless Multikills (Sep 2025) Part 4",
         "youtube_id": "ASXqiYEaFTA", "title": ROWS[2]["title"], "duration": 2100.0}
    ]


def test_match_local_duration_within_two_seconds_picks_the_right_duplicate():
    stems = ["2025-05-18_THOR HIGHLIGHTS, MULTIKILLS [FEB-MAY 2025]"]
    matched, unmatched = match_local(stems, ROWS, local_durations={stems[0]: 1181.5})
    assert [m["youtube_id"] for m in matched] == ["iViRKtsnKu0"]
    assert unmatched == []


def test_match_local_duration_outside_two_seconds_is_unmatched():
    stems = ["2025-05-18_THOR HIGHLIGHTS, MULTIKILLS [FEB-MAY 2025]"]
    matched, unmatched = match_local(stems, ROWS[:1], local_durations={stems[0]: 1184.0})
    assert matched == []
    assert unmatched[0]["stem"] == stems[0]
    assert "duration" in unmatched[0]["reason"]


def test_match_local_without_duration_on_two_duplicates_is_ambiguous():
    stems = ["2025-05-18_THOR HIGHLIGHTS, MULTIKILLS [FEB-MAY 2025]"]
    matched, unmatched = match_local(stems, ROWS[:2])
    assert matched == []
    assert unmatched[0]["reason"] == "ambiguous"


def test_match_local_no_title_is_unmatched_with_reason():
    matched, unmatched = match_local(["2025-01-01_SOMETHING ELSE"], ROWS)
    assert matched == []
    assert unmatched == [{"stem": "2025-01-01_SOMETHING ELSE", "reason": "no title match"}]


def test_match_local_never_reuses_a_channel_row():
    stems = ["2025-05-18_THOR HIGHLIGHTS, MULTIKILLS [FEB-MAY 2025]",
             "2025-05-19_THOR HIGHLIGHTS, MULTIKILLS [FEB-MAY 2025]"]
    matched, unmatched = match_local(stems, ROWS[:1])
    assert len(matched) == 1
    assert len(unmatched) == 1


# ---- fetch_description -----------------------------------------------------------------------

def writes_info_json(args):
    """Fake yt-dlp: write <id>.info.json where the -o template points, as the real tool does."""
    template = args[args.index("-o") + 1]
    video_id = args[-1].split("v=")[1]
    out = Path(template.replace("%(id)s", video_id) + ".info.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"id": video_id, "description": "Line one\nLine two\n"}), encoding="utf-8")
    return result()


def test_fetch_description_runs_skip_download_and_writes_description(tmp_path):
    out_dir = tmp_path / "channel"
    runner = FakeRunner(writes_info_json)
    status = fetch_description("iViRKtsnKu0", out_dir, runner, yt_dlp="yt-dlp.exe")
    assert status == "fetched"
    args = runner.calls[0]
    assert "--skip-download" in args and "--write-info-json" in args
    assert args[-1] == "https://www.youtube.com/watch?v=iViRKtsnKu0"
    assert (out_dir / "iViRKtsnKu0" / "iViRKtsnKu0.info.json").exists()
    assert (out_dir / "iViRKtsnKu0" / "description.txt").read_text(encoding="utf-8") == "Line one\nLine two\n"


def test_fetch_description_skips_when_description_exists(tmp_path):
    folder = tmp_path / "channel" / "iViRKtsnKu0"
    folder.mkdir(parents=True)
    (folder / "description.txt").write_text("already here", encoding="utf-8")
    runner = FakeRunner()
    assert fetch_description("iViRKtsnKu0", tmp_path / "channel", runner, yt_dlp="yt-dlp.exe") == "skipped"
    assert runner.calls == []


def test_fetch_description_builds_from_existing_info_json_without_network(tmp_path):
    folder = tmp_path / "channel" / "iViRKtsnKu0"
    folder.mkdir(parents=True)
    (folder / "iViRKtsnKu0.info.json").write_text(json.dumps({"description": "from disk"}), encoding="utf-8")
    runner = FakeRunner()
    assert fetch_description("iViRKtsnKu0", tmp_path / "channel", runner, yt_dlp="yt-dlp.exe") == "fetched"
    assert runner.calls == []
    assert (folder / "description.txt").read_text(encoding="utf-8") == "from disk"


def test_fetch_description_raises_when_yt_dlp_fails(tmp_path):
    runner = FakeRunner(lambda args: result("", returncode=1, stderr="ERROR: unavailable"))
    with pytest.raises(FetchError):
        fetch_description("iViRKtsnKu0", tmp_path / "channel", runner, yt_dlp="yt-dlp.exe")
    assert not (tmp_path / "channel" / "iViRKtsnKu0" / "description.txt").exists()


def test_fetch_description_refuses_output_inside_oldcomp(fake_root):
    _, old = fake_root
    runner = FakeRunner(writes_info_json)
    with pytest.raises(OldCompViolation):
        fetch_description("iViRKtsnKu0", old / "channel", runner, yt_dlp="yt-dlp.exe")
    assert runner.calls == []


# ---- fetch_all -------------------------------------------------------------------------------

def test_fetch_all_stops_after_three_consecutive_failures(tmp_path):
    ids = [f"id{i:09d}" for i in range(10)]
    runner = FakeRunner(lambda args: result("", returncode=1, stderr="ERROR"))
    sleeps = []
    summary = fetch_all(ids, tmp_path / "channel", runner, yt_dlp="yt-dlp.exe", sleep=sleeps.append)
    assert len(runner.calls) == 3
    assert summary["stopped"] is True
    assert summary["failed"] == ["id000000000", "id000000001", "id000000002"]


def test_fetch_all_failure_count_resets_on_success(tmp_path):
    ids = ["fail0000001", "fail0000002", "okay0000003", "fail0000004", "fail0000005", "okay0000006"]
    outcomes = {"fail0000001": 1, "fail0000002": 1, "okay0000003": 0, "fail0000004": 1, "fail0000005": 1,
                "okay0000006": 0}

    def handler(args):
        vid = args[-1].split("v=")[1]
        if outcomes[vid]:
            return result("", returncode=1, stderr="ERROR")
        return writes_info_json(args)

    runner = FakeRunner(handler)
    summary = fetch_all(ids, tmp_path / "channel", runner, yt_dlp="yt-dlp.exe", sleep=lambda s: None)
    assert summary["stopped"] is False
    assert len(runner.calls) == 6
    assert summary["fetched"] == ["okay0000003", "okay0000006"]


def test_fetch_all_paces_two_seconds_between_network_calls(tmp_path):
    ids = ["aaaaaaaaaa1", "aaaaaaaaaa2", "aaaaaaaaaa3"]
    runner = FakeRunner(writes_info_json)
    sleeps = []
    summary = fetch_all(ids, tmp_path / "channel", runner, yt_dlp="yt-dlp.exe", sleep=sleeps.append)
    assert summary["fetched"] == ids
    assert sleeps == [2.0, 2.0]


def test_fetch_all_is_resumable_and_skipped_videos_do_not_sleep(tmp_path):
    channel = tmp_path / "channel"
    (channel / "aaaaaaaaaa1").mkdir(parents=True)
    (channel / "aaaaaaaaaa1" / "description.txt").write_text("done", encoding="utf-8")
    runner = FakeRunner(writes_info_json)
    sleeps = []
    summary = fetch_all(["aaaaaaaaaa1", "aaaaaaaaaa2"], channel, runner, yt_dlp="yt-dlp.exe", sleep=sleeps.append)
    assert summary["skipped"] == ["aaaaaaaaaa1"]
    assert summary["fetched"] == ["aaaaaaaaaa2"]
    assert len(runner.calls) == 1
    assert sleeps == []


# ---- run_inventory ---------------------------------------------------------------------------

def make_local(old):
    names = [
        "2025-05-18_THOR HIGHLIGHTS, MULTIKILLS [FEB-MAY 2025].mp4",
        "2025-10-01_THOR UNLEASHED ⚡ Relentless Multikills (Sep 2025) ｜ Part 4.mp4",
    ]
    for n in names:
        (old / n).write_bytes(b"x" * 64)
    (old / "notes.txt").write_text("not a video", encoding="utf-8")
    return names


def dispatching_runner(list_stdout, durations=None):
    durations = durations or {}

    def handler(args):
        tool = Path(args[0]).name.lower()
        if tool.startswith("yt-dlp"):
            return result(list_stdout)
        if tool.startswith("ffprobe"):
            path = args[-1]
            return result(f"{durations[Path(path).name]}\n")
        raise AssertionError(f"unexpected tool {args[0]}")

    return FakeRunner(handler)


def test_run_inventory_writes_channel_index_and_source(fake_root, tmp_path):
    _, old = fake_root
    make_local(old)
    meta = tmp_path / "meta"
    runner = dispatching_runner(LIST_STDOUT, durations={
        "2025-05-18_THOR HIGHLIGHTS, MULTIKILLS [FEB-MAY 2025].mp4": 1181.0,
        "2025-10-01_THOR UNLEASHED ⚡ Relentless Multikills (Sep 2025) ｜ Part 4.mp4": 2100.2,
    })
    summary = run_inventory(old, meta, runner=runner, yt_dlp="yt-dlp.exe", ffprobe="ffprobe.exe")
    index = json.loads((meta / "channel_index.json").read_text(encoding="utf-8"))
    source = json.loads((meta / "source.json").read_text(encoding="utf-8"))
    assert index["count"] == 3
    assert [r["id"] for r in index["rows"]] == ["TL2dmvkKv98", "iViRKtsnKu0", "ASXqiYEaFTA"]
    assert source["local_count"] == 2
    assert source["matched_count"] == 2
    ids = {v["stem"]: v["youtube_id"] for v in source["videos"]}
    assert ids["2025-05-18_THOR HIGHLIGHTS, MULTIKILLS [FEB-MAY 2025]"] == "iViRKtsnKu0"
    assert ids["2025-10-01_THOR UNLEASHED ⚡ Relentless Multikills (Sep 2025) ｜ Part 4"] == "ASXqiYEaFTA"
    assert summary["matched_count"] == 2


def test_run_inventory_lists_mp4_only_and_never_changes_local_dir(fake_root, tmp_path):
    _, old = fake_root
    make_local(old)

    def snapshot():
        return sorted((p.name, p.stat().st_size, p.stat().st_mtime_ns) for p in old.iterdir())

    before = snapshot()
    runner = dispatching_runner(LIST_STDOUT, durations={})
    run_inventory(old, tmp_path / "meta", runner=runner, yt_dlp="yt-dlp.exe")
    assert snapshot() == before
    source = json.loads((tmp_path / "meta" / "source.json").read_text(encoding="utf-8"))
    assert source["local_count"] == 2  # notes.txt is not a video


def test_run_inventory_without_ffprobe_matches_on_title_only(fake_root, tmp_path):
    _, old = fake_root
    make_local(old)
    runner = dispatching_runner(LIST_STDOUT)
    run_inventory(old, tmp_path / "meta", runner=runner, yt_dlp="yt-dlp.exe")
    assert not any(Path(c[0]).name.lower().startswith("ffprobe") for c in runner.calls)


def test_run_inventory_refuses_meta_inside_oldcomp(fake_root):
    _, old = fake_root
    make_local(old)
    runner = dispatching_runner(LIST_STDOUT)
    with pytest.raises(OldCompViolation):
        run_inventory(old, old / "meta", runner=runner, yt_dlp="yt-dlp.exe")
    assert not (old / "meta").exists()


def test_default_paths_point_at_the_meta_folder_outside_oldcomp():
    assert channel_fetch.OLDCOMP_META_DEFAULT.name == "OldCompilationsMeta"
    assert channel_fetch.OLDCOMP_META_DEFAULT.parent == channel_fetch.OLDCOMP_ROOT.parent
    assert channel_fetch.CHANNEL_URL == "https://www.youtube.com/@dave369_/videos"
