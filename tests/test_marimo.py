# License: BSD-3-Clause
# Copyright the MNE Qt Browser contributors.

"""Test the marimo event pump with a fake marimo module (no marimo needed)."""

import asyncio
import sys
import types

from qtpy.QtCore import QTimer
from qtpy.QtWidgets import QLabel

from mne_qt_browser import _pg_figure


def test_marimo_pump(qapp, monkeypatch):
    """Pump starts under a fake marimo, keeps Qt serviced, stops on last close."""
    fake = types.ModuleType("marimo")
    fake.running_in_notebook = lambda: True
    monkeypatch.setitem(sys.modules, "marimo", fake)
    monkeypatch.setattr(_pg_figure, "_MARIMO_PUMP", None)
    qapp.closeAllWindows()  # leftover windows would keep the pump alive

    assert _pg_figure._setup_marimo() is None  # no running asyncio loop -> no pump

    async def main():
        task = _pg_figure._setup_marimo()
        assert task is not None
        assert not task.done()
        assert _pg_figure._setup_marimo() is task  # no second pump while one runs

        widget = QLabel("marimo pump test")
        widget.show()
        ticks = [0]
        probe = QTimer()
        probe.timeout.connect(lambda: ticks.__setitem__(0, ticks[0] + 1))
        probe.start(10)
        # While this sleep blocks, only the pump can service Qt's event queue
        await asyncio.sleep(0.5)
        probe.stop()
        assert not task.done()
        assert ticks[0] > 5, f"window frozen, only {ticks[0]} ticks"

        widget.close()
        await asyncio.wait_for(task, timeout=5)  # self-stops after last close

    asyncio.run(main())


def test_marimo_not_in_notebook(monkeypatch):
    """No pump when marimo is importable but not running the notebook."""
    fake = types.ModuleType("marimo")
    fake.running_in_notebook = lambda: False
    monkeypatch.setitem(sys.modules, "marimo", fake)
    monkeypatch.setattr(_pg_figure, "_MARIMO_PUMP", None)

    async def main():
        assert _pg_figure._setup_marimo() is None

    asyncio.run(main())


def test_marimo_pump_new_loop(qapp, monkeypatch):
    """A restarted kernel gets a fresh pump instead of a task tied to the dead loop."""
    fake = types.ModuleType("marimo")
    fake.running_in_notebook = lambda: True
    monkeypatch.setitem(sys.modules, "marimo", fake)
    monkeypatch.setattr(_pg_figure, "_MARIMO_PUMP", None)
    qapp.closeAllWindows()

    widget = QLabel("marimo pump test")
    widget.show()

    async def start_only():
        return _pg_figure._setup_marimo()

    stale = asyncio.run(start_only())  # left pending when this loop closes

    async def restart():
        task = _pg_figure._setup_marimo()
        assert task is not stale
        await asyncio.sleep(0.1)  # let the new pump see the window before it closes
        widget.close()
        await asyncio.wait_for(task, timeout=5)

    asyncio.run(restart())


def test_marimo_qt_aware_loop(monkeypatch):
    """No pump when the asyncio loop already drives Qt (a qasync loop)."""
    fake = types.ModuleType("marimo")
    fake.running_in_notebook = lambda: True
    monkeypatch.setitem(sys.modules, "marimo", fake)
    monkeypatch.setattr(_pg_figure, "_MARIMO_PUMP", None)

    class FakeQasyncLoop(asyncio.SelectorEventLoop):
        pass

    FakeQasyncLoop.__module__ = "qasync"

    async def main():
        assert _pg_figure._setup_marimo() is None

    loop = FakeQasyncLoop()
    try:
        loop.run_until_complete(main())
    finally:
        loop.close()


def test_marimo_pump_gives_up(qapp, monkeypatch):
    """Pump stops instead of spinning forever when no window ever appears."""
    fake = types.ModuleType("marimo")
    fake.running_in_notebook = lambda: True
    monkeypatch.setitem(sys.modules, "marimo", fake)
    monkeypatch.setattr(_pg_figure, "_MARIMO_PUMP", None)
    monkeypatch.setattr(_pg_figure, "_MARIMO_PUMP_GRACE", 0.2)
    qapp.closeAllWindows()

    async def main():
        task = _pg_figure._setup_marimo()
        await asyncio.wait_for(task, timeout=5)

    asyncio.run(main())
