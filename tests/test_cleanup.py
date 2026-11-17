"""
Tests for cleanup.py - interactive post-YouTube output folder cleanup.

All tests use tmp_path; no real filesystem paths are required.
User prompts are patched out so tests are fully non-interactive.
"""

from pathlib import Path
from unittest.mock import patch

import pytest

from cleanup import (
    FATE_ARCHIVE,
    FATE_RECYCLE,
    FATE_RECYCLE_VIDEO,
    FATE_REMOVE_EMPTY_FOLDER,
    FolderNotConfirmed,
    PlanChanged,
    _tier_from_name,
    _fmt_size,
    apply_cleanup,
    plan_cleanup,
    restrict_plan,
    run_cleanup,
)
from state import mark_youtube_confirmed, save as save_state


@pytest.fixture(autouse=True)
def fake_trash():
    """send2trash is always patched: a call unlinks the file and is recorded, nothing reaches a real Recycle Bin."""
    def _trash(path):
        Path(path).unlink()
    with patch("cleanup.send2trash", side_effect=_trash) as mock:
        yield mock


# ── _tier_from_name ───────────────────────────────────────────────────────────

class TestTierFromName:

    def test_quad(self):
        assert _tier_from_name("THOR_2026-02-06_22-38-56_QUAD.mp4") == "QUAD"

    def test_penta(self):
        assert _tier_from_name("THOR_2026-02-06_22-38-56_PENTA.mp4") == "PENTA"

    def test_hexa(self):
        assert _tier_from_name("THOR_2026-02-06_22-38-56_HEXA.mp4") == "HEXA"

    def test_triple(self):
        assert _tier_from_name("THOR_2026-02-06_22-38-56_TRIPLE.mp4") == "TRIPLE"

    def test_no_tier(self):
        assert _tier_from_name("THOR_2026-02-06_22-38-56.mp4") is None

    def test_case_insensitive(self):
        # The regex is case-insensitive; result is always upper
        assert _tier_from_name("THOR_2026-02-06_quad.mp4") == "QUAD"


# ── _fmt_size ─────────────────────────────────────────────────────────────────

class TestFmtSize:

    def test_returns_mb_string(self, tmp_path):
        f = tmp_path / "video.mp4"
        f.write_bytes(b"x" * 1024 * 1024)  # exactly 1 MB
        result = _fmt_size(f)
        assert "MB" in result
        assert "1.0" in result

    def test_missing_file_returns_unknown(self, tmp_path):
        assert _fmt_size(tmp_path / "missing.mp4") == "unknown size"


# ── run_cleanup ───────────────────────────────────────────────────────────────

