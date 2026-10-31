"""ScreenTutor, the whole MVP in one command.

  py -m screentutor.app          # Windows; Ctrl+C in the PowerShell window closes it

The user asks with the "Hỏi" button (the model notices when she stops talking;
a second press ends it early) or by holding Ctrl+Alt (talk while holding). The
tutor looks at the screen and the Windows state, points at one step and says
it, waits for her click and a still screen, checks the step, and goes on until
the task is done. A new question cancels the old one. The tutor never clicks or
types. Each step is kept in tutor_runs/<time>-app/ (gitignored).
"""

from __future__ import annotations

import asyncio
import json
import sys
import threading
import time
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageDraw

OWN_WIDGETS_NOTE = ("- Nút \"Hỏi\" ở góc dưới bên phải và ô chữ đen ở giữa mép trên màn hình là của chính tutor, "
                    "không phải của app nào; không chỉ vào chúng.")
NOT_HEARD = "Mình chưa nghe rõ. Bạn hỏi lại nhé."
ISLAND_MASK_H = 160   # logical px at the top centre kept out of the stillness check (the island opens up there)


def masked(img: Image.Image, rects: list[tuple[int, int, int, int]]) -> Image.Image:
    """The screenshot with our own widgets blacked out, so their changing words never count as the screen moving."""
    if not rects:
        return img
    out = img.copy()
    d = ImageDraw.Draw(out)
    for r in rects:
        d.rectangle(r, fill="black")
    return out


