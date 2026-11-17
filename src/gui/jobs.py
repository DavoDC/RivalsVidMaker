"""Background jobs for the local GUI: one at a time, progress with an ETA, cancel, capped history.

Standard library and the gui helpers only. A job runs on one daemon thread; a second start
while one runs raises Busy. History is a JSON file (last 50 jobs, written to a temp file and
then replaced). A job still recorded as running when the runner loads was cut off by a
restart, so it loads as interrupted. The worker never touches UI objects; the page reads
snapshot() on a timer.
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
import uuid
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from gui import timefmt

HISTORY_LIMIT = 50   # finished and running jobs kept in the history file
ETA_SAMPLES = 20     # progress signals kept for the rate behind the ETA
LOG = logging.getLogger("rvm.gui.jobs")

RUNNING = "running"
DONE = "done"
FAILED = "failed"
CANCELLED = "cancelled"
INTERRUPTED = "interrupted"


class Busy(Exception):
    """Raised by start() while another job runs. running_title names that job."""

    def __init__(self, running_title: str):
        self.running_title = running_title
        super().__init__(f"'{running_title}' is still running")


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


class JobContext:
    """What a job function sees: progress, the cancel flag and a logger."""

    def __init__(self, runner: "JobRunner", job_id: str, cancel: threading.Event):
        self._runner = runner
        self.job_id = job_id
        self.log = LOG
        self._cancel = cancel

    def progress(self, done, total, unit: str = "", phase: str | None = None) -> None:
        self._runner._progress(self.job_id, done, total, unit, phase)

    def cancelled(self) -> bool:
        return self._cancel.is_set()

    def wait_cancelled(self, timeout: float) -> bool:
        """Block up to timeout seconds; True as soon as cancel is requested."""
        return self._cancel.wait(timeout)


def _eta(samples: deque, total) -> float | None:
    """Seconds left from the rate across the kept signals; None until two signals show progress."""
    if total is None or len(samples) < 2:
        return None
    (t0, d0), (t1, d1) = samples[0], samples[-1]
    if t1 <= t0 or d1 <= d0:
        return None
    rate = (d1 - d0) / (t1 - t0)
    return round(max(0.0, (total - d1) / rate), 1)


class JobRunner:
    def __init__(self, history_path: str | Path, *, clock: Callable[[], float] = time.monotonic,
                 log_path: str | Path | None = None):
        self._path = Path(history_path)
        self._clock = clock
        self._log_path = None if log_path is None else str(log_path)
        self._lock = threading.Lock()
        self._records: list[dict[str, Any]] = self._load()
        self._active: dict[str, Any] | None = None

    # ----- history file -------------------------------------------------------------

    def _load(self) -> list[dict[str, Any]]:
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return []
        records = data.get("jobs") if isinstance(data, dict) else None
        if not isinstance(records, list):
            return []
        records = [r for r in records if isinstance(r, dict)][-HISTORY_LIMIT:]
        interrupted = False
        for record in records:
            if record.get("state") == RUNNING:
                record["state"] = INTERRUPTED
                record["finished_at"] = record.get("finished_at") or _now_iso()
                interrupted = True
        if interrupted:
            try:
                self._write(records)
            except OSError as exc:
                LOG.warning("could not save job history: %s", exc)
        return records

    def _write(self, records: list[dict[str, Any]]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_name(self._path.name + ".tmp")
        tmp.write_text(json.dumps({"jobs": records[-HISTORY_LIMIT:]}, indent=2), encoding="utf-8")
        os.replace(tmp, self._path)

    def _save(self) -> None:
        """Called under the lock. A failed save is logged; it never stops a job."""
        try:
            self._write(self._records)
        except OSError as exc:
            LOG.warning("could not save job history: %s", exc)

    # ----- public api ---------------------------------------------------------------

    @property
    def busy(self) -> bool:
        with self._lock:
            return self._active is not None

    def start(self, kind: str, title: str, fn: Callable[..., Any], **kwargs: Any) -> dict[str, Any]:
        """Run fn(ctx, **kwargs) on a daemon thread. Raises Busy while another job runs."""
        with self._lock:
            if self._active is not None:
                raise Busy(self._active["record"]["title"])
            record: dict[str, Any] = {
                "id": uuid.uuid4().hex[:12], "kind": kind, "title": title, "state": RUNNING,
                "started_at": _now_iso(), "finished_at": None, "elapsed": None,
                "done": 0, "total": None, "unit": "", "phase": "Starting",
                "error": None, "log_path": self._log_path,
            }
            cancel = threading.Event()
            active = {"record": record, "ctx": JobContext(self, record["id"], cancel),
                      "cancel": cancel, "samples": deque(maxlen=ETA_SAMPLES),
                      "started": self._clock(), "thread": None}
            self._records.append(record)
            del self._records[:-HISTORY_LIMIT]
            self._active = active
            self._save()
            thread = threading.Thread(target=self._run, args=(active, fn, kwargs),
                                      name=f"gui-job-{record['id']}", daemon=True)
            active["thread"] = thread
            thread.start()
            return dict(record)

    def current(self) -> dict[str, Any] | None:
        with self._lock:
            if self._active is None:
                return None
            return self._view(self._active)

    def history(self) -> list[dict[str, Any]]:
        """Newest first. Times are ISO; started_text is the display form."""
        with self._lock:
            return [self._public(r) for r in reversed(self._records)]

    def snapshot(self) -> dict[str, Any]:
        return {"current": self.current(), "history": self.history()}

    def cancel(self) -> bool:
        """Ask the running job to stop at its next check. False when nothing is running."""
        with self._lock:
            if self._active is None:
                return False
            self._active["cancel"].set()
            return True

    def wait(self, timeout: float | None = None) -> bool:
        """Join the running job's thread up to timeout. True when nothing is running afterwards."""
        with self._lock:
            thread = None if self._active is None else self._active["thread"]
        if thread is None:
            return True
        thread.join(timeout)
        return not thread.is_alive()

    # ----- internals ----------------------------------------------------------------

    def _run(self, active: dict[str, Any], fn: Callable[..., Any], kwargs: dict[str, Any]) -> None:
        record, ctx = active["record"], active["ctx"]
        state, error = DONE, None
        try:
            fn(ctx, **kwargs)
        except Exception as exc:
            state, error = FAILED, f"{type(exc).__name__}: {exc}"
            LOG.warning("job %r failed: %s", record["title"], error)
        if state != FAILED and ctx.cancelled():
            state = CANCELLED
        with self._lock:
            record["state"] = state
            record["error"] = error
            record["finished_at"] = _now_iso()
            record["elapsed"] = round(self._clock() - active["started"], 1)
            self._active = None
            self._save()

    def _progress(self, job_id: str, done, total, unit: str, phase: str | None) -> None:
        with self._lock:
            active = self._active
            if active is None or active["record"]["id"] != job_id:
                return
            record = active["record"]
            record.update(done=done, total=total, unit=unit)
            if phase is not None:
                record["phase"] = phase
            active["samples"].append((self._clock(), done))

    def _view(self, active: dict[str, Any]) -> dict[str, Any]:
        record = dict(active["record"])
        record["elapsed"] = round(self._clock() - active["started"], 1)
        record["eta"] = _eta(active["samples"], record["total"])
        record["elapsed_text"] = timefmt.duration(record["elapsed"])
        record["started_text"] = timefmt.stamp(record["started_at"])
        return record

    def _public(self, record: dict[str, Any]) -> dict[str, Any]:
        out = dict(record)
        out["started_text"] = timefmt.stamp(record.get("started_at"))
        return out
