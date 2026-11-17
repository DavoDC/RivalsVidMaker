"""Background job runner for the local GUI (DESIGN-PLAN.md section 7). Headless, no real sleeps.

Every test writes its history under tmp_path, never under data/gui/. Threads are joined with
a timeout, and the test clock is a fake that only moves when a test advances it.
"""
import json
import threading

import pytest

from gui import jobs

WAIT = 5.0  # seconds a test waits for a worker thread before failing instead of hanging


class FakeClock:
    def __init__(self, start: float = 1000.0):
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def make_runner(tmp_path, clock=None, log_path=None):
    return jobs.JobRunner(tmp_path / "jobs.json", clock=clock or FakeClock(), log_path=log_path)


def run_to_end(runner, title, fn, **kwargs):
    record = runner.start("test", title, fn, **kwargs)
    assert runner.wait(WAIT), f"job {title!r} did not finish in {WAIT}s"
    return record


def test_second_start_while_busy_raises_busy_naming_the_running_title(tmp_path):
    runner = make_runner(tmp_path)
    release = threading.Event()

    def hold(ctx):
        release.wait(WAIT)

    runner.start("scan", "Scan clips", hold)
    try:
        assert runner.busy is True
        with pytest.raises(jobs.Busy) as caught:
            runner.start("sort", "Sort clips", hold)
        assert caught.value.running_title == "Scan clips"
        assert "Scan clips" in str(caught.value)
    finally:
        release.set()
        assert runner.wait(WAIT)
    assert runner.busy is False


def test_progress_is_visible_with_an_eta_once_two_signals_exist(tmp_path):
    clock = FakeClock()
    runner = make_runner(tmp_path, clock=clock)
    first, go, second, end = (threading.Event() for _ in range(4))

    def work(ctx):
        ctx.progress(0, 10, "clips", "Scanning")
        first.set()
        go.wait(WAIT)
        ctx.progress(5, 10, "clips", "Sorting")
        second.set()
        end.wait(WAIT)

    runner.start("scan", "Scan clips", work)
    try:
        assert first.wait(WAIT)
        now = runner.current()
        assert now["done"] == 0 and now["total"] == 10 and now["unit"] == "clips"
        assert now["phase"] == "Scanning"
        assert now["eta"] is None  # one signal is not a rate yet

        clock.advance(10.0)
        go.set()
        assert second.wait(WAIT)
        now = runner.current()
        assert now["done"] == 5
        assert now["phase"] == "Sorting"
        assert now["eta"] == pytest.approx(10.0)  # 5 clips in 10s, 5 left
    finally:
        end.set()
        assert runner.wait(WAIT)


def test_cooperative_job_sees_the_cancel_flag_and_is_recorded_cancelled(tmp_path):
    runner = make_runner(tmp_path)
    started, saw_cancel = threading.Event(), threading.Event()

    def work(ctx):
        started.set()
        if ctx.wait_cancelled(WAIT):
            saw_cancel.set()

    runner.start("cleanup", "Clean up", work)
    assert started.wait(WAIT)
    assert runner.cancel() is True
    assert runner.wait(WAIT)
    assert saw_cancel.is_set()
    assert runner.history()[0]["state"] == "cancelled"


def test_cancel_with_no_running_job_is_a_no_op(tmp_path):
    assert make_runner(tmp_path).cancel() is False


def test_exception_marks_the_job_failed_with_message_and_log_path(tmp_path):
    log_path = tmp_path / "gui_2026-11-17.log"
    runner = make_runner(tmp_path, log_path=log_path)

    def boom(ctx):
        raise ValueError("disk full")

    run_to_end(runner, "Encode", boom)
    job = runner.history()[0]
    assert job["state"] == "failed"
    assert job["error"] == "ValueError: disk full"
    assert job["log_path"] == str(log_path)
    assert runner.busy is False


def test_successful_job_is_recorded_done_with_timestamps(tmp_path):
    runner = make_runner(tmp_path)
    run_to_end(runner, "Quick", lambda ctx: None)
    job = runner.history()[0]
    assert job["state"] == "done"
    assert job["title"] == "Quick"
    assert job["started_at"] and job["finished_at"]
    assert job["error"] is None


