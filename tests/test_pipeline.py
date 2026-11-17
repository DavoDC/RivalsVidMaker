"""Tests for the compile plan/apply split in pipeline.py.

plan_compile must rename and write nothing. apply_compile performs the file
work from a decisions dict and never prompts. run() is the terminal wrapper
and keeps its prompts.

Everything runs on tmp_path. Encoder, uploader, send2trash, KO scanning and
duplicate detection are patched, so no ffmpeg, Tesseract or YouTube call runs
and config/token.json is never touched.
"""
import builtins
import os
from pathlib import Path
from unittest.mock import MagicMock

import pytest

import pipeline
from clip_scanner import Clip
from config import Config

TARGET = 100
QUAD_CLIP = "THOR_2026-02-06_22-38-56.mp4"
KO_CLIP = "THOR_2026-02-07_18-00-00_KO.mp4"
DUP_CLIP = "THOR_2026-02-08_10-00-00.mp4"
LEFTOVER_CLIP = "THOR_2026-02-09_10-00-00.mp4"

# Batch 1 is QUAD (40) + KO (30) + DUP (20) = 90s. LEFTOVER (50s) starts batch 2.
DURATIONS = {
    QUAD_CLIP: 40.0,
    KO_CLIP: 30.0,
    DUP_CLIP: 20.0,
    LEFTOVER_CLIP: 50.0,
}


@pytest.fixture
def tree(tmp_path):
    clips_path = tmp_path / "Highlights"
    char_dir = clips_path / "THOR"
    char_dir.mkdir(parents=True)
    for name in DURATIONS:
        (char_dir / name).write_bytes(b"clip")
    cfg = MagicMock(spec=Config)
    cfg.clips_path = clips_path
    cfg.output_path = tmp_path / "Output"
    cfg.archive_path = tmp_path / "ClipArchive"
    cfg.ffmpeg = Path("ffmpeg")
    cfg.ffprobe = Path("ffprobe")
    cfg.tesseract = Path("tesseract")
    cfg.cache_dir = tmp_path / "cache"
    cfg.state_path = tmp_path / "state.json"
    cfg.target_batch_seconds = TARGET
    cfg.youtube_channel_id = "UCtestchannel"
    cfg.vlc_path = None
    cfg.protect_recent_clips = 0
    return cfg, char_dir


@pytest.fixture(autouse=True)
def no_real_io(monkeypatch):
    """Patch every external call. Any unexpected call to input() fails loudly."""
    trash = MagicMock(name="send2trash")
    monkeypatch.setattr(pipeline, "send2trash", trash)
    monkeypatch.setattr(os, "startfile", MagicMock(name="startfile"), raising=False)
    monkeypatch.setattr(pipeline.ko_detect, "configure", lambda **kwargs: None)
    monkeypatch.setattr(pipeline, "sort_clips", MagicMock(name="sort_clips"))
    monkeypatch.setattr(pipeline, "_print_multizone_status", lambda config: None)
    monkeypatch.setattr(pipeline, "load_state", lambda path: {})
    monkeypatch.setattr(
        pipeline, "summarize_folder", lambda folder, ffprobe, cache_dir=None: (3, 200.0)
    )
    monkeypatch.setattr(builtins, "input", _no_prompt)
    return trash


def _no_prompt(prompt=""):
    raise AssertionError(f"this path must not prompt, got: {prompt!r}")


