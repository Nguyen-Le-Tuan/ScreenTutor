import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="session")
def qt_app():
    """One QApplication for every Qt test: widgets need it, and Qt allows only one per process."""
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def one_call_at_a_time(monkeypatch):
    """Tests fake one connection; the raced pair (tutor.HEDGE) would reach the real API on the second.
    The tests of the race itself ask for it with hedge=True."""
    monkeypatch.setattr("screentutor.tutor.HEDGE", False)
