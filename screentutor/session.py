"""One task, step by step (MVP step 4). The app (app.py) speaks; this command line prints.

  ask -> point and say -> wait for the user's click -> hide the ring -> wait for a still screen
      -> check the step (follow_up) -> point at the next step ... until the task is done.

The tutor never clicks. Each step's screenshot and answer are kept in
tutor_runs/<time>/ (gitignored) for review.

The answer streams: the step is shown as soon as its place is known and the sentence is
spoken as soon as it is complete, before the plan and the notes have finished arriving.

B2 (02/11): the session keeps the plan of a big task, the part being done and the notes
of a long message, and hands them to every later turn, so she never has to ask again.
Each step says what it wants:
  click   the ring, her click, a still screen (as above)
  read    show the region and say it; it ends on her click, or on a big change that stood
          still, whichever comes first (founder); the island says "reading", in the frame's mint
  scroll  show where and say it; wait for the screen to change and stand still, no click
  none    say it; if something is loading, watch the screen and look again
A read or scroll wait with nothing happening stops as a click step does (founder). A screen
that never stands still is a video, not a failure: the next turn looks at it all the same.

B7 (02/11): a task left half done can be picked up. The session starts with the plan, the part
and the notes it had, and its first turn looks at the screen as it is now.

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

from .still import BIG_CHANGE, CHANGE_MIN

MAX_STEPS = 12        # T6 (02/11): exporting a PDF after backing out of a wrong dialog took 8 steps and hit 8
MAX_PLAN_STEPS = 30   # a task with a plan (founder's big tasks, 02/11)...
MAX_PART_STEPS = 12   # ...and each of its parts
MAX_WAITS = 3         # "please wait, it is loading" answers in a row before giving up
CLICK_WAIT_S = 180
READ_WAIT_S = 180
SCROLL_WAIT_S = 60
HIDE_PAUSE_S = 0.12   # let the ring disappear before watching the screen, or its vanishing looks like a change
RING_FLIGHT_S = 0.5   # overlay.TRAVEL_S and a little: measured 02/11, the ring's flight alone counts as a change
READ_DONE = "Đọc xong bạn bấm chuột một cái nhé."  # founder 02/11: reading has no click of its own to wait for


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
    target: str = ""               # what the step asked for: click, read, scroll or none
    shown_s: float | None = None   # seconds from the screenshot until she saw the step


@dataclass
class Session:
    """Wiring for one task. Every side effect is injected, so the loop runs the same with fakes."""
    tutor: object                  # .ask(...) and .follow_up(...), as in tutor.Tutor
    look: object                   # () -> (PIL image, state text or None)
    encode: object                 # PIL image -> data URL
    show: object                   # (x, y, caution) physical px -> None
    hide: object                   # () -> None
    say: object                    # (text) -> None
    wait_click: object             # (since, timeout_s) -> Click or None
    settle: object                 # (click) -> outcome str
    wait_screen: object = None     # () -> outcome str: wait for a loading screen to change and settle
    save: object = None            # (n, image, reply) -> None
    pause: object = time.sleep
    status: object = None          # (state) -> None for the island: thinking, turn, reading, caution, loading, error, done, idle
    cancel: object = None          # threading.Event: the user asked something new
    pointer: str | None = None     # B1b: what her mouse pointed at or circled while she asked, for the first turn
    known: str | None = None       # B5: what her own earlier tasks say that may help with this question
    wait_change: object = None     # (timeout_s, min_change, stop) -> outcome str: wait with no click to start from
    show_box: object = None        # (box, caution) physical px; until B3 draws it, a ring at the centre of the box
    show_scroll: object = None     # (point) physical px; until B3 draws the arrow, a ring there
    on_plan: object = None         # (plan, part) -> None: the parts of the task and the part being done, from 1
    confirm: object = None         # (x, y) physical px: the step she clicked there has been checked and is done
    steps: list[Step] = field(default_factory=list)
    plan: list[str] = field(default_factory=list)
    part: int = 0                  # from 1; 0 while there is no plan
    notes: str = ""
    mode: str = ""
    part_steps: int = 0            # steps taken in the current part
    clicked: object = None         # her click waiting for the check turn
    shown_at: float | None = None  # when this turn's step went on the screen, None until it has
    spoken: bool = False           # this turn's sentence has been said
    screen_size: tuple = (0, 0)    # of the screenshot this turn looks at
    reading: bool = False          # this turn's step is a region to read
    asked_at: float = 0.0

    @staticmethod
    def _is_waiting(reply) -> bool:
        """The step was done, the task is not, and there is nothing to click yet: something is loading."""
        return reply.step_done is True and reply.goal_done is False and not reply.error

    def _cancelled(self) -> bool:
        return self.cancel is not None and self.cancel.is_set()

    def _status(self, state: str) -> None:
        if self.status:
            self.status(state)

    def _track(self, reply) -> None:
        """Later turns only send what changed; the plan, the part and the notes live here."""
        before = self.plan, self.part
        self.mode = reply.mode or self.mode
        self.plan = reply.plan or self.plan
        self.notes = reply.notes or self.notes
        self.part = min(reply.part or self.part or 1, len(self.plan)) if self.plan else 0
        if self.part != before[1]:
            self.part_steps = 0
        if self.on_plan and self.plan and (self.plan, self.part) != before:
            self.on_plan(self.plan, self.part)

    def _at_limit(self, max_steps: int) -> bool:
        if self.plan:
            return len(self.steps) >= MAX_PLAN_STEPS or self.part_steps >= MAX_PART_STEPS
        return len(self.steps) >= max_steps

    def _turn_starts(self, img) -> None:
        self.shown_at, self.spoken, self.screen_size = None, False, img.size
        self.asked_at = time.monotonic()

    def _check(self, question: str, last_say: str, changed: bool | None, acted: str = "click"):
        """Look again after she acted: the next turn, with all that is known about the task."""
        self._status("thinking")
        img, state = self.look()
        self._turn_starts(img)
        return img, self.tutor.follow_up(question, last_say, self.encode(img), state, changed, plan=self.plan or None,
                                         part=self.part or None, notes=self.notes, acted=acted,
                                         on_mark=self._early_mark, on_say=self._early_say)

    def _early_mark(self, reply) -> None:
        """The answer is still arriving, but the place is known: she sees it seconds sooner."""
        self._tick(reply)
        px = reply.point_px(self.screen_size)
        if px and reply.target != "none" and not reply.goal_done and not self._cancelled():
            self._show_step(reply, px, reply.box_px(self.screen_size))

    def _early_say(self, text: str) -> None:
        if not text.isascii() and not self._cancelled():  # no diacritics: the tutor asks again, see Tutor._call
            self._speak(text)

    def _tick(self, reply) -> None:
        """The checking made visible, where she clicked, as the next step comes up."""
        click, self.clicked = self.clicked, None
        if self.confirm and click is not None and reply.step_done and not self._cancelled():
            self.confirm(click.x, click.y)

    def _show_step(self, reply, px, box) -> None:
        """Once a turn: what she should look at, and the island's colour to match."""
        if self.shown_at is not None:
            return
        self.shown_at = time.monotonic()
        self.reading = reply.target == "read" and self.wait_change is not None
        if self.reading and self.show_box:
            self.show_box(box, reply.caution)
        elif reply.target == "scroll" and self.wait_change and self.show_scroll:
            self.show_scroll(px)
        else:
            self.show(px[0], px[1], reply.caution)   # the ring first, so her eyes are there while she hears where
        self._status("caution" if reply.caution else "reading" if self.reading else "turn")  # as the mark's colour

    def _speak(self, text: str) -> None:
        if not self.spoken:
            self.spoken = True
            self.say(f"{text} {READ_DONE}" if self.shown_at is not None and self.reading else text)

    def _settle(self, click) -> str:
        self.pause(HIDE_PAUSE_S)
        return self.settle(click)

    def _click(self, reply, px) -> str | None:
        """Ring, words, her click, a still screen. None: she stopped, or asked something new."""
        self._show_step(reply, px, None)
        self._speak(reply.say)
        click = self.wait_click(self.shown_at, CLICK_WAIT_S)
        self.hide()
        if click is None or self._cancelled():
            return None  # she stopped, or asked something new; she can ask again any time
        self.clicked = click
        return self._settle(click)

    def _read(self, reply, px, box) -> tuple[str | None, str]:
        """A region to read. Returns (outcome, what she did); outcome None as in _click."""
        self._show_step(reply, px, box)
        self._speak(reply.say)
        shown_at = self.shown_at
        clicked = []

        def finished() -> bool:
            click = self.wait_click(shown_at, 0)
            if click is not None:
                clicked.append(click)
            return bool(clicked) or self._cancelled()

        self.pause(RING_FLIGHT_S)
        outcome = self.wait_change(READ_WAIT_S, BIG_CHANGE, finished)
        self.hide()
        if self._cancelled() or (outcome == "unchanged" and not clicked):
            return None, "read"
        if clicked:
            return self._settle(clicked[0]), "read"
        self.pause(HIDE_PAUSE_S)
        return outcome, "moved"

    def _scroll(self, reply, px) -> str | None:
        """Show where to scroll and wait for the screen; she has nothing to click. None as in _click."""
        self._show_step(reply, px, None)   # her turn, not "Chờ trang tải" (founder 02/11)
        self._speak(reply.say)
        self.pause(RING_FLIGHT_S)
        outcome = self.wait_change(SCROLL_WAIT_S, CHANGE_MIN, self._cancelled)
        self.hide()
        if self._cancelled() or outcome == "unchanged":
            return None
        self.pause(HIDE_PAUSE_S)
        return outcome

    def run(self, question: str, max_steps: int = MAX_STEPS, last_say: str | None = None) -> list[Step]:
        """last_say: the task is being picked up again, this was the last thing the tutor said in it."""
        if last_say is None:
            self._status("thinking")
            img, state = self.look()
            self._turn_starts(img)
            reply = self.tutor.ask(question, self.encode(img), state, self.pointer, on_mark=self._early_mark,
                                   on_say=self._early_say, known=self.known)
        else:
            if self.on_plan and self.plan:
                self.on_plan(self.plan, self.part)   # the card comes back before the tutor speaks
            img, reply = self._check(question, last_say, None, "resume")
        outcome = None
        waits = 0
        while not self._cancelled():
            self._track(reply)
            if self._at_limit(max_steps) and not reply.goal_done and not reply.error:
                if self.shown_at is not None:
                    self.hide()
                break
            px = reply.point_px(img.size)
            self.steps.append(Step(len(self.steps) + 1, reply.say, px, reply.step_done, reply.goal_done, outcome,
                                   reply.latency_s, reply.error, reply.target,
                                   None if self.shown_at is None else round(self.shown_at - self.asked_at, 2)))
            self.part_steps += 1
            if self.save:
                self.save(len(self.steps), img, reply)
            if reply.error:
                if self.shown_at is not None:
                    self.hide()
                self._status("error")
                self.say("Mình chưa xem được màn hình. Bạn hỏi lại nhé.")
                break
            if reply.goal_done or px is None:
                self._speak(reply.say)
                if not self._is_waiting(reply) or waits >= MAX_WAITS or self.wait_screen is None:
                    break  # done, or nothing to click: the sentence already says why or asks back
                # T6/T8 (02/11): a page or a file was still loading; the session used to stop here.
                waits += 1
                self._status("loading")
                outcome = self.wait_screen()
                if self._cancelled():
                    break
                img, reply = self._check(question, reply.say, outcome != "unchanged")
                continue
            waits = 0
            if reply.target == "read" and self.wait_change:
                outcome, acted = self._read(reply, px, reply.box_px(img.size))
            elif reply.target == "scroll" and self.wait_change:
                outcome, acted = self._scroll(reply, px), "moved"
            else:
                outcome, acted = self._click(reply, px), "click"
            if outcome is None or self._cancelled():
                break
            img, reply = self._check(question, reply.say, outcome != "unchanged", acted)
            self._tick(reply)
        if not self._cancelled() and not (self.steps and self.steps[-1].error):
            self._status("done" if self.steps and self.steps[-1].goal_done else "idle")
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
    from .still import wait_change, wait_until_settled
    from .tutor import Tutor, _api_key

    signal.signal(signal.SIGINT, signal.SIG_DFL)
    app = QApplication(sys.argv[:1])
    overlay = Overlay()

    class Bridge(QObject):  # the session runs in a worker thread; the ring lives in the Qt thread
        point = Signal(int, int, bool)
        clear = Signal()
        finished = Signal()

    bridge = Bridge()
    bridge.point.connect(lambda x, y, caution: overlay.point_at(x, y, caution=caution))
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
                show=lambda x, y, caution: bridge.point.emit(x, y, caution), hide=bridge.clear.emit,
                say=lambda text: print(f"\nTutor: {text}", flush=True),
                wait_click=clicks.wait,
                settle=lambda c: wait_until_settled(c.t, screen.grab)[0],
                wait_screen=lambda: wait_until_settled(time.monotonic(), screen.grab, grace_s=5.0)[0],
                wait_change=lambda timeout_s, min_change, stop: wait_change(screen.grab, timeout_s, min_change, stop),
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
