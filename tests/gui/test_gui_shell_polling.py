"""Job signature and the repaint poller behind the page's job timer (gui.shell)."""
from gui import shell


class FakeRunner:
    def __init__(self, current=None, history=()):
        self._current = current
        self._history = list(history)

    def current(self):
        return None if self._current is None else dict(self._current)

    def history(self):
        return [dict(r) for r in self._history]


class FakeSource:
    """Has a runner; read() raises so any library scan inside job_signature fails the test."""

    def __init__(self, runner):
        self.runner = runner

    def read(self):
        raise AssertionError("job_signature must never call read()")


def _job(job_id, state="running", done=0):
    return {"id": job_id, "state": state, "done": done}


# ---- job_signature ----

def test_signature_is_none_without_a_runner():
    class NoRunner:
        def read(self):
            raise AssertionError("must not read")

    assert shell.job_signature(NoRunner()) is None


def test_signature_for_an_idle_runner_with_no_history_is_all_none():
    assert shell.job_signature(FakeSource(FakeRunner())) == (None, None, None, None, None)


def test_signature_for_an_idle_runner_reads_the_newest_history_job():
    runner = FakeRunner(history=[_job("a1", "done", 9)])
    assert shell.job_signature(FakeSource(runner)) == (None, None, None, "a1", "done")


def test_signature_reads_the_running_job_id_state_and_integer_done():
    runner = FakeRunner(current=_job("b2", "running", 3))
    assert shell.job_signature(FakeSource(runner)) == ("b2", "running", 3, None, None)


def test_signature_changes_when_progress_changes():
    before = shell.job_signature(FakeSource(FakeRunner(current=_job("b2", "running", 3))))
    after = shell.job_signature(FakeSource(FakeRunner(current=_job("b2", "running", 4))))
    assert before != after


def test_signature_changes_when_the_job_finishes():
    running = shell.job_signature(FakeSource(FakeRunner(current=_job("b2", "running", 9))))
    finished = shell.job_signature(FakeSource(FakeRunner(history=[_job("b2", "done", 9)])))
    assert running != finished
    assert finished == (None, None, None, "b2", "done")


def test_signature_changes_when_a_new_job_starts():
    idle = shell.job_signature(FakeSource(FakeRunner(history=[_job("a1", "done", 9)])))
    started = shell.job_signature(FakeSource(FakeRunner(current=_job("c3", "running", 0),
                                                        history=[_job("a1", "done", 9)])))
    assert idle != started


def test_signature_never_calls_read_on_a_running_or_idle_runner():
    shell.job_signature(FakeSource(FakeRunner(current=_job("b2", "running", 1))))
    shell.job_signature(FakeSource(FakeRunner(history=[_job("a1", "done", 9)])))


# ---- Poller ----

class Clock:
    def __init__(self, now=100.0):
        self.now = now

    def __call__(self):
        return self.now


class Page:
    """A signature the test sets by hand, plus the list of repaint times."""

    def __init__(self, sig):
        self.sig = sig
        self.repaints = []
        self.clock = Clock()

    def poller(self):
        return shell.Poller(lambda: self.sig, lambda: self.repaints.append(self.clock.now), self.clock)


IDLE = (None, None, None, None, None)


def _running(job_id, done):
    return (job_id, "running", done, None, None)


def test_no_repaint_while_the_signature_is_unchanged():
    page = Page(IDLE)
    poller = page.poller()
    for _ in range(3):
        page.clock.now += 1.0
        assert poller.tick() is False
    assert page.repaints == []


def test_a_job_start_repaints_on_the_next_tick():
    page = Page(IDLE)
    poller = page.poller()
    page.sig = _running("b2", 0)
    assert poller.tick() is True
    assert page.repaints == [100.0]


def test_a_finish_repaints_at_once_even_inside_the_progress_window():
    page = Page(IDLE)
    poller = page.poller()
    page.sig = _running("b2", 0)
    poller.tick()
    page.clock.now += 0.5
    page.sig = (None, None, None, "b2", "done")
    assert poller.tick() is True
    assert len(page.repaints) == 2


