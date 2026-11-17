"""Wiring tests: each tab key calls the right bridge function, with a fake bridge and a fake page.

Nothing here runs an engine action. gui.wiring.bridge is replaced by FakeBridge, which records every
call and returns plans built by hand under tmp_path; gui.wiring.ui is replaced by FakeUi, which
records toasts and navigations. The real bridge.Refused and jobs.Busy classes are used so the
error texts are the ones the page shows.
"""
from pathlib import Path
from types import SimpleNamespace

import pytest

import cleanup
import pipeline
from gui import bridge, jobs, view_model, wiring
from gui import __main__ as gui_main


class FakeRunner:
    """Stands in for jobs.JobRunner. FakeBridge never starts a job, so the runner is only passed through."""


class FakeUi:
    def __init__(self):
        self.notes = []
        self.paths = []
        self.navigate = SimpleNamespace(to=self.paths.append)

    def notify(self, text, type=None):
        self.notes.append((text, type))


class FakeBridge:
    """Records each call as (name, args, kwargs). Plans come from the test; a failure can be set per name."""
    Refused = bridge.Refused

    def __init__(self, tmp_path):
        self.calls = []
        self.fail = {}
        self.tmp = tmp_path
        self.tokens = 0

    def _record(self, name, args, kwargs):
        self.calls.append((name, args, kwargs))
        if name in self.fail:
            raise self.fail[name]

    def _token(self):
        self.tokens += 1
        return f"tok-{self.tokens}"

    def sort(self, runner, config):
        self._record("sort", (runner, config), {})
        return {"kind": "sort"}

    def scan(self, runner, config):
        self._record("scan", (runner, config), {})
        return {"kind": "scan"}

    def recycle_clip(self, runner, config, path):
        self._record("recycle_clip", (runner, config, path), {})
        return {"kind": "recycle_clip"}

    def plan_compile(self, config, character, target_s):
        self._record("plan_compile", (config, character, target_s), {})
        return self._token(), compile_plan(self.tmp, character)

    def compile(self, runner, config, token, clips=None, extra=0, force=False):
        self._record("compile", (runner, config, token), {"clips": clips, "extra": extra, "force": force})
        return {"kind": "compile"}

    def upload(self, runner, config, folder):
        self._record("upload", (runner, config, folder), {})
        return {"kind": "upload"}

    def mark_live(self, runner, config, folder_name):
        self._record("mark_live", (runner, config, folder_name), {})
        return {"youtube_confirmed": True}

    def plan_cleanup(self, config, folder, include_video=False):
        self._record("plan_cleanup", (config, folder), {"include_video": include_video})
        return self._token(), cleanup_plan(self.tmp, include_video=include_video)

    def cleanup(self, runner, config, token):
        self._record("cleanup", (runner, config, token), {})
        return {"kind": "cleanup"}

    def plan_uncompile(self, config, folder):
        self._record("plan_uncompile", (config, folder), {})
        return self._token(), SimpleNamespace(folder_name=folder.name)

    def uncompile(self, runner, config, token):
        self._record("uncompile", (runner, config, token), {})
        return {"kind": "uncompile"}

    def sign_in(self, runner, config):
        self._record("sign_in", (runner, config), {})
        return {"kind": "sign_in"}

    def names(self):
        return [c[0] for c in self.calls]


def compile_plan(tmp_path, character="THOR"):
    """A hand-built engine CompilePlan: two batch-1 clips (one low-value, one KO) and one duplicate pair."""
    keep = pipeline.PlanClip(name=f"{character}_a_KO.mp4", path=tmp_path / "a.mp4", duration_s=60.0,
                             start_s=0.0, tier="HEXA", low_value=False)
    low = pipeline.PlanClip(name=f"{character}_b_KO.mp4", path=tmp_path / "b.mp4", duration_s=45.0,
                            start_s=60.0, tier=None, low_value=True)
    later = pipeline.PlanClip(name=f"{character}_c_QUAD.mp4", path=tmp_path / "c.mp4", duration_s=30.0,
                              start_s=0.0, tier=None, low_value=False)
    return pipeline.CompilePlan(
        character=character, folder=tmp_path / character, target_s=900.0,
        batches=[pipeline.PlanBatch(number=1, duration_s=105.0, clips=[keep, low]),
                 pipeline.PlanBatch(number=2, duration_s=30.0, clips=[later])],
        duplicates=[pipeline.PlanDuplicate(a=keep.name, b=low.name, score=0.91)],
        low_value=[low.name])


