from pathlib import Path

import pytest
from PIL import Image, ImageDraw

from screentutor.still import (BIG_CHANGE, CHANGE_MIN, GRACE_S, STILL_S, TIMEOUT_S, ChangeWatcher, SettleWatcher,
                               changed_fraction, signature, wait_change, wait_until_settled)

CASES = Path(__file__).resolve().parent.parent / "grounding_test" / "cases"
A, B = bytes(100), bytes([200] * 100)


def _case(name):
    path = CASES / f"{name}.png"
    if not path.exists():
        pytest.skip("real screenshots are not in the public repo")
    return Image.open(path).convert("RGB")


def test_caret_and_clock_are_not_changes_but_a_new_screen_is():
    word = _case("case_10")
    caret = word.copy()
    ImageDraw.Draw(caret).rectangle((700, 400, 701, 422), fill="white")           # a blinking caret
    clock = word.copy()
    ImageDraw.Draw(clock).text((1795, 1040), "1:49 AM", fill="white")              # the taskbar clock ticks
    base = signature(word)
    assert changed_fraction(base, signature(caret)) < CHANGE_MIN
    assert changed_fraction(base, signature(clock)) < CHANGE_MIN
    assert changed_fraction(base, signature(_case("case_11"))) > 0.2                # File > Export opened


def _feed(watcher, frames):
    return [watcher.feed(t, sig) for t, sig in frames]


def test_settles_after_the_screen_stops_changing():
    w = SettleWatcher(0.0)
    frames = [(0.15, A), (0.30, B), (0.45, B), (0.30 + STILL_S - 0.01, B), (0.30 + STILL_S + 0.01, B)]
    assert _feed(w, frames) == ["waiting"] * 4 + ["settled"]


def test_a_click_that_changes_nothing_is_reported_after_the_grace_time():
    w = SettleWatcher(0.0)
    assert _feed(w, [(0.15, A), (1.0, A), (GRACE_S, A)]) == ["waiting", "waiting", "unchanged"]


def test_slow_app_inside_the_grace_time_still_counts_as_a_change():
    w = SettleWatcher(0.0)
    frames = [(0.15, A), (GRACE_S - 0.2, B), (GRACE_S + 0.1, B), (GRACE_S - 0.2 + STILL_S, B)]
    assert _feed(w, frames) == ["waiting", "waiting", "waiting", "settled"]


def test_endless_change_times_out():
    w = SettleWatcher(0.0)
    frames = [(i * 0.5, A if i % 2 else B) for i in range(1, int(TIMEOUT_S / 0.5) + 1)]
    assert _feed(w, frames)[-1] == "timeout"


def test_wait_until_settled_drives_the_grabs():
    now = [0.0]
    shots = iter([Image.new("L", (40, 30), 0)] + [Image.new("L", (40, 30), 255)] * 20)

    def sleep(s):
        now[0] += s

    outcome, took = wait_until_settled(0.0, lambda: next(shots), clock=lambda: now[0], sleep=sleep)
    assert outcome == "settled" and STILL_S <= took < STILL_S + 0.5


def _page(top=0):
    """A chat page of made-up dark lines, top px scrolled."""
    img = Image.new("RGB", (1920, 1080), "white")
    d = ImageDraw.Draw(img)
    for i in range(-20, 40):
        y = 60 + i * 34 - top
        d.rectangle((420, y, 1500 - (i * 137) % 600, y + 14), fill=(40, 40, 40))
    return img


def test_a_scroll_is_a_big_change_and_a_toast_or_a_new_line_is_not():
    base = signature(_page())
    assert changed_fraction(base, signature(_page(100))) > BIG_CHANGE
    toast = _page()
    ImageDraw.Draw(toast).rectangle((1500, 880, 1900, 1040), fill=(50, 50, 60))   # a Windows notification
    assert CHANGE_MIN < changed_fraction(base, signature(toast)) < BIG_CHANGE
    bubble = _page()
    ImageDraw.Draw(bubble).rectangle((420, 1000, 900, 1060), fill=(200, 225, 255))  # a new chat message
    assert CHANGE_MIN < changed_fraction(base, signature(bubble)) < BIG_CHANGE


def test_change_watcher_settles_only_after_a_change():
    w = ChangeWatcher(0.0, 60)
    frames = [(0.15, A), (5.0, A), (5.15, B), (5.15 + STILL_S - 0.01, B), (5.15 + STILL_S + 0.01, B)]
    assert _feed(w, frames) == ["waiting"] * 4 + ["settled"]


def test_change_watcher_gives_up_when_nothing_happens():
    assert _feed(ChangeWatcher(0.0, 60), [(30.0, A), (60.0, A)]) == ["waiting", "unchanged"]


def test_a_video_never_stands_still_and_that_is_a_timeout_not_nothing():
    w = ChangeWatcher(0.0, 60)
    frames = [(i * 0.5, A if i % 2 else B) for i in range(1, 121)]
    assert _feed(w, frames)[-1] == "timeout"


def test_a_small_change_does_not_count_when_a_big_one_is_asked_for():
    base, toast = bytes(1000), bytes([200] * 10 + [0] * 990)   # 1% of the cells
    w = ChangeWatcher(0.0, 10, BIG_CHANGE)
    assert _feed(w, [(0.1, base), (0.3, toast), (5.0, toast), (10.0, toast)]) == ["waiting"] * 3 + ["unchanged"]


def test_a_slow_scroll_adds_up_to_a_big_change():
    w = ChangeWatcher(0.0, 60, BIG_CHANGE)
    frames = [(0.15 * (i + 1), bytes([200] * (i * 4) + [0] * (1000 - i * 4))) for i in range(30)]  # 0.4% a frame
    assert _feed(w, frames)[:12] == ["waiting"] * 12
    assert _feed(w, [(frames[-1][0] + STILL_S + 0.1, frames[-1][1])]) == ["settled"]


def test_wait_change_drives_the_grabs_and_can_be_stopped():
    now = [0.0]

    def sleep(s):
        now[0] += s

    shots = iter([Image.new("L", (40, 30), 0)] * 3 + [Image.new("L", (40, 30), 255)] * 20)
    assert wait_change(lambda: next(shots), 60, clock=lambda: now[0], sleep=sleep) == "settled"
    assert 0.4 + STILL_S <= now[0] < 0.4 + STILL_S + 0.5
    still = Image.new("L", (40, 30), 0)
    now[0] = 0.0
    assert wait_change(lambda: still, 5, clock=lambda: now[0], sleep=sleep) == "unchanged"
    calls = iter([False, False, True])
    assert wait_change(lambda: still, 60, stop=lambda: next(calls), clock=lambda: now[0], sleep=sleep) == "stopped"
