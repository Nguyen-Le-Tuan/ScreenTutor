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