def cleanup_plan(tmp_path, include_video=False):
    """A hand-built CleanupPlan over real files: one 1 MB clip to recycle, one skipped clip, one description,
    and the compiled video when include_video."""
    out = tmp_path / "Output" / "THOR_FEB_2026"
    (out / "clips").mkdir(parents=True, exist_ok=True)
    clip = out / "clips" / "THOR_c1_KO.mp4"
    clip.write_bytes(b"x" * (1024 * 1024))
    text = out / "THOR_FEB_2026_BATCH1_description.txt"
    text.write_bytes(b"d")
    actions = [cleanup.PlannedAction(cleanup.FATE_RECYCLE, clip, cleanup.GROUP_CLIPS),
               cleanup.PlannedAction(cleanup.FATE_RECYCLE, text, cleanup.GROUP_METADATA)]
    if include_video:
        video = out / "THOR_FEB_2026_BATCH1.mp4"
        video.write_bytes(b"v")
        actions.append(cleanup.PlannedAction(cleanup.FATE_RECYCLE_VIDEO, video, cleanup.GROUP_VIDEO))
    return cleanup.CleanupPlan(
        folder_name=out.name, output_folder=out, archive_path=tmp_path / "Archive",
        include_video=include_video, actions=tuple(actions),
        skipped=("THOR_c2_QUAD.mp4",), snapshot=frozenset())


@pytest.fixture
def config(tmp_path):
    root = tmp_path / "rvm"
    cfg = SimpleNamespace(clips_path=root / "Highlights", output_path=root / "Output",
                          archive_path=root / "ClipArchive", state_path=root / "data" / "state.json")
    cfg.clips_path.mkdir(parents=True)
    cfg.output_path.mkdir(parents=True)
    return cfg


@pytest.fixture
def fake_bridge(monkeypatch, tmp_path):
    fake = FakeBridge(tmp_path)
    monkeypatch.setattr(wiring, "bridge", fake)
    return fake


@pytest.fixture
def fake_ui(monkeypatch):
    page = FakeUi()
    monkeypatch.setattr(wiring, "ui", page)
    return page


@pytest.fixture
def actions(config, fake_bridge, fake_ui):
    return wiring.Actions(FakeRunner(), config)


def clip_file(config, name="THOR_clip1_KO.mp4"):
    path = config.clips_path / "THOR" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x")
    return path


# ----- each key calls the right bridge function with the right arguments -------------

def test_clips_sort_and_scan_start_their_jobs(actions, fake_bridge, fake_ui, config):
    clips = actions.for_tab("clips")
    clips["sort"]()
    clips["scan"]()
    assert fake_bridge.calls[0] == ("sort", (actions.runner, config), {})
    assert fake_bridge.calls[1] == ("scan", (actions.runner, config), {})
    assert fake_ui.notes == [("Sorting clips.", "positive"), ("Scanning for KOs.", "positive")]
    assert fake_ui.paths == ["/tab/clips", "/tab/clips"]


def test_clips_recycle_finds_the_one_file_and_recycles_it(actions, fake_bridge, fake_ui, config):
    path = clip_file(config)
    actions.for_tab("clips")["recycle"]("THOR_clip1_KO.mp4")
    assert fake_bridge.calls == [("recycle_clip", (actions.runner, config, path), {})]
    assert fake_ui.notes == [('Recycling "THOR_clip1_KO.mp4".', "positive")]


