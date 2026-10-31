"""The "Hỏi" button and the dynamic island (MVP step 5, Decisions 4a-4c).

Button: a pill at the bottom right, just above the taskbar, always on top. Clicking
it never takes the focus away from the app the user works in. Its colour and words
say what the tutor is doing: Hỏi / Đang nghe / Đang xem / Đang nói.

Island: a small dark pill at the top centre with the raw words the tutor heard
(founder, 30/10: show the transcript as it is; tidy it up later). The mouse over it
opens it up to the whole text. Clicks go through it, so it never blocks a browser
tab underneath. No subtitles of the tutor's own speech (founder, 29/10).

  python -m screentutor.ui --demo            # both widgets, cycling through the states
  python -m screentutor.ui --preview OUT.png --on case.png   # drawn onto a screenshot, no window
"""

from __future__ import annotations

import argparse
import math
import sys

from PySide6.QtCore import QElapsedTimer, QPointF, QRect, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QCursor, QFont, QFontMetrics, QGuiApplication, QPainter, QPen
from PySide6.QtWidgets import QWidget

from .overlay import _win_harden, _win_topmost

STATES = {
    "idle": ("Hỏi", QColor(37, 99, 235)),
    "listening": ("Đang nghe…", QColor(220, 38, 38)),
    "thinking": ("Đang xem…", QColor(217, 119, 6)),
    "speaking": ("Đang nói…", QColor(22, 163, 74)),
}
MARGIN = 16                 # logical px from the screen edge / taskbar
BUTTON_H = 52
ISLAND_H = 34
ISLAND_W_MIN, ISLAND_W_MAX, ISLAND_W_OPEN = 180, 420, 600
FLAGS = Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool | Qt.WindowDoesNotAcceptFocus


def _font(px: int, bold: bool = False) -> QFont:
    f = QFont("Segoe UI")
    f.setPixelSize(px)
    f.setBold(bold)
    return f


class AskButton(QWidget):
    clicked = Signal()

    def __init__(self, screen=None):
        super().__init__(None, FLAGS)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setCursor(Qt.PointingHandCursor)
        self._screen = screen or QGuiApplication.primaryScreen()
        self.state = "idle"
        self._clock = QElapsedTimer()
        self._clock.start()
        self._timer = QTimer(self)
        self._timer.setInterval(33)
        self._timer.timeout.connect(self.update)
        self._place()

    def _place(self) -> None:
        w = QFontMetrics(_font(20, True)).horizontalAdvance("Đang nghe…") + 2 * 28
        area = self._screen.availableGeometry()  # above the taskbar
        self.setFixedSize(QSize(w + 2 * 8, BUTTON_H + 2 * 8))  # room for the glow
        self.move(area.right() - self.width() - MARGIN + 8, area.bottom() - self.height() - MARGIN + 8)

    def set_state(self, state: str) -> None:
        self.state = state
        self._timer.start() if state != "idle" else self._timer.stop()
        self.update()

    def showEvent(self, event):
        super().showEvent(event)
        _win_harden(self, click_through=False)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()

    def paintEvent(self, _event):
        p = QPainter(self)
        paint_button(p, QRectF(self.rect()), self.state, self._clock.elapsed() / 1000)
        p.end()


def paint_button(p: QPainter, bounds: QRectF, state: str, t: float) -> None:
    label, color = STATES[state]
    p.setRenderHint(QPainter.Antialiasing)
    pill = bounds.adjusted(8, 8, -8, -8)
    r = pill.height() / 2
    if state == "listening":  # a breathing glow while it listens
        glow = QColor(color)
        glow.setAlpha(round(60 + 60 * (0.5 + 0.5 * math.sin(t * 2 * math.pi / 1.2))))
        p.setPen(Qt.NoPen)
        p.setBrush(glow)
        p.drawRoundedRect(pill.adjusted(-6, -6, 6, 6), r + 6, r + 6)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(0, 0, 0, 70))
    p.drawRoundedRect(pill.translated(0, 2), r, r)
    p.setPen(QPen(QColor(255, 255, 255), 3))
    p.setBrush(color)
    p.drawRoundedRect(pill, r, r)
    p.setFont(_font(20, True))
    p.setPen(QColor(255, 255, 255))
    p.drawText(pill, Qt.AlignCenter, label)


