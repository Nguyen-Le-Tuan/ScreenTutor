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

    def __init__(self, clicked_at: float):
        self.clicked_at = clicked_at
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
        return "unchanged" if t - self.clicked_at >= GRACE_S else "waiting"


def wait_until_settled(clicked_at: float, grab, clock=time.monotonic, sleep=time.sleep) -> tuple[str, float]:
    """Grab until the watcher decides. Returns (outcome, seconds since the click)."""
    watcher = SettleWatcher(clicked_at)
    while True:
        t = clock()
        outcome = watcher.feed(t, signature(grab()))
        if outcome != "waiting":
            return outcome, t - clicked_at
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