def test_clips_recycle_refuses_zero_or_two_matches(actions, fake_bridge, fake_ui, config):
    actions.for_tab("clips")["recycle"]("missing.mp4")
    clip_file(config, "dup.mp4")
    (config.clips_path / "other").mkdir()
    (config.clips_path / "other" / "dup.mp4").write_bytes(b"x")
    actions.for_tab("clips")["recycle"]("dup.mp4")
    assert fake_bridge.calls == []
    assert [kind for _text, kind in fake_ui.notes] == ["negative", "negative"]
    assert "missing.mp4" in fake_ui.notes[0][0]
    assert "more than one" in fake_ui.notes[1][0].lower()
    assert fake_ui.paths == []


def test_clips_keep_is_a_toast_only(actions, fake_bridge, fake_ui):
    actions.for_tab("clips")["keep"]("THOR_clip1_KO.mp4")
    assert fake_bridge.calls == []
    assert fake_ui.notes == [('Kept "THOR_clip1_KO.mp4".', "positive")]
    assert fake_ui.paths == []


def test_compile_plan_passes_the_length_in_seconds_and_stores_the_plan(actions, fake_bridge, fake_ui):
    actions.for_tab("compile")["plan"]("THOR", 900, True)
    name, args, _ = fake_bridge.calls[0]
    assert name == "plan_compile"
    assert args[1] == "THOR" and args[2] == 900
    assert fake_ui.notes == [("Planned video for THOR.", "positive")]
    assert fake_ui.paths == ["/tab/compile"]


def test_compile_submits_the_nonce_with_merged_decisions_and_the_reencode_flag(actions, fake_bridge, fake_ui):
    compile_tab = actions.for_tab("compile")
    compile_tab["plan"]("THOR", 900, True)
    token = actions.held_plans()["compile_plan"]["nonce"]
    compile_tab["recycle"]("THOR_b_KO.mp4")
    passed = {"THOR_a_KO.mp4": "keep", "THOR_b_KO.mp4": "keep", "THOR_c_QUAD.mp4": "keep"}
    compile_tab["compile"](token, passed)
    name, args, kwargs = fake_bridge.calls[-1]
    assert name == "compile"
    assert args == (actions.runner, actions.config, token)
    assert kwargs == {"clips": {"THOR_a_KO.mp4": "keep", "THOR_b_KO.mp4": "recycle",
                                "THOR_c_QUAD.mp4": "keep"},
                      "extra": 0, "force": True}


def test_compile_clears_the_held_plan_after_a_start(actions, fake_bridge, fake_ui):
    compile_tab = actions.for_tab("compile")
    compile_tab["plan"]("THOR", 900, False)
    token = actions.held_plans()["compile_plan"]["nonce"]
    compile_tab["compile"](token, {})
    assert fake_ui.notes[-1] == ("Compiling video.", "positive")
    assert "compile_plan" not in actions.held_plans()


def test_compile_refuses_a_nonce_that_is_not_the_held_plan(actions, fake_bridge, fake_ui):
    compile_tab = actions.for_tab("compile")
    compile_tab["plan"]("THOR", 900, False)
    compile_tab["compile"]("not-the-plan", {})
    assert not any(c[0] == "compile" for c in fake_bridge.calls)
    assert fake_ui.notes[-1][1] == "negative"
    assert "no longer valid" in fake_ui.notes[-1][0]


def test_compile_keep_both_and_drop_one_record_decisions_on_the_view(actions, fake_bridge, fake_ui):
    compile_tab = actions.for_tab("compile")
    compile_tab["plan"]("THOR", 900, False)
    compile_tab["drop_one"]("THOR_a_KO.mp4", "THOR_b_KO.mp4")
    decisions = {c["name"]: c["decision"] for b in actions.held_plans()["compile_plan"]["batches"]
                 for c in b["clips"]}
    assert decisions["THOR_b_KO.mp4"] == "recycle"
    assert decisions["THOR_a_KO.mp4"] == "keep"
    compile_tab["keep_both"]("THOR_a_KO.mp4", "THOR_b_KO.mp4")
    decisions = {c["name"]: c["decision"] for b in actions.held_plans()["compile_plan"]["batches"]
                 for c in b["clips"]}
    assert decisions["THOR_b_KO.mp4"] == "keep"


