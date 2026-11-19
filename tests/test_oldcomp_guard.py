"""Tests for oldcomp_guard: writes must stay out of OldCompilations, and reads never change the tree."""

import os
import re
from pathlib import Path

import pytest

import oldcomp_guard
from oldcomp_guard import assert_outside_oldcomp, open_readonly


@pytest.fixture
def fake_tree(tmp_path):
    """A stand-in for Videos\\MarvelRivals with an OldCompilations folder and a ClipArchive folder."""
    root = tmp_path / "MarvelRivals"
    old = root / "OldCompilations"
    archive = root / "ClipArchive" / "THOR"
    old.mkdir(parents=True)
    archive.mkdir(parents=True)
    (old / "a.mp4").write_bytes(b"x" * 100)
    (old / "sub").mkdir()
    (old / "sub" / "b.mp4").write_bytes(b"y" * 50)
    (archive / "THOR_2026-02-06_22-38-56_QUAD.mp4").write_bytes(b"z" * 10)
    return root, old, archive


def _snapshot(folder):
    """Sorted (relative path, size, mtime_ns) for every entry under folder."""
    rows = []
    for dirpath, dirnames, filenames in os.walk(folder):
        for name in dirnames + filenames:
            full = Path(dirpath) / name
            st = full.stat()
            rows.append((str(full.relative_to(folder)), st.st_size, st.st_mtime_ns))
    return sorted(rows)


def test_a_write_target_inside_oldcompilations_raises(fake_tree):
    _, old, _ = fake_tree
    with pytest.raises(oldcomp_guard.OldCompViolation):
        assert_outside_oldcomp(old / "out.mp4", old)


def test_a_write_target_in_a_subfolder_of_oldcompilations_raises(fake_tree):
    _, old, _ = fake_tree
    with pytest.raises(oldcomp_guard.OldCompViolation):
        assert_outside_oldcomp(old / "sub" / "new" / "out.mp4", old)


def test_a_path_that_climbs_back_into_oldcompilations_raises(fake_tree):
    _, old, archive = fake_tree
    sneaky = archive / ".." / ".." / "OldCompilations" / "out.mp4"
    with pytest.raises(oldcomp_guard.OldCompViolation):
        assert_outside_oldcomp(sneaky, old)


def test_a_path_outside_oldcompilations_is_allowed(fake_tree):
    root, old, archive = fake_tree
    assert_outside_oldcomp(archive / "THOR_2026-02-06_22-38-56_QUAD.mp4", old)
    assert_outside_oldcomp(root / "Output" / "x.mp4", old)


def test_a_sibling_whose_name_starts_with_the_same_text_is_allowed(fake_tree):
    root, old, _ = fake_tree
    # "OldCompilationsMeta" shares the prefix but is not inside OldCompilations.
    assert_outside_oldcomp(root / "OldCompilationsMeta" / "staging" / "x.mp4", old)


def test_the_check_is_case_insensitive_on_windows(fake_tree):
    root, old, _ = fake_tree
    if os.name != "nt":
        pytest.skip("case-insensitive path check is Windows behaviour")
    shouting = Path(str(root / "OLDCOMPILATIONS" / "out.mp4").upper())
    with pytest.raises(oldcomp_guard.OldCompViolation):
        assert_outside_oldcomp(shouting, old)


def test_a_symlink_that_points_into_oldcompilations_is_caught(fake_tree, tmp_path):
    _, old, _ = fake_tree
    link = tmp_path / "elsewhere"
    try:
        os.symlink(old, link, target_is_directory=True)
    except OSError:
        pytest.skip("symlink creation needs privileges on this machine")
    with pytest.raises(oldcomp_guard.OldCompViolation):
        assert_outside_oldcomp(link / "out.mp4", old)


def test_open_readonly_returns_bytes_and_opens_for_reading_only(fake_tree):
    _, old, _ = fake_tree
    with open_readonly(old / "a.mp4") as fh:
        assert fh.mode == "rb"
        assert fh.read() == b"x" * 100


def test_guarded_reads_and_checks_leave_listing_size_and_mtime_unchanged(fake_tree):
    root, old, archive = fake_tree
    before = _snapshot(old)
    with open_readonly(old / "sub" / "b.mp4") as fh:
        fh.read()
    assert_outside_oldcomp(archive / "out.mp4", old)
    with pytest.raises(oldcomp_guard.OldCompViolation):
        assert_outside_oldcomp(old / "out.mp4", old)
    assert _snapshot(old) == before


def test_guard_module_contains_no_delete_or_move_calls():
    source = Path(oldcomp_guard.__file__).read_text(encoding="utf-8")
    forbidden = re.compile(r"os\.remove|os\.unlink|shutil\.move|shutil\.rmtree|os\.rename|os\.replace|\.unlink\(|\.rename\(|\.replace\(|\.rmdir\(|\.touch\(")
    hits = [line for line in source.splitlines() if forbidden.search(line)]
    assert hits == []
