"""The dynamic island: every state of the tutor lives here, Apple-like (founder, 02/11).

Closed: a small pill at the top centre, black at 80%, so the app below shows through, and
clicks go through it. The mouse over it: fully black, a little wider (never the whole width,
so Word's toolbar stays in sight), the lower edge curved like an upward parabola, and the
talk inside. A click: a plain rectangle with all of the task. While the tutor works, an icon
and a colour say what it is doing, each with its own movement.

A1 is the shape and the spring between shapes, A2 the states, icons and painting, A4 the
window: it opens after the mouse rests on it, takes clicks only while open, and steps aside
when the ring points at something underneath.

  python -m screentutor.island --preview OUT_DIR [--on SCREENSHOT.png]   # PNG sheet and GIFs
  python -m screentutor.island --demo                                    # the real window, cycling states
"""

from __future__ import annotations

import argparse
import math
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QPoint, QPointF, QRect, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QCursor, QFont, QFontMetrics, QGuiApplication, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QWidget

from . import conversation as conv
from .overlay import CAUTION_COLOR, COLOR, READ_COLOR, _win_harden, _win_topmost

TOP = 6                      # logical px below the top edge of the screen
COLLAPSED_H = 34
IDLE_W = 92
COLLAPSED_W = (140, 300)
COLLAPSED_PAD = 62           # icon, gap and both sides around the one line
HOVER_W = (360, 480)
HOVER_MAX_SHARE = 0.4        # of the screen width (founder, 02/11: never the whole width)
HOVER_H = (130, 220)
HOVER_DEPTH = 16             # the middle of the lower edge hangs this much lower than the sides
PINNED_W = 560
PINNED_H_MIN, PINNED_MAX_SHARE = 200, 0.55
FOOTER_H = 72               # pinned: her earlier tasks, the colours, the button switch, clear history (A9)
SWATCHES = ["#000000", "#121C3A", "#083028", "#30143C", "#2C2C32"]  # black, navy, green, plum, graphite
CONFIRM_S = 4.0             # "Xoá lịch sử" asks again; a second click within this long deletes
ALPHA_CLOSED = 0.8           # founder, 02/11: 20% of the app below shows through
STIFFNESS, DAMPING = 190.0, 21.0   # damping ratio 0.76: settles in about 0.35 s with a small bounce
ALPHA_RATE = 10.0
MAX_DT = 1 / 30

BODY_PX, LABEL_PX = 15, 13
HEADER_H = 30
SIDE = 16
ME_COLOR = QColor(10, 132, 255)
TUTOR_COLOR = QColor(44, 44, 46)
TEXT = QColor(242, 242, 247)

STYLE = {  # state: (words, colour)
    "idle": ("Sẵn sàng", QColor(255, 255, 255, 140)),
    "listening": ("Đang nghe", QColor(100, 210, 255)),
    "thinking": ("Đang xem màn hình", QColor(191, 90, 242)),
    "speaking": ("Đang nói", QColor(10, 132, 255)),
    "turn": ("Đến lượt bạn bấm", QColor(COLOR)),            # the same red as the ring
    "reading": ("Bạn đọc vùng sáng nhé", QColor(READ_COLOR)),  # the same mint as the frame
    "caution": ("Cẩn thận trước khi bấm", QColor(CAUTION_COLOR)),  # the same amber as the ring
    "loading": ("Chờ trang tải", QColor(191, 90, 242)),
    "done": ("Xong rồi", QColor(48, 209, 88)),
    "error": ("Chưa nghe rõ", QColor(142, 142, 147)),
}
TURN_PULSE_S, CAUTION_PULSE_S = 1.2, 1.8   # 1.2 s matches the ring on the screen (overlay.PULSE_S)
READ_PULSE_S = 2.4


@dataclass(frozen=True)
class Shape:
    w: float
    h: float           # height of the sides; the middle of a curved edge goes `depth` lower
    r: float
    depth: float
    alpha: float

    @property
    def full_h(self) -> float:
        return self.h + max(0.0, self.depth)


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def target_shape(mode: str, screen_w: float, screen_h: float, text_w: float = 0.0,
                 content_w: float = 0.0, content_h: float = 0.0) -> Shape:
    if mode == "pinned":
        w = min(PINNED_W, screen_w - 48)
        return Shape(w, _clamp(content_h, PINNED_H_MIN, PINNED_MAX_SHARE * screen_h), 18, 0, 1.0)
    if mode == "hover":
        w = min(_clamp(content_w, *HOVER_W), HOVER_MAX_SHARE * screen_w)
        return Shape(w, _clamp(content_h, *HOVER_H), 24, HOVER_DEPTH, 1.0)
    w = IDLE_W if text_w <= 0 else _clamp(text_w + COLLAPSED_PAD, *COLLAPSED_W)
    return Shape(w, COLLAPSED_H, COLLAPSED_H / 2, 0, ALPHA_CLOSED)


def outline(s: Shape, cx: float, top: float = TOP) -> QPainterPath:
    """Rounded top corners, straight sides, and a lower edge that dips to `depth` in the middle."""
    x0, x1, yb = cx - s.w / 2, cx + s.w / 2, top + s.h
    r = min(s.r, s.h / 2, s.w / 2)
    path = QPainterPath(QPointF(x0 + r, top))
    path.lineTo(x1 - r, top)
    path.quadTo(x1, top, x1, top + r)
    path.lineTo(x1, yb - r)
    path.quadTo(x1, yb, x1 - r, yb)
    path.quadTo(cx, yb + 2 * max(0.0, s.depth), x0 + r, yb)  # the quadratic's lowest point is yb + depth
    path.quadTo(x0, yb, x0, yb - r)
    path.lineTo(x0, top + r)
    path.quadTo(x0, top, x0 + r, top)
    path.closeSubpath()
    return path