def test_compile_keep_and_recycle_refuse_a_clip_not_in_the_plan(actions, fake_bridge, fake_ui):
    compile_tab = actions.for_tab("compile")
    compile_tab["plan"]("THOR", 900, False)
    compile_tab["recycle"]("THOR_nope.mp4")
    assert fake_ui.notes[-1][1] == "negative"
    assert "THOR_nope.mp4" in fake_ui.notes[-1][0]


def test_videos_upload_mark_live_and_sign_in(actions, fake_bridge, fake_ui, config):
    videos = actions.for_tab("videos")
    folder = config.output_path / "THOR_FEB_2026"
    videos["upload"]("THOR_FEB_2026")
    videos["mark_live"]("THOR_FEB_2026")
    videos["sign_in"]()
    assert fake_bridge.calls == [
        ("upload", (actions.runner, config, folder), {}),
        ("mark_live", (actions.runner, config, "THOR_FEB_2026"), {}),
        ("sign_in", (actions.runner, config), {}),
    ]
    assert [t for t, _k in fake_ui.notes] == ["Uploading to YouTube.", "Marked as live.", "Signing in to YouTube."]


def test_videos_plan_cleanup_stores_the_plan_and_shows_it(actions, fake_bridge, fake_ui, config):
    actions.for_tab("videos")["plan_cleanup"]("THOR_FEB_2026")
    assert fake_bridge.calls == [("plan_cleanup", (config, config.output_path / "THOR_FEB_2026"),
                                  {"include_video": False})]
    shown = actions.held_plans()["cleanup_plan"]
    assert shown["slug"] == "THOR_FEB_2026"
    assert fake_ui.paths == ["/tab/videos"]


def test_videos_apply_cleanup_runs_the_held_plan_once(actions, fake_bridge, fake_ui):
    videos = actions.for_tab("videos")
    videos["plan_cleanup"]("THOR_FEB_2026")
    token = actions.held_plans()["cleanup_plan"]["nonce"]
    videos["apply_cleanup"](token, False)
    assert fake_bridge.calls[-1] == ("cleanup", (actions.runner, actions.config, token), {})
    assert fake_ui.notes[-1] == ("Cleaning up THOR_FEB_2026.", "positive")
    assert "cleanup_plan" not in actions.held_plans()
    videos["apply_cleanup"](token, False)
    assert fake_ui.notes[-1][1] == "negative"
    assert fake_bridge.names().count("cleanup") == 1


def test_a_recycle_video_mismatch_re_plans_and_does_not_apply(actions, fake_bridge, fake_ui, config):
    videos = actions.for_tab("videos")
    videos["plan_cleanup"]("THOR_FEB_2026")
    first = actions.held_plans()["cleanup_plan"]["nonce"]
    videos["apply_cleanup"](first, True)
    assert "cleanup" not in fake_bridge.names()
    replanned = fake_bridge.calls[-1]
    assert replanned == ("plan_cleanup", (config, config.output_path / "THOR_FEB_2026"), {"include_video": True})
    second = actions.held_plans()["cleanup_plan"]
    assert second["nonce"] != first
    assert any(i["fate"] == cleanup.FATE_RECYCLE_VIDEO for i in second["items"])
    assert fake_ui.paths[-1] == "/tab/videos"
    videos["apply_cleanup"](second["nonce"], True)
    assert fake_bridge.calls[-1] == ("cleanup", (actions.runner, config, second["nonce"]), {})


