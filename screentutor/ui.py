"""The "Hỏi" button (MVP step 5, Decisions 4a-4c; A5, founder 02/11).

A round microphone at the bottom right, just above the taskbar, always on top, with no
words: every state lives in the dynamic island (island.py), and the button's ring only takes
the island's colour. Black at 80%, fully black under the mouse. Clicking it never takes the
focus away from the app she works in. settings.json can switch it off (show_button) without a
code change; Ctrl+Alt still asks.

  python -m screentutor.ui --demo                             # the button, cycling through the states
  python -m screentutor.ui --preview OUT.png --on case.png    # every state drawn onto a screenshot
"""

from __future__ import annotations

import argparse
import math
import sys

from PySide6.QtCore import QElapsedTimer, QPointF, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QGuiApplication, QPainter, QPen
from PySide6.QtWidgets import QWidget

from .island import STYLE
from .overlay import _win_harden

MARGIN = 16                 # logical px from the screen edge / taskbar
BUTTON_D = 46               # the round button's diameter
GLOW = 10                   # room around it for the listening halo
FLAGS = Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool | Qt.WindowDoesNotAcceptFocus


class AskButton(QWidget):
    clicked = Signal()

    def __init__(self, screen=None):
        super().__init__(None, FLAGS)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setCursor(Qt.PointingHandCursor)
        self._screen = screen or QGuiApplication.primaryScreen()
        self.state = "idle"
        self.hover = False
        self.level: float | None = None
        self.level_source = None   # A7: the mic or voice Meter's value, read at each frame
        self._clock = QElapsedTimer()
        self._clock.start()
        self._timer = QTimer(self)
        self._timer.setInterval(33)
        self._timer.timeout.connect(self.update)
        self._place()

    def _place(self) -> None:
        area = self._screen.availableGeometry()  # above the taskbar
        side = BUTTON_D + 2 * GLOW
        self.setFixedSize(QSize(side, side))
        self.move(area.right() - side - MARGIN + GLOW, area.bottom() - side - MARGIN + GLOW)

    def set_state(self, state: str) -> None:
        self.state = state if state in STYLE else "idle"
        self._timer.start() if self.state not in ("idle", "done") else self._timer.stop()
        self.update()

    def set_level(self, level: float | None) -> None:
        self.level = level

    def showEvent(self, event):
        super().showEvent(event)
        _win_harden(self, click_through=False)

    def enterEvent(self, event):
        self.hover = True
        self.update()

    def leaveEvent(self, event):
        self.hover = False
        self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()

    def paintEvent(self, _event):
        p = QPainter(self)
        level = self.level_source() if self.level_source is not None else self.level
        paint_button(p, QRectF(self.rect()), self.state, self._clock.elapsed() / 1000, self.hover, level)
        p.end()


def paint_button(p: QPainter, bounds: QRectF, state: str, t: float, hover: bool = False,
                 level: float | None = None) -> None:
    color = STYLE.get(state, STYLE["idle"])[1]
    p.save()
    p.setRenderHint(QPainter.Antialiasing)
    c = bounds.center()
    r = min(BUTTON_D, bounds.width() - 2, bounds.height() - 2) / 2
    if state in ("listening", "speaking"):  # a halo that swells with the voice
        swell = (0.5 + 0.5 * math.sin(t * 2 * math.pi / 1.2)) if level is None else max(0.0, min(1.0, level))
        halo = QColor(color)
        halo.setAlphaF(0.22 + 0.25 * swell)
        p.setPen(Qt.NoPen)
        p.setBrush(halo)
        grow = 2 + (GLOW - 3) * swell
        p.drawEllipse(c, r + grow, r + grow)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(0, 0, 0, 255 if hover else 204))  # 80% like the closed island
    p.drawEllipse(c, r, r)
    ring = QColor(255, 255, 255, 64) if state in ("idle", "done") else QColor(color)
    if state in ("thinking", "loading"):
        ring.setAlphaF(0.3)  # dim, so the running arc on it shows
    p.setPen(QPen(ring, 2))
    p.setBrush(Qt.NoBrush)
    p.drawEllipse(c, r - 1, r - 1)
    if state in ("thinking", "loading"):  # a short arc runs round while it works
        pen = QPen(color, 2.4)
        pen.setCapStyle(Qt.RoundCap)
        p.setPen(pen)
        p.drawArc(QRectF(c.x() - r + 1, c.y() - r + 1, 2 * r - 2, 2 * r - 2), int(-t * 300 * 16) % (360 * 16), 70 * 16)
    paint_mic(p, c, QColor(255, 255, 255))
    p.restore()


def paint_mic(p: QPainter, c: QPointF, color: QColor, s: float = 1.0) -> None:
    """A microphone: the capsule, the cradle under it, the stem and the foot."""
    pen = QPen(color, 2 * s)
    pen.setCapStyle(Qt.RoundCap)
    p.setPen(Qt.NoPen)
    p.setBrush(color)
    p.drawRoundedRect(QRectF(c.x() - 4 * s, c.y() - 10 * s, 8 * s, 13 * s), 4 * s, 4 * s)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    p.drawArc(QRectF(c.x() - 7 * s, c.y() - 6 * s, 14 * s, 12 * s), 180 * 16, 180 * 16)
    p.drawLine(QPointF(c.x(), c.y() + 6 * s), QPointF(c.x(), c.y() + 9 * s))
    p.drawLine(QPointF(c.x() - 4 * s, c.y() + 9.5 * s), QPointF(c.x() + 4 * s, c.y() + 9.5 * s))


def render_preview(on: str, out: str, scale: float = 1.25) -> None:
    """The button in every state, drawn onto a screenshot in physical pixels."""
    from PySide6.QtGui import QImage

    img = QImage(on).convertToFormat(QImage.Format_ARGB32)
    p = QPainter(img)
    p.scale(scale, scale)
    w, h = img.width() / scale, img.height() / scale
    side = BUTTON_D + 2 * GLOW
    for i, state in enumerate(STYLE):
        paint_button(p, QRectF(w - side - MARGIN, h - 48 - (side + 8) * (i + 1), side, side), state, 0.3)
    p.end()
    img.save(out)


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(prog="python -m screentutor.ui")
    ap.add_argument("--demo", action="store_true")
    ap.add_argument("--preview", metavar="OUT.png")
    ap.add_argument("--on", metavar="ẢNH", help="ảnh màn hình làm nền cho --preview")
    args = ap.parse_args(argv)
    if args.preview:
        app = QGuiApplication.instance() or QGuiApplication(sys.argv[:1])
        render_preview(args.on, args.preview)
        print(f"Đã lưu {args.preview}")
        del app
        return
    import signal

    from PySide6.QtWidgets import QApplication

    signal.signal(signal.SIGINT, signal.SIG_DFL)
    app = QApplication(sys.argv[:1])
    button = AskButton()
    button.show()
    states = list(STYLE)
    step = [0]

    def next_state():
        button.set_state(states[step[0] % len(states)])
        step[0] += 1

    button.clicked.connect(lambda: print("Đã bấm nút Hỏi"))
    timer = QTimer()
    timer.timeout.connect(next_state)
    timer.start(1500)
    print("Đang chạy thử nút tròn ở góc dưới phải. Ctrl+C để tắt.")
    app.exec()


if __name__ == "__main__":
    main()
