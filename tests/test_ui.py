import pytest
from PySide6.QtCore import QRectF
from PySide6.QtGui import QColor, QImage, QPainter

from screentutor.ui import ISLAND_H, ISLAND_W_MAX, ISLAND_W_MIN, ISLAND_W_OPEN, STATES, AskButton, Island, \
    island_size, paint_button, paint_island

LONG = "cái file báo cáo tuần trước tôi lưu ở đâu rồi sao bây giờ mở ra không thấy chữ nào hết vậy"


@pytest.fixture(autouse=True)
def app(qt_app):
    return qt_app


def test_island_is_one_line_when_closed_and_wraps_when_open():
    w, h = island_size(LONG, opened=False)
    assert ISLAND_W_MIN <= w <= ISLAND_W_MAX and h == ISLAND_H
    w, h = island_size(LONG, opened=True)
    assert w == ISLAND_W_OPEN and h > ISLAND_H
    assert island_size("Hỏi", opened=False) == (ISLAND_W_MIN, ISLAND_H)


def test_every_state_paints():
    for state in STATES:
        img = QImage(260, 80, QImage.Format_ARGB32)
        img.fill(QColor(0, 0, 0, 0))
        p = QPainter(img)
        paint_button(p, QRectF(img.rect()), state, 0.3)
        paint_island(p, QRectF(0, 0, 260, ISLAND_H), state, LONG, False)
        p.end()
        assert img.pixelColor(130, 60).alpha() > 0


def test_button_emits_clicked_and_island_follows_the_state():
    from PySide6.QtCore import QPointF, Qt
    from PySide6.QtGui import QMouseEvent

    button, island = AskButton(), Island()
    seen = []
    button.clicked.connect(lambda: seen.append(1))
    pos = QPointF(20, 20)
    button.mouseReleaseEvent(QMouseEvent(QMouseEvent.Type.MouseButtonRelease, pos, pos, Qt.LeftButton,
                                         Qt.NoButton, Qt.NoModifier))
    assert seen == [1]
    button.set_state("listening")
    island.set_state("listening", "cái file báo cáo")
    assert button.state == island.state == "listening" and island.text == "cái file báo cáo"
    island.set_state("thinking")  # no new text: keeps what was heard
    assert island.text == "cái file báo cáo"
