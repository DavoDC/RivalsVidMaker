"""View model (design plan section 6): snapshot() and testid() against the /state.json contract.

Runs on every fixture scenario, on stub sources and on tmp trees read by RealSource.
Nothing here writes outside tmp_path.
"""
import ast
import copy
import dataclasses
import json
import re
from pathlib import Path

import clip_cache
import config
from gui import build_info, fixtures, view_model
from gui.sources import FixtureSource, RealSource

SRC_FILE = Path(view_model.__file__).resolve()

TOP_KEYS = {
    "schema", "generated_at", "stale", "poll_interval", "boot_id", "build", "fixture",
    "job", "summary", "clips", "compile", "videos", "archive", "activity",
    "config_problems", "notices",
}


def test_config_problems_and_notices_reach_the_page():
    broken = view_model.snapshot(FixtureSource("config_broken"))
    assert broken["config_problems"] == ["ffmpeg not found", "tesseract not found"]
    busy = view_model.snapshot(FixtureSource("busy_refused"))
    assert busy["notices"][0]["kind"] == "toast"
JOB_KINDS = ["sort", "scan", "compile", "upload", "cleanup", "uncompile", "recycle_clip"]
FORBIDDEN_WORDS = ("token", "secret", "client_id")
FORBIDDEN_IMPORTS = {
    "pipeline", "cleanup", "preprocess", "uploader", "encoder", "clip_sorter",
    "dedup", "ko_detect", "bridge", "state", "jobs", "sources", "fixtures",
}


class _Stub:
    """A Source that returns the same dict on every read (a copy, so reads cannot leak)."""

    def __init__(self, data: dict, fixture=None):
        self._data = data
        self.fixture = fixture

    def read(self) -> dict:
        return copy.deepcopy(self._data)


def _data(**over) -> dict:
    data = copy.deepcopy(fixtures.BASE)
    data.update(over)
    return data


def _fixture_snaps() -> dict:
    return {name: view_model.snapshot(FixtureSource(name)) for name in fixtures.SCENARIOS}


def _make_config(root: Path, **over) -> config.Config:
    tools = root / "tools"
    tools.mkdir(parents=True, exist_ok=True)
    for name in ("ffmpeg.exe", "ffprobe.exe", "tesseract.exe"):
        (tools / name).write_bytes(b"x")
    values = dict(
        clips_path=root / "Highlights",
        output_path=root / "Output",
        archive_path=root / "ClipArchive",
        ffmpeg=tools / "ffmpeg.exe",
        ffprobe=tools / "ffprobe.exe",
        cache_dir=root / "cache",
        tesseract=tools / "tesseract.exe",
        min_batch_seconds=600,
        target_batch_seconds=900,
        protect_recent_clips=1,
        state_path=root / "state.json",
        force_rescan_cache=False,
        use_pass2_scanner=False,
        youtube_channel_id="UC_TEST_CHANNEL",
        vlc_path=None,
    )
    values.update(over)
    return config.Config(**values)


def _clip(path: Path, size: int = 32) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"c" * size)
    return path


def _build_tree(root: Path) -> config.Config:
    cfg = _make_config(root)
    hl = cfg.clips_path
    thor_a = _clip(hl / "THOR" / "THOR_2026-07-01_10-00-00.mp4")
    _clip(hl / "THOR" / "THOR_2026-07-01_10-05-00.mp4")
    squirrel = _clip(hl / "SQUIRREL_GIRL" / "SQUIRREL_GIRL_2026-07-02_11-00-00.mp4")
    _clip(hl / "IRON_MAN_2026-07-03_12-00-00.mp4")
    _clip(cfg.output_path / "thor_vid1" / "thor_vid1.mp4")
    (cfg.output_path / "thor_vid2").mkdir(parents=True)
    arch = _clip(cfg.archive_path / "THOR" / "THOR_2026-05-01_08-00-00.mp4")
    clip_cache.cache_save(str(thor_a), str(clip_cache.character_cache_dir(cfg.cache_dir, "THOR")), duration=700.0, ko_result={"tier": "KO"})
    clip_cache.cache_save(str(squirrel), str(clip_cache.character_cache_dir(cfg.cache_dir, "SQUIRREL_GIRL")), duration=100.0, ko_result=None)
    clip_cache.cache_save(str(arch), str(clip_cache.character_cache_dir(cfg.cache_dir, "THOR")), duration=50.0, ko_result={"tier": "QUAD"})
    cfg.state_path.write_text(json.dumps({
        "output_folders": {"thor_vid1": {"youtube_confirmed": True,
                                         "confirmed_at": "2026-07-05T10:00:00+00:00"}},
    }), encoding="utf-8")
    return cfg


