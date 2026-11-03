"""The coloured pointer drawn over every window (MVP step 3, Decision 4b: colourful illustration).

A frameless, always-on-top, click-through, transparent window covers the primary
screen, taskbar included. Given a point in screenshot pixels (physical screen
pixels), a hollow ring glides there from the mouse cursor, opens up and pulses,
so the user sees where to click, can still read what is under the ring, and the
click still reaches the app underneath.

  py -m screentutor.overlay --follow-mouse            # Windows: the ring should sit on the mouse tip
  py -m screentutor.overlay --at 960 540 --seconds 5  # Windows: point at a physical pixel
  python -m screentutor.overlay --preview case.png --at 960 540 --out preview.png   # any OS, no window

B3 (02/11) adds more than the ring, all in the same window and all letting clicks through:
  focus    a rounded frame around what to read, the rest of the screen darkened (founder: try this first)
  hint     a small mouse with a turning wheel and falling chevrons: scroll here
  tick     a green tick where she clicked, once the tutor has checked the step: the checking made visible
  glow     a soft light around the screen edge while the tutor looks, gone before it speaks
  flash    the same light in green, once, when the whole task is done

Anything that moves while the session watches the screen is published in `cover`, and the
frame stands still once it has landed. WDA_EXCLUDEFROMCAPTURE would keep all this out of
screenshots without hiding it, but it would also keep it out of the demo video.
"""

from __future__ import annotations

import argparse
import math
import sys
from dataclasses import dataclass, field

from PySide6.QtCore import QElapsedTimer, QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import (QColor, QConicalGradient, QCursor, QGuiApplication, QImage, QPainter, QPainterPath, QPen)

COLOR = QColor(255, 69, 58)          # red-orange: stands out on white Word pages, Zalo blue and the dark taskbar
CAUTION_COLOR = QColor(255, 176, 0)  # amber: this click sends something or replaces a file (founder's rule, 27/10)
HALO = QColor(255, 255, 255, 230)    # white edge so the ring reads on dark and light backgrounds alike
FILL_ALPHA = 40                      # faint tint inside: the button or word under the ring stays readable
TRAVEL_S = 0.45                      # glide from the mouse cursor to the target
PULSE_S = 1.2                        # one pulse cycle
TRAVEL_R, MARK_R = 12.0, 24.0        # ring radius while gliding and once arrived (logical px)
PULSE_MAX = 52.0
PULSE_ALPHA = 200
STROKE = 4.0
TOPMOST_EVERY_MS = 500
READ_COLOR = QColor(102, 212, 207)   # mint: reading is neither a click (red) nor a warning (amber)
TICK_COLOR = QColor(48, 209, 88)     # the island's "done" green
DIM_ALPHA = 92                       # black over the rest of the screen, 36%
TINT_ALPHA = 14                      # inside the frame: only a breath of colour, the words stay as they are
BOX_RADIUS, BOX_PAD = 14.0, 8.0      # logical px; a box from the model is rarely tight, so give it air
HINT_W, HINT_H = 62.0, 132.0
TICK_S = 0.9
GLOW_S = 7.0                         # one turn of the colours
GLOW_PX = 36                         # how far the light reaches in from the edge
GLOW_IN, GLOW_OUT = 2.5, 5.0         # per second: comes up slowly, leaves before the tutor speaks
GLOW_FRAME_MS = 40
GLOW_COLORS = [QColor(10, 132, 255), QColor(191, 90, 242), QColor(255, 55, 135), QColor(255, 159, 10),
               QColor(100, 210, 255), QColor(10, 132, 255)]   # the island's own family
DONE_COLORS = [TICK_COLOR, READ_COLOR, TICK_COLOR]
FLASH_S = 1.1                        # the green light when the whole task is done


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


def paint_frame(p: QPainter, f: Frame, scale: float = 1.0, color: QColor = COLOR) -> None:
    p.setRenderHint(QPainter.Antialiasing)
    c = QPointF(f.x, f.y)
    p.setBrush(Qt.NoBrush)
    for radius, alpha in f.pulses:
        pulse = QColor(color)
        pulse.setAlpha(alpha)
        p.setPen(QPen(pulse, 3 * scale))
        p.drawEllipse(c, radius * scale, radius * scale)
    r = f.radius * scale
    fill = QColor(color)
    fill.setAlpha(FILL_ALPHA)
    p.setPen(QPen(HALO, (STROKE + 3) * scale))
    p.setBrush(fill)
    p.drawEllipse(c, r, r)
    p.setPen(QPen(color, STROKE * scale))
    p.setBrush(Qt.NoBrush)
    p.drawEllipse(c, r, r)


