"""Bridge tests: each action starts its job and runs the engine call, with the engine stubbed.

Nothing here touches the real Recycle Bin, network, ffmpeg, a browser or YouTube. Every file
is under tmp_path. An autouse sandbox replaces each mutating engine call with a stub that
records the call and fails the test if the test did not stub it; it also fails the test
when a browser or the YouTube sign-in opens without the test asking for it.
"""
import json
import threading
import webbrowser
from pathlib import Path
from types import SimpleNamespace

import pytest

import clip_sorter
import cleanup
import pipeline
import preprocess
import state
import uploader
from gui import bridge, jobs

WAIT = 5.0  # seconds a test waits for a worker thread before failing instead of hanging


class FakeClock:
    def __init__(self, start: float = 1000.0):
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


@pytest.fixture(autouse=True)
def sandbox(monkeypatch, tmp_path):
    box = SimpleNamespace(browser=[], oauth=[], trash=[], checked=[], unexpected=[], allow_oauth=False)

    def unstubbed(name):
        def stub(*args, **kwargs):
            box.unexpected.append(name)
            raise AssertionError(f"{name} was not stubbed by this test")
        return stub

    monkeypatch.setattr(webbrowser, "open", lambda *a, **k: box.browser.append(a) or True)
    monkeypatch.setattr(uploader, "TOKEN_PATH", tmp_path / "token.json")
    monkeypatch.setattr(uploader, "get_authenticated_service",
                        lambda **kw: box.oauth.append(kw) or object())
    monkeypatch.setattr(uploader, "validate_channel_id", lambda svc, cid: box.checked.append(cid) or True)
    for module in (cleanup, pipeline, bridge):
        monkeypatch.setattr(module, "send2trash", lambda p: box.trash.append(p))
    monkeypatch.setattr(cleanup, "apply_cleanup", unstubbed("cleanup.apply_cleanup"))
    monkeypatch.setattr(cleanup, "apply_uncompile", unstubbed("cleanup.apply_uncompile"))
    monkeypatch.setattr(cleanup, "retry_upload", unstubbed("cleanup.retry_upload"))
    monkeypatch.setattr(pipeline, "plan_compile", unstubbed("pipeline.plan_compile"))
    monkeypatch.setattr(pipeline, "apply_compile", unstubbed("pipeline.apply_compile"))
    monkeypatch.setattr(preprocess, "preprocess_all", unstubbed("preprocess.preprocess_all"))
    monkeypatch.setattr(clip_sorter, "sort_clips", unstubbed("clip_sorter.sort_clips"))
    monkeypatch.setattr(bridge, "PLANS", bridge.PlanStore(clock=FakeClock()))
    yield box
    assert box.unexpected == []
    assert box.browser == [], "a browser opened outside sign_in"
    assert box.oauth == [] or box.allow_oauth, "the YouTube sign-in ran outside sign_in"


@pytest.fixture
def config(tmp_path):
    root = tmp_path / "rvm"
    cfg = SimpleNamespace(
        clips_path=root / "Highlights", output_path=root / "Output", archive_path=root / "ClipArchive",
        state_path=root / "data" / "state.json", youtube_channel_id="UCtest", protect_recent_clips=5,
        force_rescan_cache=False,
    )
    cfg.clips_path.mkdir(parents=True)
    cfg.output_path.mkdir(parents=True)
    return cfg


@pytest.fixture
def runner(tmp_path):
    return jobs.JobRunner(tmp_path / "jobs.json")


def finish(runner) -> dict:
    assert runner.wait(WAIT), "job did not finish"
    return runner.history()[0]


def signed_in(tmp_path) -> None:
    (tmp_path / "token.json").write_text(json.dumps({"refresh_token": "r", "token": "t"}), encoding="utf-8")


def make_output(config, name="THOR_FEB_2026") -> Path:
    folder = config.output_path / name
    (folder / "clips").mkdir(parents=True)
    (folder / "clips" / "THOR_clip1_QUAD.mp4").write_bytes(b"x")
    (folder / "THOR_FEB_2026_BATCH1_description.txt").write_text("d", encoding="utf-8")
    (folder / "THOR_FEB_2026_BATCH1.mp4").write_bytes(b"v")
    return folder


