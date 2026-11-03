"""One task, step by step (MVP step 4). The app (app.py) speaks; this command line prints.

  ask -> point and say -> wait for the user's click -> hide the ring -> wait for a still screen
      -> check the step (follow_up) -> point at the next step ... until the task is done.

The tutor never clicks. Each step's screenshot and answer are kept in
tutor_runs/<time>/ (gitignored) for review.

The answer streams: the sentence is spoken as soon as it is complete, before the plan and
the notes have finished arriving. C1 (03/11): the step goes on the screen with the first
sound of its sentence, not as soon as its place is known. In the T13 videos the ring led
the voice by 3.0 s (median of 28 steps, 0.9-4.4 s): she clicked before she heard where,
which cut the sentence off, and on D4 the amber ring came 4.1 s before its warning.

C2 (03/11): just before the sentence is said, the screen is compared with the screenshot the
answer is about (fresh.py). If it has moved on (a toast gone, a box come up, she went ahead),
nothing is said and the tutor looks again, waiting first for a click she made meanwhile (founder:
look again in silence). At most MAX_STALE times in a row. Replayed on the T13 videos: 5 of 5
stale turns caught, 1 of 24 fresh turns flagged (tutor_eval/stale_replay.py).

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

from . import fresh
from .still import BIG_CHANGE, CHANGE_MIN, STILL_S

MAX_STEPS = 12        # T6 (02/11): exporting a PDF after backing out of a wrong dialog took 8 steps and hit 8
MAX_PLAN_STEPS = 30   # a task with a plan (founder's big tasks, 02/11)...
MAX_PART_STEPS = 12   # ...and each of its parts
MAX_WAITS = 3         # "please wait, it is loading" answers in a row before giving up
CLICK_WAIT_S = 180
READ_WAIT_S = 180
SCROLL_WAIT_S = 60
HIDE_PAUSE_S = 0.12   # let the ring disappear before watching the screen, or its vanishing looks like a change
RING_FLIGHT_S = 0.5   # overlay.TRAVEL_S and a little: measured 02/11, the ring's flight alone counts as a change
SOUND_WAIT_S = 4.0    # C1: a sentence with no voice (no sound card) still puts its step up after this long
MAX_STALE = 2         # C2: looks again at most this many times in a row; a screen that keeps moving gets its answer
TICK_R = 30           # physical px around her last click: its green tick is ours, not a change of the screen
STALE = "stale"       # C2: what a step comes to when its screen moved on before it was said
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
    stale: bool = False            # C2: the screen moved on before this step was said, so it never was
    region: float | None = None    # C2: share of the area around the target that had changed by then
    whole: float | None = None     # C2: share of the whole screen that had changed by then


@dataclass
class Session:
    """Wiring for one task. Every side effect is injected, so the loop runs the same with fakes."""
    tutor: object                  # .ask(...) and .follow_up(...), as in tutor.Tutor
    look: object                   # () -> (PIL image, state text or None)
    encode: object                 # PIL image -> data URL
    show: object                   # (x, y, caution) physical px -> None
    hide: object                   # () -> None
    say: object                    # (text, on_sound=None) -> None; on_sound() once the first sound has gone out
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
    glance: object = None          # C2: () -> PIL image of the screen now, to check an answer against before it is said
    own: object = None             # C2: () -> [(x1, y1, x2, y2)] physical px of our own widgets, left out of that check
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
    turn: int = 0                  # counts the turns, so a sound from an earlier turn shows nothing
    waiting_step: tuple | None = None  # C1: (reply, px, box) of this turn, until the first sound of its sentence
    sounded: bool = False          # this turn's sentence has made its first sound
    on_screen: object = field(default_factory=threading.Event)   # this turn's step is up
    lock: object = field(default_factory=threading.RLock)        # the voice's thread shows the step too
    seen: object = None            # the screenshot this turn's answer is about
    moved_on: bool | None = None   # C2: that screenshot is no longer the screen; None until checked
    change: object = None          # C2: what the check measured (fresh.Change), for the log
    ticked: tuple | None = None    # where this turn's green tick went
    stale_run: int = 0             # C2: turns in a row whose screen had moved on

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
        with self.lock:
            self.shown_at, self.spoken, self.screen_size = None, False, img.size
            self.asked_at = time.monotonic()
            self.turn += 1
            self.waiting_step, self.sounded, self.reading = None, False, False
            self.on_screen = threading.Event()
            self.seen, self.moved_on, self.change, self.ticked = img, None, None, None

    def _check(self, question: str, last_say: str, changed: bool | None, acted: str = "click"):
        """Look again after she acted: the next turn, with all that is known about the task."""
        self._status("thinking")
        img, state = self.look()
        self._turn_starts(img)
        return img, self.tutor.follow_up(question, last_say, self.encode(img), state, changed, plan=self.plan or None,
                                         part=self.part or None, notes=self.notes, acted=acted,
                                         on_mark=self._early_mark, on_say=self._early_say)

    def _early_mark(self, reply) -> None:
        """The answer is still arriving, but the place is known: the step waits for its sentence's first sound."""
        self._tick(reply)
        px = reply.point_px(self.screen_size)
        if px and reply.target != "none" and not reply.goal_done and not self._cancelled():
            self._prepare_step(reply, px, reply.box_px(self.screen_size))

    def _early_say(self, text: str) -> None:
        if not text.isascii() and not self._cancelled():  # no diacritics: the tutor asks again, see Tutor._call
            self._speak(text)

    def _tick(self, reply) -> None:
        """The checking made visible, where she clicked, as the next step comes up."""
        click, self.clicked = self.clicked, None
        if self.confirm and click is not None and reply.step_done and not self._cancelled():
            self.confirm(click.x, click.y)
            self.ticked = (click.x, click.y)

    def _prepare_step(self, reply, px, box) -> None:
        """This turn's step is known. It goes up with the first sound of its sentence (C1)."""
        with self.lock:
            if self.waiting_step is not None or self.shown_at is not None:
                return
            self.waiting_step = (reply, px, box)
            self.reading = reply.target == "read" and self.wait_change is not None
            if self.sounded:
                self._show_step(reply, px, box)

    def _on_sound(self, turn: int) -> None:
        """The voice's thread: her ears have the first sound of this turn's sentence."""
        with self.lock:
            if turn != self.turn or self._cancelled():
                return
            self.sounded = True
            if self.waiting_step is not None:
                self._show_step(*self.waiting_step)

    def _show_step(self, reply, px, box) -> None:
        """Once a turn: what she should look at, and the island's colour to match."""
        with self.lock:
            if self.shown_at is not None:
                return
            self.shown_at = time.monotonic()
            if self.reading and self.show_box:
                self.show_box(box, reply.caution)
            elif reply.target == "scroll" and self.wait_change and self.show_scroll:
                self.show_scroll(px)
            else:
                self.show(px[0], px[1], reply.caution)
            self._status("caution" if reply.caution else "reading" if self.reading else "turn")  # as the mark's colour
            self.on_screen.set()

    def _wait_shown(self) -> bool:
        """Until this turn's step is up. False: she asked something new first."""
        deadline = time.monotonic() + SOUND_WAIT_S
        while not self.on_screen.wait(0.05):
            if self._cancelled():
                return False
            if time.monotonic() >= deadline:   # no voice: the step goes up all the same
                with self.lock:
                    self._show_step(*self.waiting_step)
        return not self._cancelled()

    def _drop_step(self) -> None:
        """This turn ends without its step: a sound still to come must not put it up."""
        with self.lock:
            self.waiting_step = None
        if self.shown_at is not None:
            self.hide()

    def _screen_moved_on(self) -> bool:
        """C2: is the screen this turn's step is about gone? Checked once, just before the sentence is said."""
        if self.moved_on is None:
            self.moved_on = False
            if self.glance is not None and self.seen is not None and self.stale_run < MAX_STALE:
                ignore = list(self.own()) if self.own else []
                if self.ticked:
                    x, y = self.ticked
                    ignore.append((x - TICK_R, y - TICK_R, x + TICK_R, y + TICK_R))
                self.change = fresh.compare(self.seen, self.glance(), self.waiting_step[1], ignore)
                self.moved_on = self.change.stale
        return self.moved_on

    def _speak(self, text: str) -> None:
        if not self.spoken:
            if self.waiting_step is not None and self._screen_moved_on():
                return   # C2: not a word about a screen that has gone
            self.spoken = True
            self.stale_run = 0
            turn = self.turn
            self.say(f"{text} {READ_DONE}" if self.reading else text, lambda: self._on_sound(turn))

    def _look_again(self, question: str, heard: str | None):
        """C2: the screen moved on while the tutor was answering. Nothing is said: it looks again (founder 03/11).
        heard: the last sentence she heard in this task; None, nothing yet, and it asks afresh."""
        self.stale_run += 1
        self._drop_step()
        click = self.wait_click(self.asked_at, 0)   # she went ahead and clicked while it was answering
        if click is not None:
            self.clicked = click
            self._settle(click)
            acted = "click"
        else:
            self.pause(STILL_S)                     # a box that is coming up finishes first
            acted = "stale"
        if heard is None:
            return self._ask(question)
        return self._check(question, heard, True, acted)

    def _settle(self, click) -> str:
        self.pause(HIDE_PAUSE_S)
        return self.settle(click)

    def _click(self, reply, px) -> str | None:
        """Words and ring together, her click, a still screen. None: she stopped, or asked something new.
        STALE: the screen moved on before a word was said."""
        self._prepare_step(reply, px, None)
        self._speak(reply.say)
        if self.moved_on:
            return STALE
        click = self.wait_click(self.shown_at, CLICK_WAIT_S) if self._wait_shown() else None
        self.hide()
        if click is None or self._cancelled():
            return None  # she stopped, or asked something new; she can ask again any time
        self.clicked = click
        return self._settle(click)

    def _read(self, reply, px, box) -> tuple[str | None, str]:
        """A region to read. Returns (outcome, what she did); outcome None as in _click."""
        self._prepare_step(reply, px, box)
        self._speak(reply.say)
        if self.moved_on:
            return STALE, "read"
        if not self._wait_shown():
            self.hide()
            return None, "read"
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
        self._prepare_step(reply, px, None)   # her turn, not "Chờ trang tải" (founder 02/11)
        self._speak(reply.say)
        if self.moved_on:
            return STALE
        if not self._wait_shown():
            self.hide()
            return None
        self.pause(RING_FLIGHT_S)
        outcome = self.wait_change(SCROLL_WAIT_S, CHANGE_MIN, self._cancelled)
        self.hide()
        if self._cancelled() or outcome == "unchanged":
            return None
        self.pause(HIDE_PAUSE_S)
        return outcome

    def _ask(self, question: str):
        """The first turn of a new task."""
        self._status("thinking")
        img, state = self.look()
        self._turn_starts(img)
        return img, self.tutor.ask(question, self.encode(img), state, self.pointer, on_mark=self._early_mark,
                                   on_say=self._early_say, known=self.known)

    def run(self, question: str, max_steps: int = MAX_STEPS, last_say: str | None = None) -> list[Step]:
        """last_say: the task is being picked up again, this was the last thing the tutor said in it."""
        if last_say is None:
            img, reply = self._ask(question)
        else:
            if self.on_plan and self.plan:
                self.on_plan(self.plan, self.part)   # the card comes back before the tutor speaks
            img, reply = self._check(question, last_say, None, "resume")
        heard = last_say   # the last sentence she heard in this task
        outcome = None
        waits = 0
        while not self._cancelled():
            self._track(reply)
            if self._at_limit(max_steps) and not reply.goal_done and not reply.error:
                self._drop_step()
                break
            px = reply.point_px(img.size)
            self.steps.append(Step(len(self.steps) + 1, reply.say, px, reply.step_done, reply.goal_done, outcome,
                                   reply.latency_s, reply.error, reply.target,
                                   None if self.shown_at is None else round(self.shown_at - self.asked_at, 2)))
            self.part_steps += 1
            if self.save:
                self.save(len(self.steps), img, reply)
            if reply.error:
                self._drop_step()
                self._status("error")
                self.say("Mình chưa xem được màn hình. Bạn hỏi lại nhé.")
                break
            if reply.goal_done or px is None:
                self._drop_step()
                self._speak(reply.say)
                if not self._is_waiting(reply) or waits >= MAX_WAITS or self.wait_screen is None:
                    break  # done, or nothing to click: the sentence already says why or asks back
                # T6/T8 (02/11): a page or a file was still loading; the session used to stop here.
                waits += 1
                self._status("loading")
                outcome = self.wait_screen()
                if self._cancelled():
                    break
                heard = reply.say
                img, reply = self._check(question, reply.say, outcome != "unchanged")
                continue
            waits = 0
            if reply.target == "read" and self.wait_change:
                outcome, acted = self._read(reply, px, reply.box_px(img.size))
            elif reply.target == "scroll" and self.wait_change:
                outcome, acted = self._scroll(reply, px), "moved"
            else:
                outcome, acted = self._click(reply, px), "click"
            if self.change is not None:
                self.steps[-1].region, self.steps[-1].whole = self.change.region, self.change.whole
            if outcome == STALE and not self._cancelled():
                self.steps[-1].stale = True
                img, reply = self._look_again(question, heard)
                self._tick(reply)
                continue
            if outcome is None or self._cancelled():
                break
            heard = reply.say
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

    def say(text, on_sound=None):
        print(f"\nTutor: {text}", flush=True)
        if on_sound:
            on_sound()   # no voice here: the ring goes up as the words are printed

    def work():
        try:
            for left in range(args.delay, 0, -1):
                print(f"Bắt đầu sau {left} giây... chuyển sang cửa sổ cần hỏi.", flush=True)
                time.sleep(1)
            session = Session(
                tutor=tutor, look=look, encode=screen.png_data_url,
                show=lambda x, y, caution: bridge.point.emit(x, y, caution), hide=bridge.clear.emit,
                say=say, wait_click=clicks.wait,
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
