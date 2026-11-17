"""Data-source seam (DESIGN-PLAN section 6 and 11): src/gui/sources.py and src/gui/fixtures.py.

RealSource is read-only: these tests prove it by fingerprinting a tmp tree
(relative path, kind, size and mtime of every entry) before and after a read.
"""
import ast
import json
import re
from datetime import datetime
from pathlib import Path

import pytest

import clip_cache
import config
from gui import fixtures, sources
from gui.sources import FixtureSource, RealSource, Source

SRC_FILE = Path(sources.__file__).resolve()

# Section 11 scenario names, in the order the design lists them.
SECTION_11 = [
    "empty", "fresh_intake", "needs_decision", "ready", "plan", "scanning",
    "encoding", "upload_failed", "awaiting_live", "cleanup_plan", "huge_archive",
    "long_names", "stale", "config_broken", "busy_refused", "interrupted",
]

REQUIRED_KEYS = {
    "fixture", "generated_at", "stale", "config_problems", "job", "unsorted",
    "characters", "low_value", "compile_plan", "output_folders", "cleanup_plan",
    "archive", "activity", "notices",
}

TIER_KEYS = {"KO", "DOUBLE", "TRIPLE", "QUAD", "PENTA", "HEXA"}

FORBIDDEN_IMPORTS = {
    "pipeline", "cleanup", "preprocess", "uploader", "encoder",
    "clip_sorter", "dedup", "ko_detect", "bridge",
}
WRITE_NAMES = {
    "save", "cache_save", "mkdir", "makedirs", "write_text", "write_bytes",
    "unlink", "rename", "replace", "remove", "rmtree", "move", "copy",
    "copy2", "copyfile", "touch",
}


def _make_config(root: Path, **over) -> config.Config:
    """A Config whose tool paths exist, built directly (no config/config.json read)."""
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
    _clip(hl / "THOR" / "vid1_uploaded" / "THOR_2026-06-01_09-00-00.mp4")
    squirrel = _clip(hl / "SQUIRREL_GIRL" / "SQUIRREL_GIRL_2026-07-02_11-00-00.mp4")
    _clip(hl / "IRON_MAN_2026-07-03_12-00-00.mp4")
    _clip(hl / "THOR_2026-07-04_12-00-00.mp4")
    _clip(cfg.output_path / "thor_vid1" / "thor_vid1.mp4")
    (cfg.output_path / "thor_vid2").mkdir(parents=True)
    arch = _clip(cfg.archive_path / "THOR" / "THOR_2026-05-01_08-00-00.mp4")

    cache_clip = cfg.cache_dir
    clip_cache.cache_save(str(thor_a), str(cache_clip), duration=700.0, ko_result={"tier": "KO"})
    clip_cache.cache_save(str(squirrel), str(cache_clip), duration=100.0, ko_result=None)
    clip_cache.cache_save(str(arch), str(cache_clip), duration=50.0, ko_result={"tier": "QUAD"})

    cfg.state_path.write_text(json.dumps({
        "output_folders": {
            "thor_vid1": {"youtube_confirmed": True, "confirmed_at": "2026-07-05T10:00:00+00:00"},
        },
    }), encoding="utf-8")
    return cfg


def _fingerprint(root: Path) -> list:
    rows = []
    for p in sorted(root.rglob("*")):
        st = p.stat()
        rows.append((p.relative_to(root).as_posix(), p.is_dir(), st.st_size, st.st_mtime_ns))
    return rows


def _strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for k, v in value.items():
            yield from _strings(k)
            yield from _strings(v)
    elif isinstance(value, (list, tuple)):
        for v in value:
            yield from _strings(v)


# ── Scenarios (section 11) ────────────────────────────────────────────────────

def test_fixture_catalogue_matches_section_11():
    assert set(fixtures.SCENARIOS) == set(SECTION_11)
    assert len(SECTION_11) == 16


@pytest.mark.parametrize("name", SECTION_11)
def test_every_section_11_scenario_loads(name):
    data = FixtureSource(name).read()
    assert REQUIRED_KEYS <= set(data)
    assert data["fixture"] == name
    assert data["config_problems"] is not None
    assert isinstance(data["characters"], list)
    for ch in data["characters"]:
        assert set(ch["tiers"]) == TIER_KEYS


def test_unknown_scenario_is_rejected():
    with pytest.raises(ValueError):
        FixtureSource("no_such_scenario")


def test_fixture_read_returns_a_copy():
    first = FixtureSource("ready").read()
    first["characters"].clear()
    assert FixtureSource("ready").read()["characters"] != []


def test_fixture_data_is_plain_and_invented():
    for name in SECTION_11:
        for text in _strings(FixtureSource(name).read()):
            assert "\\" not in text, text
            assert not re.search(r"[A-Za-z]:[\\/]", text), text
            assert "Users" not in text, text
            assert not re.search(r"UC[A-Za-z0-9_-]{20,}", text), text


