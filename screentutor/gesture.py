"""What her mouse was saying while she asked (B1b, founder 02/11).

She points at something, or circles it, and asks about "cái này". Nothing is drawn
on the screen and no extra picture is sent: the path is worked out here and the model
gets one line of coordinates on the 0-1000 grid, or nothing.

The path may hold more than the gesture: how the mouse got there, and the way to the
round button afterwards. So a circle is looked for inside the path, not across all of
it, and the last gesture wins. A circle beats a stop, because a mouse at rest means
less than a mouse that went round something.

Every threshold here is Claude's estimate, not measured on her hand yet (T13b).
"""

from __future__ import annotations

import math

STOP_PX = 20          # a stop stays within this radius...
STOP_S = 0.6          # ...for at least this long
CLOSE_SHARE = 0.25    # a circle ends this close to where it began, as a share of its box's diagonal
MIN_W, MIN_H = 40, 20 # the smallest box around a circle, in physical px
MIN_TURN_DEG = 300    # how far the path must turn one way
THIN_PX = 6           # points closer than this add noise to the turning, not shape
LOOP_MAX_S = 6.0      # a circle takes less than this; keeps the search short on a long path


def _grid(x: float, y: float, size: tuple[int, int]) -> tuple[int, int]:
    return round(x * 1000 / size[0]), round(y * 1000 / size[1])


def _thin(samples: list[tuple[float, int, int]]) -> list[tuple[float, int, int]]:
    out = samples[:1]
    for s in samples[1:]:
        if math.hypot(s[1] - out[-1][1], s[2] - out[-1][2]) >= THIN_PX:
            out.append(s)
    return out


def _turn(a, b, c) -> float:
    """Signed angle in degrees between the segments a-b and b-c."""
    ux, uy, vx, vy = b[1] - a[1], b[2] - a[2], c[1] - b[1], c[2] - b[2]
    return math.degrees(math.atan2(ux * vy - uy * vx, ux * vx + uy * vy))


def find_circle(samples: list[tuple[float, int, int]]) -> tuple[int, int, int, int] | None:
    """The box (x1, y1, x2, y2) of the last closed loop in the path, the tightest one ending there."""
    pts = _thin(samples)
    turns = [0.0] + [_turn(pts[i - 1], pts[i], pts[i + 1]) for i in range(1, len(pts) - 1)] + [0.0]
    for end in range(len(pts) - 1, 1, -1):
        turned = 0.0
        x1, y1, x2, y2 = pts[end][1], pts[end][2], pts[end][1], pts[end][2]
        for start in range(end - 1, -1, -1):
            if pts[end][0] - pts[start][0] > LOOP_MAX_S:
                break
            _, x, y = pts[start]
            x1, y1, x2, y2 = min(x1, x), min(y1, y), max(x2, x), max(y2, y)
            if abs(turned) >= MIN_TURN_DEG and x2 - x1 >= MIN_W and y2 - y1 >= MIN_H \
                    and math.hypot(x - pts[end][1], y - pts[end][2]) <= CLOSE_SHARE * math.hypot(x2 - x1, y2 - y1):
                return x1, y1, x2, y2
            turned += turns[start]  # the corner at the start point counts only for a loop that begins earlier
    return None


def find_stop(samples: list[tuple[float, int, int]]) -> tuple[float, float] | None:
    """The middle of the last place the mouse stayed for STOP_S."""
    end = len(samples)
    while end > 0:
        anchor = samples[end - 1]
        start = end - 1
        while start > 0 and math.hypot(samples[start - 1][1] - anchor[1], samples[start - 1][2] - anchor[2]) <= STOP_PX:
            start -= 1
        if anchor[0] - samples[start][0] >= STOP_S:
            part = samples[start:end]
            return sum(s[1] for s in part) / len(part), sum(s[2] for s in part) / len(part)
        end -= 1
    return None


def describe(samples: list[tuple[float, int, int]], size: tuple[int, int]) -> str | None:
    """samples: (t, x, y) in physical px of a screen of this size. One line for the model, or None."""
    on_screen = [s for s in samples if 0 <= s[1] < size[0] and 0 <= s[2] < size[1]]
    box = find_circle(on_screen)
    if box:
        x1, y1 = _grid(box[0], box[1], size)
        x2, y2 = _grid(box[2], box[3], size)
        return f"khoanh quanh vùng ({x1}, {y1})-({x2}, {y2}) trên lưới 0-1000"
    stop = find_stop(on_screen)
    if stop:
        x, y = _grid(stop[0], stop[1], size)
        return f"dừng ở ({x}, {y}) trên lưới 0-1000"
    return None