@dataclass
class Focus:
    box: tuple[float, float, float, float]
    dim: int
    arrived: bool


def lerp_box(start: tuple[float, float], box: tuple[float, float, float, float], k: float) -> tuple[float, ...]:
    """From a point to a box: the frame opens out of the mouse as the ring flies out of it."""
    x, y = start
    return tuple(a + (b - a) * k for a, b in zip((x, y, x, y), box))


def padded(box: tuple[float, float, float, float], size: tuple[float, float], pad: float = BOX_PAD) -> tuple[float, ...]:
    return max(box[0] - pad, 0.0), max(box[1] - pad, 0.0), min(box[2] + pad, size[0]), min(box[3] + pad, size[1])


def focus_at(t: float, start: tuple[float, float], box: tuple[float, float, float, float]) -> Focus:
    """The frame t seconds after focus_on(). It stands still once it has landed."""
    k = ease_out(t / TRAVEL_S)
    return Focus(lerp_box(start, box, k), round(DIM_ALPHA * k), t >= TRAVEL_S)


def paint_focus(p: QPainter, f: Focus, size: tuple[float, float], scale: float = 1.0, color: QColor = READ_COLOR) -> None:
    p.setRenderHint(QPainter.Antialiasing)
    x1, y1, x2, y2 = f.box
    rect = QRectF(x1, y1, x2 - x1, y2 - y1)
    radius = min(BOX_RADIUS * scale, rect.width() / 2, rect.height() / 2)
    hole = QPainterPath()
    hole.addRoundedRect(rect, radius, radius)
    dark = QPainterPath()
    dark.addRect(QRectF(0, 0, size[0], size[1]))
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(0, 0, 0, f.dim))
    p.drawPath(dark.subtracted(hole))
    tint = QColor(color)
    tint.setAlpha(round(TINT_ALPHA * f.dim / DIM_ALPHA))
    p.setBrush(tint)
    p.drawPath(hole)
    p.setBrush(Qt.NoBrush)
    p.setPen(QPen(QColor(255, 255, 255, 215), 5 * scale))
    p.drawRoundedRect(rect, radius, radius)
    p.setPen(QPen(color, 3 * scale))
    p.drawRoundedRect(rect, radius, radius)


@dataclass
class Hint:
    x: float
    y: float
    phase: float      # 0..1 through one turn of the wheel
    arrived: bool


def hint_at(t: float, start: tuple[float, float], target: tuple[float, float]) -> Hint:
    k = ease_out(t / TRAVEL_S)
    phase = ((t - TRAVEL_S) % PULSE_S) / PULSE_S if t >= TRAVEL_S else 0.0
    return Hint(start[0] + (target[0] - start[0]) * k, start[1] + (target[1] - start[1]) * k, phase, t >= TRAVEL_S)


def hint_box(x: float, y: float, scale: float = 1.0) -> tuple[float, float, float, float]:
    w, h = HINT_W * scale / 2 + 2, HINT_H * scale / 2 + 2
    return x - w, y - h, x + w, y + h


def paint_hint(p: QPainter, f: Hint, scale: float = 1.0, color: QColor = COLOR) -> None:
    """A mouse with its wheel turning and chevrons falling: she may not know the word for scrolling."""
    p.setRenderHint(QPainter.Antialiasing)
    c = QPointF(f.x, f.y)
    p.setBrush(QColor(0, 0, 0, 190))
    p.setPen(QPen(QColor(255, 255, 255, 215), 2 * scale))
    p.drawRoundedRect(QRectF(c.x() - HINT_W * scale / 2, c.y() - HINT_H * scale / 2, HINT_W * scale, HINT_H * scale),
                      22 * scale, 22 * scale)
    top = c.y() - 54 * scale
    p.setBrush(Qt.NoBrush)
    p.setPen(QPen(QColor(255, 255, 255), 2.5 * scale))
    p.drawRoundedRect(QRectF(c.x() - 15 * scale, top, 30 * scale, 46 * scale), 15 * scale, 15 * scale)
    wheel = top + (8 + 12 * f.phase) * scale
    p.setPen(Qt.NoPen)
    p.setBrush(color)
    p.drawRoundedRect(QRectF(c.x() - 2.5 * scale, wheel, 5 * scale, 11 * scale), 2.5 * scale, 2.5 * scale)
    for i in range(3):
        strength = max(0.22, 1 - abs(f.phase * 3 - i - 0.5) / 1.3)
        chevron = QColor(color)
        chevron.setAlpha(round(255 * strength))
        pen = QPen(chevron, 3 * scale)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        p.setPen(pen)
        y = c.y() + (4 + i * 16) * scale
        path = QPainterPath(QPointF(c.x() - 9 * scale, y))
        path.lineTo(QPointF(c.x(), y + 7 * scale))
        path.lineTo(QPointF(c.x() + 9 * scale, y))
        p.drawPath(path)


