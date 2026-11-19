"""Tests for oldcomp_scan: the resumable batch loop over OldCompilations (fakes stand in for the scanner)."""

import json
import os
import subprocess
import sys

import pytest

import oldcomp_guard
import oldcomp_scan

VER = "v-test"


@pytest.fixture
def tree(tmp_path):
    root = tmp_path / "OldCompilations"
    root.mkdir()
    for name, size in (("a long.mp4", 3), ("b short.mp4", 1), ("c mid.mp4", 2)):
        (root / name).write_bytes(b"x" * size)
    (root / "notes.txt").write_text("ignore")
    meta = tmp_path / "OldCompilationsMeta"
    state = tmp_path / "STATE.json"
    state.write_text(json.dumps({"videos": {}, "keep": 1}))
    return root, meta, state


def _fake_duration(path):
    return {"a long.mp4": 180.0, "b short.mp4": 60.0, "c mid.mp4": 120.0}[path.rsplit("\\", 1)[-1].rsplit("/", 1)[-1]]


def _fake_scan(path, *, checkpoint_dir, **kw):
    return {"scanner_version": VER, "detector": "ncc", "duration": _fake_duration(path), "scan_time": 12.0,
            "events": [{"tier": "QUAD", "ts": 5.0}, {"tier": "KO", "ts": 9.0}, {"tier": "QUAD", "ts": 30.0}]}


def run(tree, **kw):
    root, meta, state = tree
    args = dict(root=root, meta=meta, state_path=state, scan_fn=_fake_scan, duration_fn=_fake_duration,
                version=VER, now_fn=lambda: "T", log=lambda *_: None)
    args.update(kw)
    return oldcomp_scan.scan_all(**args)


def test_shortest_first_order_and_ignores_non_video(tree):
    res = run(tree, dry_run=True)
    assert [r["stem"] for r in res["plan"]] == ["b short", "c mid", "a long"]


def test_only_and_max_videos(tree):
    assert [r["stem"] for r in run(tree, dry_run=True, only="mid")["plan"]] == ["c mid"]
    assert len(run(tree, dry_run=True, max_videos=2)["plan"]) == 2


def test_dry_run_writes_nothing(tree):
    root, meta, state = tree
    run(tree, dry_run=True)
    assert not meta.exists()
    assert json.loads(state.read_text())["videos"] == {}


def test_scan_writes_summary_index_and_state(tree):
    root, meta, state = tree
    res = run(tree)
    s = json.loads((meta / "scan" / "b short" / "summary.json").read_text())
    assert s["scanner_version"] == VER and s["counts"] == {"KO": 1, "QUAD": 2}
    assert s["sec_per_video_min"] == 12.0
    idx = json.loads((meta / "scan" / "_index.json").read_text())
    assert set(idx["videos"]) == {"a long", "b short", "c mid"}
    st = json.loads(state.read_text())
    assert st["keep"] == 1 and st["last_tick_utc"] == "T"
    v = st["videos"]["b short"]
    assert v["status"] == "scanned" and v["scanner_version"] == VER and v["counts"]["QUAD"] == 2
    assert res["scanned"] == 3


def test_skips_current_version_but_rescans_old(tree):
    root, meta, state = tree
    run(tree)
    assert run(tree)["scanned"] == 0
    p = meta / "scan" / "b short" / "summary.json"
    d = json.loads(p.read_text()); d["scanner_version"] = "old"; p.write_text(json.dumps(d))
    assert run(tree)["scanned"] == 1


def test_failure_twice_recorded_and_loop_continues(tree):
    root, meta, state = tree
    calls = []
    def flaky(path, **kw):
        calls.append(path)
        if "mid" in path:
            raise RuntimeError("ffmpeg boom")
        return _fake_scan(path, **kw)
    res = run(tree, scan_fn=flaky)
    assert res["scanned"] == 2 and res["failed"] == ["c mid"]
    assert sum("mid" in c for c in calls) == 2
    assert json.loads(state.read_text())["videos"]["c mid"]["status"] == "failed"


def test_meta_inside_root_refused(tree):
    root, _, state = tree
    with pytest.raises(oldcomp_guard.OldCompViolation):
        run(tree, meta=root / "meta")


def _dead_pid():
    p = subprocess.Popen([sys.executable, "--version"], stdout=subprocess.DEVNULL)
    p.wait()
    return p.pid


def test_second_acquire_refused_while_first_holds(tmp_path):
    meta = tmp_path / "OldCompilationsMeta"
    lock = oldcomp_scan.acquire_lock(meta)
    assert lock == meta / "_scan.lock"
    with pytest.raises(oldcomp_scan.ScanLocked) as e:
        oldcomp_scan.acquire_lock(meta)
    assert e.value.pid == os.getpid()
    oldcomp_scan.release_lock(lock)


def test_stale_lock_with_dead_pid_is_taken_over(tmp_path):
    meta = tmp_path / "OldCompilationsMeta"
    meta.mkdir()
    (meta / "_scan.lock").write_text(str(_dead_pid()))
    lock = oldcomp_scan.acquire_lock(meta)
    assert lock.read_text().strip() == str(os.getpid())
    oldcomp_scan.release_lock(lock)


def test_lock_released_after_run(tree):
    root, meta, state = tree
    run(tree)
    assert not (meta / "_scan.lock").exists()


def test_lock_released_when_run_aborts(tree):
    root, meta, state = tree

    def abort(path, **kw):
        raise KeyboardInterrupt
    with pytest.raises(KeyboardInterrupt):
        run(tree, scan_fn=abort)
    assert not (meta / "_scan.lock").exists()


def test_run_refused_while_another_holds_lock(tree):
    root, meta, state = tree
    lock = oldcomp_scan.acquire_lock(meta)
    with pytest.raises(oldcomp_scan.ScanLocked) as e:
        run(tree)
    assert e.value.pid == os.getpid()
    assert not (meta / "scan").exists()
    assert json.loads(state.read_text())["videos"] == {}
    oldcomp_scan.release_lock(lock)
