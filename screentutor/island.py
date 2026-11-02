"""The dynamic island: every state of the tutor lives here, Apple-like (founder, 02/11).

Closed: a small pill at the top centre, black at 80%, so the app below shows through, and
clicks go through it. The mouse over it: fully black, a little wider (never the whole width,
so Word's toolbar stays in sight), the lower edge curved like an upward parabola, and the
talk inside. A click: a plain rectangle with all of the task. While the tutor works, an icon
and a colour say what it is doing, each with its own movement.

A1 is the shape and the spring between shapes, A2 the states, icons and painting. The window
itself (hover, clicks, click-through) comes in A4.

  python -m screentutor.island --preview OUT_DIR [--on SCREENSHOT.png]   # PNG sheet and GIFs
"""

from __future__ import annotations

import argparse
import math
import sys
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPainterPath, QPen

from . import conversation as conv
from .overlay import CAUTION_COLOR, COLOR

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
    "caution": ("Cẩn thận trước khi bấm", QColor(CAUTION_COLOR)),  # the same amber as the ring
    "loading": ("Chờ trang tải", QColor(191, 90, 242)),
    "done": ("Xong rồi", QColor(48, 209, 88)),
    "error": ("Chưa nghe rõ", QColor(142, 142, 147)),
}
TURN_PULSE_S, CAUTION_PULSE_S = 1.2, 1.8   # 1.2 s matches the ring on the screen (overlay.PULSE_S)


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
    return 0.0, w, HEADER_H + 10 + h + 16


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
        head = QRectF(x0 + SIDE + 28, top + 6, shape.w - 2 * SIDE - 28, HEADER_H)
        if view.mode == "pinned":
            p.setFont(font(BODY_PX, bold=True))
            p.setPen(TEXT)
            p.drawText(head.adjusted(0, 0, -24, 0), Qt.AlignVCenter | Qt.AlignLeft,
                       QFontMetrics(font(BODY_PX, True)).elidedText(view.title or label, Qt.ElideRight, int(head.width() - 24)))
            p.setPen(QPen(_with_alpha(TEXT, 0.6), 1.8))  # close: a small ×
            xc, yc = head.right() - 8, head.center().y()
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
        for b in bubbles:
            paint_bubble(p, b, bx0 + SIDE, y0, color)
    p.restore()


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


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(prog="python -m screentutor.island")
    ap.add_argument("--preview", metavar="THƯ_MỤC", required=True)
    ap.add_argument("--on", metavar="ẢNH", help="ảnh màn hình làm nền")
    args = ap.parse_args(argv)
    from PySide6.QtGui import QGuiApplication

    app = QGuiApplication.instance() or QGuiApplication(sys.argv[:1])
    for f in render_preview(args.preview, args.on):
        print(f"Đã lưu {f}")
    del app


if __name__ == "__main__":
    main()