class Spring:
    def __init__(self, value: float):
        self.value = self.target = float(value)
        self.velocity = 0.0

    def step(self, dt: float) -> None:
        dt = min(dt, MAX_DT)
        self.velocity += (STIFFNESS * (self.target - self.value) - DAMPING * self.velocity) * dt
        self.value += self.velocity * dt

    def settled(self) -> bool:
        return abs(self.target - self.value) < 0.5 and abs(self.velocity) < 1.0


class Morph:
    """Moves one shape into another on springs; the opacity eases on its own."""
    KEYS = ("w", "h", "r", "depth")

    def __init__(self, shape: Shape):
        self._springs = {k: Spring(getattr(shape, k)) for k in self.KEYS}
        self.alpha = shape.alpha
        self.target = self._start = shape

    def set_target(self, shape: Shape) -> None:
        if shape == self.target:
            return
        self._start, self.target = self.shape(), shape
        for k, spring in self._springs.items():
            spring.target = getattr(shape, k)

    def step(self, dt: float) -> Shape:
        for spring in self._springs.values():
            spring.step(dt)
        self.alpha += (self.target.alpha - self.alpha) * min(1.0, min(dt, MAX_DT) * ALPHA_RATE)
        return self.shape()

    def shape(self) -> Shape:
        v = {k: s.value for k, s in self._springs.items()}
        return Shape(max(v["w"], 1.0), max(v["h"], 1.0), max(v["r"], 0.0), max(v["depth"], 0.0), self.alpha)

    def progress(self) -> float:
        """0 when the change starts, 1 when the shape has arrived."""
        start, now, goal = self._start, self.shape(), self.target
        d0 = max(abs(start.w - goal.w), abs(start.h - goal.h))
        if d0 < 1:
            return 1.0
        return _clamp(1 - max(abs(now.w - goal.w), abs(now.h - goal.h)) / d0, 0.0, 1.0)

    def moving(self) -> bool:
        return not all(s.settled() for s in self._springs.values()) or abs(self.alpha - self.target.alpha) > 0.005


# --- A2: icons --------------------------------------------------------------------------

def _with_alpha(c: QColor, a: float) -> QColor:
    out = QColor(c)
    out.setAlphaF(_clamp(c.alphaF() * a, 0.0, 1.0))
    return out


def bar_heights(n: int, t: float, level: float | None, lo: float, hi: float, speed: float) -> list[float]:
    """Sound bars: the real level when there is one, a lively pattern on top so they never look stuck."""
    out = []
    for i in range(n):
        wobble = abs(math.sin(t * (speed + i * 1.9) + i * 1.3) * math.sin(t * (speed * 0.4 + i * 0.7) + i))
        amount = 0.2 + 0.8 * wobble if level is None else _clamp(level, 0, 1) * (0.55 + 0.45 * wobble)
        out.append(lo + (hi - lo) * amount)
    return out


def paint_icon(p: QPainter, state: str, c: QPointF, t: float, since: float = 1.0, level: float | None = None) -> None:
    """One 20×20 icon centred on `c`. `t` is the clock, `since` the time in this state, `level` 0..1."""
    color = STYLE[state][1]
    p.save()
    p.setRenderHint(QPainter.Antialiasing)
    p.setBrush(Qt.NoBrush)

    def ring(r: float, width: float, col: QColor) -> None:
        p.setPen(QPen(col, width))
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(c, r, r)

    def bang(scale: float) -> None:  # an exclamation mark
        p.setPen(Qt.NoPen)
        p.setBrush(color)
        p.drawRoundedRect(QRectF(c.x() - 0.9 * scale, c.y() - 3.0 * scale, 1.8 * scale, 3.6 * scale), 0.9, 0.9)
        p.drawEllipse(QPointF(c.x(), c.y() + 2.4 * scale), 1.0 * scale, 1.0 * scale)

    if state == "idle":
        ring(5, 2, color)
    elif state in ("listening", "speaking"):
        n, width, step = (5, 2.4, 3.6) if state == "listening" else (4, 2.6, 4.0)
        heights = bar_heights(n, t, level, 3, 16, 5.3 if state == "listening" else 7.5)
        p.setPen(Qt.NoPen)
        p.setBrush(color)
        x = c.x() - ((n - 1) * step + width) / 2
        for i, h in enumerate(heights):
            if state == "speaking" and i in (0, n - 1):
                h *= 0.7
            p.drawRoundedRect(QRectF(x + i * step, c.y() - h / 2, width, h), width / 2, width / 2)
    elif state == "thinking":
        p.setPen(Qt.NoPen)
        p.setBrush(color)
        for k in range(3):
            a = t * 3.2 + k * 2 * math.pi / 3
            p.drawEllipse(QPointF(c.x() + 6 * math.cos(a), c.y() + 6 * math.sin(a)),
                          1.5 + (0.5 + 0.5 * math.sin(a)), 1.5 + (0.5 + 0.5 * math.sin(a)))
    elif state in ("turn", "caution"):
        period = TURN_PULSE_S if state == "turn" else CAUTION_PULSE_S
        phase = (t % period) / period
        ring(4 + 4.5 * phase, 1.8, _with_alpha(color, 1 - phase))
        ring(4.5, 2.2, color)
        if state == "caution":
            bang(0.85)
    elif state == "reading":
        p.setPen(Qt.NoPen)
        phase = (t % READ_PULSE_S) / READ_PULSE_S
        for i, width in enumerate((14, 14, 9)):  # three lines of text, the eye going down them
            strength = max(0.35, 1 - abs(phase * 3 - i - 0.5) / 1.4)
            p.setBrush(_with_alpha(color, strength))
            p.drawRoundedRect(QRectF(c.x() - 7, c.y() - 6.5 + i * 5, width, 3), 1.5, 1.5)
    elif state == "loading":
        ring(6.5, 2.2, _with_alpha(color, 0.22))
        pen = QPen(color, 2.2)
        pen.setCapStyle(Qt.RoundCap)
        p.setPen(pen)
        p.drawArc(QRectF(c.x() - 6.5, c.y() - 6.5, 13, 13), int(-t * 300 * 16) % (360 * 16), 100 * 16)
    elif state == "done":
        p.setPen(Qt.NoPen)
        p.setBrush(_with_alpha(color, 0.2))
        p.drawEllipse(c, 8.5, 8.5)
        pts = [QPointF(c.x() - 4.4, c.y() + 0.4), QPointF(c.x() - 1.3, c.y() + 3.3), QPointF(c.x() + 4.4, c.y() - 2.8)]
        lens = [math.dist((a.x(), a.y()), (b.x(), b.y())) for a, b in zip(pts, pts[1:])]
        left = _clamp(since / 0.45, 0, 1) * sum(lens)  # the tick draws itself in 0.45 s
        pen = QPen(color, 2.2)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        path = QPainterPath(pts[0])
        for (a, b), ln in zip(zip(pts, pts[1:]), lens):
            if left <= 0:
                break
            f = min(1.0, left / ln)
            path.lineTo(a + (b - a) * f)
            left -= ln
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        p.drawPath(path)
    else:  # error
        ring(7.5, 2, color)
        bang(1.2)
    p.restore()


