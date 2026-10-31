"""Watching the user's mouse clicks and the Ctrl+Alt hold (MVP steps 4 and 5).

Decision 2b: the tutor only observes the clicks; nothing is ever sent to an app.
Decision 4c: holding Ctrl+Alt calls the tutor.

The state of the buttons and keys is polled (GetAsyncKeyState, GetCursorPos)
instead of installing a global hook: nothing keylogger-like for antivirus tools
to flag, and a slow moment in Python cannot make Windows drop a hook. A click
lasts 50-150 ms, so a 15 ms poll does not miss it.

  py -m screentutor.inputs --seconds 30     # Windows: print every click and Ctrl+Alt hold
"""

from __future__ import annotations

import argparse
import math
import sys
import threading
import time
from dataclasses import dataclass

POLL_S = 0.015
DOUBLE_CLICK_S = 0.5     # Windows default double-click time
DOUBLE_CLICK_PX = 10     # physical px between the two clicks of a double click
HOLD_S = 0.3             # Ctrl+Alt must stay down this long, so quick shortcuts are not mistaken for it


@dataclass
class Sample:
    t: float
    left: bool
    right: bool
    ctrl: bool
    alt: bool
    x: int
    y: int


@dataclass
class Click:
    t: float          # when the button went down
    x: int            # physical screen pixels, where the button went down
    y: int
    button: str       # "left" or "right"
    double: bool = False


@dataclass
class Hold:
    t: float
    started: bool     # True when Ctrl+Alt has been held long enough, False when it is let go


class InputTracker:
    """Turns polled samples into clicks and Ctrl+Alt holds. Pure logic, no Windows calls."""

    def __init__(self):
        self._prev: Sample | None = None
        self._down: dict[str, tuple[float, int, int]] = {}
        self._last_left: Click | None = None
        self._combo_since: float | None = None
        self._holding = False

    def feed(self, s: Sample) -> list[Click | Hold]:
        events: list[Click | Hold] = []
        prev = self._prev
        for button in ("left", "right"):
            now, was = getattr(s, button), bool(prev and getattr(prev, button))
            if now and not was:
                self._down[button] = (s.t, s.x, s.y)
            elif was and not now and button in self._down:
                t, x, y = self._down.pop(button)
                click = Click(t, x, y, button)
                if button == "left":
                    last = self._last_left
                    click.double = bool(last and not last.double and t - last.t <= DOUBLE_CLICK_S
                                        and math.hypot(x - last.x, y - last.y) <= DOUBLE_CLICK_PX)
                    self._last_left = click
                events.append(click)

        combo = s.ctrl and s.alt
        if combo and self._combo_since is None:
            self._combo_since = s.t
        elif not combo:
            self._combo_since = None
            if self._holding:
                self._holding = False
                events.append(Hold(s.t, started=False))
        if combo and not self._holding and s.t - self._combo_since >= HOLD_S:
            self._holding = True
            events.append(Hold(s.t, started=True))
        self._prev = s
        return events


def read_sample() -> Sample:
    """One reading of the real mouse and keyboard (Windows). Coordinates are physical pixels
    once the process is DPI aware (Qt makes it so; screen.grab() does too)."""
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    down = lambda vk: bool(user32.GetAsyncKeyState(vk) & 0x8000)  # noqa: E731
    pt = wintypes.POINT()
    user32.GetCursorPos(ctypes.byref(pt))
    return Sample(time.monotonic(), down(0x01), down(0x02), down(0x11), down(0x12), pt.x, pt.y)


def watch(on_event, stop: threading.Event, read=read_sample, poll_s: float = POLL_S) -> None:
    """Poll until stop is set, calling on_event(event) for each click or hold. Run it in a thread."""
    tracker = InputTracker()
    while not stop.is_set():
        for event in tracker.feed(read()):
            on_event(event)
        time.sleep(poll_s)


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(prog="python -m screentutor.inputs")
    ap.add_argument("--seconds", type=float, default=30)
    args = ap.parse_args(argv)
    if sys.platform != "win32":
        sys.exit("Chỉ chạy trên Windows.")
    from .screen import _dpi_aware

    _dpi_aware()

    def show(e):
        if isinstance(e, Click):
            kind = "BẤM ĐÚP" if e.double else ("bấm trái" if e.button == "left" else "bấm phải")
            print(f"{kind} tại ({e.x}, {e.y})")
        else:
            print("GIỮ Ctrl+Alt: bắt đầu" if e.started else "GIỮ Ctrl+Alt: thả ra")

    stop = threading.Event()
    threading.Timer(args.seconds, stop.set).start()
    print(f"Đang nghe {args.seconds:.0f} giây. Bấm, bấm đúp, bấm phải, giữ Ctrl+Alt...")
    watch(show, stop)


if __name__ == "__main__":
    main()
