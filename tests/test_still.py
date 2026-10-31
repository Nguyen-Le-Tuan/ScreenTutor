from pathlib import Path

import pytest
from PIL import Image, ImageDraw

from screentutor.still import (CHANGE_MIN, GRACE_S, STILL_S, TIMEOUT_S, SettleWatcher, changed_fraction, signature,
                               wait_until_settled)

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
