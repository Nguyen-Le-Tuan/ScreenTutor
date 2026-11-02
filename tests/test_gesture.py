import math
import random
import time

from screentutor.gesture import describe, find_circle

SIZE = (1920, 1080)
DT = 0.015


def _circle(cx, cy, rx, ry, t0=0.0, seconds=1.5, turns=1.0, start_deg=0.0):
    n = round(seconds / DT)
    return [(t0 + i * DT, round(cx + rx * math.cos(math.radians(start_deg) + turns * 2 * math.pi * i / n)),
             round(cy + ry * math.sin(math.radians(start_deg) + turns * 2 * math.pi * i / n))) for i in range(n + 1)]


def _line(a, b, t0=0.0, seconds=0.5):
    n = round(seconds / DT)
    return [(t0 + i * DT, round(a[0] + (b[0] - a[0]) * i / n), round(a[1] + (b[1] - a[1]) * i / n)) for i in range(n + 1)]


def _still(x, y, t0=0.0, seconds=1.0):
    return [(t0 + i * DT, x, y) for i in range(round(seconds / DT) + 1)]


def test_a_circle_around_a_message_gives_its_region():
    # around the box (480, 300)-(1440, 600): 250-750 across and 278-556 down on the grid
    line = describe(_circle(960, 450, 480, 150), SIZE)
    assert line == "khoanh quanh vùng (250, 278)-(750, 556) trên lưới 0-1000"


def test_a_circle_drawn_the_other_way_or_twice_counts_too():
    assert describe(_circle(960, 450, 480, 150, turns=-1.0), SIZE).startswith("khoanh quanh vùng")
    assert describe(_circle(960, 450, 480, 150, turns=2.0, seconds=3.0), SIZE).startswith("khoanh quanh vùng")


def test_a_circle_that_does_not_quite_close_still_counts():
    assert describe(_circle(960, 450, 300, 200, turns=0.9), SIZE).startswith("khoanh quanh vùng")
    assert describe(_circle(960, 450, 300, 200, turns=0.6), SIZE) is None


def test_a_shaky_hand_still_draws_a_circle():
    rng = random.Random(7)
    shaky = [(t + rng.uniform(0, 0.004), x + rng.randint(-3, 3), y + rng.randint(-3, 3))
             for t, x, y in _circle(960, 450, 300, 120)]
    assert describe(shaky, SIZE).startswith("khoanh quanh vùng")


def test_a_rounded_box_drawn_by_hand_counts():
    a, b, c, d = (500, 300), (1000, 310), (1010, 500), (490, 490)
    path = _line(a, b, seconds=0.4)
    for p, q in ((b, c), (c, d), (d, a), (a, (620, 300))):
        path += _line(p, q, t0=path[-1][0] + DT, seconds=0.4)
    assert describe(path, SIZE).startswith("khoanh quanh vùng")


def test_a_circle_on_the_way_to_the_round_button_is_still_found():
    # claude's catch 02/11: the path as a whole does not close, because it ends on the button
    path = _line((200, 900), (480, 450), seconds=0.6)
    path += _circle(960, 450, 480, 150, t0=path[-1][0] + DT, start_deg=180)
    path += _line((480, 450), (1850, 1000), t0=path[-1][0] + DT, seconds=0.7)
    assert describe(path, SIZE) == "khoanh quanh vùng (250, 278)-(750, 556) trên lưới 0-1000"


def test_the_last_of_two_circles_wins():
    first = _circle(300, 300, 200, 100)
    second = _circle(1400, 700, 200, 100, t0=first[-1][0] + 1.0)
    assert describe(first + second, SIZE) == "khoanh quanh vùng (625, 556)-(833, 741) trên lưới 0-1000"


def test_a_still_mouse_gives_a_point():
    assert describe(_still(960, 540, seconds=0.7), SIZE) == "dừng ở (500, 500) trên lưới 0-1000"
    assert describe(_still(960, 540, seconds=0.4), SIZE) is None


def test_a_small_shake_is_still_a_stop_but_a_slow_drift_is_not():
    shake = [(i * DT, 960 + (i % 7) * 3, 540 - (i % 5) * 3) for i in range(60)]
    assert describe(shake, SIZE).startswith("dừng ở")
    drift = [(i * DT, 100 + i * 4, 540) for i in range(200)]
    assert describe(drift, SIZE) is None


def test_the_last_stop_wins_and_a_circle_beats_a_stop():
    path = _still(200, 200, seconds=1.0) + _line((200, 200), (800, 500), t0=1.1) + _still(800, 500, t0=1.7)
    assert describe(path, SIZE) == "dừng ở (417, 463) trên lưới 0-1000"
    circled = _still(200, 200, seconds=1.0) + _circle(960, 450, 480, 150, t0=1.1, start_deg=180) \
        + _still(480, 450, t0=2.7, seconds=0.8)
    assert describe(circled, SIZE).startswith("khoanh quanh vùng")


def test_a_zigzag_across_the_screen_is_nothing():
    path, t = [], 0.0
    for i in range(6):
        a, b = (100, 300 + i * 40), (1800, 300 + (i + 1) * 40)
        path += _line(a if i % 2 == 0 else b, b if i % 2 == 0 else a, t0=t, seconds=0.3)
        t = path[-1][0] + DT
    assert describe(path, SIZE) is None


def test_going_back_and_forth_along_a_line_is_nothing():
    path = _line((300, 500), (1200, 500), seconds=0.3)
    path += _line((1200, 500), (300, 500), t0=path[-1][0] + DT, seconds=0.3)
    assert describe(path, SIZE) is None


def test_a_short_path_is_nothing():
    assert describe([], SIZE) is None
    assert describe([(0.0, 10, 10)], SIZE) is None
    assert describe(_line((100, 100), (130, 110), seconds=0.1), SIZE) is None


def test_a_circle_too_small_to_mean_anything_is_not_a_circle():
    assert find_circle(_circle(960, 540, 15, 8)) is None
    assert find_circle(_circle(960, 540, 21, 11)) is not None  # just over 40x20


def test_a_loop_made_slowly_over_a_long_time_is_not_a_circle():
    assert find_circle(_circle(960, 540, 300, 200, seconds=8.0)) is None


def test_the_grid_follows_the_screen_size():
    assert describe(_still(1366, 768), (2732, 1536)) == "dừng ở (500, 500) trên lưới 0-1000"
    assert describe(_still(1919, 1079), SIZE) == "dừng ở (999, 999) trên lưới 0-1000"


def test_a_mouse_outside_the_captured_screen_is_ignored():
    assert describe(_still(2500, 400), SIZE) is None   # a second monitor
    assert describe(_still(-50, 400), SIZE) is None


def test_a_long_busy_path_is_worked_out_quickly():
    # she is waiting for the answer and this runs before the call to the model; a wave along the screen
    # never closes, so every start is tried: 45 s of moving the mouse without a stop, the longest question
    n = round(45 / DT)
    wave = [(i * DT, round(20 + 40 * i * DT), round(540 + 200 * math.sin(i * DT * 3))) for i in range(n)]
    started = time.perf_counter()
    assert describe(wave, SIZE) is None
    assert time.perf_counter() - started < 1.0