# --- A2: the island itself --------------------------------------------------------------

def font(px: int, bold: bool = False) -> QFont:
    f = QFont("Segoe UI")
    f.setPixelSize(px)
    f.setBold(bold)
    return f


def measure_with(px: int):
    m = QFontMetrics(font(px))
    return lambda s: m.horizontalAdvance(s)


@dataclass
class View:
    """Everything the island needs to draw one frame; built by the window (A4) or the preview."""
    mode: str = "collapsed"
    state: str = "idle"
    task: conv.Task | None = None
    title: str = ""
    since: float = 0.0
    level: float | None = None
    content_alpha: float = 1.0
    layout_w: float = 0.0     # the width the open island is heading to, so text does not re-wrap while it grows
    scroll: float = 0.0       # pinned: how far the talk has been scrolled up
    recent: tuple[tuple[str, str], ...] = ()   # pinned: (when, title) of her latest earlier tasks
    show_button: bool = True
    color: str = "#000000"
    confirm_clear: bool = False


def header_rect(shape: Shape, cx: float, top: float = TOP) -> QRectF:
    return QRectF(cx - shape.w / 2 + SIDE + 28, top + 6, shape.w - 2 * SIDE - 28, HEADER_H)


def close_center(shape: Shape, cx: float, top: float = TOP) -> QPointF:
    """Where the × of the pinned island sits; the window tests clicks against it."""
    head = header_rect(shape, cx, top)
    return QPointF(head.right() - 8, head.center().y())


def hover_messages(task: conv.Task | None) -> list[conv.Message]:
    """The open island: her question and the tutor's sentences; the parts show as "Phần 1/3" instead."""
    return [m for m in task.messages if not m.plan] if task else []


def content_size(view: View, screen_w: float, screen_h: float) -> tuple[float, float, float]:
    """(text width closed, content width open, content height open) for target_shape()."""
    measure = measure_with(BODY_PX)
    label = STYLE[view.state][0]
    text = conv.collapsed_text(view.state, view.task, label, COLLAPSED_W[1] - COLLAPSED_PAD, measure)
    messages = view.task.messages if view.task else []
    if view.mode == "collapsed":
        return (measure(text) if text else 0.0), 0.0, 0.0
    if view.mode == "hover":
        shown = hover_messages(view.task)
        w = min(_clamp(conv.natural_width(shown, measure) + 2 * SIDE, *HOVER_W), HOVER_MAX_SHARE * screen_w)
        bubbles, h = conv.layout(shown, w - 2 * SIDE, measure, current=True)
        _, h = conv.newest_that_fit(bubbles, HOVER_H[1] - HEADER_H - 14, keep_first=True)
        return 0.0, w, HEADER_H + h + 14
    w = min(PINNED_W, screen_w - 48)
    _, h = conv.layout(messages, w - 2 * SIDE, measure, current=True)
    return 0.0, w, HEADER_H + 10 + h + 16 + FOOTER_H


