"""Character avatars and display names (task 47), the app icon and the serve wiring that carries both.

Nothing here downloads an image or writes outside tmp_path: register() is pointed at a tmp asset folder.
"""
from pathlib import Path

from gui import avatars, tokens

REPO_ROOT = Path(__file__).resolve().parents[2]
MAIN_SRC = REPO_ROOT / "src" / "gui" / "__main__.py"
FAVICON = REPO_ROOT / "assets" / "favicon.svg"
GITIGNORE = REPO_ROOT / ".gitignore"


# ---- display names ---------------------------------------------------------------------------

def test_display_name_turns_folder_names_into_words():
    assert avatars.display_name("DOCTOR_STRANGE") == "Doctor Strange"
    assert avatars.display_name("THOR") == "Thor"


def test_display_name_keeps_the_small_words_lower_case_inside_a_name():
    assert avatars.display_name("JEFF_THE_LAND_SHARK") == "Jeff the Land Shark"
    assert avatars.display_name("CLOAK_AND_DAGGER") == "Cloak and Dagger"


def test_display_name_capitalises_a_small_word_when_it_comes_first():
    assert avatars.display_name("THE_THING") == "The Thing"


# ---- initials --------------------------------------------------------------------------------

def test_initials_use_first_and_last_word_when_there_are_several():
    assert avatars.initials("DOCTOR_STRANGE") == "DS"
    assert avatars.initials("JEFF_THE_LAND_SHARK") == "JS"


def test_initials_use_the_first_two_letters_of_a_single_word():
    assert avatars.initials("THOR") == "TH"


# ---- avatar markup ---------------------------------------------------------------------------

def test_avatar_without_a_portrait_is_an_initials_badge_and_no_image(tmp_path):
    html = avatars.avatar_html("THOR", asset_dir=tmp_path)
    assert "<img" not in html
    assert ">TH</span>" in html
    assert f"border:1px solid {tokens.LINE}" in html
    assert f"color:{tokens.TEXT_DIM}" in html
    assert f"font-size:{tokens.SIZE_FINE}px" in html
    assert f"background:{tokens.PANEL}" in html


def test_avatar_with_a_portrait_file_is_an_image_from_the_characters_url(tmp_path):
    (tmp_path / "THOR.png").write_bytes(b"")
    html = avatars.avatar_html("THOR", asset_dir=tmp_path)
    assert '<img src="/characters/THOR.png"' in html
    assert 'width="28" height="28"' in html
    assert "<span" not in html


def test_avatar_is_a_28px_square_hidden_from_assistive_tech(tmp_path):
    html = avatars.avatar_html("THOR", asset_dir=tmp_path)
    assert 'aria-hidden="true"' in html
    assert "flex:none" in html
    assert f"border-radius:{tokens.RADIUS_PANEL}px" in html
    assert "width:28px;height:28px" in html


def test_avatar_escapes_a_folder_name_that_holds_markup(tmp_path):
    html = avatars.avatar_html("<script>", asset_dir=tmp_path)
    assert "<script" not in html
    assert "&lt;" in html


def test_avatar_defaults_to_the_repo_asset_folder_when_no_folder_is_given(monkeypatch, tmp_path):
    monkeypatch.setattr(avatars, "ASSET_DIR", tmp_path)
    (tmp_path / "THOR.png").write_bytes(b"")
    assert '<img src="/characters/THOR.png"' in avatars.avatar_html("THOR")


# ---- name cell (avatar then display name, shared by Clips, Archive and Videos) ---------------

def test_name_cell_is_the_badge_then_the_display_name_in_a_flex_row(monkeypatch, tmp_path):
    monkeypatch.setattr(avatars, "ASSET_DIR", tmp_path)
    html = avatars.name_cell_html("DOCTOR_STRANGE")
    assert html == ('<div style="display:flex;align-items:center;gap:8px;">'
                    + avatars.avatar_html("DOCTOR_STRANGE", asset_dir=tmp_path) + "Doctor Strange</div>")
    assert ">DS</span>" in html
    assert "DOCTOR_STRANGE" not in html


def test_name_cell_escapes_a_name_that_holds_markup(monkeypatch, tmp_path):
    monkeypatch.setattr(avatars, "ASSET_DIR", tmp_path)
    html = avatars.name_cell_html("<i>x</i>")
    assert "<i>" not in html
    assert "&lt;i&gt;x&lt;/i&gt;" in html


# ---- static mount ----------------------------------------------------------------------------

class _FakeApp:
    def __init__(self):
        self.mounts = []

    def add_static_files(self, url_path, local_directory):
        self.mounts.append((url_path, local_directory))


def test_register_creates_the_asset_folder_and_mounts_it_at_characters(monkeypatch, tmp_path):
    target = tmp_path / "characters"
    monkeypatch.setattr(avatars, "ASSET_DIR", target)
    app = _FakeApp()
    avatars.register(app)
    assert target.is_dir()
    assert app.mounts == [("/characters", str(target))]


def test_asset_folder_is_the_characters_folder_under_the_repo_root():
    assert avatars.ASSET_DIR == REPO_ROOT / "assets" / "characters"
    assert avatars.URL_PREFIX == "/characters"


# ---- app icon and serve wiring ---------------------------------------------------------------

def test_favicon_svg_is_gone_the_icon_renderer_replaces_it():
    assert not FAVICON.exists()


def test_serve_passes_the_favicon_and_registers_the_avatar_mount():
    text = MAIN_SRC.read_text(encoding="utf-8")
    assert "avatars.register(app)" in text
    assert "favicon=icon.data_url" in text and "favicon.svg" not in text
    run_line = next(line for line in text.splitlines() if "ui.run(" in line)
    assert "favicon=" in run_line


def test_gitignore_keeps_character_portraits_out_of_git():
    lines = GITIGNORE.read_text(encoding="utf-8").splitlines()
    assert "assets/characters/" in lines
    assert "# character portraits are game art, fetched locally, never committed" in lines
