import pytest
from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QGuiApplication, QMouseEvent, QWheelEvent

from screentutor import conversation as conv
from screentutor import island
from screentutor.island import Island


@pytest.fixture(autouse=True)
def app(qt_app):
    return qt_app


class Fake:
    """A clock and a mouse the test moves by hand."""

    def __init__(self):
        self.t = 100.0
        self.pos = QPoint(5, 500)

    def clock(self):
        return self.t

    def cursor(self):
        return self.pos


def make(task=True):
    fake = Fake()
    isl = Island(clock=fake.clock, cursor=fake.cursor)
    if task:
        t = conv.Task()
        t.hear("Mẹ muốn xuất giáo án ra PDF rồi gửi cho tiệm in")
        t.plan(["Xuất PDF", "Mở Zalo", "Gửi file"])
        for i in range(12):
            t.say(f"Bước {i}: bấm vào chỗ khoanh đỏ ở giữa màn hình để đi tiếp nhé.")
        isl.set_state("turn", t)
    isl.show()
    return isl, fake


def settle(isl, fake, secs=1.0):
    for _ in range(int(secs * 60)):
        fake.t += 1 / 60
        isl.tick()


def centre(isl):
    g = QGuiApplication.primaryScreen().geometry()
    return QPoint(g.x() + g.width() // 2, g.y() + island.TOP + island.COLLAPSED_H // 2)


def test_starts_closed_at_the_top_centre_and_lets_clicks_through():
    isl, fake = make()
    settle(isl, fake)
    g = QGuiApplication.primaryScreen().geometry()
    assert isl.mode == "collapsed" and isl.click_through
    assert isl.testAttribute(Qt.WA_TransparentForMouseEvents)
    assert abs(isl.geometry().center().x() - g.center().x()) <= 1 and isl.geometry().top() == g.top()
    assert isl.contains_global(QPointF(centre(isl))) and not isl.contains_global(QPointF(5, 500))


def test_opens_only_after_the_mouse_rests_and_closes_after_it_leaves():
    isl, fake = make()
    settle(isl, fake)
    fake.pos = centre(isl)
    isl.poll()
    fake.t += island.HOVER_DWELL_S / 2
    isl.poll()
    assert isl.mode == "collapsed"  # passing over it on the way to a tab does not open it
    fake.t += island.HOVER_DWELL_S
    isl.poll()
    assert isl.mode == "hover" and not isl.click_through
    settle(isl, fake)
    assert isl.width() <= 0.4 * QGuiApplication.primaryScreen().geometry().width() + 4
    fake.pos = QPoint(5, 500)
    isl.poll()
    fake.t += island.LEAVE_S / 2
    isl.poll()
    assert isl.mode == "hover"
    fake.t += island.LEAVE_S
    isl.poll()
    assert isl.mode == "collapsed" and isl.click_through


def click(isl, local: QPointF):
    isl.mouseReleaseEvent(QMouseEvent(QMouseEvent.Type.MouseButtonRelease, local, local, Qt.LeftButton,
                                      Qt.NoButton, Qt.NoModifier))


def test_click_pins_it_and_the_close_mark_or_a_click_outside_closes_it():
    isl, fake = make()
    isl.set_mode("hover")
    settle(isl, fake)
    click(isl, QPointF(isl.width() / 2, 20))
    assert isl.mode == "pinned" and not isl.click_through
    settle(isl, fake)
    assert isl.global_click(QPointF(centre(isl))) is True  # on the island: not her step
    assert isl.mode == "pinned"
    click(isl, island.close_center(isl.morph.shape(), isl.width() / 2))
    assert isl.mode == "collapsed"
    isl.set_mode("pinned")
    settle(isl, fake)
    assert isl.global_click(QPointF(5, 500)) is False and isl.mode == "collapsed"


def test_a_click_on_the_closed_island_goes_through_to_her_app():
    isl, fake = make()
    settle(isl, fake)
    assert isl.global_click(QPointF(centre(isl))) is False


def test_pinned_talk_scrolls_within_bounds():
    isl, fake = make()
    isl.set_mode("pinned")
    settle(isl, fake)
    assert isl.max_scroll() > 0  # twelve steps do not fit
    down = QWheelEvent(QPointF(10, 10), QPointF(10, 10), QPoint(0, 0), QPoint(0, -120 * 50), Qt.NoButton,
                       Qt.NoModifier, Qt.NoScrollPhase, False)
    isl.wheelEvent(down)
    assert isl.scroll == isl.max_scroll()
    up = QWheelEvent(QPointF(10, 10), QPointF(10, 10), QPoint(0, 0), QPoint(0, 120 * 50), Qt.NoButton,
                     Qt.NoModifier, Qt.NoScrollPhase, False)
    isl.wheelEvent(up)
    assert isl.scroll == 0


def test_steps_aside_when_the_ring_points_underneath():
    isl, fake = make()
    settle(isl, fake)
    isl.set_avoid(QPointF(centre(isl)))  # the target is right under the closed island
    assert isl.hidden_for_target and isl.click_through and not isl.contains_global(QPointF(centre(isl)))
    isl.set_avoid(None)
    assert not isl.hidden_for_target
    g = QGuiApplication.primaryScreen().geometry()
    isl.set_mode("hover")
    below = QPointF(g.center().x() - 150, g.top() + 120)  # under where the open island would be
    isl.set_avoid(below)
    assert isl.no_hover and isl.mode == "collapsed"
    fake.pos = centre(isl)
    for _ in range(5):
        fake.t += island.HOVER_DWELL_S
        isl.poll()
    assert isl.mode == "collapsed"  # it does not open over her target


def test_done_rests_after_a_while_and_the_frame_clock_stops():
    isl, fake = make()
    isl.set_state("done")
    settle(isl, fake, island.DONE_HOLD_S + 1.0)
    assert isl.view.state == "idle"
    settle(isl, fake, 1.0)
    assert not isl._frame.isActive()


def test_resizes_to_the_shape_and_paints(qt_app):
    isl, fake = make()
    settle(isl, fake)
    small = isl.width()
    isl.set_mode("pinned")
    settle(isl, fake)
    assert isl.width() > small and isl.height() >= island.PINNED_H_MIN
    assert isl.own_rect().width() == round(isl.morph.shape().w)
    img = isl.grab().toImage()
    assert img.pixelColor(isl.width() // 2, island.TOP + 10).alpha() > 200


def test_sound_bars_read_the_level_source_only_while_sound_plays():
    isl, fake = make()
    level = [0.7]
    isl.level_source = lambda: level[0]
    isl.set_state("listening")
    fake.t += 0.02
    isl.tick()
    assert isl.view.level == 0.7
    isl.set_state("thinking")
    level[0] = 0.1
    fake.t += 0.02
    isl.tick()
    assert isl.view.level is None  # no bars while it thinks


def test_publishes_where_to_mask_and_where_clicks_land_on_it():
    isl, fake = make()
    settle(isl, fake)
    g = isl.geometry()
    assert isl.cover == (g.x(), g.y(), g.width(), g.height()) and isl.takes_clicks is None  # closed: clicks go through
    isl.set_mode("pinned")
    settle(isl, fake)
    g = isl.geometry()
    assert isl.takes_clicks == (g.x(), g.y(), g.width(), g.height())
    isl.set_mode("collapsed")
    isl.set_avoid(QPointF(centre(isl)))
    assert isl.cover is None  # hidden over her target: nothing of ours to mask there


def test_a_pinned_island_over_the_target_closes_and_an_error_rests():
    isl, fake = make()
    isl.set_mode("pinned")
    settle(isl, fake)
    r = isl.own_rect()
    isl.set_avoid(QPointF(r.center().x() + 150, r.bottom() - 10))
    assert isl.mode == "collapsed"
    isl.set_state("error")
    settle(isl, fake, island.DONE_HOLD_S + 0.5)
    assert isl.view.state == "idle"