def paint_island(p: QPainter, shape: Shape, cx: float, view: View, t: float,
                 base: QColor = QColor(0, 0, 0), top: float = TOP) -> None:
    p.save()
    p.setRenderHint(QPainter.Antialiasing)
    path = outline(shape, cx, top)
    p.setPen(Qt.NoPen)
    p.setBrush(_with_alpha(base, shape.alpha))
    p.drawPath(path)
    p.setClipPath(path)
    x0 = cx - shape.w / 2
    label, color = STYLE[view.state]
    if view.mode == "collapsed":
        measure = measure_with(BODY_PX)
        text = conv.collapsed_text(view.state, view.task, label, shape.w - COLLAPSED_PAD, measure)
        mid = top + shape.h / 2
        if not text:
            paint_icon(p, view.state, QPointF(cx, mid), t, view.since, view.level)
        else:
            paint_icon(p, view.state, QPointF(x0 + 14 + 10, mid), t, view.since, view.level)
            p.setOpacity(view.content_alpha)
            p.setFont(font(BODY_PX))
            p.setPen(TEXT)
            p.drawText(QRectF(x0 + 14 + 28, top, shape.w - 14 - 28 - 14, shape.h), Qt.AlignVCenter | Qt.AlignLeft, text)
    else:
        p.setOpacity(view.content_alpha)
        paint_icon(p, view.state, QPointF(x0 + SIDE + 10, top + 6 + HEADER_H / 2), t, view.since, view.level)
        head = header_rect(shape, cx, top)
        if view.mode == "pinned":
            p.setFont(font(BODY_PX, bold=True))
            p.setPen(TEXT)
            p.drawText(head.adjusted(0, 0, -24, 0), Qt.AlignVCenter | Qt.AlignLeft,
                       QFontMetrics(font(BODY_PX, True)).elidedText(view.title or label, Qt.ElideRight, int(head.width() - 24)))
            p.setPen(QPen(_with_alpha(TEXT, 0.6), 1.8))  # close: a small ×
            xc, yc = close_center(shape, cx, top).x(), close_center(shape, cx, top).y()
            p.drawLine(QPointF(xc - 4.5, yc - 4.5), QPointF(xc + 4.5, yc + 4.5))
            p.drawLine(QPointF(xc - 4.5, yc + 4.5), QPointF(xc + 4.5, yc - 4.5))
        else:
            p.setFont(font(LABEL_PX))
            p.setPen(_with_alpha(TEXT, 0.72))
            p.drawText(head, Qt.AlignVCenter | Qt.AlignLeft, label)
            progress = conv.plan_progress(view.task)
            if progress:
                p.setPen(STYLE["done"][1])
                p.drawText(head, Qt.AlignVCenter | Qt.AlignRight, progress)
        measure = measure_with(BODY_PX)
        width = (view.layout_w or shape.w) - 2 * SIDE
        bx0 = cx - (view.layout_w or shape.w) / 2
        messages = hover_messages(view.task) if view.mode == "hover" else (view.task.messages if view.task else [])
        bubbles, _ = conv.layout(messages, width, measure, current=view.state in ("speaking", "turn", "caution"))
        if view.mode == "hover":
            bubbles, _ = conv.newest_that_fit(bubbles, shape.h - HEADER_H - 14, keep_first=True)
        y0 = top + 6 + HEADER_H + (4 if view.mode == "hover" else 10)
        if view.mode == "pinned":  # the talk scrolls under a fixed header
            p.setClipRect(QRectF(x0, y0 - 4, shape.w, shape.h - FOOTER_H - (y0 - 4 - top)), Qt.IntersectClip)
            y0 -= view.scroll
        for b in bubbles:
            paint_bubble(p, b, bx0 + SIDE, y0, color)
        if view.mode == "pinned":
            p.setClipPath(path)
            paint_footer(p, shape, cx, view, top)
    p.restore()


def footer_layout(shape: Shape, cx: float, top: float = TOP) -> dict[str, QRectF]:
    """Where the parts of the pinned island's bottom row sit; painting and clicks share it."""
    x0, y0 = cx - shape.w / 2 + SIDE, top + shape.h - FOOTER_H
    out = {"line": QRectF(x0, y0, shape.w - 2 * SIDE, 1), "recent": QRectF(x0, y0 + 8, shape.w - 2 * SIDE, 20)}
    y = y0 + 38
    for i in range(len(SWATCHES)):
        out[f"swatch{i}"] = QRectF(x0 + i * 26, y, 18, 18)
    out["button"] = QRectF(x0 + len(SWATCHES) * 26 + 14, y - 3, 128, 24)
    out["clear"] = QRectF(cx + shape.w / 2 - SIDE - 168, y - 3, 168, 24)
    return out


def paint_footer(p: QPainter, shape: Shape, cx: float, view: View, top: float = TOP) -> None:
    box = footer_layout(shape, cx, top)
    p.setPen(QPen(_with_alpha(TEXT, 0.12), 1))
    p.drawLine(box["line"].topLeft(), box["line"].topRight())
    p.setFont(font(LABEL_PX))
    dim = _with_alpha(TEXT, 0.6)
    p.setPen(dim)
    items = " · ".join(f"{title} ({when})" for when, title in view.recent) or "chưa có"
    p.drawText(box["recent"], Qt.AlignVCenter | Qt.AlignLeft,
               QFontMetrics(font(LABEL_PX)).elidedText(f"Việc trước: {items}", Qt.ElideRight, int(box["recent"].width())))
    for i, hexcolor in enumerate(SWATCHES):  # the island's colour (founder, 02/11: last, but there)
        r = box[f"swatch{i}"]
        chosen = hexcolor.lower() == view.color.lower()
        p.setPen(QPen(QColor(255, 255, 255) if chosen else _with_alpha(TEXT, 0.35), 2 if chosen else 1.2))
        p.setBrush(QColor(hexcolor) if hexcolor != "#000000" else QColor(20, 20, 22))
        p.drawEllipse(r.center(), 9, 9)
    b = box["button"]  # a small switch: the round button on or off
    track = QRectF(b.left(), b.center().y() - 8, 30, 16)
    on = view.show_button
    p.setPen(Qt.NoPen)
    p.setBrush(STYLE["done"][1] if on else _with_alpha(TEXT, 0.25))
    p.drawRoundedRect(track, 8, 8)
    p.setBrush(QColor(255, 255, 255))
    p.drawEllipse(QPointF(track.right() - 8 if on else track.left() + 8, track.center().y()), 6, 6)
    p.setPen(dim)
    p.drawText(QRectF(track.right() + 8, b.top(), b.width() - 38, b.height()), Qt.AlignVCenter | Qt.AlignLeft, "Nút tròn")
    c = box["clear"]
    red = STYLE["turn"][1]
    p.setPen(QPen(red if view.confirm_clear else _with_alpha(TEXT, 0.3), 1.2))
    p.setBrush(_with_alpha(red, 0.18) if view.confirm_clear else Qt.NoBrush)
    p.drawRoundedRect(c, 12, 12)
    p.setPen(red if view.confirm_clear else dim)
    p.drawText(c, Qt.AlignCenter, "Bấm lần nữa để xoá" if view.confirm_clear else "Xoá lịch sử")


