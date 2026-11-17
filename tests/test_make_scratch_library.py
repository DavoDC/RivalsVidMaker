"""
Tests for scripts/make_scratch_library.py - the fake clip library for safe GUI runs.

Every test builds into pytest's tmp_path. Nothing here touches a real clips folder.
"""

import importlib.util
import json
import re
from pathlib import Path

import pytest

import clip_sorter
from config import load

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "make_scratch_library.py"
_spec = importlib.util.spec_from_file_location("make_scratch_library", SCRIPT)
mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mod)

NAME_RE = re.compile(r"^[A-Z][A-Z ]*_2026-11-01_\d{2}-\d{2}-\d{2}\.mp4$")
REAL_FFMPEG = mod.DEFAULT_FFMPEG_DIR / "ffmpeg.exe"


def fake_ffdir(tmp_path: Path) -> Path:
    """A folder holding a placeholder ffmpeg.exe, so main() passes its tool check."""
    ffdir = tmp_path / "ffbin"
    ffdir.mkdir(exist_ok=True)
    (ffdir / "ffmpeg.exe").write_bytes(b"")
    return ffdir


def fake_make_clip(ffmpeg, path, seconds):
    """Stands in for ffmpeg: writes an empty file where the real clip would go."""
    Path(path).write_bytes(b"")


def test_clip_names_match_pattern_and_sort_in_creation_order():
    names = mod.clip_names(10, 0, "THOR")
    assert len(names) == 10
    assert len(set(names)) == 10
    assert all(NAME_RE.match(n) for n in names)
    assert names == sorted(names)


def test_clip_names_continue_from_start_index():
    assert mod.clip_names(5, 5, "THOR") == mod.clip_names(10, 0, "THOR")[5:]


def test_clip_names_use_the_game_stem_for_the_character():
    assert mod.clip_names(1, 0, "SQUIRREL GIRL") == ["SQUIRREL GIRL_2026-11-01_10-00-00.mp4"]


def test_plan_names_covers_every_folder_with_its_layout_count():
    plan = mod.plan_names()
    assert list(plan) == list(mod.LAYOUT)
    for folder, count in mod.LAYOUT.items():
        assert len(plan[folder]) == count, folder


def test_plan_names_has_no_duplicate_names_or_timestamps():
    names = [n for group in mod.plan_names().values() for n in group]
    assert len(names) == 10
    assert len(set(names)) == 10


def test_plan_names_character_folders_use_the_folder_name():
    plan = mod.plan_names()
    assert all(n.startswith("THOR_") for n in plan["Highlights/THOR"])
    assert all(n.startswith("HELA_") for n in plan["Highlights/HELA"])


def test_every_planned_name_parses_to_its_folder_character():
    plan = mod.plan_names()
    for folder in ("Highlights/THOR", "Highlights/HELA"):
        expected = Path(folder).name
        for name in plan[folder]:
            assert clip_sorter.extract_character(Path(name).stem) == expected, name


def test_loose_character_list_matches_the_loose_folder_count():
    assert len(mod.LOOSE_CHARACTERS) == mod.LAYOUT["Highlights"]


def test_loose_names_parse_to_hela_squirrel_girl_thor_in_time_order():
    loose = mod.plan_names()["Highlights"]
    assert [clip_sorter.extract_character(Path(n).stem) for n in loose] == [
        "HELA", "SQUIRREL_GIRL", "THOR",
    ]
    assert loose == sorted(loose)


def test_sort_moves_two_loose_clips_and_keeps_the_newest(tmp_path):
    clips = tmp_path / "Highlights"
    clips.mkdir()
    loose = mod.plan_names()["Highlights"]
    for name in loose:
        (clips / name).write_bytes(b"")

    assert clip_sorter.sort_clips(clips, protect_recent=1) == 2
    assert (clips / "SQUIRREL_GIRL").is_dir()
    assert (clips / "HELA" / loose[0]).is_file()
    assert (clips / "SQUIRREL_GIRL" / loose[1]).is_file()
    assert (clips / loose[2]).is_file()


def test_layout_totals_ten_clips_in_expected_folders():
    counts = mod.layout()
    assert sum(counts.values()) == 10
    assert counts == {
        "Highlights": 3,
        "Highlights/THOR": 4,
        "Highlights/HELA": 3,
        "Output": 0,
        "ClipArchive": 0,
        "cache": 0,
    }


def test_config_dict_paths_all_sit_under_dest(tmp_path):
    dest = tmp_path / "scratch"
    cfg = mod.config_dict(dest, tmp_path / "ffmpeg")
    for key in ("clips_path", "output_path", "archive_path", "cache_dir", "state_path"):
        p = Path(cfg[key])
        assert p.is_absolute(), key
        assert p.resolve().is_relative_to(dest.resolve()), key
    assert Path(cfg["clips_path"]) == dest.resolve() / "Highlights"
    assert cfg["youtube_channel_id"] == "SCRATCH"


