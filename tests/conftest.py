import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="session")
def qt_app():
    """One QApplication for every Qt test: widgets need it, and Qt allows only one per process."""
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])