def test_videos_restore_plans_the_uncompile_then_runs_it(actions, fake_bridge, fake_ui, config):
    actions.for_tab("videos")["restore"]("THOR_FEB_2026")
    assert fake_bridge.names() == ["plan_uncompile", "uncompile"]
    assert fake_bridge.calls[0][1] == (config, config.output_path / "THOR_FEB_2026")
    assert fake_bridge.calls[1][1][2] == "tok-1"
    assert fake_ui.notes == [("Restoring clips for THOR_FEB_2026.", "positive")]


# ----- a job-starting action toasts that the job started, never that it finished ------

# The finished-claim wording each job-starting action used before. The prefixes are checked as
# literal text in wiring.py, so a dynamic f-string toast (Cleaned up {slug}.) still matches.
FINISHED_CLAIMS = ["Sorted clips.", "Scanned for KOs.", "Compiled video.", "Uploaded to YouTube.",
                   "Signed in to YouTube.", "Cleaned up ", "Restored clips for ", 'Recycled "']


def test_job_starting_toasts_never_claim_the_job_finished():
    source = Path(wiring.__file__).read_text(encoding="utf-8")
    for old in FINISHED_CLAIMS:
        assert old not in source, f"{old!r} is still a toast in wiring.py"


# ----- refusals and errors become negative toasts with their text ---------------------

def test_a_refused_action_shows_its_text_as_a_negative_toast(actions, fake_bridge, fake_ui):
    fake_bridge.fail["upload"] = bridge.Refused("Sign in to YouTube first.")
    actions.for_tab("videos")["upload"]("THOR_FEB_2026")
    assert fake_ui.notes == [("Sign in to YouTube first.", "negative")]
    assert fake_ui.paths == []


def test_a_busy_job_names_the_running_job_and_the_fix(actions, fake_bridge, fake_ui):
    fake_bridge.fail["sort"] = jobs.Busy("Scan clips")
    actions.for_tab("clips")["sort"]()
    text, kind = fake_ui.notes[0]
    assert kind == "negative"
    assert "Scan clips" in text and "Wait" in text


def test_any_other_error_is_a_negative_toast_with_the_message(actions, fake_bridge, fake_ui):
    fake_bridge.fail["sign_in"] = RuntimeError("the network is down")
    actions.for_tab("videos")["sign_in"]()
    assert fake_ui.notes == [("the network is down", "negative")]
    assert fake_ui.paths == []


def test_a_folder_not_marked_live_is_a_negative_toast(actions, fake_bridge, fake_ui):
    fake_bridge.fail["cleanup"] = cleanup.FolderNotConfirmed("'THOR_FEB_2026' is not marked live on YouTube.")
    videos = actions.for_tab("videos")
    videos["plan_cleanup"]("THOR_FEB_2026")
    token = actions.held_plans()["cleanup_plan"]["nonce"]
    videos["apply_cleanup"](token, False)
    assert fake_ui.notes[-1] == ("'THOR_FEB_2026' is not marked live on YouTube.", "negative")


# ----- plan view dicts match what view_model accepts ----------------------------------

def test_held_compile_plan_is_accepted_by_view_model(actions, fake_bridge, fake_ui):
    actions.for_tab("compile")["plan"]("THOR", 900, False)
    shown = view_model._compile(actions.held_plans()["compile_plan"])["plan"]
    assert shown["character"] == "THOR"
    assert shown["target_s"] == 900.0
    assert shown["nonce"] == "tok-1"
    assert [b["number"] for b in shown["batches"]] == [1, 2]
    first = shown["batches"][0]["clips"]
    assert [c["name"] for c in first] == ["THOR_a_KO.mp4", "THOR_b_KO.mp4"]
    assert first[0]["tier"] == "HEXA" and first[0]["decision"] == "keep"
    assert first[1]["start_s"] == 60.0 and first[1]["duration_s"] == 45.0
    assert shown["duplicates"] == [{"a": "THOR_a_KO.mp4", "b": "THOR_b_KO.mp4", "score": 0.91}]