def _bubble_path(r: QRectF, tail_right: bool) -> QPainterPath:
    big, small = 14.0, 4.0
    tl, tr = big, big
    br, bl = (small, big) if tail_right else (big, small)
    path = QPainterPath(QPointF(r.left() + tl, r.top()))
    path.lineTo(r.right() - tr, r.top())
    path.quadTo(r.right(), r.top(), r.right(), r.top() + tr)
    path.lineTo(r.right(), r.bottom() - br)
    path.quadTo(r.right(), r.bottom(), r.right() - br, r.bottom())
    path.lineTo(r.left() + bl, r.bottom())
    path.quadTo(r.left(), r.bottom(), r.left(), r.bottom() - bl)
    path.lineTo(r.left(), r.top() + tl)
    path.quadTo(r.left(), r.top(), r.left() + tl, r.top())
    path.closeSubpath()
    return path


def paint_bubble(p: QPainter, b: conv.Bubble, ox: float, oy: float, accent: QColor) -> None:
    rect = QRectF(ox + b.x, oy + b.y, b.w, b.h)
    path = _bubble_path(rect, tail_right=b.who == "me")
    p.setPen(QPen(accent, 1.5) if b.current else Qt.NoPen)
    p.setBrush(ME_COLOR if b.who == "me" else TUTOR_COLOR)
    p.drawPath(path)
    p.setFont(font(BODY_PX))
    y = rect.top() + conv.PAD_Y
    if not b.plan:
        p.setPen(QColor(255, 255, 255) if b.who == "me" else TEXT)
        for line in b.lines:
            p.drawText(QRectF(rect.left() + conv.PAD_X, y, rect.width(), conv.LINE_H), Qt.AlignVCenter | Qt.AlignLeft, line)
            y += conv.LINE_H
        return
    p.setPen(TEXT)
    p.drawText(QRectF(rect.left() + conv.PAD_X, y, rect.width(), conv.LINE_H), Qt.AlignVCenter | Qt.AlignLeft, b.lines[0])
    y += conv.LINE_H
    measure = measure_with(BODY_PX)
    inner = rect.width() - 2 * conv.PAD_X - conv.INDENT
    green, grey = STYLE["done"][1], _with_alpha(TEXT, 0.6)
    for n, part in enumerate(b.plan):
        col = green if n == b.part else grey
        marker = QPointF(rect.left() + conv.PAD_X + 6, y + conv.LINE_H / 2)
        p.setPen(QPen(col, 1.6))
        p.setBrush(col if n < b.part else Qt.NoBrush)
        p.drawEllipse(marker, 4.5, 4.5)
        if n == b.part:
            p.setPen(Qt.NoPen)
            p.setBrush(col)
            p.drawEllipse(marker, 2, 2)
        p.setPen(col if n == b.part else grey)
        for line in conv.wrap(f"{n + 1}. {part}", inner, measure):
            p.drawText(QRectF(rect.left() + conv.PAD_X + conv.INDENT, y, inner, conv.LINE_H),
                       Qt.AlignVCenter | Qt.AlignLeft, line)
            y += conv.LINE_H


# --- A4: the window ---------------------------------------------------------------------

HOVER_DWELL_S = 0.25     # the mouse rests this long on the closed island before it opens
LEAVE_S = 0.30           # and leaves for this long before it closes again
DONE_HOLD_S = 3.0        # "done" (or an error) shows this long, then the island rests
POLL_MS, FRAME_MS = 60, 16
AVOID_MARGIN = 20        # logical px around the island where the ring's target counts as underneath
SCROLL_STEP = 42         # px per wheel notch in the pinned island
FLAGS = Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool | Qt.WindowDoesNotAcceptFocus


