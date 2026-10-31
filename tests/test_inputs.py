import threading

from screentutor.inputs import HOLD_S, Click, Hold, InputTracker, Sample, watch


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
