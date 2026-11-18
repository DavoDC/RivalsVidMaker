"""The only GUI module that runs engine actions which write (enforced by tests/gui/test_gui_seam.py).

Each action is one function. A write runs as a job on jobs.JobRunner, so the page sees it as
the current job. A plan is read-only and is stored under a single-use nonce; running it
consumes the nonce, so a stale, reused, expired or wrong-kind token refuses before any file
moves. Refusals raise Refused, Busy or the engine's FolderNotConfirmed.

Only sign_in may open a browser. upload and compile check for a saved sign-in first and
refuse without one, so the engine cannot fall through to the browser login. Nothing here
prints or reads input.
"""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any, Callable

import clip_sorter
import cleanup as engine_cleanup
import pipeline as engine_pipeline
import preprocess
import state
import uploader
from send2trash import send2trash
from state import save as save_state
from gui import jobs, nonce


class Refused(RuntimeError):
    """An action refused before it ran: a stale, reused or expired plan, a missing sign-in, or a path not allowed."""


class PlanStore:
    """Plans held under single-use nonces. nonce.NonceStore checks the token; this keeps the plan."""

    def __init__(self, clock: Callable[[], float] = time.monotonic):
        self._nonces = nonce.NonceStore(clock=clock)
        self._plans: dict[str, Any] = {}
        self._lock = threading.Lock()

    def issue(self, kind: str, plan: Any) -> str:
        with self._lock:
            token = self._nonces.issue(kind)
            self._plans[token] = plan
            while len(self._plans) > nonce.NONCE_LIMIT:
                del self._plans[next(iter(self._plans))]
            return token

    def take(self, kind: str, token: str) -> Any:
        """Return the plan once. Raises Refused for an unknown, reused, expired or wrong-kind token."""
        with self._lock:
            plan = self._plans.pop(token, None)
            if plan is None or not self._nonces.consume(token, kind):
                raise Refused("This plan is no longer valid. Make the plan again.")
            return plan


PLANS = PlanStore()


def _require_idle(runner: jobs.JobRunner) -> None:
    current = runner.current()
    if current is not None:
        raise jobs.Busy(current["title"])


