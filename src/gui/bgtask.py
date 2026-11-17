# copied from a sibling local GUI kit (bgtask.py)
"""Fire-and-forget asyncio tasks that cannot be garbage collected mid-run.

The event loop holds only a weak reference to a task, so a bare
asyncio.create_task(...) whose result is dropped can vanish before it
finishes, and its exception is then lost. spawn() keeps a strong reference
until the task is done and writes any failure to the app log.
"""
from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from typing import Any

import applog

_tasks: set[asyncio.Task[Any]] = set()


def spawn(coro: Coroutine[Any, Any, Any]) -> asyncio.Task[Any]:
    """Start coro as a task that the module keeps alive until it finishes."""
    task = asyncio.create_task(coro)
    _tasks.add(task)
    task.add_done_callback(_on_done)
    return task


def _on_done(task: asyncio.Task[Any]) -> None:
    _tasks.discard(task)
    if task.cancelled():
        return
    exc = task.exception()
    if exc is not None:
        applog.write("bgtask", f"background task failed: {exc!r}")