def test_kwargs_reach_the_job_function(tmp_path):
    runner = make_runner(tmp_path)
    seen = {}

    def work(ctx, folder, limit):
        seen.update(folder=folder, limit=limit)

    run_to_end(runner, "Scan", work, folder="raw", limit=3)
    assert seen == {"folder": "raw", "limit": 3}


def test_history_caps_at_fifty_newest_first_and_on_disk(tmp_path):
    runner = make_runner(tmp_path)
    for n in range(55):
        run_to_end(runner, f"job-{n}", lambda ctx: None)

    history = runner.history()
    assert len(history) == jobs.HISTORY_LIMIT == 50
    assert history[0]["title"] == "job-54"
    assert history[-1]["title"] == "job-5"

    on_disk = json.loads((tmp_path / "jobs.json").read_text(encoding="utf-8"))
    assert len(on_disk["jobs"]) == 50
    assert on_disk["jobs"][-1]["title"] == "job-54"


def test_history_is_written_to_a_temp_file_then_replaced(tmp_path, monkeypatch):
    real_replace = jobs.os.replace
    calls = []

    def spy(src, dst):
        calls.append((str(src), str(dst)))
        assert str(src).endswith(".tmp")
        assert jobs.Path(src).exists(), "the temp file must be complete before the replace"
        real_replace(src, dst)

    monkeypatch.setattr(jobs.os, "replace", spy)
    runner = make_runner(tmp_path)
    run_to_end(runner, "One", lambda ctx: None)

    assert calls, "history was never replaced into place"
    assert all(dst == str(tmp_path / "jobs.json") for _, dst in calls)
    assert not (tmp_path / "jobs.json.tmp").exists()


def test_failed_write_leaves_the_previous_history_intact(tmp_path, monkeypatch):
    runner = make_runner(tmp_path)
    run_to_end(runner, "Kept", lambda ctx: None)
    before = (tmp_path / "jobs.json").read_text(encoding="utf-8")

    def refuse(src, dst):
        raise OSError("replace refused")

    monkeypatch.setattr(jobs.os, "replace", refuse)
    run_to_end(runner, "Lost", lambda ctx: None)  # the job still finishes; the save is logged
    assert (tmp_path / "jobs.json").read_text(encoding="utf-8") == before


def test_job_recorded_as_running_loads_as_interrupted(tmp_path):
    path = tmp_path / "jobs.json"
    path.write_text(json.dumps({"jobs": [
        {"id": "a1", "title": "Encode", "kind": "encode", "state": "done"},
        {"id": "b2", "title": "Upload", "kind": "upload", "state": "running", "finished_at": None},
    ]}), encoding="utf-8")

    runner = jobs.JobRunner(path, clock=FakeClock())
    history = runner.history()
    assert [job["state"] for job in history] == ["interrupted", "done"]
    assert history[0]["title"] == "Upload"
    assert history[0]["finished_at"]  # an interrupted job still gets an end time
    assert runner.current() is None
    assert json.loads(path.read_text(encoding="utf-8"))["jobs"][1]["state"] == "interrupted"


def test_unreadable_history_file_loads_empty_instead_of_failing_boot(tmp_path):
    path = tmp_path / "jobs.json"
    path.write_text("{not json", encoding="utf-8")
    runner = jobs.JobRunner(path, clock=FakeClock())
    assert runner.history() == []
    assert runner.busy is False


def test_running_job_is_written_to_history_before_it_finishes(tmp_path):
    runner = make_runner(tmp_path)
    release, started = threading.Event(), threading.Event()

    def hold(ctx):
        started.set()
        release.wait(WAIT)

    runner.start("scan", "Scan clips", hold)
    try:
        assert started.wait(WAIT)
        on_disk = json.loads((tmp_path / "jobs.json").read_text(encoding="utf-8"))
        assert on_disk["jobs"][-1]["state"] == "running"
        assert on_disk["jobs"][-1]["title"] == "Scan clips"
    finally:
        release.set()
        assert runner.wait(WAIT)
