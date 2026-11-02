import pytest
from PySide6.QtCore import QPointF
from PySide6.QtGui import QColor, QImage, QPainter

from screentutor import conversation as conv
from screentutor import island
from screentutor.island import Morph, Shape, Spring, View, outline, paint_icon, paint_island, target_shape
from screentutor.overlay import CAUTION_COLOR, COLOR

SW, SH = 1536, 864  # 1920×1080 at 125%


@pytest.fixture(autouse=True)
def app(qt_app):
    return qt_app


def test_closed_island_is_small_and_80_percent():
    idle = target_shape("collapsed", SW, SH)
    assert idle.w == island.IDLE_W and idle.h == island.COLLAPSED_H and idle.alpha == 0.8 and idle.depth == 0
    assert target_shape("collapsed", SW, SH, text_w=10).w == island.COLLAPSED_W[0]
    assert target_shape("collapsed", SW, SH, text_w=5000).w == island.COLLAPSED_W[1]


def test_open_island_never_takes_the_whole_width():
    for content_w in (0, 400, 5000):
        s = target_shape("hover", SW, SH, content_w=content_w, content_h=150)
        assert island.HOVER_W[0] <= s.w <= island.HOVER_W[1] and s.w <= 0.4 * SW
        assert s.alpha == 1.0 and s.depth == island.HOVER_DEPTH
    assert target_shape("hover", 800, 600, content_w=5000).w <= 0.4 * 800
    assert target_shape("hover", SW, SH, content_h=5000).h == island.HOVER_H[1]


def test_pinned_island_is_a_plain_rectangle_within_the_screen():
    s = target_shape("pinned", SW, SH, content_h=5000)
    assert s.depth == 0 and s.alpha == 1.0 and s.w <= SW - 48 and s.h <= 0.55 * SH
    assert target_shape("pinned", SW, SH, content_h=10).h == island.PINNED_H_MIN


def test_outline_hangs_lower_in_the_middle_than_at_the_sides():
    s = Shape(480, 160, 24, 16, 1.0)
    path = outline(s, cx=768, top=6)
    box = path.boundingRect()
    assert abs(box.width() - 480) < 0.5 and abs(box.center().x() - 768) < 0.5
    assert abs(box.bottom() - (6 + 160 + 16)) < 0.5
    assert path.contains(QPointF(768, 6 + 160 + 12))           # the dip in the middle
    assert not path.contains(QPointF(768 - 230, 6 + 160 + 12))  # the sides end higher
    flat = outline(Shape(480, 160, 18, 0, 1.0), 768, 6).boundingRect()
    assert abs(flat.bottom() - 166) < 0.5


def test_spring_settles_on_the_target_with_a_small_bounce():
    s = Spring(0)
    s.target = 100
    peak = 0.0
    for _ in range(60):  # 1 s at 60 fps
        s.step(1 / 60)
        peak = max(peak, s.value)
    assert s.settled() and abs(s.value - 100) < 0.5
    assert 100 < peak < 105
    big = Spring(0)
    big.target = 100
    big.step(5.0)  # a stalled frame does not throw it away
    assert 0 < big.value < 150


def test_morph_reports_progress_and_stops_moving():
    a = target_shape("collapsed", SW, SH)
    b = target_shape("hover", SW, SH, content_w=420, content_h=170)
    m = Morph(a)
    assert not m.moving() and m.progress() == 1.0
    m.set_target(b)
    assert m.moving() and m.progress() == 0.0
    seen = []
    for _ in range(90):
        m.step(1 / 60)
        seen.append(m.progress())
    assert seen[10] < seen[30] and m.progress() > 0.99 and not m.moving()
    assert abs(m.shape().w - b.w) < 0.5 and abs(m.alpha - 1.0) < 0.01


def test_states_have_their_own_colours_and_match_the_ring():
    assert set(island.STYLE) == {"idle", "listening", "thinking", "speaking", "turn", "caution", "loading", "done", "error"}
    assert island.STYLE["turn"][1] == QColor(COLOR)
    assert island.STYLE["caution"][1] == QColor(CAUTION_COLOR)
    working = ["listening", "thinking", "speaking", "turn", "caution", "done", "error"]
    assert len({island.STYLE[s][1].name() for s in working}) == len(working)


def _icon(state: str, t: float = 0.3, since: float = 1.0, level=None) -> QImage:
    img = QImage(40, 40, QImage.Format_ARGB32)
    img.fill(QColor(0, 0, 0, 0))
    p = QPainter(img)
    paint_icon(p, state, QPointF(20, 20), t, since, level)
    p.end()
    return img


def _ink(img: QImage, outside_box: bool = False, min_alpha: int = 20) -> int:
    n = 0
    for y in range(img.height()):
        for x in range(img.width()):
            inside = 9 <= x <= 31 and 9 <= y <= 31
            if img.pixelColor(x, y).alpha() > min_alpha and inside != outside_box:
                n += 1
    return n


def test_every_icon_draws_inside_its_20_px_box():
    for state in island.STYLE:
        for t in (0.0, 0.4, 1.1):
            img = _icon(state, t)
            assert _ink(img) > 0, state
            assert _ink(img, outside_box=True) == 0, state


def test_tick_draws_itself_and_bars_follow_the_level():
    assert _ink(_icon("done", since=0.05), min_alpha=120) < _ink(_icon("done", since=1.0), min_alpha=120)
    assert _ink(_icon("listening", level=0.05)) < _ink(_icon("listening", level=1.0))
    assert island.bar_heights(5, 0.3, 0.0, 3, 16, 5) == [3.0] * 5


def test_island_paints_in_every_mode():
    task = conv.Task()
    task.hear("Mẹ muốn xuất giáo án ra PDF")
    task.plan(["Xuất PDF", "Gửi file"])
    task.say("Bấm chữ File ở góc trên bên trái.")
    for mode in ("collapsed", "hover", "pinned"):
        view = View(mode, "turn", task, title="Xuất giáo án ra PDF", since=1.0)
        tw, w, h = island.content_size(view, SW, SH)
        shape = target_shape(mode, SW, SH, tw, w, h)
        img = QImage(800, 600, QImage.Format_ARGB32)
        img.fill(QColor(255, 255, 255))
        p = QPainter(img)
        paint_island(p, shape, 400, view, 0.3)
        p.end()
        assert img.pixelColor(400, 8).red() < 80  # dark at the top centre
        if mode == "hover":
            assert img.pixelColor(400, round(6 + shape.h + shape.depth - 3)).red() < 120  # the dip is filled
    closed = target_shape("collapsed", SW, SH)
    img = QImage(200, 60, QImage.Format_ARGB32)
    img.fill(QColor(255, 255, 255))
    p = QPainter(img)
    paint_island(p, closed, 100, View(), 0.3)
    p.end()
    assert 40 < img.pixelColor(100 - 40, 20).red() < 70  # 80% black over white: about 51