def mark_live(config, folder_name: str) -> None:
    config.state_path.parent.mkdir(parents=True, exist_ok=True)
    data = state.mark_youtube_confirmed(state.load(config.state_path), folder_name)
    state.save(data, config.state_path)


def hold_a_job(runner):
    gate = threading.Event()
    runner.start("scan", "Scanning clips", lambda ctx: gate.wait(WAIT))
    return gate


# ----- job kinds ---------------------------------------------------------------------

def test_sort_starts_a_sort_job(config, runner, monkeypatch):
    calls = []
    monkeypatch.setattr(clip_sorter, "sort_clips", lambda path, protect_recent=0: calls.append((path, protect_recent)) or 0)
    bridge.sort(runner, config)
    record = finish(runner)
    assert (record["kind"], record["state"]) == ("sort", "done")
    assert calls == [(config.clips_path, 5)]


def test_scan_starts_a_scan_job_and_passes_the_low_value_collector(config, runner, monkeypatch):
    seen = {}

    def fake_scan(cfg, dry_run=False, on_low_value=None, on_progress=None):
        seen["cfg"] = cfg
        on_low_value(Path("THOR_x_KO.mp4"))
        return {}

    monkeypatch.setattr(preprocess, "preprocess_all", fake_scan)
    bridge.scan(runner, config)
    record = finish(runner)
    assert (record["kind"], record["state"]) == ("scan", "done")
    assert seen["cfg"] is config


@pytest.mark.parametrize("args, expected_phase", [
    ((1, 3, "THOR"), "Scanning THOR"),
    ((3, 3, ""), "Finishing"),
])
def test_scan_reports_clip_progress_to_the_job_bar(config, runner, monkeypatch, args, expected_phase):
    def fake_scan(cfg, dry_run=False, on_low_value=None, on_progress=None):
        on_progress(*args)
        return {}

    monkeypatch.setattr(preprocess, "preprocess_all", fake_scan)
    bridge.scan(runner, config)
    record = finish(runner)
    assert (record["kind"], record["state"]) == ("scan", "done")
    assert (record["done"], record["total"], record["unit"], record["phase"]) == (
        args[0], args[1], "clips", expected_phase)


def test_compile_plans_then_applies_once_under_its_nonce(config, runner, monkeypatch, tmp_path):
    signed_in(tmp_path)
    plan = SimpleNamespace(character="THOR")
    applied = []
    monkeypatch.setattr(pipeline, "plan_compile", lambda cfg, character, target_s: plan)

    def fake_apply(cfg, p, decisions, force=False, on_progress=None):
        applied.append((p, decisions, force))
        on_progress(30, 60)
        return SimpleNamespace(compiled=True, uploaded=True, needs_sign_in=False, upload_failed=False, error="")

    monkeypatch.setattr(pipeline, "apply_compile", fake_apply)
    token, returned = bridge.plan_compile(config, "THOR", 900)
    assert returned is plan
    bridge.compile(runner, config, token, clips={"THOR_a_KO.mp4": "keep"}, extra=0)
    record = finish(runner)
    assert (record["kind"], record["state"]) == ("compile", "done")
    assert applied == [(plan, {"clips": {"THOR_a_KO.mp4": "keep"}, "extra": 0}, False)]
    with pytest.raises(bridge.Refused):
        bridge.compile(runner, config, token)


def test_upload_starts_an_upload_job_without_prompting(config, runner, monkeypatch, tmp_path):
    signed_in(tmp_path)
    folder = make_output(config)
    calls = []
    monkeypatch.setattr(cleanup, "retry_upload",
                        lambda out, cfg, confirm=True: calls.append((out, confirm)) or
                        SimpleNamespace(uploaded=True, needs_sign_in=False, cancelled=False, error=None))
    bridge.upload(runner, config, folder)
    record = finish(runner)
    assert (record["kind"], record["state"]) == ("upload", "done")
    assert calls == [(folder, False)]


def test_upload_fails_the_job_when_sign_in_is_needed(config, runner, monkeypatch, tmp_path):
    signed_in(tmp_path)
    folder = make_output(config)
    monkeypatch.setattr(cleanup, "retry_upload",
                        lambda out, cfg, confirm=True: SimpleNamespace(
                            uploaded=False, needs_sign_in=True, cancelled=False, error="channel mismatch"))
    bridge.upload(runner, config, folder)
    record = finish(runner)
    assert record["state"] == "failed"
    assert "Sign in again" in record["error"]