def test_config_dict_token_path_sits_under_dest_and_is_not_created(tmp_path):
    dest = tmp_path / "scratch"
    cfg = mod.config_dict(dest, tmp_path / "ffmpeg")
    token = Path(cfg["token_path"])
    assert token == dest.resolve() / "token.json"
    assert token.is_relative_to(dest.resolve())
    assert not token.exists()


def test_config_load_accepts_written_file(tmp_path):
    dest = tmp_path / "scratch"
    dest.mkdir()
    path = mod.write_config(dest, tmp_path / "ffmpeg")
    assert path == dest / "config.json"
    cfg = load(path)
    assert cfg.clips_path == dest.resolve() / "Highlights"
    assert cfg.output_path == dest.resolve() / "Output"
    assert cfg.archive_path == dest.resolve() / "ClipArchive"
    assert cfg.state_path == dest.resolve() / "state.json"
    assert cfg.youtube_channel_id == "SCRATCH"
    assert cfg.min_batch_seconds == 20
    assert cfg.target_batch_seconds == 40
    assert cfg.protect_recent_clips == 1
    assert cfg.force_rescan_cache is False


def test_check_dest_accepts_missing_folder(tmp_path):
    dest = tmp_path / "nope"
    assert mod.check_dest(dest, False) is None
    assert mod.check_dest(dest, True) is None


def test_check_dest_accepts_empty_folder(tmp_path):
    dest = tmp_path / "empty"
    dest.mkdir()
    assert mod.check_dest(dest, False) is None
    assert mod.check_dest(dest, True) is None


def test_check_dest_refuses_unmarked_folder_even_with_force(tmp_path):
    dest = tmp_path / "unmarked"
    dest.mkdir()
    (dest / "keep.txt").write_text("x", encoding="utf-8")
    for force in (False, True):
        reason = mod.check_dest(dest, force)
        assert isinstance(reason, str)
        assert "\n" not in reason


def test_check_dest_marked_folder_needs_force(tmp_path):
    dest = tmp_path / "marked"
    dest.mkdir()
    (dest / mod.MARKER).write_text("made by script", encoding="utf-8")
    assert isinstance(mod.check_dest(dest, False), str)
    assert mod.check_dest(dest, True) is None


def test_make_clip_builds_the_documented_ffmpeg_call(tmp_path, monkeypatch):
    seen = {}

    def fake_run(cmd, **kwargs):
        seen["cmd"] = cmd
        seen["kwargs"] = kwargs

    monkeypatch.setattr(mod.subprocess, "run", fake_run)
    out = tmp_path / "clip.mp4"
    mod.make_clip(tmp_path / "ffmpeg.exe", out, 1)
    cmd = seen["cmd"]
    assert cmd[0] == str(tmp_path / "ffmpeg.exe")
    assert cmd[-1] == str(out)
    assert "testsrc2=size=1280x720:rate=30" in cmd
    assert "sine=frequency=440" in cmd
    assert cmd[cmd.index("-t") + 1] == "1"
    assert seen["kwargs"]["timeout"] == 60


@pytest.mark.parametrize("force_args", [[], ["--force"]])
def test_main_refuses_non_empty_unmarked_folder(tmp_path, force_args):
    dest = tmp_path / "d"
    dest.mkdir()
    (dest / "keep.mp4").write_bytes(b"x")
    argv = [str(dest), "--ffmpeg-dir", str(fake_ffdir(tmp_path))] + force_args
    assert mod.main(argv) == 2
    assert (dest / "keep.mp4").exists()


def test_main_refuses_when_ffmpeg_missing_and_leaves_dest_alone(tmp_path):
    dest = tmp_path / "scratch"
    argv = [str(dest), "--ffmpeg-dir", str(tmp_path / "no-such-dir")]
    assert mod.main(argv) == 2
    assert not dest.exists()


def test_main_builds_then_rebuilds_only_with_force(tmp_path, monkeypatch):
    monkeypatch.setattr(mod, "make_clip", fake_make_clip)
    dest = tmp_path / "scratch"
    argv = [str(dest), "--ffmpeg-dir", str(fake_ffdir(tmp_path))]

    assert mod.main(argv) == 0
    assert len(list(dest.rglob("*.mp4"))) == 10
    assert (dest / mod.MARKER).is_file()
    assert json.loads((dest / "state.json").read_text(encoding="utf-8")) == {}
    assert (dest / "config.json").is_file()

    (dest / "stray.txt").write_text("old run", encoding="utf-8")
    assert mod.main(argv) == 2
    assert (dest / "stray.txt").exists()

    assert mod.main(argv + ["--force"]) == 0
    assert not (dest / "stray.txt").exists()
    assert len(list(dest.rglob("*.mp4"))) == 10


@pytest.mark.skipif(not REAL_FFMPEG.exists(), reason="ffmpeg.exe not found under dependencies/ffmpeg")
def test_end_to_end_builds_ten_real_clips(tmp_path):
    dest = tmp_path / "scratch"
    assert mod.main([str(dest), "--seconds", "1"]) == 0
    assert len(list(dest.rglob("*.mp4"))) == 10
    cfg = load(dest / "config.json")
    assert cfg.clips_path == dest.resolve() / "Highlights"
