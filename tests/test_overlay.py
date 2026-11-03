import pytest
from PySide6.QtGui import QColor, QImage, QPainter

from screentutor.overlay import (COLOR, MARK_R, PULSE_MAX, PULSE_S, TRAVEL_R, TRAVEL_S, ease_out, frame_at,
                                 paint_frame, to_logical)


@pytest.fixture(autouse=True)
def app(qt_app):
    return qt_app


def test_physical_pixels_map_to_logical_at_125_percent():
    assert to_logical(1920, 1080, 1.25) == (1536, 864)
    assert to_logical(960, 540, 1.25) == (768, 432)
    assert to_logical(100, 50, 1.0, (1920, 0)) == (2020, 50)


def test_ring_glides_opens_up_then_pulses():
    start, target = (0.0, 0.0), (300.0, 200.0)
    f0 = frame_at(0, start, target)
    assert (f0.x, f0.y, f0.radius) == (0, 0, TRAVEL_R)
    mid = frame_at(TRAVEL_S / 2, start, target)
    assert 0 < mid.x < 300 and TRAVEL_R < mid.radius < MARK_R and not mid.arrived and mid.pulses == []
    for t in (TRAVEL_S, TRAVEL_S + 0.3, TRAVEL_S + PULSE_S * 3.7):
        f = frame_at(t, start, target)
        assert (f.x, f.y, f.radius) == (*target, MARK_R) and f.arrived and len(f.pulses) == 2
        (r1, a1), (r2, a2) = f.pulses
        assert MARK_R <= r1 < r2 <= PULSE_MAX and a1 > a2  # the wider pulse is the fainter one


def test_ease_out_is_monotonic_and_bounded():
    values = [ease_out(i / 20) for i in range(-2, 23)]
    assert values == sorted(values) and values[0] == 0 and values[-1] == 1


def test_ring_leaves_the_target_readable():
    img = QImage(400, 300, QImage.Format_ARGB32)
    img.fill(QColor(0, 0, 0, 0))
    p = QPainter(img)
    paint_frame(p, frame_at(TRAVEL_S + 0.1, (200, 150), (200, 150)))
    p.end()
    on_ring = img.pixelColor(200 + int(MARK_R), 150)
    assert (on_ring.red(), on_ring.green(), on_ring.blue()) == (COLOR.red(), COLOR.green(), COLOR.blue())
    assert img.pixelColor(200, 150).alpha() < 60  # only a faint tint over the target
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
