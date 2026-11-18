import re
import subprocess
from datetime import datetime

from gui import build_info

SHA = "0123456789abcdef0123456789abcdef01234567"
COMMIT_ISO = "2026-11-17T10:00:00+00:00"
EXPECTED_DATE = datetime.fromisoformat(COMMIT_ISO).astimezone().strftime("%d/%m/%Y")


class FakeGit:
    """Stands in for subprocess.run. Records each git call so tests can count them."""

    def __init__(self, log_out=f"{SHA} {COMMIT_ISO}\n", status_out="", fail=False, raises=None):
        self.log_out = log_out
        self.status_out = status_out
        self.fail = fail
        self.raises = raises
        self.calls = []

    def __call__(self, cmd, **kwargs):
        self.calls.append(cmd)
        if self.raises is not None:
            raise self.raises
        if self.fail:
            return subprocess.CompletedProcess(cmd, 128, "", "fatal: not a git repository")
        if "log" in cmd:
            return subprocess.CompletedProcess(cmd, 0, self.log_out, "")
        if "status" in cmd:
            return subprocess.CompletedProcess(cmd, 0, self.status_out, "")
        return subprocess.CompletedProcess(cmd, 1, "", "")


def _clock_of_commit():
    dt = datetime.fromisoformat(COMMIT_ISO).astimezone()
    return f"{dt.hour % 12 or 12}:{dt.minute:02d}{'am' if dt.hour < 12 else 'pm'}"


def test_describe_has_the_commit_time_as_h_mm_am_pm():
    info = build_info.describe(runner=FakeGit(), refresh=True)
    assert info["time"] == _clock_of_commit()


def test_short_is_the_sha_and_commit_time_with_dirty_marker_last():
    info = build_info.describe(runner=FakeGit(), refresh=True)
    assert build_info.short(info) == f"0123456 {_clock_of_commit()}"
    dirty = build_info.describe(runner=FakeGit(status_out=" M src/gui/x.py\n"), refresh=True)
    assert build_info.short(dirty) == f"0123456 {_clock_of_commit()} +dirty"


def test_short_is_unknown_outside_a_checkout():
    info = build_info.describe(runner=FakeGit(fail=True), refresh=True)
    assert build_info.short(info) == "unknown"


def test_line_is_repo_short_sha_and_commit_date():
    fake = FakeGit()
    info = build_info.describe(runner=fake, refresh=True)
    line = build_info.line(info)
    assert re.fullmatch(r"RivalsVidMaker [0-9a-f]{7} \d{2}/\d{2}/\d{4}", line)
    assert line == f"RivalsVidMaker 0123456 {EXPECTED_DATE}"


def test_line_adds_dirty_marker_when_tracked_files_changed():
    fake = FakeGit(status_out=" M src/gui/build_info.py\n")
    info = build_info.describe(runner=fake, refresh=True)
    assert info["dirty"] is True
    assert build_info.line(info).endswith(" +dirty")


def test_clean_tree_has_no_dirty_marker():
    info = build_info.describe(runner=FakeGit(), refresh=True)
    assert info["dirty"] is False
    assert "+dirty" not in build_info.line(info)


def test_git_runs_once_per_process(monkeypatch):
    fake = FakeGit()
    info_first = build_info.describe(runner=fake, refresh=True)
    calls_after_first = len(fake.calls)
    assert calls_after_first == 2  # one log, one status

    build_info.describe(runner=fake)
    build_info.describe(runner=fake)
    assert len(fake.calls) == calls_after_first
    assert info_first["sha"] == "0123456"

    default = FakeGit()
    monkeypatch.setattr(build_info.subprocess, "run", default)
    build_info._cache.clear()
    build_info.line()
    build_info.line()
    build_info.as_dict()
    assert len(default.calls) == 2


def test_as_dict_has_the_contract_keys():
    info = build_info.as_dict()
    assert set(info) == {"line", "sha", "dirty", "date", "boot_id", "started_at"}
    assert re.fullmatch(r"[0-9a-f]{12}", info["boot_id"])
    datetime.fromisoformat(info["started_at"])


def test_no_git_degrades_to_unknown_without_raising():
    fake = FakeGit(raises=FileNotFoundError("git"))
    info = build_info.describe(runner=fake, refresh=True)
    assert info["sha"] == "unknown"
    assert info["dirty"] is False
    assert build_info.line(info) == "RivalsVidMaker unknown"


def test_not_a_repo_degrades_to_unknown_without_raising():
    info = build_info.describe(runner=FakeGit(fail=True), refresh=True)
    assert info["sha"] == "unknown"
    assert build_info.line(info) == "RivalsVidMaker unknown"