def main(argv=None) -> None:
    if sys.platform != "win32":
        sys.exit("Chỉ chạy trên Windows (cần màn hình, chuột, micro và loa thật).")

    import signal

    from PySide6.QtCore import QObject, Signal
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtWidgets import QApplication

    from . import screen
    from .inputs import Click, Hold, watch
    from .listen import Mic, _api_key, listen
    from .overlay import Overlay
    from .session import ClickBox, Session
    from .speak import Speaker
    from .state import format_vi, take_snapshot
    from .still import wait_until_settled
    from .tutor import Tutor
    from .ui import ISLAND_W_OPEN, AskButton, Island

    signal.signal(signal.SIGINT, signal.SIG_DFL)
    app = QApplication(sys.argv[:1])
    qscreen = QGuiApplication.primaryScreen()
    dpr = qscreen.devicePixelRatio()
    overlay, button, island = Overlay(), AskButton(), Island()
    button.show()
    island.show()

    key = _api_key()
    tutor = Tutor(key)
    speaker = Speaker()
    threading.Thread(target=speaker.load, daemon=True).start()
    out = Path("tutor_runs") / (datetime.now().strftime("%Y%m%d-%H%M%S") + "-app")
    out.mkdir(parents=True, exist_ok=True)

    class Bridge(QObject):  # worker threads talk to the widgets only through these
        point = Signal(int, int)
        clear = Signal()
        state = Signal(str, object)

    bridge = Bridge()
    bridge.point.connect(lambda x, y: overlay.point_at(x, y))
    bridge.clear.connect(overlay.clear)

    def on_state(state, text):
        button.set_state("idle" if state == "waiting" else state)
        island.set_state("idle" if state == "waiting" else state, text)

    bridge.state.connect(on_state)
    show_state = lambda state, text=None: bridge.state.emit(state, text)  # noqa: E731

    def physical(widget) -> tuple[int, int, int, int]:
        g = widget.geometry()
        return round(g.left() * dpr), round(g.top() * dpr), round((g.right() + 1) * dpr), round((g.bottom() + 1) * dpr)

    def own_rects() -> list[tuple[int, int, int, int]]:
        top = qscreen.geometry()
        cx = top.width() / 2
        band = (round((cx - ISLAND_W_OPEN / 2) * dpr), 0, round((cx + ISLAND_W_OPEN / 2) * dpr),
                round(ISLAND_MASK_H * dpr))
        return [physical(button), band]

    def on_button(click: Click) -> bool:
        x1, y1, x2, y2 = physical(button)
        return x1 <= click.x <= x2 and y1 <= click.y <= y2

    def look():
        return screen.grab(), format_vi(take_snapshot()) + "\n" + OWN_WIDGETS_NOTE

    def say(text: str) -> None:
        """Speak without blocking the session; a click or a new question cuts it off."""
        def run():
            show_state("speaking")
            speaker.speak(text)
            show_state("waiting")
        speaker.stop()
        threading.Thread(target=run, daemon=True).start()

    def save(n, img, reply):
        stamp = time.strftime("%H%M%S")
        img.save(out / f"{stamp}_step{n:02d}.png")
        data = {k: v for k, v in asdict(reply).items() if k != "raw"}
        (out / f"{stamp}_step{n:02d}.json").write_text(json.dumps(data, ensure_ascii=False, indent=2),
                                                       encoding="utf-8")

    current = {"cancel": None, "stop": None, "mode": None, "listening": False}
    clicks = ClickBox()

    def question(mode: str, stop: threading.Event, cancel: threading.Event) -> None:
        current["listening"] = True
        show_state("listening", "")
        try:
            mic = Mic()
        except Exception as e:  # no microphone, or Windows privacy settings block it
            print(f"Không mở được micro: {e}", flush=True)
            current["listening"] = False
            say("Mình chưa nghe được micro. Bạn kiểm tra lại micro nhé.")
            return
        try:
            heard = asyncio.run(listen(key, mic.frames(stop), mode, stop=stop,
                                       on_partial=lambda t: show_state("listening", t)))
        finally:
            stop.set()
            mic.close()
            current["listening"] = False
        print(f"Nghe được: {heard.text!r}" + (f" (lỗi: {heard.error})" if heard.error else ""), flush=True)
        if cancel.is_set():
            return
        if not heard.text:
            show_state("speaking", heard.partial or "")
            say(NOT_HEARD)
            return
        show_state("thinking", heard.text)

        def wait_click(since, timeout_s):
            click = clicks.wait(since, timeout_s, cancel=cancel, ignore=on_button)
            if click is not None:
                speaker.stop()  # she has acted; no need to finish the sentence
            return click

        session = Session(
            tutor=tutor, look=look, encode=screen.png_data_url,
            show=lambda x, y: bridge.point.emit(x, y), hide=bridge.clear.emit, say=say,
            wait_click=wait_click,
            settle=lambda c: wait_until_settled(c.t, lambda: masked(screen.grab(), own_rects()))[0],
            save=save, status=lambda st: show_state(st), cancel=cancel)
        steps = session.run(heard.text)
        for s in steps:
            print(f"  bước {s.n}: {s.say} | trỏ {s.point_px} | sau cú bấm {s.settle or '—'} | "
                  f"bước xong {s.step_done} | việc xong {s.goal_done} | {s.latency_s:.1f} s", flush=True)
        if not cancel.is_set():
            show_state("waiting")

    def ask(mode: str) -> None:
        if current["listening"] and current["mode"] == "ENDPOINTING" and mode == "ENDPOINTING":
            current["stop"].set()  # a second press on Hỏi: she has finished talking
            return
        if current["cancel"] is not None:
            current["cancel"].set()  # a new question replaces the old one
            current["stop"].set()
        speaker.stop()
        bridge.clear.emit()
        current.update(cancel=threading.Event(), stop=threading.Event(), mode=mode)
        threading.Thread(target=question, args=(mode, current["stop"], current["cancel"]), daemon=True).start()

    def on_input(event) -> None:
        clicks.put(event)
        if isinstance(event, Hold):
            if event.started:
                ask("PUSH_TO_TALK")
            elif current["mode"] == "PUSH_TO_TALK" and current["stop"] is not None:
                current["stop"].set()  # Ctrl+Alt let go: the question is complete

    button.clicked.connect(lambda: ask("ENDPOINTING"))
    stop_inputs = threading.Event()
    threading.Thread(target=watch, args=(on_input, stop_inputs), daemon=True).start()
    print("ScreenTutor đang chạy. Bấm nút \"Hỏi\" hoặc giữ Ctrl+Alt rồi nói. Ctrl+C ở đây để tắt.", flush=True)
    try:
        app.exec()
    finally:
        stop_inputs.set()
        tutor.close()


if __name__ == "__main__":
    main()