def test_a_failure_repaints_at_once_inside_the_progress_window():
    page = Page(IDLE)
    poller = page.poller()
    page.sig = _running("b2", 0)
    poller.tick()
    page.clock.now += 0.2
    page.sig = (None, None, None, "b2", "failed")
    assert poller.tick() is True


def test_progress_alone_repaints_at_most_once_per_two_seconds():
    page = Page(IDLE)
    poller = page.poller()
    page.sig = _running("b2", 0)
    poller.tick()  # repaint at 100.0 (start)
    # progress every half second; only the ticks at least 2 s after the last paint repaint
    for step in range(1, 9):
        page.clock.now = 100.0 + 0.5 * step
        page.sig = _running("b2", step)
        poller.tick()
    assert page.repaints == [100.0, 102.0, 104.0]


def test_a_throttled_progress_change_lands_on_a_later_tick_without_a_new_change():
    page = Page(IDLE)
    poller = page.poller()
    page.sig = _running("b2", 0)
    poller.tick()  # repaint at 100.0
    page.clock.now = 100.5
    page.sig = _running("b2", 1)
    assert poller.tick() is False  # held back: inside the 2 s window
    page.clock.now = 102.0
    assert poller.tick() is True  # same signature, window elapsed: the pending change lands
    assert page.repaints == [100.0, 102.0]


def test_a_repaint_after_the_window_uses_the_newest_progress():
    page = Page(IDLE)
    poller = page.poller()
    page.sig = _running("b2", 0)
    poller.tick()
    page.clock.now = 100.5
    page.sig = _running("b2", 1)
    poller.tick()
    page.clock.now = 101.0
    page.sig = _running("b2", 7)
    poller.tick()
    page.clock.now = 102.0
    assert poller.tick() is True
    assert page.sig == _running("b2", 7)
    assert page.repaints == [100.0, 102.0]


def test_a_signature_back_at_the_painted_value_repaints_nothing():
    page = Page(IDLE)
    poller = page.poller()
    page.sig = _running("b2", 0)
    poller.tick()
    page.clock.now = 100.5
    page.sig = _running("b2", 1)
    poller.tick()
    page.sig = _running("b2", 0)
    page.clock.now = 102.5
    assert poller.tick() is False
    assert page.repaints == [100.0]


def test_the_poller_starts_from_the_signature_it_is_given_at_construction():
    page = Page(_running("b2", 4))
    poller = page.poller()
    assert poller.tick() is False
    assert page.repaints == []


def test_the_default_clock_is_the_module_clock_and_tests_can_replace_it(monkeypatch):
    clock = Clock(now=50.0)
    monkeypatch.setattr(shell, "CLOCK", clock)
    repaints = []
    state = {"sig": IDLE}
    poller = shell.Poller(lambda: state["sig"], lambda: repaints.append(clock.now))
    state["sig"] = _running("b2", 0)
    assert poller.tick() is True
    assert repaints == [50.0]


# ---- wiring: build_page starts the job timer only for a page with a runner ----

def _timers_on_page(source):
    import asyncio

    from nicegui import ui
    from nicegui.element_filter import ElementFilter
    from nicegui.testing.user_simulation import user_simulation

    from gui.sources import FixtureSource

    def root():
        shell.build_page(source if source is not None else FixtureSource("empty"), builders={})

    async def run():
        async with user_simulation(root) as user:
            await user.open("/?tab=clips")
            with user.client:
                return len(list(ElementFilter(kind=ui.timer, only_visible=False)))

    return asyncio.run(run())


def test_a_page_with_a_job_runner_starts_one_timer():
    from gui import __main__ as gui_main
    from gui.sources import FixtureSource

    source = gui_main.WiredSource(FixtureSource("empty"), FakeRunner())
    assert _timers_on_page(source) == 1


def test_a_page_without_a_job_runner_starts_no_timer():
    assert _timers_on_page(None) == 0