class Island(QWidget):
    """Top-centre pill with the words heard. Click-through; opens up while the mouse is over it."""

    def __init__(self, screen=None):
        super().__init__(None, FLAGS | Qt.WindowTransparentForInput)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self._screen = screen or QGuiApplication.primaryScreen()
        self.state = "idle"
        self.text = ""
        self.opened = False
        self._hover = QTimer(self)  # hover by polling: a click-through window gets no mouse events
        self._hover.setInterval(120)
        self._hover.timeout.connect(self._check_hover)
        self._relayout()

    def set_state(self, state: str, text: str | None = None) -> None:
        self.state = state
        if text is not None:
            self.text = text
        self._relayout()
        self.update()

    def showEvent(self, event):
        super().showEvent(event)
        _win_harden(self, click_through=True)
        self._hover.start()

    def _check_hover(self) -> None:
        inside = self.geometry().contains(QCursor.pos(self._screen))
        if inside != self.opened:
            self.opened = inside
            self._relayout()
            self.update()
        _win_topmost(self)

    def _relayout(self) -> None:
        w, h = island_size(self.text or STATES[self.state][0], self.opened)
        top = self._screen.geometry()
        self.setFixedSize(w, h)
        self.move(top.x() + (top.width() - w) // 2, top.y() + 6)

    def paintEvent(self, _event):
        p = QPainter(self)
        paint_island(p, QRectF(self.rect()), self.state, self.text, self.opened)
        p.end()


def island_size(text: str, opened: bool) -> tuple[int, int]:
    m = QFontMetrics(_font(15))
    if not opened:
        return max(ISLAND_W_MIN, min(ISLAND_W_MAX, m.horizontalAdvance(text) + 56)), ISLAND_H
    rect = m.boundingRect(QRect(0, 0, ISLAND_W_OPEN - 56, 2000), Qt.TextWordWrap, text)
    return ISLAND_W_OPEN, max(ISLAND_H, rect.height() + 20)


def paint_island(p: QPainter, bounds: QRectF, state: str, text: str, opened: bool) -> None:
    p.setRenderHint(QPainter.Antialiasing)
    r = min(ISLAND_H / 2, bounds.height() / 2)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(17, 17, 17, 225))
    p.drawRoundedRect(bounds, r, r)
    p.setBrush(STATES[state][1])
    p.drawEllipse(QPointF(bounds.left() + 20, bounds.top() + ISLAND_H / 2), 5, 5)
    p.setFont(_font(15))
    p.setPen(QColor(255, 255, 255))
    area = bounds.adjusted(36, 8, -16, -8)
    shown = text or STATES[state][0]
    if opened:
        p.drawText(area, Qt.TextWordWrap | Qt.AlignLeft | Qt.AlignTop, shown)
    else:
        elided = QFontMetrics(p.font()).elidedText(shown, Qt.ElideLeft, int(area.width()))  # keep her last words
        p.drawText(area, Qt.AlignVCenter | Qt.AlignLeft, elided)


def render_preview(on: str, out: str, scale: float = 1.25) -> None:
    """Button (every state) and island (closed and open) drawn onto a screenshot in physical pixels."""
    from PySide6.QtGui import QImage

    img = QImage(on).convertToFormat(QImage.Format_ARGB32)
    p = QPainter(img)
    p.scale(scale, scale)
    w, h = img.width() / scale, img.height() / scale
    sample = "cái file báo cáo tuần trước tôi lưu ở đâu rồi sao bây giờ mở ra không thấy chữ nào hết vậy"  # made up, not mom's words
    iw, ih = island_size(sample, False)
    paint_island(p, QRectF((w - iw) / 2, 6, iw, ih), "thinking", sample, False)
    ow, oh = island_size(sample, True)
    paint_island(p, QRectF((w - ow) / 2, 60, ow, oh), "thinking", sample, True)
    bw = 200
    for i, state in enumerate(STATES):
        paint_button(p, QRectF(w - bw - MARGIN, h - 48 - (BUTTON_H + 30) * (i + 1), bw, BUTTON_H + 16), state, 0.3)
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
    button, island = AskButton(), Island()
    button.show()
    island.show()
    script = [("listening", "cái file báo cáo"), ("listening", "cái file báo cáo tuần trước tôi lưu ở đâu rồi"),
              ("thinking", None), ("speaking", None), ("idle", None)]
    step = [0]

    def next_state():
        state, text = script[step[0] % len(script)]
        button.set_state(state)
        island.set_state(state, text)
        step[0] += 1

    button.clicked.connect(lambda: print("Đã bấm nút Hỏi"))
    timer = QTimer()
    timer.timeout.connect(next_state)
    timer.start(2500)
    print("Đang chạy thử: nút Hỏi ở góc dưới phải, ô chữ ở giữa mép trên. Rê chuột lên ô chữ để mở rộng. Ctrl+C để tắt.")
    app.exec()


if __name__ == "__main__":
    main()
