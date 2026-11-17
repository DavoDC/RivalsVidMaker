"""
Tests for scripts/fetch_character_icons.py - the portrait fetcher for assets/characters.

Nothing here touches the network. Every test passes a fake fetch, and the default fetch is
only checked for its URL guard, which raises before any request is made.
"""

import importlib.util
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "fetch_character_icons.py"
_spec = importlib.util.spec_from_file_location("fetch_character_icons", SCRIPT)
mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mod)

PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"fake-png-body"
BUILD = "https://www.marvelrivals.com/pc/gw/20261012144108/img/heroes"

SAMPLE_PAGE = (
    '<a href="./366w78k4i4gap/index.html" data-id="366w78k4i4gap" data-name="ADAM WARLOCK" '
    'title="ADAM WARLOCK"><img src="' + BUILD + '/366w78k4i4gap/avatar_e2f9f6e4.png" alt="">'
    '<img src="' + BUILD + '/366w78k4i4gap/card-image_abf2a5ad.png" alt="">'
    '<img src="' + BUILD + '/366w78k4i4gap/avatar-active_e8ed91df.png" alt=""></a>'
    '<a href="./2g4bea0bj96lx/index.html" data-id="2g4bea0bj96lx" data-name="ANGELA" '
    'title="ANGELA"><img src="' + BUILD + '/2g4bea0bj96lx/avatar_95580dcd.png" alt=""></a>'
)


def page_with(*anchors: str) -> str:
    return "<html><body>" + "".join(anchors) + "</body></html>"


def anchor(name: str, avatar: str = "avatar_aaaa.png") -> str:
    return (
        f'<a href="./x/index.html" data-id="x" data-name="{name}" title="{name}">'
        f'<img src="{BUILD}/x/{avatar}" alt=""></a>'
    )


def make_fetch(page: str, image: bytes = PNG_BYTES, overrides=None):
    """Fake fetch: the heroes page returns `page`, each image returns `image` unless overridden."""
    overrides = overrides or {}
    calls = []

    def fake(url):
        calls.append(url)
        if url == mod.HEROES_URL:
            return page.encode("utf-8")
        if url in overrides:
            return overrides[url]
        return image

    fake.calls = calls
    return fake


# parse_heroes


def test_parse_heroes_takes_the_avatar_image_for_each_hero():
    assert mod.parse_heroes(SAMPLE_PAGE) == [
        ("ADAM_WARLOCK", BUILD + "/366w78k4i4gap/avatar_e2f9f6e4.png"),
        ("ANGELA", BUILD + "/2g4bea0bj96lx/avatar_95580dcd.png"),
    ]


def test_parse_heroes_keeps_hyphens_in_names():
    page = page_with(anchor("SPIDER-MAN"))
    assert mod.parse_heroes(page) == [("SPIDER-MAN", BUILD + "/x/avatar_aaaa.png")]


def test_parse_heroes_unescapes_ampersands_and_turns_spaces_into_underscores():
    page = page_with(anchor("CLOAK &amp; DAGGER"))
    assert [folder for folder, _ in mod.parse_heroes(page)] == ["CLOAK_&_DAGGER"]


def test_parse_heroes_lists_a_duplicated_anchor_once_in_page_order():
    page = page_with(anchor("ANGELA"), anchor("THOR"), anchor("ANGELA"))
    assert [folder for folder, _ in mod.parse_heroes(page)] == ["ANGELA", "THOR"]


def test_parse_heroes_ignores_anchors_without_an_avatar_image():
    page = page_with(anchor("NO_PORTRAIT", avatar="card-image_bbbb.png"), anchor("THOR"))
    assert [folder for folder, _ in mod.parse_heroes(page)] == ["THOR"]


def test_parse_heroes_returns_nothing_for_a_page_without_anchors():
    assert mod.parse_heroes("<html><body>maintenance</body></html>") == []


# fetch URL guard


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com/heroes/",
        "http://www.marvelrivals.com/heroes/",
        "https://www.marvelrivals.com.evil.example/x.png",
        "file:///C:/Windows/win.ini",
    ],
)
def test_fetch_rejects_urls_outside_marvelrivals(url):
    with pytest.raises(ValueError):
        mod.fetch(url)


# main


def test_main_writes_both_pngs(tmp_path):
    dest = tmp_path / "characters"
    fake = make_fetch(SAMPLE_PAGE)
    assert mod.main(["--dest", str(dest)], fetch=fake) == 0
    assert (dest / "ADAM_WARLOCK.png").read_bytes() == PNG_BYTES
    assert (dest / "ANGELA.png").read_bytes() == PNG_BYTES


def test_main_second_run_keeps_existing_files(tmp_path, capsys):
    dest = tmp_path / "characters"
    mod.main(["--dest", str(dest)], fetch=make_fetch(SAMPLE_PAGE))
    fake = make_fetch(SAMPLE_PAGE)
    assert mod.main(["--dest", str(dest)], fetch=fake) == 0
    assert fake.calls == [mod.HEROES_URL]
    assert "Saved 0, kept 2, failed 0." in capsys.readouterr().out


def test_main_force_rewrites_existing_files(tmp_path):
    dest = tmp_path / "characters"
    dest.mkdir()
    (dest / "ANGELA.png").write_bytes(b"\x89PNG\r\n\x1a\nold")
    fake = make_fetch(SAMPLE_PAGE, image=PNG_BYTES)
    assert mod.main(["--dest", str(dest), "--force"], fetch=fake) == 0
    assert (dest / "ANGELA.png").read_bytes() == PNG_BYTES
    assert len(fake.calls) == 3


def test_main_dry_run_writes_nothing(tmp_path, capsys):
    dest = tmp_path / "characters"
    fake = make_fetch(SAMPLE_PAGE)
    assert mod.main(["--dest", str(dest), "--dry-run"], fetch=fake) == 0
    assert not dest.exists()
    assert fake.calls == [mod.HEROES_URL]
    out = capsys.readouterr().out
    assert "ADAM_WARLOCK" in out and "ANGELA" in out


def test_main_counts_a_non_png_body_as_failed(tmp_path, capsys):
    dest = tmp_path / "characters"
    page = SAMPLE_PAGE
    angela = BUILD + "/2g4bea0bj96lx/avatar_95580dcd.png"
    fake = make_fetch(page, overrides={angela: b"<html>blocked</html>"})
    assert mod.main(["--dest", str(dest)], fetch=fake) == 0
    assert (dest / "ADAM_WARLOCK.png").exists()
    assert not (dest / "ANGELA.png").exists()
    out = capsys.readouterr().out
    assert "failed: ANGELA: not a PNG" in out
    assert "Saved 1, kept 0, failed 1." in out


def test_main_exits_1_when_the_page_has_no_heroes(tmp_path, capsys):
    dest = tmp_path / "characters"
    fake = make_fetch("<html><body>maintenance</body></html>")
    assert mod.main(["--dest", str(dest)], fetch=fake) == 1
    assert "No heroes found on the page; the site layout may have changed." in capsys.readouterr().out
    assert fake.calls == [mod.HEROES_URL]