class Island(QWidget):
    """The island on the screen. Never takes the focus; takes clicks only while open or pinned."""

    def __init__(self, screen=None, clock=time.monotonic, cursor=None):
        super().__init__(None, FLAGS)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self._screen = screen or QGuiApplication.primaryScreen()
        self._clock = clock
        self._cursor = cursor or (lambda: QCursor.pos(self._screen))
        self.view = View()
        self.base = QColor(0, 0, 0)
        self.mode = "collapsed"
        self.click_through = True
        self.scroll = 0.0
        self._state_at = self._last = clock()
        self._inside_since: float | None = None
        self._outside_since: float | None = None
        self._avoid: QPointF | None = None
        self.hidden_for_target = False     # the ring points under the closed island: get out of the way
        self.level_source = None           # A6: a callable giving the mic or voice level 0..1 (Meter.value)
        # A9: the pinned island's bottom row. The app sets these and saves what she picks.
        self.recent: list[tuple[str, str]] = []
        self.show_button = True
        self.color = "#000000"
        self.on_color = self.on_button_toggle = self.on_clear = None
        self._confirm_until = 0.0
        # A7: read from worker threads, so plain tuples swapped whole (logical x, y, w, h), or None
        self.cover: tuple[int, int, int, int] | None = None        # what to grey out for the stillness check
        self.takes_clicks: tuple[int, int, int, int] | None = None  # where a click lands on the island, not her app
        self.no_hover = False              # the ring points under where the open island would be
        self.morph = Morph(self._target())
        self._frame = QTimer(self)
        self._frame.setInterval(FRAME_MS)
        self._frame.timeout.connect(self.tick)
        self._poll = QTimer(self)
        self._poll.setInterval(POLL_MS)
        self._poll.timeout.connect(self.poll)
        self._fit()
        self._apply_click_through()

    # what the tutor is doing -------------------------------------------------------------

    def set_state(self, state: str, task: conv.Task | None = None, level: float | None = None) -> None:
        if state != self.view.state:
            self._state_at = self._clock()
        self.view.state = state
        if task is not None:
            self.view.task = task
            self.view.title = task.question
        self.view.level = level
        self._relayout()

    def set_level(self, level: float | None) -> None:
        self.view.level = level

    def task_changed(self) -> None:
        """Call after adding to the current task: the open island may need to grow."""
        if self.view.task is not None:
            self.view.title = self.view.task.question
        self._relayout()

    def set_avoid(self, point: QPointF | None, box: QRectF | None = None) -> None:
        """The ring's target in logical screen coordinates, or None when there is no ring. With a box to read,
        the island gets out of the way of all of it, not only of its centre."""
        self._avoid = point
        self.hidden_for_target = self.no_hover = False
        if point is not None:
            closed = self._screen_rect(target_shape("collapsed", *self._screen_wh(), *self._sizes("collapsed")[:1]))
            opened = self._screen_rect(target_shape("hover", *self._screen_wh(), 0, *self._sizes("hover")[1:]))
            def under(rect: QRect) -> bool:
                rect = rect.adjusted(-AVOID_MARGIN, -AVOID_MARGIN, AVOID_MARGIN, AVOID_MARGIN)
                return rect.contains(point.toPoint()) or (box is not None and rect.toRectF().intersects(box))

            if under(closed):
                self.hidden_for_target = True
            elif under(opened):
                self.no_hover = True
            covered = self.mode != "collapsed" and self.own_rect().contains(point.toPoint())
            if self.mode != "collapsed" and (self.hidden_for_target or self.no_hover or covered):
                self.set_mode("collapsed")  # open or pinned over her target: close
        self._apply_click_through()
        self.update()

    # opening and closing -----------------------------------------------------------------

    def set_mode(self, mode: str) -> None:
        self.mode = self.view.mode = mode
        self.scroll = 0.0
        self._inside_since = self._outside_since = None
        self._apply_click_through()
        self._relayout()

    def poll(self) -> None:
        """Every 60 ms: where the mouse is. A click-through window gets no mouse events of its own."""
        now = self._clock()
        inside = self.contains_global(QPointF(self._cursor()))
        if self.mode == "collapsed":
            if inside and not (self.hidden_for_target or self.no_hover):
                self._inside_since = self._inside_since if self._inside_since is not None else now
                if now - self._inside_since >= HOVER_DWELL_S:
                    self.set_mode("hover")
            else:
                self._inside_since = None
        elif self.mode == "hover":
            if not inside:
                self._outside_since = self._outside_since if self._outside_since is not None else now
                if now - self._outside_since >= LEAVE_S:
                    self.set_mode("collapsed")
            else:
                self._outside_since = None
        if self.isVisible():
            _win_topmost(self)

    def global_click(self, pos: QPointF) -> bool:
        """A click anywhere on the screen, from the app's click watcher. True when it was on the island,
        so the session does not take it as her step. A click outside closes the pinned island."""
        on = self.contains_global(pos)
        if self.mode == "pinned" and not on:
            self.set_mode("collapsed")
        return on and not self.click_through

    def contains_global(self, pos: QPointF) -> bool:
        if self.hidden_for_target:
            return False
        local = QPointF(pos) - QPointF(self.geometry().topLeft())
        return outline(self.morph.shape(), self.width() / 2).contains(local)

    def own_rect(self) -> QRect:
        """Logical screen rectangle the island covers now; the app greys it out of screenshots."""
        return self._screen_rect(self.morph.shape())

    # Qt events -----------------------------------------------------------------------------

    def showEvent(self, event):
        super().showEvent(event)
        self._apply_click_through()
        self._poll.start()

    def hideEvent(self, event):
        super().hideEvent(event)
        self._publish()

    def mouseReleaseEvent(self, event):
        if event.button() != Qt.LeftButton:
            return
        if self.mode == "hover":
            self.set_mode("pinned")
        elif self.mode == "pinned":
            pos = event.position()
            x = close_center(self.morph.shape(), self.width() / 2)
            if math.dist((pos.x(), pos.y()), (x.x(), x.y())) <= 12:
                self.set_mode("collapsed")
                return
            self.footer_click(pos)

    def footer_click(self, pos: QPointF) -> None:
        box = footer_layout(self.morph.shape(), self.width() / 2)
        for i, hexcolor in enumerate(SWATCHES):
            if box[f"swatch{i}"].adjusted(-3, -3, 3, 3).contains(pos):
                self.color, self.base = hexcolor, QColor(hexcolor)
                if self.on_color:
                    self.on_color(hexcolor)
        if box["button"].contains(pos):
            self.show_button = not self.show_button
            if self.on_button_toggle:
                self.on_button_toggle(self.show_button)
        if box["clear"].contains(pos):
            now = self._clock()
            if now <= self._confirm_until:  # the second click: delete
                self._confirm_until = 0.0
                self.recent = []
                if self.on_clear:
                    self.on_clear()
            else:
                self._confirm_until = now + CONFIRM_S
                QTimer.singleShot(int(CONFIRM_S * 1000) + 50, self.update)  # the question goes away by itself
        self.update()

    def wheelEvent(self, event):
        if self.mode != "pinned":
            return
        self.scroll = _clamp(self.scroll - event.angleDelta().y() / 120 * SCROLL_STEP, 0, self.max_scroll())
        self.view.scroll = self.scroll
        self.update()

    def max_scroll(self) -> float:
        shape = self.morph.target
        _, _, needed = self._sizes("pinned")
        return max(0.0, needed - shape.h)

    def paintEvent(self, _event):
        if self.hidden_for_target:
            return
        now = self._clock()
        v = self.view
        v.since = now - self._state_at
        v.scroll = self.scroll
        v.recent, v.show_button, v.color = tuple(self.recent), self.show_button, self.color
        v.confirm_clear = now <= self._confirm_until
        v.layout_w = self.morph.target.w if self.mode != "collapsed" else 0.0
        prog = self.morph.progress()
        v.content_alpha = _clamp((prog - 0.55) / 0.45, 0, 1) if self.mode != "collapsed" else _clamp((prog - 0.4) / 0.6, 0, 1)
        p = QPainter(self)
        paint_island(p, self.morph.shape(), self.width() / 2, v, now, base=self.base)
        p.end()

    # animation -----------------------------------------------------------------------------

    def tick(self) -> None:
        now = self._clock()
        dt, self._last = now - self._last, now
        self.morph.step(dt)
        if self.level_source is not None and self.view.state in ("listening", "speaking"):
            self.view.level = self.level_source()
        if self.view.state in ("done", "error") and now - self._state_at >= DONE_HOLD_S:
            self.set_state("idle")
        if not self.morph.moving():
            self._fit()
        self.update()
        if not self.morph.moving() and self.view.state == "idle":
            self._frame.stop()  # nothing moves: no CPU spent while she works

    def _relayout(self) -> None:
        self.morph.set_target(self._target())
        self._fit()
        self._last = self._clock()
        if not self._frame.isActive():
            self._frame.start()
        self.update()

    def _sizes(self, mode: str) -> tuple[float, float, float]:
        v = View(mode, self.view.state, self.view.task, self.view.title)
        return content_size(v, *self._screen_wh())

    def _target(self) -> Shape:
        tw, w, h = self._sizes(self.mode)
        return target_shape(self.mode, *self._screen_wh(), tw, w, h)

    def _screen_wh(self) -> tuple[float, float]:
        g = self._screen.geometry()
        return float(g.width()), float(g.height())

    def _screen_rect(self, shape: Shape) -> QRect:
        g = self._screen.geometry()
        return QRect(round(g.x() + g.width() / 2 - shape.w / 2), g.y() + TOP, round(shape.w), round(shape.full_h))

    def _fit(self) -> None:
        """Window = the larger of the shape now and the shape it is heading to, so it resizes twice per change."""
        now, goal = self.morph.shape(), self.morph.target
        w = math.ceil(max(now.w, goal.w)) + 4
        h = math.ceil(TOP + max(now.full_h, goal.full_h)) + 4
        g = self._screen.geometry()
        rect = QRect(g.x() + (g.width() - w) // 2, g.y(), w, h)
        if rect != self.geometry():
            self.setGeometry(rect)
            if self.isVisible():
                self._apply_click_through()  # T7 (02/11): Windows forgot the click-through after a resize
        self._publish()

    def _publish(self) -> None:
        g = self.geometry()
        box = (g.x(), g.y(), g.width(), g.height())
        self.cover = None if self.hidden_for_target or not self.isVisible() else box
        self.takes_clicks = None if self.click_through or not self.isVisible() else box

    def _apply_click_through(self) -> None:
        self.click_through = self.mode == "collapsed" or self.hidden_for_target
        self.setAttribute(Qt.WA_TransparentForMouseEvents, self.click_through)
        self._publish()
        if self.isVisible():
            _win_harden(self, click_through=self.click_through)


# --- previews for the founder -----------------------------------------------------------

def _demo_task(step: int = 3) -> conv.Task:
    """Made-up words, not hers."""
    task = conv.Task()
    task.hear("Mẹ muốn xuất giáo án ra PDF rồi gửi cho tiệm in")
    if step >= 1:
        task.plan(["Xuất giáo án ra PDF", "Mở chat tiệm in trong Zalo", "Gửi file PDF"])
    if step >= 2:
        task.say("Bấm chữ File ở góc trên bên trái.")
        task.say("Bấm Export ở cột bên trái.")
    if step >= 3:
        task.say("Bấm nút Create PDF/XPS ở giữa màn hình để tạo bản PDF.")
    return task


def render_preview(out_dir: str, on: str | None = None, scale: float = 1.25) -> list[Path]:
    from PIL import Image
    from PySide6.QtGui import QImage

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    if on:
        bg = QImage(on).convertToFormat(QImage.Format_ARGB32)
    else:
        bg = QImage(1920, 1080, QImage.Format_ARGB32)
        bg.fill(QColor(236, 236, 240))
    sw, sh = bg.width() / scale, bg.height() / scale
    cx = sw / 2

    def to_pil(img: QImage) -> Image.Image:
        img = img.convertToFormat(QImage.Format_RGBA8888)
        return Image.frombuffer("RGBA", (img.width(), img.height()), bytes(img.constBits()), "raw", "RGBA", 0, 1).convert("RGB")

    def frame(views: list[tuple[View, Shape, float]], t: float, crop: QRectF) -> QImage:
        img = bg.copy()
        p = QPainter(img)
        p.scale(scale, scale)
        for view, shape, y in views:
            paint_island(p, shape, cx, view, t, top=y)
        p.end()
        return img.copy(round(crop.x() * scale), round(crop.y() * scale), round(crop.width() * scale), round(crop.height() * scale))

    def shape_for(view: View) -> Shape:
        tw, w, h = content_size(view, sw, sh)
        return target_shape(view.mode, sw, sh, tw, w, h)

    files = []
    # 1. a still sheet: every state closed, then open and pinned
    rows: list[tuple[View, Shape, float]] = []
    y = TOP
    for state in STYLE:
        task = _demo_task(0 if state == "listening" else 3)
        if state == "caution":
            task.say("Bấm Yes thì file PDF cũ cùng tên sẽ bị thay bằng file mới.")
        if state == "done":
            task.say("Xong phần một: đã có bản PDF. Giờ sang phần hai, mở Zalo.")
        v = View("collapsed", state, task, since=1.0)
        rows.append((v, shape_for(v), y))
        y += COLLAPSED_H + 10
    hover = View("hover", "turn", _demo_task(), since=1.0)
    rows.append((hover, shape_for(hover), y + 6))
    y += shape_for(hover).full_h + 22
    pinned = View("pinned", "turn", _demo_task(), title="Xuất giáo án ra PDF rồi gửi tiệm in", since=1.0)
    rows.append((pinned, shape_for(pinned), y))
    y += shape_for(pinned).full_h + 10
    img = bg.copy() if y * scale <= bg.height() else QImage(bg.width(), round(y * scale) + 20, QImage.Format_ARGB32)
    if y * scale > bg.height():
        img.fill(QColor(236, 236, 240))
        pp = QPainter(img)
        pp.drawImage(0, 0, bg)
        pp.end()
    p = QPainter(img)
    p.scale(scale, scale)
    for view, shape, yy in rows:
        paint_island(p, shape, cx, view, 0.35, top=yy)
    p.end()
    crop_w = PINNED_W + 120
    sheet = img.copy(round((cx - crop_w / 2) * scale), 0, round(crop_w * scale), round((y + 10) * scale))
    files.append(out / "island_sheet.png")
    sheet.save(str(files[-1]))

    # 2. each state closed, with its movement
    crop = QRectF(cx - 200, 0, 400, COLLAPSED_H + 2 * TOP)
    frames, fps = [], 20
    for state in STYLE:
        task = _demo_task(0 if state == "listening" else 3)
        for i in range(int(1.6 * fps)):
            t = i / fps
            v = View("collapsed", state, task, since=t)
            frames.append(to_pil(frame([(v, shape_for(v), TOP)], t, crop)))
    files.append(out / "island_states.gif")
    frames[0].save(files[-1], save_all=True, append_images=frames[1:], duration=1000 // fps, loop=0)

    # 3. the changes of shape: closed → open on hover → pinned → closed, on the springs
    crop = QRectF(cx - PINNED_W / 2 - 30, 0, PINNED_W + 60, 0.55 * sh + 40)
    script = [("collapsed", "listening", 1.4), ("collapsed", "thinking", 1.0), ("collapsed", "speaking", 1.2),
              ("collapsed", "turn", 0.8), ("hover", "turn", 1.8), ("pinned", "turn", 1.8), ("collapsed", "turn", 1.0),
              ("collapsed", "done", 1.2)]
    first = View("collapsed", "idle", None)
    morph = Morph(shape_for(first))
    frames, t = [], 0.0
    words = _demo_task(0).question.split()
    for mode, state, secs in script:
        start = t
        for _ in range(int(secs * fps)):
            since = t - start
            task = _demo_task(3)
            if state == "listening":
                task = conv.Task()
                task.hear(" ".join(words[:max(1, int(len(words) * min(1, since / (secs * 0.8))))]))
            elif state == "done":
                task.say("Xong phần một: đã có bản PDF. Giờ sang phần hai, mở Zalo.")
            v = View(mode, state, task, title="Xuất giáo án ra PDF rồi gửi tiệm in", since=since)
            goal = shape_for(v)
            v.layout_w = goal.w
            morph.set_target(goal)
            shape = morph.step(1 / fps)
            prog = morph.progress()
            v.content_alpha = _clamp((prog - 0.55) / 0.45, 0, 1) if mode != "collapsed" else _clamp((prog - 0.4) / 0.6, 0, 1)
            frames.append(to_pil(frame([(v, shape, TOP)], t, crop)))
            t += 1 / fps
    files.append(out / "island_morph.gif")
    frames[0].save(files[-1], save_all=True, append_images=frames[1:], duration=1000 // fps, loop=0)
    return files


def demo() -> None:
    """The real window cycling through a made-up task; rest the mouse on it to open, click to pin."""
    import signal

    from PySide6.QtWidgets import QApplication

    signal.signal(signal.SIGINT, signal.SIG_DFL)
    app = QApplication(sys.argv[:1])
    isl = Island()
    isl.show()
    full = _demo_task(3)
    script = [("listening", 0), ("listening", 1), ("thinking", 2), ("speaking", 3), ("turn", 3), ("loading", 3),
              ("caution", 4), ("done", 5), ("idle", 5)]
    step = [0]

    def next_state():
        state, k = script[step[0] % len(script)]
        task = conv.Task()
        words = full.question.split()
        task.hear(" ".join(words[:4]) if k == 0 else full.question)
        if k >= 2:
            task.plan(["Xuất giáo án ra PDF", "Mở chat tiệm in trong Zalo", "Gửi file PDF"])
        if k >= 3:
            for m in full.messages[2:]:
                task.say(m.text)
        if k >= 4:
            task.say("Bấm Yes thì file PDF cũ cùng tên sẽ bị thay bằng file mới.")
        if k >= 5:
            task.say("Xong phần một: đã có bản PDF. Giờ sang phần hai, mở Zalo.")
        isl.set_state(state, task)
        step[0] += 1

    timer = QTimer()
    timer.timeout.connect(next_state)
    timer.start(2200)
    next_state()
    print("Island đang chạy ở giữa mép trên. Rê chuột lên ô để mở, bấm vào để ghim, bấm × để đóng. Ctrl+C để tắt.")
    app.exec()


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(prog="python -m screentutor.island")
    ap.add_argument("--preview", metavar="THƯ_MỤC")
    ap.add_argument("--on", metavar="ẢNH", help="ảnh màn hình làm nền")
    ap.add_argument("--demo", action="store_true")
    args = ap.parse_args(argv)
    if args.demo:
        demo()
        return
    if not args.preview:
        ap.error("cần --preview hoặc --demo")
    app = QGuiApplication.instance() or QGuiApplication(sys.argv[:1])
    for f in render_preview(args.preview, args.on):
        print(f"Đã lưu {f}")
    del app


if __name__ == "__main__":
    main()