@pytest.fixture
def fakes(tree, monkeypatch):
    """Patch the scan, KO, dedup, encode, description and upload calls."""
    cfg, char_dir = tree

    def fake_scan_folder(folder, ffprobe, workers=8, protect_recent=0, cache_dir=None):
        return [
            Clip(path=p, duration=DURATIONS[p.name])
            for p in sorted(Path(folder).iterdir())
            if p.suffix == ".mp4"
        ]

    def fake_ko_scan(clip_path, clip_name):
        if clip_name == QUAD_CLIP:
            return clip_name, {"tier": "QUAD", "start_ts": 5.0, "max_ts": 8.0}, 0.0, False
        return clip_name, None, 0.0, False

    def fake_find_duplicates(clips, *args, **kwargs):
        by_name = {c.name: c for c in clips}
        if QUAD_CLIP in by_name and DUP_CLIP in by_name:
            return [(by_name[QUAD_CLIP], by_name[DUP_CLIP], 2.5)]
        return []

    def fake_encode(batch, char_name, output_dir, ffmpeg, out_stem=None, force=False, on_progress=None):
        output_dir.mkdir(parents=True, exist_ok=True)
        out = output_dir / f"{out_stem}.mp4"
        out.write_bytes(b"video")
        return out

    def fake_write_description(batch, char_name, highlights, output_dir, out_stem=None, **kwargs):
        output_dir.mkdir(parents=True, exist_ok=True)
        desc = output_dir / f"{out_stem}_description.txt"
        desc.write_text("Title\n\nDescription", encoding="utf-8")
        return desc

    encode = MagicMock(name="encode", side_effect=fake_encode)
    monkeypatch.setattr(pipeline, "scan_folder", fake_scan_folder)
    monkeypatch.setattr(pipeline, "_ko_scan_one", fake_ko_scan)
    monkeypatch.setattr(pipeline, "find_duplicates", fake_find_duplicates)
    monkeypatch.setattr(pipeline, "print_dup_table", lambda pairs: None)
    monkeypatch.setattr(pipeline, "encode", encode)
    monkeypatch.setattr(pipeline, "write_description", MagicMock(side_effect=fake_write_description))
    monkeypatch.setattr(pipeline.uploader, "get_authenticated_service", MagicMock(return_value=object()))
    monkeypatch.setattr(pipeline.uploader, "validate_channel_id", MagicMock(return_value=True))
    monkeypatch.setattr(pipeline.uploader, "parse_description_file", MagicMock(return_value=("Title", "Desc")))
    monkeypatch.setattr(pipeline.uploader, "upload_and_save_state", MagicMock(return_value=None))
    token = cfg.output_path.parent / "token.json"
    monkeypatch.setattr(pipeline.uploader, "TOKEN_PATH", token)
    return {"encode": encode, "char_dir": char_dir, "cfg": cfg}


def _scripted_input(monkeypatch, answers):
    """Answer input() from a script and record each prompt text in order."""
    prompts = []
    remaining = iter(answers)

    def fake_input(prompt=""):
        prompts.append(prompt)
        return next(remaining)

    monkeypatch.setattr(builtins, "input", fake_input)
    return prompts


@pytest.fixture
def menu_pick(monkeypatch, tree):
    _cfg, char_dir = tree
    monkeypatch.setattr(
        pipeline, "pick_action",
        lambda *args, **kwargs: {"type": "compile", "folder": char_dir},
    )


# ── plan_compile ─────────────────────────────────────────────────────────────

class TestPlanCompile:
    def test_plan_renames_nothing(self, tree, fakes):
        cfg, char_dir = tree
        before = sorted(p.name for p in char_dir.iterdir())

        pipeline.plan_compile(cfg, char_dir, TARGET)

        assert sorted(p.name for p in char_dir.iterdir()) == before
        assert not (char_dir / "THOR_2026-02-06_22-38-56_QUAD.mp4").exists()

    def test_plan_carries_batches_tiers_durations_duplicates_and_low_value(self, tree, fakes):
        cfg, char_dir = tree

        plan = pipeline.plan_compile(cfg, char_dir, TARGET)

        assert plan.target_s == TARGET
        assert plan.character == "THOR"
        assert [b.number for b in plan.batches] == [1, 2]

        b1 = plan.batches[0]
        assert [c.name for c in b1.clips] == [QUAD_CLIP, KO_CLIP, DUP_CLIP]
        assert b1.duration_s == 90.0
        assert [c.duration_s for c in b1.clips] == [40.0, 30.0, 20.0]
        assert [c.start_s for c in b1.clips] == [0.0, 40.0, 70.0]
        assert [c.tier for c in b1.clips] == ["QUAD", None, None]
        assert [c.low_value for c in b1.clips] == [False, True, False]

        assert plan.low_value == [KO_CLIP]
        assert len(plan.duplicates) == 1
        dup = plan.duplicates[0]
        assert (dup.a, dup.b, dup.score) == (QUAD_CLIP, DUP_CLIP, 2.5)

        b2 = plan.batches[1]
        assert [c.name for c in b2.clips] == [LEFTOVER_CLIP]
        assert b2.clips[0].tier is None

    def test_plan_of_empty_folder_has_no_batches(self, tree, fakes, monkeypatch):
        cfg, char_dir = tree
        monkeypatch.setattr(pipeline, "scan_folder", lambda *a, **k: [])

        plan = pipeline.plan_compile(cfg, char_dir, TARGET)

        assert plan.batches == []
        assert plan.duplicates == []


