"""The last tab the user showed: remembered in memory by the shell, read by the tray Open item."""
import asyncio

import pytest
from nicegui.testing.user_simulation import user_simulation

from gui import last_tab, shell
from gui.sources import FixtureSource


@pytest.fixture(autouse=True)
def _fresh_last_tab():
    last_tab.reset()
    yield
    last_tab.reset()


def test_remember_a_valid_key_then_get_returns_it():
    last_tab.remember("videos")
    assert last_tab.get() == "videos"


def test_remember_an_unknown_key_is_ignored():
    last_tab.remember("videos")
    last_tab.remember("nonsense")
    assert last_tab.get() == "videos"


def test_get_is_none_before_anything_is_remembered():
    assert last_tab.get() is None


def test_reset_gives_none_again():
    last_tab.remember("archive")
    last_tab.reset()
    assert last_tab.get() is None


def _recording_builders():
    def make(key):
        def build(source):
            pass
        return build
    return {key: make(key) for key in ("clips", "compile", "videos", "archive", "activity")}


async def _build_page(tab):
    def root():
        shell.build_page(FixtureSource("empty"), initial_tab=tab, builders=_recording_builders())

    async with user_simulation(root) as user:
        await user.open("/")


def test_building_the_page_with_initial_tab_remembers_that_tab():
    asyncio.run(_build_page("archive"))
    assert last_tab.get() == "archive"


def test_building_the_page_with_an_unknown_tab_remembers_the_default_tab():
    asyncio.run(_build_page("nonsense"))
    assert last_tab.get() == "clips"