def _build_folder_tree(root: Path) -> config.Config:
    cfg = _make_config(root)
    out = cfg.output_path
    _clip(out / "thor_enc" / "thor_enc.mp4")
    (out / "thor_enc" / "thor_enc_description.txt").write_text("text", encoding="utf-8")
    (out / "thor_enc" / "clips.json").write_text(json.dumps({
        "slug": "thor_enc", "char": "THOR",
        "clips": [{"name": "THOR_a.mp4", "tier": "QUAD"}, {"name": "THOR_b.mp4", "tier": "PENTA"},
                  {"name": "THOR_c.mp4", "tier": "KO"}],
    }), encoding="utf-8")
    _clip(out / "thor_enc" / "clips" / "THOR_a.mp4")
    _clip(out / "iron_bad" / "clips" / "IRON_a.mp4")
    (out / "iron_bad" / "clips.json").write_text("{not json", encoding="utf-8")
    _clip(out / "thor_up" / "thor_up.mp4")
    cfg.state_path.write_text(json.dumps({
        "videos": {"thor_up": {"url": "https://example.test/watch?v=up1"}},
    }), encoding="utf-8")
    return cfg


def _walk(value):
    """Every dict key and every string value in a payload, recursively."""
    if isinstance(value, dict):
        for key, item in value.items():
            yield str(key)
            yield from _walk(item)
    elif isinstance(value, list):
        for item in value:
            yield from _walk(item)
    elif isinstance(value, str):
        yield value


def _row_lists(snap: dict) -> dict:
    """Every list of contract rows, keyed by its path in the payload."""
    lists = {
        "clips.characters": snap["clips"]["characters"],
        "clips.unsorted": snap["clips"]["unsorted"],
        "clips.low_value": snap["clips"]["low_value"],
        "videos.folders": snap["videos"]["folders"],
        "archive.by_character": snap["archive"]["by_character"],
        "activity.jobs": snap["activity"]["jobs"],
    }
    plan = snap["compile"]["plan"]
    if plan:
        lists["compile.clips"] = [c for b in plan["batches"] for c in b["clips"]]
        lists["compile.duplicates"] = plan["duplicates"]
    cleanup = snap["videos"]["cleanup_plan"]
    if cleanup:
        lists["cleanup.items"] = cleanup["items"]
    return lists


def _folder_snap(row: dict) -> dict:
    return view_model.snapshot(_Stub(_data(output_folders=[row])))["videos"]["folders"][0]


# ----- top level and fixtures ---------------------------------------------------------


def test_every_fixture_has_the_contract_top_level_keys():
    for name, snap in _fixture_snaps().items():
        assert set(snap) == TOP_KEYS, name
        assert snap["schema"] == 1, name
        assert snap["poll_interval"] == 2, name
        assert snap["fixture"] == name, name
        assert snap["boot_id"] == build_info.BOOT_ID, name
        assert snap["build"] == build_info.line(), name


def test_real_tree_snapshot_has_the_contract_top_level_keys(tmp_path):
    snap = view_model.snapshot(RealSource(_build_tree(tmp_path)))
    assert set(snap) == TOP_KEYS
    assert snap["fixture"] is None