# ── apply_compile ────────────────────────────────────────────────────────────

class TestApplyCompile:
    def test_default_decisions_compile_batch_one_renamed_and_within_target(self, tree, fakes):
        cfg, char_dir = tree
        plan = pipeline.plan_compile(cfg, char_dir, TARGET)

        result = pipeline.apply_compile(cfg, plan, {})

        assert result.compiled is True
        assert result.duration_s == 90.0
        assert result.duration_s <= TARGET
        encoded = fakes["encode"].call_args.args[0]
        assert [c.name for c in encoded.clips] == [
            "THOR_2026-02-06_22-38-56_QUAD.mp4", KO_CLIP, DUP_CLIP,
        ]
        assert (result.out_dir / "clips" / "THOR_2026-02-06_22-38-56_QUAD.mp4").exists()

    def test_low_value_archive_moves_clip_to_archive(self, tree, fakes):
        cfg, char_dir = tree
        plan = pipeline.plan_compile(cfg, char_dir, TARGET)

        result = pipeline.apply_compile(cfg, plan, {"clips": {KO_CLIP: "archive"}})

        assert result.compiled is True
        assert (cfg.archive_path / "THOR" / KO_CLIP).exists()
        assert not (char_dir / KO_CLIP).exists()
        encoded = fakes["encode"].call_args.args[0]
        assert KO_CLIP not in [c.name for c in encoded.clips]

    def test_low_value_recycle_sends_clip_to_trash(self, tree, fakes, no_real_io):
        cfg, char_dir = tree
        plan = pipeline.plan_compile(cfg, char_dir, TARGET)

        result = pipeline.apply_compile(cfg, plan, {"clips": {KO_CLIP: "recycle"}})

        assert result.compiled is True
        no_real_io.assert_called_once_with(str(char_dir / KO_CLIP))
        assert not (cfg.archive_path / "THOR" / KO_CLIP).exists()

    def test_duplicate_drop_leaves_clip_in_highlights(self, tree, fakes):
        cfg, char_dir = tree
        plan = pipeline.plan_compile(cfg, char_dir, TARGET)

        result = pipeline.apply_compile(cfg, plan, {"clips": {DUP_CLIP: "drop"}})

        assert result.compiled is True
        encoded = fakes["encode"].call_args.args[0]
        assert DUP_CLIP not in [c.name for c in encoded.clips]
        assert (char_dir / DUP_CLIP).exists()

    def test_extra_adds_leftover_clips_in_order(self, tree, fakes):
        cfg, char_dir = tree
        plan = pipeline.plan_compile(cfg, char_dir, TARGET)

        result = pipeline.apply_compile(cfg, plan, {"extra": 1})

        assert result.duration_s == 140.0
        encoded = fakes["encode"].call_args.args[0]
        assert [c.name for c in encoded.clips][-1] == LEFTOVER_CLIP

    def test_all_clips_removed_does_file_work_and_no_encode(self, tree, fakes):
        cfg, char_dir = tree
        plan = pipeline.plan_compile(cfg, char_dir, TARGET)
        decisions = {"clips": {KO_CLIP: "archive", QUAD_CLIP: "drop", DUP_CLIP: "drop"}}

        result = pipeline.apply_compile(cfg, plan, decisions)

        assert result.compiled is False
        assert (cfg.archive_path / "THOR" / KO_CLIP).exists()
        fakes["encode"].assert_not_called()

    def test_force_and_on_progress_reach_encoder(self, tree, fakes):
        cfg, char_dir = tree
        plan = pipeline.plan_compile(cfg, char_dir, TARGET)
        progress = MagicMock(name="on_progress")

        pipeline.apply_compile(cfg, plan, {}, force=True, on_progress=progress)

        kwargs = fakes["encode"].call_args.kwargs
        assert kwargs["force"] is True
        assert kwargs["on_progress"] is progress

    def test_channel_mismatch_keeps_token(self, tree, fakes, monkeypatch, caplog):
        cfg, char_dir = tree
        token = pipeline.uploader.TOKEN_PATH
        token.write_text("{}", encoding="utf-8")
        monkeypatch.setattr(
            pipeline.uploader, "get_authenticated_service",
            MagicMock(side_effect=ValueError("channel mismatch")),
        )
        plan = pipeline.plan_compile(cfg, char_dir, TARGET)

        with caplog.at_level("WARNING"):
            result = pipeline.apply_compile(cfg, plan, {})

        assert token.exists()
        assert result.needs_sign_in is True
        assert result.uploaded is False
        assert result.upload_failed is False
        assert "Token kept" in caplog.text
        assert "Auto-deleting" not in caplog.text

    def test_upload_error_is_reported_as_upload_failed(self, tree, fakes, monkeypatch):
        cfg, char_dir = tree
        monkeypatch.setattr(
            pipeline.uploader, "upload_and_save_state",
            MagicMock(side_effect=Exception("network down")),
        )
        plan = pipeline.plan_compile(cfg, char_dir, TARGET)

        result = pipeline.apply_compile(cfg, plan, {})

        assert result.uploaded is False
        assert result.upload_failed is True
        assert result.needs_sign_in is False
        assert result.video_path.exists()