def test_compile_and_upload_refuse_without_a_saved_sign_in(config, runner, monkeypatch):
    folder = make_output(config)
    monkeypatch.setattr(pipeline, "plan_compile", lambda cfg, character, target_s: SimpleNamespace())
    token, _ = bridge.plan_compile(config, "THOR", 900)
    with pytest.raises(bridge.Refused, match="Sign in"):
        bridge.compile(runner, config, token)
    with pytest.raises(bridge.Refused, match="Sign in"):
        bridge.upload(runner, config, folder)


def test_sign_in_is_the_only_action_that_may_open_a_browser(config, runner, sandbox):
    sandbox.allow_oauth = True
    bridge.sign_in(runner, config)
    record = finish(runner)
    assert (record["kind"], record["state"]) == ("sign_in", "done")
    assert sandbox.oauth == [{"expected_channel_id": "UCtest"}]
    assert sandbox.checked == ["UCtest"]


def test_sign_in_channel_mismatch_fails_the_job(config, runner, monkeypatch, sandbox):
    sandbox.allow_oauth = True

    def mismatch(svc, cid):
        raise ValueError("wrong channel")

    monkeypatch.setattr(uploader, "validate_channel_id", mismatch)
    bridge.sign_in(runner, config)
    record = finish(runner)
    assert record["state"] == "failed"
    assert "wrong channel" in record["error"]


# ----- cleanup: plan, nonce, live check ----------------------------------------------

def stub_apply_cleanup(monkeypatch, calls):
    def fake(plan, state_path=None):
        calls.append((plan, state_path))
        return cleanup.ApplyResult()
    monkeypatch.setattr(cleanup, "apply_cleanup", fake)


def test_cleanup_runs_the_plan_once_and_refuses_a_reused_nonce(config, runner, monkeypatch):
    folder = make_output(config)
    mark_live(config, folder.name)
    calls = []
    stub_apply_cleanup(monkeypatch, calls)
    token, plan = bridge.plan_cleanup(config, folder)
    bridge.cleanup(runner, config, token)
    record = finish(runner)
    assert (record["kind"], record["state"]) == ("cleanup", "done")
    assert calls == [(plan, config.state_path)]
    with pytest.raises(bridge.Refused):
        bridge.cleanup(runner, config, token)
    assert len(calls) == 1


def test_cleanup_refuses_an_unknown_nonce(config, runner, monkeypatch):
    calls = []
    stub_apply_cleanup(monkeypatch, calls)
    with pytest.raises(bridge.Refused):
        bridge.cleanup(runner, config, "not-a-real-token")
    assert calls == []


def test_cleanup_refuses_an_expired_nonce(config, runner, monkeypatch):
    clock = FakeClock()
    monkeypatch.setattr(bridge, "PLANS", bridge.PlanStore(clock=clock))
    folder = make_output(config)
    mark_live(config, folder.name)
    calls = []
    stub_apply_cleanup(monkeypatch, calls)
    token, _ = bridge.plan_cleanup(config, folder)
    clock.advance(601)
    with pytest.raises(bridge.Refused):
        bridge.cleanup(runner, config, token)
    assert calls == []


def test_a_token_from_one_plan_kind_cannot_run_another(config, runner, monkeypatch):
    folder = make_output(config)
    mark_live(config, folder.name)
    calls = []
    stub_apply_cleanup(monkeypatch, calls)
    token, _ = bridge.plan_cleanup(config, folder)
    with pytest.raises(bridge.Refused):
        bridge.uncompile(runner, config, token)
    assert calls == []


def test_cleanup_refuses_when_the_folder_is_not_marked_live(config, runner, monkeypatch):
    folder = make_output(config)
    calls = []
    stub_apply_cleanup(monkeypatch, calls)
    token, _ = bridge.plan_cleanup(config, folder)
    with pytest.raises(cleanup.FolderNotConfirmed):
        bridge.cleanup(runner, config, token)
    assert calls == []