def _make_output_folder(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    """Create a standard output folder structure and return key paths."""
    out = tmp_path / "THOR_Feb-Mar_2026"
    out.mkdir()
    clips_dir = out / "clips"
    clips_dir.mkdir()
    mp4 = out / "THOR_Feb-Mar_2026.mp4"
    mp4.write_bytes(b"compiled video")
    return out, clips_dir, mp4, tmp_path / "ClipArchive"


class TestRunCleanupMissingFolder:

    def test_nonexistent_folder_logs_error(self, tmp_path, caplog):
        import logging
        archive = tmp_path / "ClipArchive"
        with caplog.at_level(logging.ERROR):
            run_cleanup(tmp_path / "MISSING", archive)
        assert any("not found" in r.message.lower() for r in caplog.records)


class TestRunCleanupArchiving:

    def test_quad_clip_moved_to_archive_when_confirmed(self, tmp_path):
        out, clips_dir, mp4, archive = _make_output_folder(tmp_path)
        quad_clip = clips_dir / "THOR_2026-02-06_22-38-56_QUAD.mp4"
        quad_clip.write_bytes(b"quad data")

        # Confirm YT, confirm archive, decline delete, decline video delete
        with patch("builtins.input", side_effect=["y", "y", "n", "n"]):
            run_cleanup(out, archive, state_path=out.parent / "state.json")

        assert (archive / "THOR" / quad_clip.name).exists()
        assert not quad_clip.exists()

    def test_quad_clip_stays_when_archiving_declined(self, tmp_path):
        out, clips_dir, mp4, archive = _make_output_folder(tmp_path)
        quad_clip = clips_dir / "THOR_2026-02-06_22-38-56_QUAD.mp4"
        quad_clip.write_bytes(b"quad data")

        # Confirm YT, decline archive, decline delete, decline video delete
        with patch("builtins.input", side_effect=["y", "n", "n", "n"]):
            run_cleanup(out, archive, state_path=out.parent / "state.json")

        assert quad_clip.exists()
        assert not archive.exists()

    def test_archive_skips_existing_destination(self, tmp_path):
        out, clips_dir, mp4, archive = _make_output_folder(tmp_path)
        quad_clip = clips_dir / "THOR_2026-02-06_22-38-56_QUAD.mp4"
        quad_clip.write_bytes(b"source")
        archive.mkdir()
        existing = archive / quad_clip.name
        existing.write_bytes(b"already archived")

        with patch("builtins.input", side_effect=["y", "y", "n", "n"]):
            run_cleanup(out, archive, state_path=out.parent / "state.json")

        # Existing archive file is not overwritten
        assert existing.read_bytes() == b"already archived"


class TestRunCleanupDeletion:

    def test_remaining_clips_deleted_when_confirmed(self, tmp_path):
        out, clips_dir, mp4, archive = _make_output_folder(tmp_path)
        clip = clips_dir / "THOR_2026-02-06_22-38-56.mp4"
        clip.write_bytes(b"no tier")

        # Confirm YT, no quad+ to archive, confirm delete, decline video delete
        with patch("builtins.input", side_effect=["y", "y", "n"]):
            run_cleanup(out, archive, state_path=out.parent / "state.json")

        assert not clip.exists()

    def test_remaining_clips_kept_when_deletion_declined(self, tmp_path):
        out, clips_dir, mp4, archive = _make_output_folder(tmp_path)
        clip = clips_dir / "THOR_2026-02-06_22-38-56.mp4"
        clip.write_bytes(b"no tier")

        with patch("builtins.input", side_effect=["y", "n", "n"]):
            run_cleanup(out, archive, state_path=out.parent / "state.json")

        assert clip.exists()

    def test_quad_plus_not_in_remaining_after_archive(self, tmp_path):
        """After archiving, Quad+ clips must not appear in the deletion list."""
        out, clips_dir, mp4, archive = _make_output_folder(tmp_path)
        quad = clips_dir / "THOR_2026-02-06_22-38-56_QUAD.mp4"
        quad.write_bytes(b"quad")
        plain = clips_dir / "THOR_2026-02-07_18-00-00.mp4"
        plain.write_bytes(b"plain")

        # Confirm YT, confirm archive, confirm delete remaining, decline video delete
        with patch("builtins.input", side_effect=["y", "y", "y", "n"]):
            run_cleanup(out, archive, state_path=out.parent / "state.json")

        assert (archive / "THOR" / quad.name).exists()
        assert not plain.exists()


class TestRunCleanupVideoFile:

    def test_compiled_mp4_deleted_when_confirmed(self, tmp_path):
        out, clips_dir, mp4, archive = _make_output_folder(tmp_path)

        # Confirm YT, no clips: skip archive, skip deletion, confirm video delete
        with patch("builtins.input", side_effect=["y", "y"]):
            run_cleanup(out, archive, state_path=out.parent / "state.json")

        assert not mp4.exists()

    def test_compiled_mp4_kept_when_declined(self, tmp_path):
        out, clips_dir, mp4, archive = _make_output_folder(tmp_path)

        with patch("builtins.input", side_effect=["y", "n"]):
            run_cleanup(out, archive, state_path=out.parent / "state.json")

        assert mp4.exists()

    def test_no_mp4_section_when_no_video(self, tmp_path):
        """If no compiled .mp4 exists, cleanup completes without prompting for it."""
        out, clips_dir, mp4, archive = _make_output_folder(tmp_path)
        mp4.unlink()

        # YT confirmation fires, then nothing else (no clips, no video)
        with patch("builtins.input", side_effect=["y"]) as mock_input:
            run_cleanup(out, archive, state_path=out.parent / "state.json")
        assert mock_input.call_count == 1


class TestRunUncompile:

    def test_uncompile_deletes_clips_json(self, tmp_path):
        """run_uncompile() should delete clips.json manifest during cleanup."""
        from cleanup import run_uncompile
        from pathlib import Path
        import json

        # Create output folder with clips and clips.json
        out_folder = tmp_path / "THOR_MAR_2026"
        out_folder.mkdir()
        clips_dir = out_folder / "clips"
        clips_dir.mkdir()

        # Create a clip file
        clip = clips_dir / "THOR_2026-03-01_12-00-00_QUAD.mp4"
        clip.write_bytes(b"fake video")

        # Create clips.json manifest
        clips_json = out_folder / "clips.json"
        clips_json.write_text(json.dumps({"clips": ["THOR_2026-03-01_12-00-00_QUAD.mp4"]}))

        # Create highlights folder
        highlights = tmp_path / "Highlights"
        (highlights / "THOR").mkdir(parents=True)

        # Run uncompile with confirmation
        with patch("builtins.input", return_value="y"):
            with patch("cleanup.send2trash") as mock_trash:
                with patch("builtins.print"):  # Suppress emoji print
                    run_uncompile(out_folder, highlights)
                # Verify clips.json was sent to trash
                calls = [str(call) for call in mock_trash.call_args_list]
                assert any("clips.json" in call for call in calls), \
                    f"clips.json not sent to trash. Calls: {calls}"


# ── retry_upload (unified retry path) ─────────────────────────────────────────

from types import SimpleNamespace


def _make_retry_folder(tmp_path: Path) -> Path:
    """Output folder holding a compiled .mp4 and a description file."""
    out = tmp_path / "THOR_Feb-Mar_2026"
    out.mkdir()
    (out / "THOR_Feb-Mar_2026.mp4").write_bytes(b"compiled video")
    (out / "THOR_Feb-Mar_2026_description.txt").write_text("Title line\n\nBody", encoding="utf-8")
    return out


def _retry_config(tmp_path: Path):
    return SimpleNamespace(youtube_channel_id="UCtestchannel", state_path=tmp_path / "state.json")


class TestRetryUploadUnified:

    def test_confirm_false_never_calls_input(self, tmp_path):
        import cleanup
        out = _make_retry_folder(tmp_path)
        with patch("builtins.input", side_effect=AssertionError("input must not be called")), \
             patch("uploader.get_authenticated_service", return_value=object()), \
             patch("uploader.validate_channel_id"), \
             patch("uploader.parse_description_file", return_value=("Title", "Body")), \
             patch("uploader.upload_and_save_state") as mock_upload, \
             patch("builtins.print"):
            result = cleanup.retry_upload(out, _retry_config(tmp_path), confirm=False)
        assert mock_upload.call_count == 1
        assert result.uploaded is True

    def test_confirm_true_asks_first_and_cancel_skips_upload(self, tmp_path):
        import cleanup
        out = _make_retry_folder(tmp_path)
        with patch("builtins.input", return_value="n") as mock_input, \
             patch("uploader.get_authenticated_service") as mock_auth, \
             patch("uploader.upload_and_save_state") as mock_upload, \
             patch("builtins.print"):
            result = cleanup.retry_upload(out, _retry_config(tmp_path), confirm=True)
        assert mock_input.call_count == 1
        mock_auth.assert_not_called()
        mock_upload.assert_not_called()
        assert result.uploaded is False
        assert result.cancelled is True

    def test_auth_value_error_returns_needs_sign_in_and_keeps_token(self, tmp_path):
        import cleanup
        import uploader
        out = _make_retry_folder(tmp_path)
        token = tmp_path / "token.json"
        token.write_text('{"type": "authorized_user"}', encoding="utf-8")
        with patch("uploader.TOKEN_PATH", token), \
             patch("uploader.get_authenticated_service",
                   side_effect=ValueError("Could not retrieve channel info from YouTube")), \
             patch("uploader.upload_and_save_state") as mock_upload, \
             patch("uploader.parse_description_file", return_value=("Title", "Body")), \
             patch("builtins.print"):
            result = cleanup.retry_upload(out, _retry_config(tmp_path), confirm=False)
        assert result.needs_sign_in is True
        assert result.uploaded is False
        assert token.exists(), "auth failure must not delete the token file"
        mock_upload.assert_not_called()

    def test_channel_mismatch_value_error_keeps_token(self, tmp_path):
        import cleanup
        out = _make_retry_folder(tmp_path)
        token = tmp_path / "token.json"
        token.write_text('{"type": "authorized_user"}', encoding="utf-8")
        with patch("uploader.TOKEN_PATH", token), \
             patch("uploader.get_authenticated_service", return_value=object()), \
             patch("uploader.validate_channel_id", side_effect=ValueError("Channel mismatch")), \
             patch("uploader.parse_description_file", return_value=("Title", "Body")), \
             patch("builtins.print"):
            result = cleanup.retry_upload(out, _retry_config(tmp_path), confirm=False)
        assert result.needs_sign_in is True
        assert token.exists()

    def test_upload_value_error_is_not_an_auth_failure(self, tmp_path):
        import cleanup
        out = _make_retry_folder(tmp_path)
        token = tmp_path / "token.json"
        token.write_text('{"type": "authorized_user"}', encoding="utf-8")
        with patch("uploader.TOKEN_PATH", token), \
             patch("uploader.get_authenticated_service", return_value=object()), \
             patch("uploader.validate_channel_id"), \
             patch("uploader.parse_description_file", return_value=("Title", "Body")), \
             patch("uploader.upload_and_save_state", side_effect=ValueError("Upload failed: 500")), \
             patch("builtins.print"):
            result = cleanup.retry_upload(out, _retry_config(tmp_path), confirm=False)
        assert result.needs_sign_in is False
        assert result.uploaded is False
        assert "500" in result.error
        assert token.exists()

    def test_missing_video_returns_error_without_auth(self, tmp_path):
        import cleanup
        out = _make_retry_folder(tmp_path)
        (out / "THOR_Feb-Mar_2026.mp4").unlink()
        with patch("uploader.get_authenticated_service") as mock_auth, \
             patch("builtins.print"):
            result = cleanup.retry_upload(out, _retry_config(tmp_path), confirm=False)
        mock_auth.assert_not_called()
        assert result.uploaded is False
        assert result.error


class TestPipelineRetryDelegates:

    def test_pipeline_retry_delegates_to_cleanup_without_prompt(self, tmp_path):
        import cleanup
        import pipeline
        out = _make_retry_folder(tmp_path)
        config = _retry_config(tmp_path)
        with patch.object(cleanup, "retry_upload",
                          return_value=cleanup.RetryResult(uploaded=True)) as mock_retry:
            pipeline._retry_youtube_upload(out, config)
        mock_retry.assert_called_once_with(out, config, confirm=False)


# ── plan_cleanup / apply_cleanup ──────────────────────────────────────────────

QUAD = "THOR_2026-02-06_22-38-56_QUAD.mp4"
PENTA = "THOR_2026-02-07_10-00-00_PENTA.mp4"
HEXA = "THOR_2026-02-08_10-00-00_HEXA.mp4"
PLAIN = "THOR_2026-02-09_10-00-00.mp4"


def _build_tree(tmp_path: Path):
    """Output folder with Quad+ clips, one plain clip, the compiled video, a description and clips.json."""
    out, clips_dir, mp4, archive = _make_output_folder(tmp_path)
    for name in (QUAD, PENTA, HEXA, PLAIN):
        (clips_dir / name).write_bytes(b"clip " + name.encode())
    desc = out / "THOR_Feb-Mar_2026_description.txt"
    desc.write_text("Title\n\nBody", encoding="utf-8")
    clips_json = out / "clips.json"
    clips_json.write_text("{}", encoding="utf-8")
    return out, clips_dir, mp4, archive, desc, clips_json


def _live_state(tmp_path: Path, folder_name: str) -> Path:
    path = tmp_path / "state.json"
    save_state(mark_youtube_confirmed({"output_folders": {}}, folder_name), path)
    return path


def _tree_fingerprint(root: Path) -> list:
    """Every path under root with its kind, size and mtime. Equal fingerprints mean nothing changed."""
    rows = []
    for p in sorted(root.rglob("*")):
        st = p.stat()
        rows.append((str(p.relative_to(root)), p.is_dir(), st.st_size, st.st_mtime_ns))
    return rows


class TestPlanCleanup:

    def test_every_file_gets_a_fate(self, tmp_path):
        out, clips_dir, mp4, archive, desc, clips_json = _build_tree(tmp_path)
        plan = plan_cleanup(out, archive)
        fates = {a.path.name: a.fate for a in plan.actions}
        assert fates[QUAD] == FATE_ARCHIVE
        assert fates[PENTA] == FATE_ARCHIVE
        assert fates[HEXA] == FATE_ARCHIVE
        assert fates[PLAIN] == FATE_RECYCLE
        assert fates[desc.name] == FATE_RECYCLE
        assert fates["clips.json"] == FATE_RECYCLE
        assert fates["clips"] == FATE_REMOVE_EMPTY_FOLDER
        assert mp4.name not in fates, "compiled video is planned only with include_video"
        assert out.name not in fates, "output folder keeps the compiled video, so it stays"
        quad_action = next(a for a in plan.actions if a.path.name == QUAD)
        assert quad_action.dest == archive / "THOR" / QUAD

    def test_include_video_adds_recycle_video(self, tmp_path):
        out, clips_dir, mp4, archive, desc, clips_json = _build_tree(tmp_path)
        plan = plan_cleanup(out, archive, include_video=True)
        video = [a for a in plan.actions if a.fate == FATE_RECYCLE_VIDEO]
        assert [a.path for a in video] == [mp4]
        assert any(a.fate == FATE_REMOVE_EMPTY_FOLDER and a.path == out for a in plan.actions), \
            "with the video planned, nothing is left in the output folder"

    def test_planning_changes_nothing(self, tmp_path, fake_trash):
        out, clips_dir, mp4, archive, desc, clips_json = _build_tree(tmp_path)
        before = _tree_fingerprint(tmp_path)
        plan_cleanup(out, archive, include_video=True)
        assert _tree_fingerprint(tmp_path) == before
        assert not archive.exists()
        fake_trash.assert_not_called()

    def test_quad_with_existing_archive_copy_is_kept_not_recycled(self, tmp_path):
        out, clips_dir, mp4, archive, desc, clips_json = _build_tree(tmp_path)
        (archive / "THOR").mkdir(parents=True)
        (archive / "THOR" / QUAD).write_bytes(b"already archived")
        plan = plan_cleanup(out, archive)
        assert QUAD in plan.skipped
        assert all(a.path.name != QUAD for a in plan.actions)


class TestApplyCleanup:

    def test_apply_performs_exactly_the_planned_operations(self, tmp_path, fake_trash):
        out, clips_dir, mp4, archive, desc, clips_json = _build_tree(tmp_path)
        plan = plan_cleanup(out, archive)
        result = apply_cleanup(plan, _live_state(tmp_path, out.name))
        assert (archive / "THOR" / QUAD).exists()
        assert (archive / "THOR" / PENTA).exists()
        assert (archive / "THOR" / HEXA).exists()
        assert not (clips_dir / QUAD).exists()
        sent = sorted(Path(c.args[0]) for c in fake_trash.call_args_list)
        assert sent == sorted([clips_dir / PLAIN, desc, clips_json])
        assert not clips_dir.exists(), "clips/ is removed once the plan empties it"
        assert mp4.exists(), "compiled video was not planned, so it stays"
        assert result.errors == []

    def test_apply_refuses_unless_folder_marked_live(self, tmp_path, fake_trash):
        out, clips_dir, mp4, archive, desc, clips_json = _build_tree(tmp_path)
        plan = plan_cleanup(out, archive)
        before = _tree_fingerprint(tmp_path)
        with pytest.raises(FolderNotConfirmed):
            apply_cleanup(plan, None)
        with pytest.raises(FolderNotConfirmed):
            apply_cleanup(plan, tmp_path / "state.json")
        assert _tree_fingerprint(tmp_path) == before
        fake_trash.assert_not_called()

    def test_apply_raises_plan_changed_when_file_appeared(self, tmp_path, fake_trash):
        out, clips_dir, mp4, archive, desc, clips_json = _build_tree(tmp_path)
        plan = plan_cleanup(out, archive)
        (clips_dir / "THOR_2026-02-10_09-00-00.mp4").write_bytes(b"new clip")
        with pytest.raises(PlanChanged):
            apply_cleanup(plan, _live_state(tmp_path, out.name))
        assert (clips_dir / QUAD).exists()
        assert (clips_dir / PLAIN).exists()
        assert not archive.exists()
        fake_trash.assert_not_called()

    def test_apply_raises_plan_changed_when_file_vanished(self, tmp_path, fake_trash):
        out, clips_dir, mp4, archive, desc, clips_json = _build_tree(tmp_path)
        plan = plan_cleanup(out, archive)
        (clips_dir / PLAIN).unlink()
        with pytest.raises(PlanChanged):
            apply_cleanup(plan, _live_state(tmp_path, out.name))
        assert (clips_dir / QUAD).exists()
        assert not archive.exists()
        fake_trash.assert_not_called()

    def test_apply_raises_plan_changed_when_archive_destination_appeared(self, tmp_path, fake_trash):
        out, clips_dir, mp4, archive, desc, clips_json = _build_tree(tmp_path)
        plan = plan_cleanup(out, archive)
        (archive / "THOR").mkdir(parents=True)
        (archive / "THOR" / QUAD).write_bytes(b"appeared after planning")
        with pytest.raises(PlanChanged):
            apply_cleanup(plan, _live_state(tmp_path, out.name))
        assert (clips_dir / QUAD).exists()
        fake_trash.assert_not_called()


class TestDryRunAndPlanBugs:

    def test_dry_run_writes_no_state_and_changes_nothing(self, tmp_path, fake_trash):
        """Old run_cleanup wrote the YouTube-confirmed state even on a dry run."""
        out, clips_dir, mp4, archive, desc, clips_json = _build_tree(tmp_path)
        state_path = tmp_path / "state.json"
        before = _tree_fingerprint(tmp_path)
        with patch("builtins.input", side_effect=AssertionError("dry run must not prompt")):
            run_cleanup(out, archive, state_path=state_path, dry_run=True)
        assert not state_path.exists()
        assert _tree_fingerprint(tmp_path) == before
        fake_trash.assert_not_called()

    def test_run_cleanup_without_state_path_changes_nothing(self, tmp_path, fake_trash):
        out, clips_dir, mp4, archive, desc, clips_json = _build_tree(tmp_path)
        before = _tree_fingerprint(tmp_path)
        with patch("builtins.input", side_effect=AssertionError("no state_path, so no prompts")):
            run_cleanup(out, archive)
        assert _tree_fingerprint(tmp_path) == before
        fake_trash.assert_not_called()

    def test_description_and_clips_json_removed_only_via_plan(self, tmp_path, fake_trash):
        """Old run_cleanup sent description and clips.json to the Recycle Bin outside any plan."""
        out, clips_dir, mp4, archive, desc, clips_json = _build_tree(tmp_path)
        plan = plan_cleanup(out, archive)
        metadata = [a.path for a in plan.actions if a.group == "metadata"]
        assert sorted(metadata) == sorted([desc, clips_json])
        apply_cleanup(restrict_plan(plan, keep=lambda a: False), _live_state(tmp_path, out.name))
        assert desc.exists()
        assert clips_json.exists()
        fake_trash.assert_not_called()

    def test_declining_clip_removal_keeps_description_and_clips_json(self, tmp_path, fake_trash):
        """The description is needed to retry an upload; it goes only when every clip goes."""
        out, clips_dir, mp4, archive, desc, clips_json = _build_tree(tmp_path)
        answers = iter(["y", "n", "n", "n"])  # live yes, archive no, recycle no, video no
        with patch("builtins.input", side_effect=lambda *_: next(answers, "n")):
            run_cleanup(out, archive, state_path=tmp_path / "state.json")
        assert desc.exists()
        assert clips_json.exists()
        fake_trash.assert_not_called()

    def test_partial_approval_keeps_description_and_clips_json(self, tmp_path, fake_trash):
        out, clips_dir, mp4, archive, desc, clips_json = _build_tree(tmp_path)
        answers = iter(["y", "y", "n", "n"])  # archive yes, recycle no: PLAIN clip stays
        with patch("builtins.input", side_effect=lambda *_: next(answers, "n")):
            run_cleanup(out, archive, state_path=tmp_path / "state.json")
        assert (clips_dir / PLAIN).exists()
        assert desc.exists()
        assert clips_json.exists()

    def test_prompts_no_longer_say_permanently(self, tmp_path):
        """send2trash is recoverable, so no prompt may claim the deletion is permanent."""
        out, clips_dir, mp4, archive, desc, clips_json = _build_tree(tmp_path)
        with patch("builtins.input", return_value="y") as mock_input:
            run_cleanup(out, archive, state_path=tmp_path / "state.json")
        prompts = [c.args[0] for c in mock_input.call_args_list]
        assert prompts, "expected at least one prompt"
        assert not any("permanent" in p.lower() for p in prompts)
