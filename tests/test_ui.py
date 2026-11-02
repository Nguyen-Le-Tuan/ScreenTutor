import pytest
from PySide6.QtCore import QRectF
from PySide6.QtGui import QColor, QImage, QPainter

from screentutor.ui import AskButton, paint_button


@pytest.fixture(autouse=True)
def app(qt_app):
    return qt_app


def test_button_emits_clicked_and_reads_its_level_source():
    from PySide6.QtCore import QPointF, Qt
    from PySide6.QtGui import QMouseEvent

    button = AskButton()
    seen = []
    button.clicked.connect(lambda: seen.append(1))
    pos = QPointF(20, 20)
    button.mouseReleaseEvent(QMouseEvent(QMouseEvent.Type.MouseButtonRelease, pos, pos, Qt.LeftButton,
                                         Qt.NoButton, Qt.NoModifier))
    assert seen == [1]
    button.set_state("listening")
    reads = []
    button.level_source = lambda: reads.append(1) or 0.5
    button.grab()  # paints once
    assert button.state == "listening" and reads


def test_round_button_paints_every_island_state_and_darkens_under_the_mouse():
    from screentutor.island import STYLE
    from screentutor.ui import BUTTON_D, GLOW

    side = BUTTON_D + 2 * GLOW
    for state in STYLE:
        for hover in (False, True):
            img = QImage(side, side, QImage.Format_ARGB32)
            img.fill(QColor(255, 255, 255))
            p = QPainter(img)
            paint_button(p, QRectF(img.rect()), state, 0.3, hover)
            p.end()
            edge = img.pixelColor(side // 2 + BUTTON_D // 2 - 2, side // 2)  # on the ring
            body = img.pixelColor(side // 2 + 9, side // 2 + 9)               # dark body, off the mic
            assert body.red() < (10 if hover else 60), state
            if state not in ("idle", "done", "thinking", "loading"):  # those two: a dim ring and a running arc
                want = STYLE[state][1]
                assert abs(edge.red() - want.red()) + abs(edge.green() - want.green()) < 120, state


def test_button_sits_bottom_right_and_ignores_unknown_states():
    from PySide6.QtGui import QGuiApplication

    button = AskButton()
    area = QGuiApplication.primaryScreen().availableGeometry()
    assert button.geometry().right() <= area.right() and button.geometry().bottom() <= area.bottom()
    assert button.geometry().right() > area.right() - 100
    button.set_state("nonsense")
    assert button.state == "idle" and not button._timer.isActive()
    button.set_state("listening")
    assert button._timer.isActive()