def test_cleanup_refuses_while_another_job_runs_and_keeps_the_plan(config, runner, monkeypatch):
    folder = make_output(config)
    mark_live(config, folder.name)
    calls = []
    stub_apply_cleanup(monkeypatch, calls)
    token, _ = bridge.plan_cleanup(config, folder)
    gate = hold_a_job(runner)
    with pytest.raises(jobs.Busy):
        bridge.cleanup(runner, config, token)
    gate.set()
    assert runner.wait(WAIT)
    bridge.cleanup(runner, config, token)
    assert finish(runner)["kind"] == "cleanup"
    assert len(calls) == 1


def test_a_second_action_while_a_job_runs_raises_busy(config, runner):
    gate = hold_a_job(runner)
    with pytest.raises(jobs.Busy):
        bridge.sort(runner, config)
    gate.set()
    assert runner.wait(WAIT)


def test_compile_passes_force_through_to_apply_compile(config, runner, monkeypatch, tmp_path):
    signed_in(tmp_path)
    plan = SimpleNamespace(character="THOR")
    applied = []
    monkeypatch.setattr(pipeline, "plan_compile", lambda cfg, character, target_s: plan)

    def fake_apply(cfg, p, decisions, force=False, on_progress=None):
        applied.append(force)
        return SimpleNamespace(compiled=True, uploaded=True, needs_sign_in=False, upload_failed=False, error="")

    monkeypatch.setattr(pipeline, "apply_compile", fake_apply)
    token, _ = bridge.plan_compile(config, "THOR", 900)
    bridge.compile(runner, config, token, clips={}, extra=0, force=True)
    assert finish(runner)["state"] == "done"
    assert applied == [True]


# ----- uncompile ---------------------------------------------------------------------

def test_uncompile_plans_and_applies_without_a_live_mark(config, runner, monkeypatch):
    folder = make_output(config)
    calls = []

    def fake(plan, state_path=None):
        calls.append(plan)
        return cleanup.ApplyResult()

    monkeypatch.setattr(cleanup, "apply_uncompile", fake)
    token, plan = bridge.plan_uncompile(config, folder)
    assert plan.folder_name == folder.name
    bridge.uncompile(runner, config, token)
    record = finish(runner)
    assert (record["kind"], record["state"]) == ("uncompile", "done")
    assert calls == [plan]


# ----- recycle one clip --------------------------------------------------------------

def test_recycle_clip_sends_one_clip_to_the_recycle_bin(config, runner, sandbox):
    clip = config.clips_path / "THOR" / "THOR_clip1_KO.mp4"
    clip.parent.mkdir()
    clip.write_bytes(b"x")
    bridge.recycle_clip(runner, config, clip)
    record = finish(runner)
    assert (record["kind"], record["state"]) == ("recycle_clip", "done")
    assert sandbox.trash == [str(clip)]


def test_recycle_clip_refuses_a_path_outside_the_clips_folder(config, runner, tmp_path, sandbox):
    outside = tmp_path / "elsewhere.mp4"
    outside.write_bytes(b"x")
    with pytest.raises(bridge.Refused):
        bridge.recycle_clip(runner, config, outside)
    assert sandbox.trash == []


def test_recycle_clip_refuses_a_missing_file(config, runner, sandbox):
    with pytest.raises(bridge.Refused):
        bridge.recycle_clip(runner, config, config.clips_path / "THOR" / "gone.mp4")
    assert sandbox.trash == []


# ----- mark live ---------------------------------------------------------------------

def test_mark_live_writes_the_state_mark(config, runner):
    folder = make_output(config)
    entry = bridge.mark_live(runner, config, folder.name)
    assert entry["youtube_confirmed"] is True
    assert state.is_youtube_confirmed(state.load(config.state_path), folder.name)


def test_mark_live_refuses_while_a_job_runs(config, runner):
    folder = make_output(config)
    gate = hold_a_job(runner)
    with pytest.raises(jobs.Busy):
        bridge.mark_live(runner, config, folder.name)
    assert not config.state_path.exists()
    gate.set()
    assert runner.wait(WAIT)


def test_mark_live_refuses_a_folder_that_is_not_there(config, runner):
    with pytest.raises(bridge.Refused):
        bridge.mark_live(runner, config, "THOR_missing")
    assert not config.state_path.exists()
