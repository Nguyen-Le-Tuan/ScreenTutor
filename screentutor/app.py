"""ScreenTutor, the whole MVP in one command.

  py -m screentutor.app          # Windows; Ctrl+C in the PowerShell window closes it

The user asks with the round button (the model notices when she stops talking;
a second press ends it early) or by holding Ctrl+Alt (talk while holding). The
tutor looks at the screen and the Windows state, points at one step and says
it, waits for her click and a still screen, checks the step, and goes on until
the task is done. A new question cancels the old one. The tutor never clicks or
types. Each step is kept in tutor_runs/<time>-app/ (gitignored).

What it is doing shows in the dynamic island at the top centre (A7, founder 02/11): its
colour and icon, her words and the tutor's as a chat, and the sound bars of her voice and
its own. A big task shows its parts there too (B2).
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import threading
import time
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageDraw

from . import conversation as conv
from .gesture import describe

# Facts about this machine sent with the state text. WPS: T6/T8 (02/11), the "Create PDF" button only asked to
# install WPS; founder: use File > Export > Create PDF/XPS. Zalo Temp: T5 X-1 (02/11), founder's observation.
MACHINE_NOTES = "\n".join([
    "- Nút tròn hình micro ở góc dưới bên phải và ô đen ở giữa mép trên màn hình là của chính tutor, "
    "không phải của app nào; không chỉ vào chúng.",
    "- Nút \"Create PDF\" của WPS trên thanh công cụ Word không dùng được trên máy này (bấm vào chỉ hiện hộp đòi "
    "cài WPS). Muốn xuất PDF thì dùng File > Export > Create PDF/XPS.",
    "- Bấm thẳng vào file trong tin nhắn Zalo thì Word mở một bản tạm chỉ đọc (Read-Only) trong thư mục Zalo Temp; "
    "sửa trên bản đó sẽ không vào file thật. Muốn sửa, người dùng phải quay lại Zalo tải file về một thư mục thật rồi "
    "mở bản đó; không sửa trên bản tạm.",
])
WAIT_GRACE_S = 5.0    # a loading page may stay blank this long before anything changes
PRE_ASK_S = 3.0       # B1b: she may point just before she presses the button or holds Ctrl+Alt
NOT_HEARD = "Mình chưa nghe rõ. Bạn hỏi lại nhé."
NO_MIC = "Mình chưa nghe được micro. Bạn kiểm tra lại micro nhé."
SETTINGS_POLL_MS = 2000
PEEK_S, PART_PEEK_S = 5.0, 3.0   # the island opens by itself: on a new plan, and on each new part


def masked(img: Image.Image, rects: list[tuple[int, int, int, int]]) -> Image.Image:
    """The screenshot with our own widgets blacked out, so their changing words never count as the screen moving."""
    if not rects:
        return img
    out = img.copy()
    d = ImageDraw.Draw(out)
    for r in rects:
        d.rectangle(r, fill="black")
    return out


def to_physical(box: tuple[int, int, int, int] | None, dpr: float) -> tuple[int, int, int, int] | None:
    """A logical (x, y, w, h) box to physical (x1, y1, x2, y2) pixels, as screenshots and clicks use."""
    if box is None:
        return None
    x, y, w, h = box
    return round(x * dpr), round(y * dpr), round((x + w) * dpr), round((y + h) * dpr)


def inside(box: tuple[int, int, int, int] | None, x: int, y: int) -> bool:
    return box is not None and box[0] <= x <= box[2] and box[1] <= y <= box[3]


def pointing(samples, size: tuple[int, int], own: list[tuple[int, int, int, int]]) -> str | None:
    """What her mouse said while she asked (B1b). The path over our own button and island does not count:
    with the round button the mouse rests there all the time she talks, and that points at nothing."""
    return describe([s for s in samples if not any(inside(r, s[1], s[2]) for r in own)], size)


def outcome_of(steps, cancelled: bool) -> str:
    """How a task ended, for the history: a new question cut it off, the tutor failed, or it is done."""
    if cancelled:
        return "interrupted"
    if steps and steps[-1].error:
        return "error"
    if steps and steps[-1].goal_done:
        return "done"
    return "stopped"


class Feed:
    """What the tutor does, turned into what the island and the button show (A7). Qt thread only.

    The session sets the state underneath (thinking, turn, caution, loading, done, idle,
    error); while a sentence is being spoken the island shows "speaking" on top of it, and
    goes back to that state when the voice stops. Each question is a new task in the chat.
    """

    def __init__(self, island, button=None, voice_meter=None, dpr: float = 1.0):
        self.island, self.button = island, button
        self.voice_meter = voice_meter
        self.mic_meter = None
        self.dpr = dpr
        self.glow = None               # (on) -> None: the light around the screen while the tutor looks
        self.flash = None              # () -> None: the green light when a task is done
        self.flashed = False
        self.task: conv.Task | None = None
        self.base = "idle"
        self.speaking = 0              # the token of the sentence being spoken, 0 when quiet

    def listen(self, mic_meter=None) -> None:
        self.task = conv.Task()
        self.mic_meter = mic_meter
        self.base, self.speaking = "listening", 0
        self._show()

    def hear(self, text: str) -> None:
        if self.task is None:
            self.task = conv.Task()
        self.task.hear(text)
        self.island.task_changed()

    def status(self, state: str) -> None:
        self.base = state
        self._show()

    def notice(self) -> None:
        """B4: the tutor speaks up by itself. A task of its own in the chat, in the caution colour."""
        self.task = conv.Task()
        self.base, self.speaking = "notice", 0
        self._show()

    def say_start(self, text: str, token: int) -> None:
        if self.task is None:
            self.task = conv.Task()
        self.task.say(text)
        self.speaking = token
        self._show()

    def say_end(self, token: int) -> None:
        if token == self.speaking:  # an older sentence that was cut off must not end the new one
            self.speaking = 0
            self._show()

    def plan(self, parts: list[str], part: int) -> None:
        """The parts of a big task and the one being done, from 1: the island's card and "Phần k/n"."""
        if self.task is None:
            self.task = conv.Task()
        first = not any(m.plan for m in self.task.messages)
        self.task.plan(parts, max(part - 1, 0))
        self.island.task_changed()
        self.island.peek(PEEK_S if first else PART_PEEK_S)

    def ring(self, x: int, y: int, caution: bool) -> None:
        from PySide6.QtCore import QPointF

        self.island.set_avoid(QPointF(x / self.dpr, y / self.dpr))

    def frame(self, x1: int, y1: int, x2: int, y2: int) -> None:
        from PySide6.QtCore import QPointF, QRectF

        d = self.dpr
        self.island.set_avoid(QPointF((x1 + x2) / 2 / d, (y1 + y2) / 2 / d), QRectF(x1 / d, y1 / d, (x2 - x1) / d, (y2 - y1) / d))

    def unring(self) -> None:
        self.island.set_avoid(None)

    def recent(self, items: list[tuple[str, str]]) -> None:
        """Her latest earlier tasks, (when, title), for the pinned island's bottom row."""
        self.island.recent = list(items)
        self.island.update()

    def collapse(self) -> None:
        """A new question: a pinned island closes so it does not cover what she asks about."""
        if self.island.mode != "collapsed":
            self.island.set_mode("collapsed")

    def shown(self) -> str:
        return "speaking" if self.speaking else self.base

    def _show(self) -> None:
        state = self.shown()
        if self.glow and state != "thinking":
            self.glow(False)  # it never outlasts the looking; look() turns it on after the screenshot
        if self.flash and state == "done" and not self.flashed:
            self.flash()   # once a task: "done" comes back after the last sentence has been spoken
        self.flashed = state == "done" or (self.flashed and state == "speaking")
        source = None
        if state == "speaking" and self.voice_meter is not None:
            source = lambda m=self.voice_meter: m.value  # noqa: E731
        elif state == "listening" and self.mic_meter is not None:
            source = lambda m=self.mic_meter: m.value  # noqa: E731
        self.island.level_source = source
        self.island.set_state(state, self.task)
        if self.button is not None:
            self.button.level_source = source
            self.button.set_state(state)


