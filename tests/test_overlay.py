import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtGui import QColor, QGuiApplication, QImage, QPainter

from screentutor.overlay import (COLOR, MARK_R, PULSE_MAX, PULSE_S, TRAVEL_R, TRAVEL_S, ease_out, frame_at,
                                 paint_frame, to_logical)


@pytest.fixture(scope="module", autouse=True)
def app():
    yield QGuiApplication.instance() or QGuiApplication([])


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