# ── run() terminal wrapper ───────────────────────────────────────────────────

class TestRunPrompts:
    def test_run_reaches_every_prompt_in_order(self, tree, fakes, menu_pick, monkeypatch):
        cfg, _char_dir = tree
        prompts = _scripted_input(monkeypatch, ["y", "y", "y", "y"])

        pipeline.run(cfg)

        assert prompts[0].startswith("  [y] include  [a] archive to ClipArchive  [d] delete")
        assert prompts[1] == "Happy with this video length? [Y/n]: "
        assert prompts[2] == "Make this video? [y/N]: "
        assert prompts[3] == "Suspected duplicates found. Continue anyway? [y/N]: "
        assert len(prompts) == 4
        assert (cfg.output_path / "THOR_Feb_2026_BATCH1" / "THOR_Feb_2026_BATCH1.mp4").exists()

    def test_run_archive_then_cancel_at_make_video_touches_nothing(self, tree, fakes, menu_pick, monkeypatch):
        cfg, char_dir = tree
        _scripted_input(monkeypatch, ["a", "y", "n"])

        pipeline.run(cfg)

        assert (char_dir / KO_CLIP).exists()
        assert not (cfg.archive_path / "THOR" / KO_CLIP).exists()
        fakes["encode"].assert_not_called()

    def test_run_dry_run_renames_nothing_and_writes_nothing(self, tree, fakes, menu_pick, monkeypatch):
        cfg, char_dir = tree
        before = sorted(p.name for p in char_dir.iterdir())
        _scripted_input(monkeypatch, ["y", "y", "y"])

        pipeline.run(cfg, dry_run=True)

        assert sorted(p.name for p in char_dir.iterdir()) == before
        assert not any(p.stem.endswith("_QUAD") for p in char_dir.iterdir())
        fakes["encode"].assert_not_called()
        assert not any(cfg.output_path.rglob("*.mp4"))

    def test_run_upload_failure_still_asks_to_re_authenticate(self, tree, fakes, menu_pick, monkeypatch):
        cfg, _char_dir = tree
        monkeypatch.setattr(
            pipeline.uploader, "upload_and_save_state",
            MagicMock(side_effect=Exception("network down")),
        )
        prompts = _scripted_input(monkeypatch, ["y", "y", "y", "y", "n"])

        pipeline.run(cfg)

        assert prompts[-1] == "Delete token.json and re-authenticate? [y/N]: "