def test_testid_has_kind_slug_and_six_hex_digits():
    tid = view_model.testid("video", "thor_vid1")
    assert re.fullmatch(r"video-thor-vid1-[0-9a-f]{6}", tid)
    assert view_model.testid("video", "thor_vid1") == tid  # deterministic


def test_testid_keeps_names_that_slug_alike_apart():
    assert view_model.testid("clip-char", "IRON MAN") != view_model.testid("clip-char", "IRON-MAN")
    assert view_model.testid("clip-char", "THOR") != view_model.testid("video", "THOR")


def test_testids_are_unique_within_every_list_on_long_names():
    snap = view_model.snapshot(FixtureSource("long_names"))
    for path, rows in _row_lists(snap).items():
        ids = [r["testid"] for r in rows if "testid" in r]
        assert len(ids) == len(set(ids)), path
    assert len(snap["clips"]["characters"]) == 1
    assert len(snap["clips"]["unsorted"]) == 1


def test_testids_are_unique_within_every_list_in_every_fixture():
    for name, snap in _fixture_snaps().items():
        for path, rows in _row_lists(snap).items():
            ids = [r["testid"] for r in rows if "testid" in r]
            assert len(ids) == len(set(ids)), (name, path)


# ----- stage ---------------------------------------------------------------------------


STAGE_CASES = [
    # live wins even when the folder still holds a video and a url
    ("live", dict(video_count=1, youtube_confirmed=True, video_url="u")),
    ("live", dict(video_count=0, youtube_confirmed=True)),
    # cleaned_partly: no video, but a description or a clips folder is left
    ("cleaned_partly", dict(video_count=0, has_desc=True)),
    ("cleaned_partly", dict(video_count=0, has_clips_dir=True, video_url="u")),
    # uploaded: a url is recorded (the video need not still be on disk)
    ("uploaded", dict(video_count=1, video_url="u")),
    ("uploaded", dict(video_count=0, video_url="u")),
    # encoded: everything else
    ("encoded", dict(video_count=1)),
    ("encoded", dict(video_count=0)),
]


def test_stage_rule_first_match_wins():
    for expected, over in STAGE_CASES:
        options = dict(over)
        video_count = options.pop("video_count")
        row = fixtures.folder("thor_case", video_count, **options)
        assert _folder_snap(row)["stage"] == expected, (expected, over)


def test_folder_row_has_exactly_the_contract_keys_and_months_may_be_none():
    row = fixtures.folder("thor_vid1", 1, character="THOR", has_desc=True, clips=3,
                          quad_plus=1, has_clips_dir=True, video_url="u")
    out = _folder_snap(row)
    assert set(out) == {"testid", "slug", "character", "months", "has_video", "has_desc",
                        "clips", "quad_plus", "stage", "video_url", "confirmed_at"}
    assert out["months"] is None
    assert out["testid"] == view_model.testid("video", "thor_vid1")


def test_summary_counts_follow_the_stage_and_clip_fields():
    snap = view_model.snapshot(FixtureSource("needs_decision"))
    summary = snap["summary"]
    assert summary["unsorted"] == 1
    assert summary["protected"] == 0
    assert summary["new_clips"] == 1
    assert summary["low_value_pending"] == 2
    assert summary["ready_characters"] == 2

    cleanup = view_model.snapshot(FixtureSource("cleanup_plan"))["summary"]
    assert cleanup["videos_to_clean"] == 1
    assert cleanup["videos_to_upload"] == 0
    assert cleanup["videos_to_confirm"] == 0

    awaiting = view_model.snapshot(FixtureSource("awaiting_live"))["summary"]
    assert awaiting["videos_to_confirm"] == 1


