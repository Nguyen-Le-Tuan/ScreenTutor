import pytest
from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QImage, QPainter

from screentutor.overlay import (COLOR, DOT_PULSE_MAX, DOT_R, DOT_TRAVEL_S, LAND_POP, LAND_S, PULSE_S, TRAIL, arc,
                                 dot_at, ease_out, landing, paint_dot, to_logical)


@pytest.fixture(autouse=True)
def app(qt_app):
    return qt_app


def test_physical_pixels_map_to_logical_at_125_percent():
    assert to_logical(1920, 1080, 1.25) == (1536, 864)
    assert to_logical(960, 540, 1.25) == (768, 432)
    assert to_logical(100, 50, 1.0, (1920, 0)) == (2020, 50)


def test_the_dot_leaves_from_beside_the_mouse_and_flies_along_an_arc():
    start, target = (0.0, 0.0), (300.0, 0.0)
    first = dot_at(0, start, target)
    assert (first.x, first.y) == start and not first.arrived and first.trail == []
    mid = dot_at(DOT_TRAVEL_S / 2, start, target)
    assert 100 < mid.x < 200 and abs(mid.y) > 10          # bent to the side, not a straight line
    assert len(mid.trail) == TRAIL and mid.trail[0][2] > mid.trail[-1][2]   # the trail fades behind it
    assert arc(0.5, start, target) == (mid.x, mid.y)


def test_it_lands_bounces_once_then_pulses_in_place():
    start, target = (0.0, 0.0), (300.0, 200.0)
    landed = dot_at(DOT_TRAVEL_S, start, target)
    assert (landed.x, landed.y) == target and landed.arrived and landed.radius == DOT_R * LAND_POP
    for t in (DOT_TRAVEL_S + LAND_S, DOT_TRAVEL_S + PULSE_S * 3.7):
        d = dot_at(t, start, target)
        assert (d.x, d.y, d.radius) == (*target, DOT_R) and d.trail == [] and d.pulse_at == target
        (r1, a1), (r2, a2) = d.pulses
        assert DOT_R < r1 < r2 <= DOT_PULSE_MAX and a1 > a2   # the wider pulse is the fainter one


def test_beside_the_dot_rests_below_right_and_the_pulses_stay_on_the_target():
    d = dot_at(DOT_TRAVEL_S + 1, (0, 0), (300, 200), style="beside")
    assert d.x > 300 and d.y > 200 and d.pulse_at == (300, 200)
    assert landing((300, 200), "beside", 1.25)[0] - 300 > landing((300, 200), "beside", 1.0)[0] - 300


def test_ease_out_is_monotonic_and_bounded():
    values = [ease_out(i / 20) for i in range(-2, 23)]
    assert values == sorted(values) and values[0] == 0 and values[-1] == 1


def test_the_dot_is_solid_with_a_white_edge_and_the_pulses_are_faint():
    img = QImage(400, 300, QImage.Format_ARGB32)
    img.fill(QColor(0, 0, 0, 0))
    p = QPainter(img)
    paint_dot(p, dot_at(DOT_TRAVEL_S + LAND_S + 0.01, (200, 150), (200, 150)))
    p.end()
    centre = img.pixelColor(200, 150)
    assert centre.rgba() == COLOR.rgba() and centre.alpha() == 255
    edge = img.pixelColor(200 + int(DOT_R) + 1, 150)
    assert edge.red() > 240 and edge.green() > 200          # the white halo
    assert img.pixelColor(5, 5).alpha() == 0


# B3: the frame, the darkening, the scroll hint, the tick, the glow

from PIL import Image  # noqa: E402
from PySide6.QtGui import QImage, QPainter  # noqa: E402

from screentutor.overlay import (DIM_ALPHA, READ_COLOR, TICK_S, TRAVEL_S, EdgeGlow, Overlay, focus_at, hint_at,  # noqa: E402
                                 hint_box, lerp_box, padded, paint_focus, paint_hint, paint_tick)
from PySide6.QtGui import QColor  # noqa: E402
from screentutor.still import CHANGE_MIN, GRAB_EVERY_S, changed_fraction, signature  # noqa: E402

W, H, DPR = 1536, 864, 1.25