def test_held_cleanup_plan_is_accepted_by_view_model(actions, fake_bridge, fake_ui):
    actions.for_tab("videos")["plan_cleanup"]("THOR_FEB_2026")
    shown = view_model._cleanup(actions.held_plans()["cleanup_plan"])
    assert shown["slug"] == "THOR_FEB_2026"
    assert shown["nonce"] == "tok-1"
    fates = {item["name"]: item["fate"] for item in shown["items"]}
    assert fates["THOR_c1_KO.mp4"] == "recycle"
    assert fates["THOR_FEB_2026_BATCH1_description.txt"] == "recycle"
    assert fates["THOR_c2_QUAD.mp4"] == "keep"
    assert shown["totals"]["remove_count"] == 2
    assert shown["totals"]["remove_mb"] == pytest.approx(1.0, abs=0.01)
    clip = next(i for i in shown["items"] if i["name"] == "THOR_c1_KO.mp4")
    assert clip["size_mb"] == pytest.approx(1.0, abs=0.01)


def test_nothing_is_held_before_a_plan_is_made(actions):
    assert actions.held_plans() == {}


# ----- the fixture stand-in never touches the bridge ------------------------------------

def test_fixture_stand_in_toasts_every_key_and_never_calls_the_bridge(monkeypatch, fake_ui):
    class ForbiddenBridge:
        def __getattr__(self, name):
            raise AssertionError(f"bridge.{name} was called from a fixture run")

    monkeypatch.setattr(wiring, "bridge", ForbiddenBridge())
    stand_in = wiring.FixtureActions()
    seen = 0
    for tab in ("clips", "compile", "videos"):
        for name, action in stand_in.for_tab(tab).items():
            action("THOR", 900, True)
            seen += 1
    assert seen == sum(len(names) for names in wiring.TAB_ACTIONS.values())
    assert {text for text, _kind in fake_ui.notes} == {"Fixture: nothing is written."}
    assert fake_ui.paths == []
    assert stand_in.held_plans() == {}


def test_every_tab_has_exactly_the_keys_the_tabs_call(actions):
    assert set(wiring.TAB_ACTIONS["clips"]) == {"sort", "scan", "keep", "recycle"}
    assert set(wiring.TAB_ACTIONS["compile"]) == {"plan", "compile", "keep", "recycle", "keep_both", "drop_one"}
    assert set(wiring.TAB_ACTIONS["videos"]) == {"upload", "mark_live", "plan_cleanup", "apply_cleanup",
                                                 "sign_in", "restore"}
    for tab, names in wiring.TAB_ACTIONS.items():
        assert set(actions.for_tab(tab)) == set(names)


# ----- WiredSource injects the held plans; serve picks the stand-in in fixture mode ----------

class _StubSource:
    fixture = None

    def __init__(self, payload):
        self.payload = payload

    def read(self):
        return dict(self.payload)


def test_wired_source_injects_held_plans_only_when_one_is_held(actions, fake_bridge, fake_ui, tmp_path):
    runner = jobs.JobRunner(tmp_path / "jobs.json")
    wired = gui_main.WiredSource(_StubSource({"activity": []}), runner, actions)
    assert "compile_plan" not in wired.read()
    actions.for_tab("compile")["plan"]("THOR", 900, False)
    data = wired.read()
    assert data["compile_plan"]["character"] == "THOR"
    assert "cleanup_plan" not in data


def test_wired_source_with_a_fixture_stand_in_keeps_the_fixture_plan(tmp_path):
    runner = jobs.JobRunner(tmp_path / "jobs.json")
    wired = gui_main.WiredSource(_StubSource({"compile_plan": {"character": "IRON"}}), runner,
                                 wiring.FixtureActions())
    assert wired.read()["compile_plan"] == {"character": "IRON"}


def test_make_actions_uses_the_stand_in_for_a_fixture_and_the_real_actions_otherwise(config, tmp_path):
    runner = jobs.JobRunner(tmp_path / "jobs.json")
    assert isinstance(gui_main._make_actions(runner, config, "empty"), wiring.FixtureActions)
    assert isinstance(gui_main._make_actions(runner, config, None), wiring.Actions)