def main(argv=None) -> None:
    if sys.platform != "win32":
        sys.exit("Chỉ chạy trên Windows (cần màn hình, chuột, micro và loa thật).")

    import signal

    from PySide6.QtCore import QObject, QPointF, QTimer, Signal
    from PySide6.QtGui import QColor, QGuiApplication
    from PySide6.QtWidgets import QApplication

    from . import guards, screen, winstate
    from . import settings as settings_mod
    from .history import History, when_label
    from .inputs import Click, Hold, Trail, watch
    from .island import Island
    from .listen import Mic, _api_key, listen
    from .overlay import Overlay, _win_topmost
    from .session import ClickBox, Session
    from .speak import Speaker
    from .state import format_vi, take_snapshot, zalo_temp_dir
    from .still import wait_change, wait_until_settled
    from .tutor import Tutor
    from .ui import AskButton

    signal.signal(signal.SIGINT, signal.SIG_DFL)
    app = QApplication(sys.argv[:1])
    qscreen = QGuiApplication.primaryScreen()
    dpr = qscreen.devicePixelRatio()
    screen_size = to_physical((0, 0, qscreen.geometry().width(), qscreen.geometry().height()), dpr)[2:]
    overlay, button, island = Overlay(), AskButton(), Island()

    def colour(text: str) -> QColor:
        c = QColor(text)
        return c if c.isValid() else QColor(0, 0, 0)

    prefs = settings_mod.load()
    overlay.glow_enabled = prefs.edge_glow
    island.base = colour(prefs.island_color)
    island.color, island.show_button = prefs.island_color, prefs.show_button
    button.setVisible(prefs.show_button)
    island.show()

    key = _api_key()
    tutor = Tutor(key)
    speaker = Speaker()
    threading.Thread(target=speaker.load, daemon=True).start()
    threading.Thread(target=tutor.warm, daemon=True).start()  # T8 (02/11): the first answer took 8.8 s
    out = Path("tutor_runs") / (datetime.now().strftime("%Y%m%d-%H%M%S") + "-app")
    out.mkdir(parents=True, exist_ok=True)
    feed = Feed(island, button, speaker.meter, dpr)
    feed.glow, feed.flash = overlay.glow, overlay.flash

    def keep_ours_on_top() -> None:  # the darkened screen must not cover the button and the island
        for widget in (island, button):
            if widget.isVisible():
                _win_topmost(widget)

    overlay.after_topmost = keep_ours_on_top
    history = History()  # A8: C:\ScreenTutor\history, one file per task, no pictures or sound

    def recent_items() -> list[tuple[str, str]]:
        now = time.time()
        return [(when_label(r.started_at, now), r.title) for r in history.recent(2)]

    feed.recent(recent_items())

    class Bridge(QObject):  # worker threads talk to the widgets only through these
        point = Signal(int, int, bool)
        frame = Signal(int, int, int, int, bool)
        hint = Signal(int, int)
        tick = Signal(int, int)
        glow = Signal(bool)
        clear = Signal()
        call = Signal(str, object)

    bridge = Bridge()

    def on_point(x, y, caution):
        overlay.point_at(x, y, caution=caution)
        feed.ring(x, y, caution)

    def on_clear():
        overlay.clear()
        feed.unring()

    def on_frame(x1, y1, x2, y2, caution):
        overlay.focus_on(x1, y1, x2, y2, caution=caution)
        feed.frame(x1, y1, x2, y2)

    def on_hint(x, y):
        overlay.scroll_hint(x, y)
        feed.ring(x, y, False)

    bridge.point.connect(on_point)
    bridge.frame.connect(on_frame)
    bridge.hint.connect(on_hint)
    bridge.tick.connect(overlay.tick_at)
    bridge.glow.connect(overlay.glow)
    bridge.clear.connect(on_clear)
    bridge.call.connect(lambda name, args: getattr(feed, name)(*args))
    post = lambda name, *args: bridge.call.emit(name, args)  # noqa: E731

    watch_prefs = settings_mod.Watch()

    def reload_prefs():
        new = watch_prefs.poll()
        if new is not None:  # founder, 02/11: switch the button off without a code change
            button.setVisible(new.show_button)
            button_box[0] = physical(button)
            island.base = colour(new.island_color)
            island.color, island.show_button = new.island_color, new.show_button
            overlay.glow_enabled = new.edge_glow
            island.update()

    def save_prefs(**change) -> None:
        """What she picked in the pinned island goes into settings.json, as if typed there."""
        current = settings_mod.load()
        for k, v in change.items():
            setattr(current, k, v)
        settings_mod.save(current)

    def on_button_toggle(show: bool) -> None:
        save_prefs(show_button=show)
        button.setVisible(show)
        button_box[0] = physical(button)

    def on_clear() -> None:
        n = history.clear()
        print(f"Đã xoá {n} việc trong lịch sử.", flush=True)

    island.on_color = lambda c: save_prefs(island_color=c)
    island.on_button_toggle = on_button_toggle
    island.on_clear = on_clear

    prefs_timer = QTimer()
    prefs_timer.timeout.connect(reload_prefs)
    prefs_timer.start(SETTINGS_POLL_MS)

    def physical(widget) -> tuple[int, int, int, int] | None:
        if not widget.isVisible():
            return None
        g = widget.geometry()
        return to_physical((g.x(), g.y(), g.width(), g.height()), dpr)

    button_box = [physical(button)]  # refreshed on the Qt thread; read by the worker threads

    def own_rects() -> list[tuple[int, int, int, int]]:
        return [r for r in (button_box[0], to_physical(island.cover, dpr), to_physical(overlay.cover, dpr))
                if r is not None]

    def grab_own_masked():
        return masked(screen.grab(), own_rects())

    def on_own_widget(click: Click) -> bool:
        """Clicks on the button, or on the open island, are not her step."""
        return inside(button_box[0], click.x, click.y) or inside(to_physical(island.takes_clicks, dpr), click.x, click.y)

    def look():
        img = screen.grab()
        bridge.glow.emit(True)  # only now: it must not be in the picture
        return img, format_vi(take_snapshot()) + "\n" + MACHINE_NOTES

    said = [0]

    def say(text: str) -> None:
        """Speak without blocking the session; a click or a new question cuts it off."""
        said[0] += 1
        token = said[0]

        def run():
            try:
                speaker.speak(text)
            finally:
                post("say_end", token)
        speaker.stop()
        post("say_start", text, token)  # before the session's next state, so the island never flickers
        threading.Thread(target=run, daemon=True).start()

    def save(n, img, reply):
        stamp = time.strftime("%H%M%S")
        img.save(out / f"{stamp}_step{n:02d}.png")
        data = {k: v for k, v in asdict(reply).items() if k != "raw"}
        (out / f"{stamp}_step{n:02d}.json").write_text(json.dumps(data, ensure_ascii=False, indent=2),
                                                       encoding="utf-8")

    current = {"cancel": None, "stop": None, "mode": None, "listening": False, "thread": None}
    clicks = ClickBox()
    trail = Trail()

    def question(mode: str, stop: threading.Event, cancel: threading.Event, asked_at: float) -> None:
        current["listening"] = True
        try:
            mic = Mic()
        except Exception as e:  # no microphone, or Windows privacy settings block it
            print(f"Không mở được micro: {e}", flush=True)
            current["listening"] = False
            post("status", "error")
            say(NO_MIC)
            return
        post("listen", mic.meter)
        try:
            heard = asyncio.run(listen(key, mic.frames(stop), mode, stop=stop, on_partial=lambda t: post("hear", t)))
        finally:
            stop.set()
            mic.close()
            current["listening"] = False
        print(f"Nghe được: {heard.text!r}" + (f" (lỗi: {heard.error})" if heard.error else ""), flush=True)
        if cancel.is_set():
            return
        if not heard.text:
            if heard.partial:
                post("hear", heard.partial)
            post("status", "error")
            say(NOT_HEARD)
            return
        post("hear", heard.text)
        pointer = pointing(trail.between(asked_at - PRE_ASK_S, time.monotonic()), screen_size, own_rects())
        print(f"Chuột lúc hỏi: {pointer or 'không chỉ vào đâu'}", flush=True)
        rec = history.start(heard.text)

        def save_step(n, img, reply):
            save(n, img, reply)
            history.add_step(rec, reply.say, reply.element, reply.step_done, reply.goal_done, reply.caution,
                             reply.latency_s)

        def on_plan(plan, part):
            post("plan", plan, part)
            history.set_plan(rec, plan, part)

        def wait_click(since, timeout_s):
            click = clicks.wait(since, timeout_s, cancel=cancel, ignore=on_own_widget)
            if click is not None:
                speaker.stop()  # she has acted; no need to finish the sentence
            return click

        session = Session(
            tutor=tutor, look=look, encode=screen.png_data_url,
            show=lambda x, y, caution: bridge.point.emit(x, y, caution), hide=bridge.clear.emit, say=say,
            wait_click=wait_click,
            settle=lambda c: wait_until_settled(c.t, grab_own_masked)[0],
            wait_screen=lambda: wait_until_settled(time.monotonic(), grab_own_masked, grace_s=WAIT_GRACE_S)[0],
            wait_change=lambda timeout_s, min_change, stop: wait_change(grab_own_masked, timeout_s, min_change, stop),
            show_box=lambda box, caution: bridge.frame.emit(*box, caution),
            show_scroll=lambda px: bridge.hint.emit(*px),
            confirm=bridge.tick.emit,
            save=save_step, status=lambda st: post("status", st), cancel=cancel, pointer=pointer, on_plan=on_plan)
        steps = session.run(heard.text)
        history.finish(rec, outcome_of(steps, cancel.is_set()))
        post("recent", recent_items())
        for s in steps:
            print(f"  bước {s.n} ({s.target or 'click'}): {s.say} | trỏ {s.point_px} | sau cú bấm {s.settle or '—'} | "
                  f"bước xong {s.step_done} | việc xong {s.goal_done} | {s.latency_s:.1f} s", flush=True)

    def ask(mode: str) -> None:
        if current["listening"] and current["mode"] == "ENDPOINTING" and mode == "ENDPOINTING":
            current["stop"].set()  # a second press on the button: she has finished talking
            return
        if current["cancel"] is not None:
            current["cancel"].set()  # a new question replaces the old one
            current["stop"].set()
        speaker.stop()
        bridge.clear.emit()
        post("collapse")  # ask() also runs on the input thread (Ctrl+Alt): widgets only via the bridge
        current.update(cancel=threading.Event(), stop=threading.Event(), mode=mode)
        current["thread"] = threading.Thread(target=question, args=(mode, current["stop"], current["cancel"],
                                                                    time.monotonic()), daemon=True)
        current["thread"].start()

    def on_click_qt(x: int, y: int) -> None:
        button_box[0] = physical(button)
        island.global_click(QPointF(x / dpr, y / dpr))  # a click outside closes the pinned island

    class Clicks(QObject):
        at = Signal(int, int)

    click_bridge = Clicks()
    click_bridge.at.connect(on_click_qt)

    def on_input(event) -> None:
        clicks.put(event)
        if isinstance(event, Click):
            click_bridge.at.emit(event.x, event.y)
        if isinstance(event, Hold):
            if event.started:
                ask("PUSH_TO_TALK")
            elif current["mode"] == "PUSH_TO_TALK" and current["stop"] is not None:
                current["stop"].set()  # Ctrl+Alt let go: the question is complete

    def watch_traps() -> None:
        """B4: reads the window in front and one folder, on this machine only. Waits while the tutor is busy,
        so it never talks over a task; what it noticed in the meantime it says when the task is over."""
        guard = guards.ZaloCopy()
        folder = zalo_temp_dir(os.environ.get("TEMP", ""))
        while folder is not None and not stop_inputs.wait(guards.EVERY_S):
            thread = current["thread"]
            if (thread is not None and thread.is_alive()) or feed.speaking:
                continue
            try:
                hwnd = winstate.foreground_hwnd()
                copy = guard.check(winstate.describe(hwnd) if hwnd else None, guards.temp_copies(folder), time.time())
            except Exception as e:  # a sensor that fails must never take the app down
                print(f"Không đọc được cửa sổ để gác: {e}", flush=True)
                continue
            if copy is not None:
                post("notice")
                say(guards.sentence(button_box[0] is not None))

    button.clicked.connect(lambda: ask("ENDPOINTING"))
    stop_inputs = threading.Event()
    threading.Thread(target=watch, args=(on_input, stop_inputs), kwargs={"trail": trail}, daemon=True).start()
    threading.Thread(target=watch_traps, daemon=True).start()
    print("ScreenTutor đang chạy. Bấm nút tròn hoặc giữ Ctrl+Alt rồi nói. Ctrl+C ở đây để tắt.", flush=True)
    try:
        app.exec()
    finally:
        stop_inputs.set()
        tutor.close()


if __name__ == "__main__":
    main()