def _shot(paint, bg=(255, 255, 255)):
    """A 1536x864 logical screen drawn at 125%, as a PIL image of 1920x1080."""
    q = QImage(1920, 1080, QImage.Format_RGBA8888)
    q.fill(QColor(*bg))
    p = QPainter(q)
    paint(p)
    p.end()
    return Image.frombytes("RGBA", (1920, 1080), q.constBits().tobytes()).convert("RGB")


def test_the_frame_opens_out_of_the_mouse_and_the_screen_darkens_with_it():
    box = (100.0, 200.0, 700.0, 500.0)
    first, mid, last = focus_at(0, (900, 600), box), focus_at(TRAVEL_S / 2, (900, 600), box), focus_at(TRAVEL_S, (900, 600), box)
    assert first.box == (900, 600, 900, 600) and first.dim == 0 and not first.arrived
    assert 0 < mid.dim < DIM_ALPHA and mid.box[0] < 900
    assert last.box == box and last.dim == DIM_ALPHA and last.arrived
    assert focus_at(99, (900, 600), box) == last   # it stands still: nothing to mistake for the screen changing


def test_a_box_gets_some_air_but_stays_on_the_screen():
    assert padded((100, 100, 200, 200), (W, H)) == (92, 92, 208, 208)
    assert padded((2, 3, W - 1, H - 1), (W, H)) == (0, 0, W, H)
    assert lerp_box((10, 20), (0, 0, 100, 100), 0.5) == (5, 10, 55, 60)


def test_the_darkening_leaves_the_box_as_it_was_and_darkens_the_rest_slightly():
    box = (480, 270, 1440, 810)
    img = _shot(lambda p: paint_focus(p, focus_at(TRAVEL_S, (0, 0), box), (1920, 1080), 1.25))
    inside, outside = img.getpixel((960, 540)), img.getpixel((100, 100))
    assert min(inside) >= 245                                # the words she reads keep their contrast
    assert abs(outside[0] - 255 * (1 - DIM_ALPHA / 255)) < 3  # darker, not black


def test_the_landed_frame_does_not_count_as_the_screen_changing():
    box = (480, 270, 1440, 810)
    a = signature(_shot(lambda p: paint_focus(p, focus_at(TRAVEL_S, (0, 0), box), (1920, 1080), 1.25)))
    b = signature(_shot(lambda p: paint_focus(p, focus_at(TRAVEL_S + 5, (0, 0), box), (1920, 1080), 1.25)))
    assert changed_fraction(a, b) == 0


def test_a_scroll_still_shows_through_the_darkening():
    from tests.test_still import _page

    box = (420, 100, 1500, 900)
    def dimmed(top):
        img = _page(top)
        q = QImage(img.convert("RGBA").tobytes(), 1920, 1080, QImage.Format_RGBA8888).copy()
        p = QPainter(q)
        paint_focus(p, focus_at(TRAVEL_S, (0, 0), box), (1920, 1080), 1.25)
        p.end()
        return Image.frombytes("RGBA", (1920, 1080), q.constBits().tobytes()).convert("RGB")

    from screentutor.still import BIG_CHANGE
    assert changed_fraction(signature(dimmed(0)), signature(dimmed(100))) > BIG_CHANGE


def test_the_hint_flies_in_then_turns_its_wheel():
    assert hint_at(0, (0, 0), (500, 400)).x == 0 and not hint_at(0, (0, 0), (500, 400)).arrived
    landed = hint_at(TRAVEL_S + 0.3, (0, 0), (500, 400))
    assert (landed.x, landed.y) == (500, 400) and landed.arrived and 0 < landed.phase < 1
    x1, y1, x2, y2 = hint_box(500, 400)
    assert x1 < 500 < x2 and y1 < 400 < y2


def test_the_hint_is_published_so_its_motion_is_kept_out_of_the_screen_watch(qt_app):
    ov = Overlay()
    assert ov.cover is None
    ov.scroll_hint(1000, 500)
    assert ov.cover is not None and ov.cover[0] < 1000 < ov.cover[0] + ov.cover[2] + 500
    ov.clear()
    assert ov.cover is None