def test_config_broken_reports_missing_tools_and_stale_has_old_timestamp():
    broken = FixtureSource("config_broken").read()
    assert broken["config_problems"]
    stale = FixtureSource("stale").read()
    assert stale["stale"] is True
    assert datetime.fromisoformat(stale["generated_at"]) < datetime.fromisoformat(fixtures.GENERATED_AT)


def test_protocol_is_satisfied_by_both_sources(tmp_path):
    assert isinstance(FixtureSource("empty"), Source)
    assert isinstance(RealSource(_make_config(tmp_path)), Source)


# ── RealSource on a tmp Highlights tree ───────────────────────────────────────

def test_real_source_lists_characters_unsorted_and_output_folders(tmp_path):
    cfg = _build_tree(tmp_path)
    data = RealSource(cfg).read()

    assert data["fixture"] is None
    assert data["stale"] is False
    assert data["config_problems"] == []
    assert REQUIRED_KEYS <= set(data)

    assert data["unsorted"] == [
        {"name": "IRON_MAN_2026-07-03_12-00-00.mp4", "protected": False},
        {"name": "THOR_2026-07-04_12-00-00.mp4", "protected": True},
    ]

    chars = {c["name"]: c for c in data["characters"]}
    assert sorted(chars) == ["SQUIRREL_GIRL", "THOR"]
    thor = chars["THOR"]
    assert thor["clips"] == 2            # nested vid1_uploaded clip is not counted
    assert thor["scanned"] == 1
    assert thor["unscanned"] == 1
    assert thor["minutes"] == 11.7
    assert thor["tiers"]["KO"] == 1
    assert thor["ready"] is True         # one 700 s batch clears min_batch_seconds (600)
    assert chars["SQUIRREL_GIRL"]["ready"] is False   # 100 s is below 600 s
    assert chars["SQUIRREL_GIRL"]["tiers"] == {t: 0 for t in TIER_KEYS}

    folders = {f["slug"]: f for f in data["output_folders"]}
    assert folders["thor_vid1"]["video_count"] == 1
    assert folders["thor_vid1"]["youtube_confirmed"] is True
    assert folders["thor_vid1"]["confirmed_at"] == "2026-07-05T10:00:00+00:00"
    assert folders["thor_vid2"]["video_count"] == 0
    assert folders["thor_vid2"]["youtube_confirmed"] is False
    assert folders["thor_vid2"]["confirmed_at"] is None

    assert data["archive"]["total"] == 1
    arch = data["archive"]["by_character"]
    assert [(a["name"], a["count"]) for a in arch] == [("THOR", 1)]
    assert arch[0]["tiers"]["QUAD"] == 1

    assert data["job"] is None
    assert data["compile_plan"] is None
    assert data["cleanup_plan"] is None
    assert data["activity"] == []
    assert data["low_value"] == []
    assert data["notices"] == []


def test_real_source_writes_nothing(tmp_path):
    cfg = _build_tree(tmp_path)
    before = _fingerprint(tmp_path)
    RealSource(cfg).read()
    RealSource(cfg).read()
    assert _fingerprint(tmp_path) == before


def test_real_source_creates_nothing_when_folders_are_missing(tmp_path):
    cfg = _make_config(tmp_path)
    before = _fingerprint(tmp_path)
    data = RealSource(cfg).read()
    assert data["unsorted"] == []
    assert data["characters"] == []
    assert data["output_folders"] == []
    assert data["archive"] == {"total": 0, "by_character": []}
    assert not cfg.clips_path.exists()
    assert not cfg.cache_dir.exists()
    assert not cfg.state_path.exists()
    assert _fingerprint(tmp_path) == before


def test_real_source_reports_missing_tools(tmp_path):
    cfg = _make_config(tmp_path, ffmpeg=tmp_path / "nope" / "ffmpeg.exe")
    problems = RealSource(cfg).read()["config_problems"]
    assert any("ffmpeg" in p for p in problems)


# ── Read-only import boundary ─────────────────────────────────────────────────

def _parsed_sources():
    return ast.parse(SRC_FILE.read_text(encoding="utf-8"), filename=str(SRC_FILE))


def _imported_modules(tree):
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module.split(".")[0])
    return names


def test_sources_imports_no_mutating_engine_module():
    tree = _parsed_sources()
    assert _imported_modules(tree) & FORBIDDEN_IMPORTS == set()


def test_sources_only_uses_read_only_helpers():
    tree = _parsed_sources()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "state":
            assert {a.name for a in node.names} <= {"load"}
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
            if node.value.id == "state":
                assert node.attr in {"load", "is_youtube_confirmed"}  # both pure reads
            if node.value.id == "clip_cache":
                assert node.attr == "cache_load"
        if isinstance(node, ast.Attribute):
            assert node.attr not in WRITE_NAMES, node.attr
        if isinstance(node, ast.Name):
            assert node.id not in WRITE_NAMES, node.id
