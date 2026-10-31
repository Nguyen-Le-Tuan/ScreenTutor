"""One task, step by step (MVP step 4). The app (app.py) speaks; this command line prints.

  ask -> point and say -> wait for the user's click -> hide the ring -> wait for a still screen
      -> check the step (follow_up) -> point at the next step ... until the task is done.

The tutor never clicks. Each step's screenshot and answer are kept in
tutor_runs/<time>/ (gitignored) for review.

  py -m screentutor.session --delay 6 "Mẹ muốn xuất giáo án ra PDF"     # Windows
"""

from __future__ import annotations

import argparse
import json
import sys
import threading
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

MAX_STEPS = 8
CLICK_WAIT_S = 180
HIDE_PAUSE_S = 0.12   # let the ring disappear before watching the screen, or its vanishing looks like a change


@dataclass
class Step:
    n: int
    say: str
    point_px: tuple[int, int] | None
    step_done: bool | None = None
    goal_done: bool | None = None
    settle: str | None = None      # how the screen behaved after the previous click
    latency_s: float = 0.0
    error: str | None = None


@dataclass
class Session:
    """Wiring for one task. Every side effect is injected, so the loop runs the same with fakes."""
    tutor: object                  # .ask(question, data_url, state) / .follow_up(goal, last_say, data_url, state, changed)
    look: object                   # () -> (PIL image, state text or None)
    encode: object                 # PIL image -> data URL
    show: object                   # (x, y) physical px -> None
    hide: object                   # () -> None
    say: object                    # (text) -> None
    wait_click: object             # (since, timeout_s) -> Click or None
    settle: object                 # (click) -> outcome str
    save: object = None            # (n, image, reply) -> None
    pause: object = time.sleep
    status: object = None          # ("thinking" | "waiting") -> None, for the button and the island
    cancel: object = None          # threading.Event: the user asked something new
    steps: list[Step] = field(default_factory=list)

    def _cancelled(self) -> bool:
        return self.cancel is not None and self.cancel.is_set()

    def _status(self, state: str) -> None:
        if self.status:
            self.status(state)

    def run(self, question: str, max_steps: int = MAX_STEPS) -> list[Step]:
        self._status("thinking")
        img, state = self.look()
        reply = self.tutor.ask(question, self.encode(img), state)
        outcome = None
        for n in range(1, max_steps + 1):
            if self._cancelled():
                break
            px = reply.point_px(img.size)
            self.steps.append(Step(n, reply.say, px, reply.step_done, reply.goal_done, outcome,
                                   reply.latency_s, reply.error))
            if self.save:
                self.save(n, img, reply)
            if reply.error:
                self.say("Mình chưa xem được màn hình. Bạn hỏi lại nhé.")
                break
            if reply.goal_done or px is None:
                self.say(reply.say)
                break  # done, or nothing to click: the sentence already says why or asks back
            shown_at = time.monotonic()
            self.show(*px)        # the ring first, so her eyes are there while she hears where
            self.say(reply.say)
            self._status("waiting")
            click = self.wait_click(shown_at, CLICK_WAIT_S)
            self.hide()
            if click is None or self._cancelled():
                break  # she stopped, or asked something new; she can ask again any time
            self.pause(HIDE_PAUSE_S)
            outcome = self.settle(click)
            if self._cancelled():
                break
            self._status("thinking")
            img, state = self.look()
            reply = self.tutor.follow_up(question, reply.say, self.encode(img), state, outcome != "unchanged")
        return self.steps


class ClickBox:
    """Collects clicks from the input watcher thread; the session takes the first one after the ring appears."""

    def __init__(self):
        self._clicks = []
        self._cv = threading.Condition()

    def put(self, event) -> None:
        from .inputs import Click

        if isinstance(event, Click):
            with self._cv:
                self._clicks.append(event)
                self._cv.notify_all()

    def wait(self, since: float, timeout_s: float, cancel: threading.Event | None = None, ignore=None):
        """First click after since, skipping clicks ignore(click) says are not on the app (the Hỏi button)."""
        deadline = time.monotonic() + timeout_s
        with self._cv:
            while True:
                fresh = [c for c in self._clicks if c.t >= since and not (ignore and ignore(c))]
                if fresh:
                    self._clicks.clear()
                    return fresh[0]
                left = deadline - time.monotonic()
                if left <= 0 or (cancel is not None and cancel.is_set()):
                    return None
                self._cv.wait(min(left, 0.1))


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(prog="python -m screentutor.session")
    ap.add_argument("question", help="câu người dùng hỏi")
    ap.add_argument("--delay", type=int, default=0, help="chờ bấy nhiêu giây trước khi chụp lần đầu")
    args = ap.parse_args(argv)
    if sys.platform != "win32":
        sys.exit("Chỉ chạy trên Windows (cần màn hình, chuột và lớp phủ thật).")

    import signal

    from PySide6.QtCore import QObject, Signal
    from PySide6.QtWidgets import QApplication

    from . import screen
    from .inputs import watch
    from .overlay import Overlay
    from .state import format_vi, take_snapshot
    from .still import wait_until_settled
    from .tutor import Tutor, _api_key

    signal.signal(signal.SIGINT, signal.SIG_DFL)
    app = QApplication(sys.argv[:1])
    overlay = Overlay()

    class Bridge(QObject):  # the session runs in a worker thread; the ring lives in the Qt thread
        point = Signal(int, int)
        clear = Signal()
        finished = Signal()

    bridge = Bridge()
    bridge.point.connect(lambda x, y: overlay.point_at(x, y))
    bridge.clear.connect(overlay.clear)
    bridge.finished.connect(app.quit)

    out = Path("tutor_runs") / (datetime.now().strftime("%Y%m%d-%H%M%S") + "-session")
    out.mkdir(parents=True, exist_ok=True)

    def look():
        return screen.grab(), format_vi(take_snapshot())

    def save(n, img, reply):
        img.save(out / f"step_{n:02d}.png")
        data = {k: v for k, v in asdict(reply).items() if k != "raw"}
        (out / f"step_{n:02d}.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    clicks = ClickBox()
    stop = threading.Event()
    threading.Thread(target=watch, args=(clicks.put, stop), daemon=True).start()
    tutor = Tutor(_api_key())

    def work():
        try:
            for left in range(args.delay, 0, -1):
                print(f"Bắt đầu sau {left} giây... chuyển sang cửa sổ cần hỏi.", flush=True)
                time.sleep(1)
            session = Session(
                tutor=tutor, look=look, encode=screen.png_data_url,
                show=lambda x, y: bridge.point.emit(x, y), hide=bridge.clear.emit,
                say=lambda text: print(f"\nTutor: {text}", flush=True),
                wait_click=clicks.wait,
                settle=lambda c: wait_until_settled(c.t, screen.grab)[0],
                save=save)
            steps = session.run(args.question)
            for s in steps:
                print(f"  bước {s.n}: sau cú bấm = {s.settle or '—'}, bước xong = {s.step_done}, "
                      f"việc xong = {s.goal_done}, trỏ = {s.point_px}, {s.latency_s:.1f} s")
            (out / "session.json").write_text(json.dumps([asdict(s) for s in steps], ensure_ascii=False, indent=2),
                                              encoding="utf-8")
            print(f"Đã lưu {out}")
        finally:
            stop.set()
            tutor.close()
            bridge.finished.emit()

    threading.Thread(target=work, daemon=True).start()
    app.exec()


if __name__ == "__main__":
    main()