def test_the_tick_pops_and_goes():
    assert TICK_S < 1.5
    at = lambda t: _shot(lambda p: paint_tick(p, 500, 500, t, 1.25)).getpixel((500, 488))  # noqa: E731
    assert at(0.3)[1] > at(0.3)[0]            # green while it shows
    assert at(TICK_S) == (255, 255, 255)      # and gone


def test_the_glow_stays_at_the_edge_and_leaves_the_middle_alone():
    glow = EdgeGlow(1920, 1080, 1.25)
    img = _shot(lambda p: glow.paint(p, 2.0, 1.0), bg=(235, 238, 242))
    assert img.getpixel((960, 540)) == (235, 238, 242)
    assert img.getpixel((960, 3)) != (235, 238, 242) and img.getpixel((3, 540)) != (235, 238, 242)


def test_glow_ticks_and_clear_keep_out_of_each_others_way(qt_app):
    ov = Overlay()
    ov.point_at(100, 100)
    ov.tick_at(50, 50)
    ov.clear()                 # the ring goes at once, for the screenshot
    assert ov._target is None and ov._w.isVisible()   # the tick is still showing
    ov._ticks = []
    ov._tick()
    assert not ov._w.isVisible()
    ov.glow(True)
    assert ov._w.isVisible()
    ov.glow_enabled = False    # settings.json: off on a slow machine
    ov.glow(True)
    assert not ov._glowing


def test_a_frame_replaces_a_ring_and_clear_removes_it(qt_app):
    ov = Overlay()
    seen = []
    ov.after_topmost = lambda: seen.append(1)
    ov.point_at(100, 100)
    ov.focus_on(100, 100, 400, 300)
    assert ov._target is None and ov._box is not None and ov._color == READ_COLOR and seen
    ov.focus_on(100, 100, 400, 300, caution=True)
    assert ov._color != READ_COLOR
    ov.clear()
    assert ov._box is None and not ov._w.isVisible()


def test_paint_hint_and_box_do_not_fail_on_any_scale():
    for scale in (1.0, 1.25, 2.0):
        _shot(lambda p: paint_hint(p, hint_at(1.0, (0, 0), (500, 400)), scale))
        _shot(lambda p: paint_focus(p, focus_at(0.1, (10, 10), (300, 300, 310, 305)), (1920, 1080), scale))


def test_the_green_flash_comes_and_goes(qt_app):
    ov = Overlay()
    ov.flash()
    assert ov._w.isVisible() and ov._flash_at is not None
    ov._flash_at -= 2
    ov._tick()
    assert ov._flash_at is None and not ov._w.isVisible()
    ov.glow_enabled = False
    ov.flash()
    assert ov._flash_at is None


# C4: the dot beside her mouse

from screentutor.overlay import BREATH, COMPANION_OFFSET, DOT_R, Companion, breath_at, follow  # noqa: E402


def test_the_waiting_dot_walks_beside_the_mouse_a_step_behind():
    goal = (100 + COMPANION_OFFSET[0], 100 + COMPANION_OFFSET[1])
    assert follow(None, (100, 100)) == goal                 # it appears in its place
    step = follow((0.0, 0.0), (100, 100))
    assert 0 < step[0] < goal[0] and 0 < step[1] < goal[1]  # then follows, a step behind
    dot = (0.0, 0.0)
    for _ in range(30):
        dot = follow(dot, (100, 100))
    assert abs(dot[0] - goal[0]) < 0.1 and abs(dot[1] - goal[1]) < 0.1


def test_it_breathes_only_while_the_tutor_looks():
    assert breath_at(0.7, False) == (DOT_R, 255)
    sizes = [breath_at(t / 10, True)[0] for t in range(17)]
    assert min(sizes) == DOT_R and DOT_R * 1.15 < max(sizes) <= DOT_R * (1 + BREATH) + 1e-9


def test_the_dot_is_out_only_during_a_task_and_never_in_a_screenshot(qt_app):
    c = Companion()
    assert not c.visible() and c.centre() is None and c.cover is None
    c.set_on(True)
    assert c.visible() and c.centre() is not None and c.cover is not None
    assert c.veil(True) is True and not c.visible() and c.cover is None
    assert c.veil(False) is False and c.visible()
    c.set_away(True)                                         # it has flown to the mark
    assert not c.visible() and c.centre() is None and c.cover is None
    c.set_away(False)
    c.set_on(False)
    assert not c.visible() and c.cover is None