def test_ready_follows_min_batch_seconds(tmp_path):
    cfg = _build_tree(tmp_path)

    def ready_for(min_batch):
        snap = view_model.snapshot(RealSource(dataclasses.replace(cfg, min_batch_seconds=min_batch)))
        return {c["name"]: c["ready"] for c in snap["clips"]["characters"]}

    assert ready_for(600)["THOR"] is True    # one 700 s batch clears a 600 s floor
    assert ready_for(800)["THOR"] is False   # and does not clear an 800 s one


# ----- privacy and mirror --------------------------------------------------------------


def test_no_payload_carries_token_secret_or_client_id(tmp_path):
    payloads = list(_fixture_snaps().values())
    payloads.append(view_model.snapshot(RealSource(_build_tree(tmp_path / "a"))))
    payloads.append(view_model.snapshot(RealSource(_build_folder_tree(tmp_path / "b"))))
    for snap in payloads:
        for text in _walk(snap):
            lowered = text.lower()
            for word in FORBIDDEN_WORDS:
                assert word not in lowered, (snap["fixture"], text)


def test_every_job_kind_is_a_job_and_an_activity_somewhere():
    snaps = _fixture_snaps()
    job_kinds = {s["job"]["kind"] for s in snaps.values() if s["job"]}
    activity_kinds = {j["kind"] for s in snaps.values() for j in s["activity"]["jobs"]}
    for kind in JOB_KINDS:
        assert kind in job_kinds, kind
        assert kind in activity_kinds, kind


def test_job_row_maps_eta_and_defaults_cancellable():
    raw = {"id": "abc123", "kind": "scan", "title": "Scan", "phase": "scanning", "done": 1,
           "total": 4, "unit": "clips", "eta": 12.5, "started_at": "2026-11-17T08:55:00+00:00"}
    snap = view_model.snapshot(_Stub(_data()), job=raw)
    assert snap["job"] == {"id": "abc123", "kind": "scan", "title": "Scan", "phase": "scanning",
                           "done": 1, "total": 4, "unit": "clips", "eta_s": 12.5,
                           "started_at": "2026-11-17T08:55:00+00:00", "cancellable": True}
    assert view_model.snapshot(_Stub(_data()))["job"] is None


def test_only_scan_and_cleanup_jobs_are_cancellable_whatever_the_record_says():
    assert view_model.CANCELLABLE_KINDS == frozenset({"scan", "cleanup"})
    for kind, expected in (("scan", True), ("cleanup", True), ("encode", False),
                           ("upload", False), ("compile", False), ("sort", False)):
        snap = view_model.snapshot(_Stub(_data()), job={"id": "j", "kind": kind, "cancellable": True})
        assert snap["job"]["cancellable"] is expected, kind


# ----- overrides and history -----------------------------------------------------------


def test_job_argument_overrides_the_source_job():
    source = _Stub(_data(job={"id": "src", "kind": "sort", "title": "S", "phase": "p", "done": 0,
                              "total": None, "unit": "", "eta_s": None,
                              "started_at": None, "cancellable": True}))
    assert view_model.snapshot(source)["job"]["id"] == "src"
    assert view_model.snapshot(source, job={"id": "live", "kind": "scan"})["job"]["id"] == "live"


def test_history_records_map_state_and_finish_time_to_activity_rows():
    history = [{"id": "h2", "kind": "upload", "title": "Upload thor_vid1", "state": "failed",
                "started_at": "2026-11-17T08:00:00+00:00", "finished_at": "2026-11-17T08:01:00+00:00",
                "error": "auth expired", "log_path": None}]
    rows = view_model.snapshot(_Stub(_data()), history=history)["activity"]["jobs"]
    assert len(rows) == 1
    assert rows[0]["testid"] == view_model.testid("job", "h2")
    assert rows[0]["result"] == "failed"
    assert rows[0]["ended_at"] == "2026-11-17T08:01:00+00:00"
    assert rows[0]["error"] == "auth expired"