def paint_tick(p: QPainter, x: float, y: float, t: float, scale: float = 1.0) -> None:
    """t seconds after the tutor checked the step: pops up, draws its tick, fades away."""
    pop = ease_out(t / 0.22)
    fade = 1 - min(max((t - 0.55) / (TICK_S - 0.55), 0.0), 1.0)
    if fade <= 0:
        return
    p.setRenderHint(QPainter.Antialiasing)
    r = 17 * scale * (0.6 + 0.4 * pop)
    c = QPointF(x, y)
    p.setOpacity(fade)
    p.setPen(QPen(QColor(255, 255, 255, 230), 3 * scale))
    p.setBrush(TICK_COLOR)
    p.drawEllipse(c, r, r)
    pen = QPen(QColor(255, 255, 255), 3.4 * scale)
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    k = r / 17
    path = QPainterPath(c + QPointF(-7.5 * k, 0.5 * k))
    path.lineTo(c + QPointF(-2.2 * k, 5.6 * k))
    path.lineTo(c + QPointF(8 * k, -5 * k))
    p.drawPath(path)
    p.setOpacity(1.0)


class EdgeGlow:
    """The soft light around the screen. The edge is drawn once at a quarter of the size, so each
    frame only turns the colours; a full-screen window repaints often while the tutor thinks."""

    def __init__(self, w: float, h: float, scale: float = 1.0):
        self.w, self.h = w, h
        self.small = (max(int(w) // 4, 1), max(int(h) // 4, 1))
        self.mask = QImage(*self.small, QImage.Format_ARGB32_Premultiplied)
        self.mask.fill(Qt.transparent)
        p = QPainter(self.mask)
        p.setRenderHint(QPainter.Antialiasing)
        p.setBrush(Qt.NoBrush)
        depth = max(int(GLOW_PX * scale / 4), 1)
        for i in range(depth):
            p.setPen(QPen(QColor(255, 255, 255, round(205 * (1 - i / depth) ** 2.4)), 1.6))
            r = depth + 2 - i * 0.6        # rounder inside, so the corners fade instead of showing a square
            p.drawRoundedRect(QRectF(i, i, self.small[0] - 2 * i, self.small[1] - 2 * i), r, r)
        p.end()

    def paint(self, p: QPainter, t: float, level: float, colors: list[QColor] = GLOW_COLORS) -> None:
        buf = QImage(*self.small, QImage.Format_ARGB32_Premultiplied)
        buf.fill(Qt.transparent)
        q = QPainter(buf)
        gradient = QConicalGradient(self.small[0] / 2, self.small[1] / 2, -(t / GLOW_S * 360) % 360)
        for i, color in enumerate(colors):
            gradient.setColorAt(i / (len(colors) - 1), color)
        q.fillRect(buf.rect(), gradient)
        q.setCompositionMode(QPainter.CompositionMode_DestinationIn)
        q.drawImage(0, 0, self.mask)
        q.end()
        p.setOpacity(min(max(level, 0.0), 1.0))
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        p.drawImage(QRectF(0, 0, self.w, self.h), buf)
        p.setOpacity(1.0)


class Overlay:
    """Owns the click-through window. Call from the Qt (main) thread."""

    def __init__(self, screen=None):
        from PySide6.QtWidgets import QWidget

        class _Canvas(QWidget):
            def paintEvent(inner, _event):  # noqa: N805
                p = QPainter(inner)
                self._paint(p)
                p.end()

        self._screen = screen or QGuiApplication.primaryScreen()
        self._w = _Canvas(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
                          | Qt.WindowTransparentForInput | Qt.WindowDoesNotAcceptFocus)
        self._w.setAttribute(Qt.WA_TranslucentBackground)
        self._w.setAttribute(Qt.WA_ShowWithoutActivating)
        self._w.setAttribute(Qt.WA_TransparentForMouseEvents)
        self._w.setGeometry(self._screen.geometry())  # full screen, taskbar included
        self._target = None            # the ring's target
        self._box = None               # or the frame's box
        self._hint = None              # or where to scroll
        self._start = (0.0, 0.0)
        self._until_ms = None
        self._color = COLOR
        self._clock = QElapsedTimer()
        self._clock.start()
        self._steady = QElapsedTimer()  # never restarted: the ticks and the glow outlive the mark they follow
        self._steady.start()
        self._ticks: list[tuple[float, float, float]] = []   # (seconds on _steady, x, y) logical
        self._glowing = False
        self._glow_level = 0.0
        self._glow_last = 0.0
        self._flash_at: float | None = None
        self._edge = None
        self.glow_enabled = True
        self.cover: tuple[int, int, int, int] | None = None  # logical (x, y, w, h) that moves; read by worker threads
        self.after_topmost = None      # our other windows stay above the darkened screen
        self._last_topmost = 0
        self._timer = QTimer(self._w)
        self._timer.setInterval(16)
        self._timer.timeout.connect(self._tick)

    def point_at(self, px: float, py: float, seconds: float | None = None, caution: bool = False) -> None:
        """px, py: pixels of a screenshot of this screen (physical pixels). caution: amber instead of red."""
        self._color = CAUTION_COLOR if caution else COLOR
        x, y = to_logical(px, py, self._screen.devicePixelRatio())
        self._start = self._from()
        self._box = self._hint = None
        self._target = (x, y)
        self._clock.restart()
        self._until_ms = None if seconds is None else seconds * 1000
        self._publish()
        self._run()

    def focus_on(self, x1: float, y1: float, x2: float, y2: float, caution: bool = False) -> None:
        """A region to read, in physical pixels: the frame opens out of the mouse and the rest darkens."""
        self._color = CAUTION_COLOR if caution else READ_COLOR
        dpr = self._screen.devicePixelRatio()
        size = (self._w.width(), self._w.height())
        self._start = self._from()
        self._target = self._hint = None
        self._box = padded((*to_logical(x1, y1, dpr), *to_logical(x2, y2, dpr)), size)
        self._clock.restart()
        self._until_ms = None
        self._publish()
        self._run()

    def scroll_hint(self, px: float, py: float) -> None:
        """Where to scroll, in physical pixels."""
        self._color = COLOR
        self._start = self._from()
        self._target = self._box = None
        self._hint = to_logical(px, py, self._screen.devicePixelRatio())
        self._clock.restart()
        self._until_ms = None
        self._publish()
        self._run()

    def tick_at(self, px: float, py: float) -> None:
        """The step at this physical pixel has been checked."""
        x, y = to_logical(px, py, self._screen.devicePixelRatio())
        self._ticks.append((self._steady.elapsed() / 1000, x, y))
        self._run()

    def glow(self, on: bool) -> None:
        """The light around the screen while the tutor looks. Never on while a screenshot is taken."""
        self._glowing = on and self.glow_enabled
        self._glow_last = self._steady.elapsed() / 1000
        if self._glowing:
            self._run()

    def flash(self) -> None:
        """The whole task is done."""
        if self.glow_enabled:
            self._flash_at = self._steady.elapsed() / 1000
            self._run()

    def clear(self) -> None:
        """Gone at once: the session takes a screenshot right after this, and the ticks stay out of its way."""
        self._target = self._box = self._hint = None
        self._publish()
        if not self._busy():
            self._stop()

    def _from(self) -> tuple[float, float]:
        if self._target is not None:
            f = self._frame()
            return f.x, f.y
        geo = self._screen.geometry()
        cursor = QCursor.pos(self._screen)
        return cursor.x() - geo.x(), cursor.y() - geo.y()

    def _busy(self) -> bool:
        return any(v is not None for v in (self._target, self._box, self._hint)) or bool(self._ticks) \
            or self._glowing or self._glow_level > 0 or self._flash_at is not None

    def _moving(self) -> bool:
        landed = self._box is not None and self._clock.elapsed() / 1000 >= TRAVEL_S
        return not landed or bool(self._ticks) or self._glow_level > 0 or self._flash_at is not None

    def _publish(self) -> None:
        self.cover = None
        if self._hint is not None:
            x1, y1, x2, y2 = hint_box(*self._hint)
            self.cover = round(x1), round(y1), round(x2 - x1), round(y2 - y1)

    def _run(self) -> None:
        self._w.show()
        _win_harden(self._w)
        self._raise_ours()
        self._timer.setInterval(16)
        self._timer.start()

    def _stop(self) -> None:
        self._timer.stop()
        self._glow_level = 0.0
        self._w.hide()

    def _raise_ours(self) -> None:
        if self.after_topmost:
            self.after_topmost()

    def _frame(self) -> Frame:
        return frame_at(self._clock.elapsed() / 1000, self._start, self._target)

    def _paint(self, p: QPainter) -> None:
        now = self._steady.elapsed() / 1000
        t = self._clock.elapsed() / 1000
        if self._glow_level > 0 or self._flash_at is not None:
            if self._edge is None:
                self._edge = EdgeGlow(self._w.width(), self._w.height())
            if self._glow_level > 0:
                self._edge.paint(p, now, self._glow_level)
            if self._flash_at is not None:
                self._edge.paint(p, now * 3, math.sin(math.pi * min((now - self._flash_at) / FLASH_S, 1.0)), DONE_COLORS)
        if self._box is not None:
            paint_focus(p, focus_at(t, self._start, self._box), (self._w.width(), self._w.height()), color=self._color)
        if self._hint is not None:
            paint_hint(p, hint_at(t, self._start, self._hint), color=self._color)
        if self._target is not None:
            paint_frame(p, self._frame(), color=self._color)
        for t0, x, y in self._ticks:
            paint_tick(p, x, y, now - t0)

    def _tick(self) -> None:
        elapsed = self._clock.elapsed()
        if self._until_ms is not None and elapsed >= self._until_ms:
            self.clear()
            return
        now = self._steady.elapsed() / 1000
        self._ticks = [m for m in self._ticks if now - m[0] < TICK_S]
        if self._flash_at is not None and now - self._flash_at >= FLASH_S:
            self._flash_at = None
        step = now - self._glow_last
        self._glow_last = now
        goal, rate = (1.0, GLOW_IN) if self._glowing else (0.0, GLOW_OUT)
        self._glow_level = min(self._glow_level + rate * step, 1.0) if goal else max(self._glow_level - rate * step, 0.0)
        if not self._busy():
            self._stop()
            return
        if now * 1000 - self._last_topmost >= TOPMOST_EVERY_MS:
            self._last_topmost = now * 1000
            _win_topmost(self._w)
            self._raise_ours()
        moving = self._moving()
        self._timer.setInterval(16 if moving and not self._only_glow() else GLOW_FRAME_MS if moving else TOPMOST_EVERY_MS)
        if moving:
            self._w.update()

    def _only_glow(self) -> bool:
        return self._glow_level > 0 and not self._ticks and all(v is None for v in (self._target, self._box, self._hint))


def _win_harden(widget, click_through: bool = True) -> None:
    """Belt and braces on Windows: never take focus, no taskbar button, and (by default) never take clicks."""
    if sys.platform != "win32":
        return
    import ctypes

    GWL_EXSTYLE = -20
    WS_EX_TRANSPARENT, WS_EX_TOOLWINDOW, WS_EX_LAYERED, WS_EX_NOACTIVATE = 0x20, 0x80, 0x80000, 0x08000000
    user32 = ctypes.windll.user32
    user32.GetWindowLongW.restype = ctypes.c_long
    hwnd = ctypes.c_void_p(int(widget.winId()))
    WS_EX_APPWINDOW = 0x40000  # T5 (02/11): the ring showed up in Alt+Tab; an app-window flag overrides the tool flag
    style = (user32.GetWindowLongW(hwnd, GWL_EXSTYLE) | WS_EX_TOOLWINDOW | WS_EX_LAYERED | WS_EX_NOACTIVATE) \
        & ~WS_EX_APPWINDOW & ~WS_EX_TRANSPARENT  # the island takes clicks again once it opens (02/11)
    user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style | WS_EX_TRANSPARENT if click_through else style)
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
