import threading

from screentutor.inputs import HOLD_S, Click, Hold, InputTracker, Sample, Trail, watch


def _run(steps):
    """steps: (t, left, right, ctrl, alt, x, y) tuples -> all events."""
    tracker = InputTracker()
    events = []
    for st in steps:
        events += tracker.feed(Sample(*st))
    return events


def _press(t0, x, y, length=0.08, button="left"):
    l, r = (True, False) if button == "left" else (False, True)
    return [(t0, l, r, False, False, x, y), (t0 + length, False, False, False, False, x + 1, y)]


def test_click_is_reported_on_release_at_the_press_position():
    events = _run([(0.0, False, False, False, False, 0, 0)] + _press(0.1, 500, 300))
    assert events == [Click(0.1, 500, 300, "left", double=False)]


def test_double_click_needs_two_quick_clicks_close_together():
    ev = _run(_press(0.0, 500, 300) + _press(0.3, 503, 302))
    assert [e.double for e in ev] == [False, True]
    assert [e.double for e in _run(_press(0.0, 500, 300) + _press(0.9, 500, 300))] == [False, False]
    assert [e.double for e in _run(_press(0.0, 500, 300) + _press(0.3, 600, 300))] == [False, False]
    triple = _run(_press(0.0, 500, 300) + _press(0.2, 500, 300) + _press(0.4, 500, 300))
    assert [e.double for e in triple] == [False, True, False]


def test_right_click():
    assert _run(_press(0.0, 10, 20, button="right")) == [Click(0.0, 10, 20, "right")]


def test_ctrl_alt_hold_starts_after_hold_time_and_ends_on_release():
    t = [0.0, 0.1, 0.1 + HOLD_S, 0.6, 0.7]
    steps = [(t[0], False, False, True, False, 0, 0),   # Ctrl only
             (t[1], False, False, True, True, 0, 0),    # Ctrl+Alt down
             (t[2], False, False, True, True, 0, 0),    # held long enough
             (t[3], False, False, True, True, 0, 0),
             (t[4], False, False, True, False, 0, 0)]   # Alt let go
    assert _run(steps) == [Hold(t[2], True), Hold(t[4], False)]


def test_quick_ctrl_alt_shortcut_is_not_a_hold():
    steps = [(0.0, False, False, True, True, 0, 0), (0.1, False, False, False, False, 0, 0)]
    assert _run(steps) == []


def test_watch_polls_until_stopped():
    samples = iter([Sample(0.0, True, False, False, False, 5, 5), Sample(0.05, False, False, False, False, 5, 5)])
    stop, seen = threading.Event(), []

    def read():
        try:
            return next(samples)
        except StopIteration:
            stop.set()
            return Sample(0.1, False, False, False, False, 5, 5)

    watch(seen.append, stop, read=read, poll_s=0)
    assert seen == [Click(0.0, 5, 5, "left")]


def test_trail_gives_the_samples_of_a_time_span():
    trail = Trail()
    for i in range(10):
        trail.add(float(i), i * 10, i * 20)
    assert trail.between(2.0, 4.0) == [(2.0, 20, 40), (3.0, 30, 60), (4.0, 40, 80)]
    assert trail.between(20.0, 30.0) == []


def test_trail_forgets_what_is_older_than_it_keeps():
    trail = Trail(keep_s=1.0, poll_s=0.25)   # room for 4 samples
    for i in range(6):
        trail.add(float(i), i, i)
    assert [p[0] for p in trail.between(0.0, 10.0)] == [2.0, 3.0, 4.0, 5.0]


def test_trail_can_be_read_while_the_input_thread_writes():
    trail, stop, seen = Trail(keep_s=1.0, poll_s=0.001), threading.Event(), []

    def write():
        i = 0
        while not stop.is_set():
            trail.add(float(i), i, i)
            i += 1

    writer = threading.Thread(target=write)
    writer.start()
    for _ in range(200):
        seen.append(len(trail.between(0.0, 1e12)))
    stop.set()
    writer.join()
    assert max(seen) <= 1000


def test_watch_writes_the_trail_only_when_given_one():
    samples = iter([Sample(0.0, False, False, False, False, 5, 6), Sample(0.1, False, False, False, False, 7, 8)])
    stop, trail = threading.Event(), Trail()

    def read():
        try:
            return next(samples)
        except StopIteration:
            stop.set()
            return Sample(0.2, False, False, False, False, 9, 9)

    watch(lambda e: None, stop, read=read, poll_s=0, trail=trail)
    assert trail.between(0.0, 0.1) == [(0.0, 5, 6), (0.1, 7, 8)]


def test_a_press_and_release_far_apart_is_a_drag_not_a_click():
    from screentutor.inputs import DRAG_PX, Drag

    events = _run([(0.0, True, False, False, False, 100, 200), (0.4, True, False, False, False, 300, 205),
                    (0.5, False, False, False, False, 300, 205)])
    assert events == [Drag(0.0, 100, 200, 300, 205)]
    shaky = _run([(0.0, True, False, False, False, 100, 200), (0.1, False, False, False, False, 100 + DRAG_PX - 2, 203)])
    assert [type(e).__name__ for e in shaky] == ["Click"] and shaky[0].x == 100


def test_only_the_taught_shortcuts_are_seen_never_what_she_types():
    from screentutor.inputs import Combo

    tracker = InputTracker()
    seen = []
    for t, ctrl, keys in [(0.0, False, {"C"}), (0.1, False, set()),          # typing "c": nothing
                          (0.2, True, set()), (0.3, True, {"C"}), (0.4, True, {"C"}),   # Ctrl+C, held
                          (0.5, False, set()), (0.6, False, {"Enter"}), (0.7, False, set())]:
        seen += tracker.feed(Sample(t, False, False, ctrl, False, 0, 0, frozenset(keys)))
    assert seen == [Combo(0.3, "Ctrl+C"), Combo(0.6, "Enter")]