def test_plans_argument_overrides_the_source_plans():
    fixture_plan = fixtures.SCENARIOS["plan"]["compile_plan"]
    snap = view_model.snapshot(_Stub(_data()), plans={"compile_plan": fixture_plan})
    plan = snap["compile"]["plan"]
    assert plan["nonce"] == fixture_plan["nonce"]
    first_clip = plan["batches"][0]["clips"][0]
    assert first_clip["testid"] == view_model.testid("plan-clip", first_clip["name"])
    assert plan["duplicates"][0]["score"] == fixture_plan["duplicates"][0]["score"]
    assert view_model.snapshot(_Stub(_data()))["compile"] == {"plan": None}


def test_cleanup_plan_items_get_fate_testids():
    snap = view_model.snapshot(FixtureSource("cleanup_plan"))
    cleanup = snap["videos"]["cleanup_plan"]
    assert cleanup["slug"] == "thor_vid1"
    assert cleanup["totals"] == {"remove_count": 2, "remove_mb": 1602.5}
    item = cleanup["items"][0]
    assert item["testid"] == view_model.testid("fate", item["name"])


def test_snapshot_never_mutates_its_source():
    data = _data(unsorted=[{"name": "a.mp4", "protected": False}],
                 output_folders=[fixtures.folder("thor_x", 1)])
    before = copy.deepcopy(data)
    source = _Stub(data)
    view_model.snapshot(source)
    view_model.snapshot(source, job={"id": "x", "kind": "scan"})
    assert data == before


def test_archive_rows_carry_testids_and_totals():
    snap = view_model.snapshot(FixtureSource("huge_archive"))
    assert snap["archive"]["total"] == 4200
    row = snap["archive"]["by_character"][0]
    assert set(row) == {"testid", "name", "count", "tiers"}
    assert row["testid"] == view_model.testid("archive", row["name"])


# ----- parity and shape ----------------------------------------------------------------


def test_real_rows_have_the_same_keys_as_fixture_rows(tmp_path):
    snaps = list(_fixture_snaps().values())
    snaps.append(view_model.snapshot(RealSource(_build_tree(tmp_path / "a"))))
    snaps.append(view_model.snapshot(RealSource(_build_folder_tree(tmp_path / "b"))))
    key_sets: dict[str, set] = {}
    for snap in snaps:
        for path, rows in _row_lists(snap).items():
            key_sets.setdefault(path, set()).update(frozenset(r) for r in rows)
    for path, sets in key_sets.items():
        assert len(sets) == 1, path
    assert len(key_sets["clips.characters"]) == 1
    assert len(key_sets["videos.folders"]) == 1


def test_real_tree_snapshot_matches_a_stub_source_built_from_the_same_data(tmp_path):
    source = RealSource(_build_folder_tree(tmp_path))
    real = view_model.snapshot(source)
    raw = source.read()
    from_data = view_model.snapshot(_Stub(raw))
    real.pop("generated_at")
    from_data.pop("generated_at")
    assert real == from_data


def test_real_tree_folder_rows_match_the_fixture_stages(tmp_path):
    snap = view_model.snapshot(RealSource(_build_folder_tree(tmp_path)))
    stages = {f["slug"]: f["stage"] for f in snap["videos"]["folders"]}
    # thor_enc: video and clips, no url yet; iron_bad: clips folder and a bad manifest, no video;
    # thor_up: a video with a recorded url.
    assert stages == {"thor_enc": "encoded", "iron_bad": "cleaned_partly", "thor_up": "uploaded"}


# ----- purity --------------------------------------------------------------------------


def test_view_model_imports_no_mutating_or_source_modules():
    tree = ast.parse(SRC_FILE.read_text(encoding="utf-8"))
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module.split(".")[0])
            names.update(alias.name for alias in node.names)
    assert not (names & FORBIDDEN_IMPORTS), names & FORBIDDEN_IMPORTS
