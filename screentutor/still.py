"""Has the screen settled after the user's click? (MVP step 4, Decision 2b)

After each click the tutor takes small greyscale copies of the screen every
~150 ms and compares each with the one before. A blinking caret or the taskbar
clock changes only a few of the 192x108 cells, which stays under the threshold.
The pointer ring is hidden as soon as the user clicks, so it is never in these
copies.

Three outcomes, each followed by a check turn:
  settled    the screen changed, then stayed still for STILL_S
  unchanged  nothing changed within GRACE_S: the click did nothing visible
  timeout    still changing after TIMEOUT_S (a video, an animation): check anyway

B2 (02/11): wait_change waits the same way with no click to start from, for a step
where she scrolls or reads. It looks at how far the screen has come from where it
began, so a slow scroll adds up. The ring is still on the screen during this wait;
its pulse stays under CHANGE_MIN, its flight from the mouse does not (measured 02/11),
so the session starts the wait once the ring has landed.

  py -m screentutor.still --seconds 60    # Windows: after each click, print the outcome and how long it took
"""

from __future__ import annotations

import argparse
import sys
import threading
import time

from PIL import Image

SIG_SIZE = (192, 108)
PIXEL_TOL = 16          # grey levels a cell may drift without counting as changed
CHANGE_MIN = 0.002      # share of cells that must change to call it a change (~41 of 20,736)
BIG_CHANGE = 0.05       # a read step ends on this much: a scroll counts, a toast does not (founder 02/11, estimate)
STILL_S = 0.7
GRACE_S = 2.5           # a slow app (Word opening a file) may show nothing for a moment
TIMEOUT_S = 12.0
GRAB_EVERY_S = 0.15


def signature(img: Image.Image) -> bytes:
    return img.convert("L").resize(SIG_SIZE, Image.Resampling.BILINEAR).tobytes()


def changed_fraction(a: bytes, b: bytes, tol: int = PIXEL_TOL) -> float:
    if len(a) != len(b):
        return 1.0
    return sum(abs(x - y) > tol for x, y in zip(a, b)) / len(a)


class SettleWatcher:
    """Feed it (time, signature) pairs after a click; it says when to look again. Pure logic."""

    def __init__(self, clicked_at: float, grace_s: float = GRACE_S):
        self.clicked_at = clicked_at
        self.grace_s = grace_s
        self._prev: bytes | None = None
        self._changed = False
        self._last_change = clicked_at

    def feed(self, t: float, sig: bytes) -> str:
        """Returns "waiting", "settled", "unchanged" or "timeout"."""
        if self._prev is not None and changed_fraction(self._prev, sig) >= CHANGE_MIN:
            self._changed = True
            self._last_change = t
        self._prev = sig
        if t - self.clicked_at >= TIMEOUT_S:
            return "timeout"
        if self._changed:
            return "settled" if t - self._last_change >= STILL_S else "waiting"
        return "unchanged" if t - self.clicked_at >= self.grace_s else "waiting"


def wait_until_settled(clicked_at: float, grab, clock=time.monotonic, sleep=time.sleep,
                       grace_s: float = GRACE_S) -> tuple[str, float]:
    """Grab until the watcher decides. Returns (outcome, seconds since the click)."""
    watcher = SettleWatcher(clicked_at, grace_s)
    while True:
        t = clock()
        outcome = watcher.feed(t, signature(grab()))
        if outcome != "waiting":
            return outcome, t - clicked_at
        sleep(GRAB_EVERY_S)


class ChangeWatcher:
    """Feed it (time, signature) pairs while she scrolls or reads; no click to start from. Pure logic."""

    def __init__(self, started_at: float, timeout_s: float, min_change: float = CHANGE_MIN):
        self.started_at, self.timeout_s, self.min_change = started_at, timeout_s, min_change
        self._first: bytes | None = None
        self._prev: bytes | None = None
        self._changed = False
        self._last_change = started_at

    def feed(self, t: float, sig: bytes) -> str:
        """Returns "waiting", "settled", "unchanged" (nothing happened) or "timeout" (still changing: a video)."""
        if self._first is None:
            self._first = self._prev = sig
        if changed_fraction(self._prev, sig) >= CHANGE_MIN:
            self._last_change = t
        self._prev = sig
        self._changed = self._changed or changed_fraction(self._first, sig) >= self.min_change
        if self._changed and t - self._last_change >= STILL_S:
            return "settled"
        if t - self.started_at >= self.timeout_s:
            return "timeout" if self._changed else "unchanged"
        return "waiting"


def wait_change(grab, timeout_s: float, min_change: float = CHANGE_MIN, stop=None, clock=time.monotonic,
                sleep=time.sleep) -> str:
    """Wait for the screen to change and stand still. stop() can end the wait: it returns "stopped"."""
    watcher = ChangeWatcher(clock(), timeout_s, min_change)
    while True:
        if stop is not None and stop():
            return "stopped"
        outcome = watcher.feed(clock(), signature(grab()))
        if outcome != "waiting":
            return outcome
        sleep(GRAB_EVERY_S)


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(prog="python -m screentutor.still")
    ap.add_argument("--seconds", type=float, default=60)
    args = ap.parse_args(argv)
    if sys.platform != "win32":
        sys.exit("Chỉ chạy trên Windows.")
    from . import screen
    from .inputs import Click, watch

    clicks: list[Click] = []
    stop = threading.Event()
    threading.Thread(target=watch, args=(lambda e: isinstance(e, Click) and clicks.append(e), stop),
                     daemon=True).start()
    threading.Timer(args.seconds, stop.set).start()
    print(f"Đang theo dõi {args.seconds:.0f} giây. Sau mỗi cú bấm, chờ màn hình đứng yên rồi báo.")
    while not stop.is_set():
        if not clicks:
            time.sleep(0.05)
            continue
        click = clicks.pop(0)
        outcome, took = wait_until_settled(click.t, screen.grab)
        extra = len(clicks)
        clicks.clear()  # clicks made while waiting belong to the same moment
        label = {"settled": "ĐỨNG YÊN", "unchanged": "KHÔNG ĐỔI", "timeout": "QUÁ GIỜ"}[outcome]
        print(f"Bấm tại ({click.x}, {click.y}) -> {label} sau {took:.1f} s"
              + (f" (thêm {extra} cú bấm trong lúc chờ)" if extra else ""))


if __name__ == "__main__":
    main()
