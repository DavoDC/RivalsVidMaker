from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
REQUIREMENTS = REPO_ROOT / "config" / "requirements.txt"
GITIGNORE = REPO_ROOT / ".gitignore"


def test_requirements_lists_nicegui():
    lines = REQUIREMENTS.read_text(encoding="utf-8").splitlines()
    assert any(line.strip().startswith("nicegui") for line in lines)


def test_gitignore_ignores_gui_runtime_folders():
    lines = {line.strip() for line in GITIGNORE.read_text(encoding="utf-8").splitlines()}
    for entry in ("data/captures/", "data/gui/", "data/.cache/"):
        assert entry in lines, f"missing .gitignore entry: {entry}"
