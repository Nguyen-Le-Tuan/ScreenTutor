"""The coloured pointer drawn over every window (MVP step 3, Decision 4b: colourful illustration).

A frameless, always-on-top, click-through, transparent window covers the primary
screen, taskbar included. Given a point in screenshot pixels (physical screen
pixels), a hollow ring glides there from the mouse cursor, opens up and pulses,
so the user sees where to click, can still read what is under the ring, and the
click still reaches the app underneath.

  py -m screentutor.overlay --follow-mouse            # Windows: the ring should sit on the mouse tip
  py -m screentutor.overlay --at 960 540 --seconds 5  # Windows: point at a physical pixel
  python -m screentutor.overlay --preview case.png --at 960 540 --out preview.png   # any OS, no window
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field

from PySide6.QtCore import QElapsedTimer, QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QCursor, QGuiApplication, QImage, QPainter, QPen

COLOR = QColor(255, 69, 58)          # red-orange: stands out on white Word pages, Zalo blue and the dark taskbar
HALO = QColor(255, 255, 255, 230)    # white edge so the ring reads on dark and light backgrounds alike
FILL_ALPHA = 40                      # faint tint inside: the button or word under the ring stays readable
TRAVEL_S = 0.45                      # glide from the mouse cursor to the target
PULSE_S = 1.2                        # one pulse cycle
TRAVEL_R, MARK_R = 12.0, 24.0        # ring radius while gliding and once arrived (logical px)
PULSE_MAX = 52.0
PULSE_ALPHA = 200
STROKE = 4.0
TOPMOST_EVERY_MS = 500


def to_logical(px: float, py: float, dpr: float, origin: tuple[float, float] = (0.0, 0.0)) -> tuple[float, float]:
    """Screenshot (physical) pixels -> Qt logical coordinates. At 125% scaling, 1920x1080 -> 1536x864."""
    return origin[0] + px / dpr, origin[1] + py / dpr


def ease_out(t: float) -> float:
    t = min(max(t, 0.0), 1.0)
    return 1 - (1 - t) ** 3


@dataclass
class Frame:
    x: float
    y: float
    radius: float
    arrived: bool
    pulses: list[tuple[float, int]] = field(default_factory=list)  # (radius, alpha)


def frame_at(t: float, start: tuple[float, float], target: tuple[float, float]) -> Frame:
    """The ring t seconds after point_at(): gliding and opening up, then pulsing in place."""
    k = ease_out(t / TRAVEL_S)
    x = start[0] + (target[0] - start[0]) * k
    y = start[1] + (target[1] - start[1]) * k
    radius = TRAVEL_R + (MARK_R - TRAVEL_R) * k
    if t < TRAVEL_S:
        return Frame(x, y, radius, arrived=False)
    phase = ((t - TRAVEL_S) % PULSE_S) / PULSE_S
    pulses = []
    for offset in (0.0, 0.5):
        q = (phase + offset) % 1.0
        pulses.append((MARK_R + (PULSE_MAX - MARK_R) * q, round(PULSE_ALPHA * (1 - q))))
    return Frame(x, y, radius, arrived=True, pulses=sorted(pulses))


def paint_frame(p: QPainter, f: Frame, scale: float = 1.0) -> None:
    p.setRenderHint(QPainter.Antialiasing)
    c = QPointF(f.x, f.y)
    p.setBrush(Qt.NoBrush)
    for radius, alpha in f.pulses:
        pulse = QColor(COLOR)
        pulse.setAlpha(alpha)
        p.setPen(QPen(pulse, 3 * scale))
        p.drawEllipse(c, radius * scale, radius * scale)
    r = f.radius * scale
    fill = QColor(COLOR)
    fill.setAlpha(FILL_ALPHA)
    p.setPen(QPen(HALO, (STROKE + 3) * scale))
    p.setBrush(fill)
    p.drawEllipse(c, r, r)
    p.setPen(QPen(COLOR, STROKE * scale))
    p.setBrush(Qt.NoBrush)
    p.drawEllipse(c, r, r)


class Overlay:
    """Owns the click-through window. Call from the Qt (main) thread."""

    def __init__(self, screen=None):
        from PySide6.QtWidgets import QWidget

        class _Canvas(QWidget):
            def paintEvent(inner, _event):  # noqa: N805
                if self._target is None:
                    return
                p = QPainter(inner)
                paint_frame(p, self._frame())
                p.end()

        self._screen = screen or QGuiApplication.primaryScreen()
        self._w = _Canvas(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
                          | Qt.WindowTransparentForInput | Qt.WindowDoesNotAcceptFocus)
        self._w.setAttribute(Qt.WA_TranslucentBackground)
        self._w.setAttribute(Qt.WA_ShowWithoutActivating)
        self._w.setAttribute(Qt.WA_TransparentForMouseEvents)
        self._w.setGeometry(self._screen.geometry())  # full screen, taskbar included
        self._target = None
        self._start = (0.0, 0.0)
        self._until_ms = None
        self._clock = QElapsedTimer()
        self._last_topmost = 0
        self._timer = QTimer(self._w)
        self._timer.setInterval(16)
        self._timer.timeout.connect(self._tick)

    def point_at(self, px: float, py: float, seconds: float | None = None) -> None:
        """px, py: pixels of a screenshot of this screen (physical pixels)."""
        geo = self._screen.geometry()
        x, y = to_logical(px, py, self._screen.devicePixelRatio())
        if self._target is not None:
            f = self._frame()
            self._start = (f.x, f.y)
        else:
            cursor = QCursor.pos(self._screen)
            self._start = (cursor.x() - geo.x(), cursor.y() - geo.y())
        self._target = (x, y)
        self._clock.restart()
        self._until_ms = None if seconds is None else seconds * 1000
        self._w.show()
        _win_harden(self._w)
        self._timer.start()

    def clear(self) -> None:
        self._target = None
        self._timer.stop()
        self._w.hide()

    def _frame(self) -> Frame:
        return frame_at(self._clock.elapsed() / 1000, self._start, self._target)

    def _tick(self) -> None:
        elapsed = self._clock.elapsed()
        if self._until_ms is not None and elapsed >= self._until_ms:
            self.clear()
            return
        if elapsed - self._last_topmost >= TOPMOST_EVERY_MS or elapsed < self._last_topmost:
            self._last_topmost = elapsed
            _win_topmost(self._w)
        self._w.update()


def _win_harden(widget) -> None:
    """Belt and braces on Windows: never take focus, never take clicks, no taskbar button."""
    if sys.platform != "win32":
        return
    import ctypes

    GWL_EXSTYLE = -20
    WS_EX_TRANSPARENT, WS_EX_TOOLWINDOW, WS_EX_LAYERED, WS_EX_NOACTIVATE = 0x20, 0x80, 0x80000, 0x08000000
    user32 = ctypes.windll.user32
    user32.GetWindowLongW.restype = ctypes.c_long
    hwnd = ctypes.c_void_p(int(widget.winId()))
    style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
    user32.SetWindowLongW(hwnd, GWL_EXSTYLE,
                          style | WS_EX_TRANSPARENT | WS_EX_TOOLWINDOW | WS_EX_LAYERED | WS_EX_NOACTIVATE)
    _win_topmost(widget)


def _win_topmost(widget) -> None:
    """Stay above the taskbar and windows raised after us, without stealing focus."""
    if sys.platform != "win32":
        return
    import ctypes

    HWND_TOPMOST = ctypes.c_void_p(-1)
    SWP_NOSIZE, SWP_NOMOVE, SWP_NOACTIVATE = 0x1, 0x2, 0x10
    ctypes.windll.user32.SetWindowPos(ctypes.c_void_p(int(widget.winId())), HWND_TOPMOST, 0, 0, 0, 0,
                                      SWP_NOSIZE | SWP_NOMOVE | SWP_NOACTIVATE)


def render_preview(image_path: str, px: float, py: float, t: float = TRAVEL_S + 0.3, scale: float = 1.25) -> QImage:
    """The pointer painted onto a screenshot, as it looks t seconds after point_at(). No window needed.

    The screenshot is in physical pixels, so sizes are multiplied by the display scale (125% on mom's laptop).
    """
    img = QImage(image_path).convertToFormat(QImage.Format_ARGB32)
    p = QPainter(img)
    paint_frame(p, frame_at(t, (px, py), (px, py)), scale)
    p.end()
    return img


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(prog="python -m screentutor.overlay")
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--follow-mouse", action="store_true",
                      help="Windows: mỗi 2 giây chỉ vào đầu con trỏ chuột, để kiểm vòng có nằm đúng chỗ không")
    mode.add_argument("--preview", metavar="ẢNH", help="vẽ con trỏ lên một ảnh màn hình có sẵn, không mở cửa sổ")
    ap.add_argument("--at", nargs=2, type=float, metavar=("X", "Y"), help="toạ độ pixel trên ảnh chụp màn hình")
    ap.add_argument("--seconds", type=float, default=20, help="tự tắt sau bấy nhiêu giây")
    ap.add_argument("--out", default="overlay_preview.png", help="file ảnh ra (dùng với --preview)")
    args = ap.parse_args(argv)
    if not (args.follow_mouse or args.preview or args.at):
        ap.error("cần --follow-mouse, --at X Y, hoặc --preview ẢNH --at X Y")

    if args.preview:
        if not args.at:
            sys.exit("--preview cần --at X Y")
        app = QGuiApplication.instance() or QGuiApplication(sys.argv[:1])
        render_preview(args.preview, *args.at).save(args.out)
        print(f"Đã lưu {args.out}")
        del app
        return

    import signal

    from PySide6.QtWidgets import QApplication

    signal.signal(signal.SIGINT, signal.SIG_DFL)  # Ctrl+C closes it even while Qt runs
    app = QApplication.instance() or QApplication(sys.argv[:1])
    overlay = Overlay()
    if args.at:
        overlay.point_at(*args.at)
    if args.follow_mouse:
        screen = QGuiApplication.primaryScreen()
        dpr = screen.devicePixelRatio()

        def follow():
            pos = QCursor.pos(screen)
            overlay.point_at(pos.x() * dpr, pos.y() * dpr)
            print(f"Chuột ở ({pos.x() * dpr:.0f}, {pos.y() * dpr:.0f}) pixel thật; tỉ lệ màn hình {dpr}")

        follow()
        timer = QTimer()
        timer.timeout.connect(follow)
        timer.start(2000)
    print(f"Lớp phủ đang chạy, tự tắt sau {args.seconds:.0f} giây (Ctrl+C trong cửa sổ lệnh để tắt sớm).")
    QTimer.singleShot(round(args.seconds * 1000), app.quit)
    app.exec()


if __name__ == "__main__":
    main()