def test_the_dot_flies_from_where_it_waited(qt_app):
    o = Overlay()
    o.start_from = lambda: (123.0, 45.0)
    o.point_at(500, 500)
    assert o._start == (123.0, 45.0)
    o.start_from = lambda: None                              # not out: from the mouse, as before
    o.clear()
    o.point_at(500, 500)
    assert o._start != (123.0, 45.0)
    o.clear()


def test_the_waiting_dot_moving_with_the_mouse_is_not_the_screen_changing():
    # it is left in the grabs still.py watches after a click; at its biggest breath, moved 60 px
    from screentutor.still import CHANGE_MIN, changed_fraction, signature

    def dot(x, y):
        def paint(p):
            r = DOT_R * (1 + BREATH) * 1.25
            p.setRenderHint(QPainter.Antialiasing)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(255, 255, 255))
            p.drawEllipse(QPointF(x, y), r + 3.2, r + 3.2)
            p.setBrush(COLOR)
            p.drawEllipse(QPointF(x, y), r, r)
        return _shot(paint, bg=(30, 30, 30))

    assert changed_fraction(signature(dot(500, 500)), signature(dot(560, 530))) < CHANGE_MIN


# K: the drag and the keys

from screentutor.overlay import (DRAG_HOLD_S, DRAG_MOVE_S, DRAG_REST_S, drag_at, key_parts,  # noqa: E402
                                 paint_keys)


def test_the_drag_flies_to_its_start_then_presses_drags_and_lets_go_over_and_over():
    a, b = (100.0, 200.0), (400.0, 200.0)
    assert drag_at(0, (0, 0), a, b).band is None                       # still flying to the start
    t0 = DOT_TRAVEL_S
    pressed = drag_at(t0 + DRAG_HOLD_S / 2, (0, 0), a, b)
    assert (pressed.dot.x, pressed.dot.y) == a and pressed.dot.radius < DOT_R
    mid = drag_at(t0 + DRAG_HOLD_S + DRAG_MOVE_S / 2, (0, 0), a, b)
    assert 100 < mid.dot.x < 400 and mid.band == (a, (mid.dot.x, mid.dot.y)) and mid.band_alpha > 0
    rest = drag_at(t0 + DRAG_HOLD_S + DRAG_MOVE_S + DRAG_REST_S * 0.9, (0, 0), a, b)
    assert (rest.dot.x, rest.dot.y) == b and rest.dot.radius == DOT_R and rest.band_alpha < mid.band_alpha
    again = drag_at(t0 + DRAG_HOLD_S + DRAG_MOVE_S + DRAG_REST_S + 0.01, (0, 0), a, b)
    assert (again.dot.x, again.dot.y) == a                             # and again


def test_keys_read_like_the_keys_and_typing_ends_in_enter():
    assert key_parts("Ctrl+C") == (["Ctrl", "C"], "+")
    assert key_parts("15", typing=True) == (["gõ 15", "Enter"], "→")


def test_the_keys_stay_on_the_screen(qt_app):
    img = QImage(800, 600, QImage.Format_ARGB32)
    img.fill(QColor(0, 0, 0, 0))
    p = QPainter(img)
    x1, y1, x2, y2 = paint_keys(p, 780, 590, ["Ctrl", "C"], "+", 1.0, bounds=(800, 600))
    p.end()
    assert 0 <= x1 < x2 <= 800 and 0 <= y1 < y2 <= 600


def test_a_drag_or_keys_replace_the_dot_and_clear_removes_them(qt_app):
    o = Overlay()
    o.drag(100, 100, 400, 100)
    assert o._drag_to is not None and o._busy()
    o.keys(None, None, "Ctrl+C")
    assert o._drag_to is None and o._target is None and o._keys is not None and o._busy()
    o.keys(200, 200, "15", typing=True)
    assert o._target is not None and o._keys[0] == ["gõ 15", "Enter"]
    o.clear()
    assert o._keys is None and o._target is None