def _require_sign_in(config) -> None:
    """Refuse unless the config's token file holds a refresh token, so the engine never falls through to the browser."""
    try:
        data = json.loads(uploader.resolve_token_path(config.token_path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = None
    if not isinstance(data, dict) or not data.get("refresh_token"):
        raise Refused("Sign in to YouTube first.")


def _report_errors(ctx: jobs.JobContext, result) -> None:
    """Log each failed file. A job with any failure ends failed, so the page shows it."""
    for action, error in result.errors:
        ctx.log.error("%s failed for %s: %s", action.fate, action.path.name, error)
    if result.errors:
        raise RuntimeError(f"{len(result.errors)} item(s) failed; see the log")
    ctx.log.info("%d item(s) done", len(result.done))


def _count(n: int, noun: str) -> str:
    return f"{n} {noun}" if n == 1 else f"{n} {noun}s"


def _sorted_summary(moved: int, skipped: int) -> str:
    text = f"Sorted {moved} clip{'' if moved == 1 else 's'}."
    if skipped:
        text += f" Skipped {skipped}."
    return text


def sort(runner: jobs.JobRunner, config) -> dict:
    def job(ctx: jobs.JobContext) -> None:
        skipped: list[tuple[str, str]] = []
        moved = clip_sorter.sort_clips(config.clips_path, protect_recent=config.protect_recent_clips,
                                       on_skip=lambda name, reason: skipped.append((name, reason)))
        for name, reason in skipped:
            ctx.log.warning("Skipped %s: %s", name, reason)
        if skipped:
            ctx.log.info("Sorted %d clip(s), skipped %d", moved, len(skipped))
        else:
            ctx.log.info("Sorted %d clip(s)", moved)
        ctx.summary(_sorted_summary(moved, len(skipped)))

    _require_idle(runner)
    return runner.start("sort", "Sort clips", job)


def scan(runner: jobs.JobRunner, config) -> dict:
    def job(ctx: jobs.JobContext) -> None:
        low_value: list[Path] = []
        preprocess.preprocess_all(
            config,
            on_low_value=low_value.append,
            on_progress=lambda done, total, char: ctx.progress(
                done, total, "clips", f"Scanning {char}" if char else "Finishing"),
        )
        ctx.log.info("Scan found %d low-value clip(s)", len(low_value))
        ctx.summary(f"Scanned clips. Found {_count(len(low_value), 'low-value clip')}.")

    _require_idle(runner)
    return runner.start("scan", "Scan clips", job)


def plan_compile(config, character: Path | str, target_s: float) -> tuple[str, Any]:
    """Read-only plan. Returns (nonce, plan); the plan runs once through compile()."""
    plan = engine_pipeline.plan_compile(config, character, target_s)
    return PLANS.issue("compile", plan), plan


def compile(runner: jobs.JobRunner, config, token: str, clips: dict | None = None, extra: int = 0,
            force: bool = False, upload: bool = True) -> dict:
    """force is the Re-encode flag: True encodes even when the video already exists.
    upload=False compiles without a YouTube upload, so no sign-in is needed."""
    _require_idle(runner)
    if upload:
        _require_sign_in(config)
    plan = PLANS.take("compile", token)
    decisions = {"clips": dict(clips or {}), "extra": int(extra)}

    def job(ctx: jobs.JobContext) -> None:
        def on_progress(encoded, total) -> None:
            ctx.progress(round(encoded), round(total), "s", "Encoding")

        result = engine_pipeline.apply_compile(config, plan, decisions, force=force, on_progress=on_progress,
                                               upload=upload)
        if result.needs_sign_in or result.upload_failed:
            ctx.log.warning("Compiled, but the upload did not finish: %s", result.error)
        ctx.log.info("Compile finished: compiled=%s uploaded=%s", result.compiled, result.uploaded)
        if result.uploaded:
            ctx.summary("Compiled and uploaded.")
        elif not result.compiled:
            ctx.summary("Nothing was compiled.")
        elif result.needs_sign_in or result.upload_failed:
            ctx.summary("Compiled. The upload did not finish.")
        else:
            ctx.summary("Compiled. Not uploaded.")

    return runner.start("compile", "Compile video", job)


def upload(runner: jobs.JobRunner, config, output_folder: Path | str) -> dict:
    folder = Path(output_folder)

    def job(ctx: jobs.JobContext) -> None:
        result = engine_cleanup.retry_upload(folder, config, confirm=False)
        if result.needs_sign_in:
            raise RuntimeError("Sign in again; the saved sign-in was kept.")
        if not result.uploaded:
            raise RuntimeError(result.error or "The upload did not finish.")
        ctx.summary("Uploaded to YouTube.")

    _require_idle(runner)
    _require_sign_in(config)
    return runner.start("upload", "Upload video", job)


def mark_live(runner: jobs.JobRunner, config, folder_name: str) -> dict:
    """Record that a folder's video is live on YouTube. A quick state write, so it waits for no job."""
    _require_idle(runner)
    if not folder_name or not (config.output_path / folder_name).is_dir():
        raise Refused(f"No output folder named '{folder_name}'.")
    data = state.mark_youtube_confirmed(state.load(config.state_path), folder_name)
    save_state(data, config.state_path)
    return data["output_folders"][folder_name]


def plan_cleanup(config, output_folder: Path | str, include_video: bool = False) -> tuple[str, Any]:
    plan = engine_cleanup.plan_cleanup(Path(output_folder), config.archive_path, include_video=include_video)
    return PLANS.issue("cleanup", plan), plan


def cleanup(runner: jobs.JobRunner, config, token: str) -> dict:
    _require_idle(runner)
    plan = PLANS.take("cleanup", token)
    if not state.is_youtube_confirmed(state.load(config.state_path), plan.folder_name):
        raise engine_cleanup.FolderNotConfirmed(
            f"'{plan.folder_name}' is not marked live on YouTube; nothing was touched.")

    def job(ctx: jobs.JobContext) -> None:
        result = engine_cleanup.apply_cleanup(plan, state_path=config.state_path)
        _report_errors(ctx, result)
        ctx.summary(f"Cleaned up {_count(len(result.done), 'item')}.")

    return runner.start("cleanup", "Clean up output folder", job)


def plan_uncompile(config, output_folder: Path | str) -> tuple[str, Any]:
    plan = engine_cleanup.plan_uncompile(Path(output_folder), config.clips_path)
    return PLANS.issue("uncompile", plan), plan


def uncompile(runner: jobs.JobRunner, config, token: str) -> dict:
    _require_idle(runner)
    plan = PLANS.take("uncompile", token)

    def job(ctx: jobs.JobContext) -> None:
        result = engine_cleanup.apply_uncompile(plan, state_path=config.state_path)
        _report_errors(ctx, result)
        ctx.summary(f"Restored {_count(len(result.done), 'item')}.")

    return runner.start("uncompile", "Restore clips", job)


def recycle_clip(runner: jobs.JobRunner, config, clip_path: Path | str) -> dict:
    """Send one clip under the clips folder to the Recycle Bin. Recoverable, so no plan step."""
    _require_idle(runner)
    path = Path(clip_path)
    try:
        inside = path.resolve().is_relative_to(config.clips_path.resolve())
    except OSError:
        inside = False
    if not inside or not path.is_file():
        raise Refused("Only a clip file inside the clips folder can be recycled.")

    def job(ctx: jobs.JobContext) -> None:
        send2trash(str(path))
        ctx.log.info("Sent to Recycle Bin: %s", path.name)
        ctx.summary(f'Recycled "{path.name}".')

    return runner.start("recycle_clip", f"Recycle {path.name}", job)


def sign_in(runner: jobs.JobRunner, config) -> dict:
    """The only action that may open a browser: the YouTube sign-in, then the channel check."""
    def job(ctx: jobs.JobContext) -> None:
        youtube = uploader.get_authenticated_service(expected_channel_id=config.youtube_channel_id)
        uploader.validate_channel_id(youtube, config.youtube_channel_id)
        ctx.log.info("Signed in to YouTube")
        ctx.summary("Signed in to YouTube.")

    return runner.start("sign_in", "Sign in to YouTube", job)
