"""Pure scoring functions: turn a model's point into hit / near / miss.

Coordinates flow through three spaces:
  model answer  --(convention)-->  sent-image pixels  --(resize factor)-->  original pixels
The docs disagree on the convention (computer use says pixels, image
understanding says a 0-1000 grid), so every answer is scored under both and
the calibration stage tells us which one the model really uses.
"""

from __future__ import annotations

import math

Box = tuple[int, int, int, int]  # x1, y1, x2, y2 in original-image pixels

CONVENTIONS = ("pixel", "norm1000")


def to_sent_pixels(x: float, y: float, convention: str, sent_w: int, sent_h: int) -> tuple[float, float]:
    """Interpret a raw model point as pixels of the image that was sent."""
    if convention == "pixel":
        return x, y
    if convention == "norm1000":
        return x * sent_w / 1000, y * sent_h / 1000
    raise ValueError(f"unknown convention: {convention}")


def to_original(x: float, y: float, sent_size: tuple[int, int], orig_size: tuple[int, int]) -> tuple[float, float]:
    """Undo a resize: sent-image pixels -> original-image pixels."""
    return x * orig_size[0] / sent_size[0], y * orig_size[1] / sent_size[1]


def distance_to_box(x: float, y: float, box: Box) -> float:
    """0 inside the box (edges included), otherwise distance to the nearest edge."""
    x1, y1, x2, y2 = box
    dx = max(x1 - x, 0, x - x2)
    dy = max(y1 - y, 0, y - y2)
    return math.hypot(dx, dy)


def classify(x: float, y: float, boxes: list[Box], near_px: float) -> tuple[str, float]:
    """Return ("hit"|"near"|"miss", distance to the closest box)."""
    d = min(distance_to_box(x, y, b) for b in boxes)
    if d == 0:
        return "hit", 0.0
    if d <= near_px:
        return "near", d
    return "miss", d


def offset_from_center(x: float, y: float, box: Box) -> tuple[float, float]:
    cx, cy = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
    return x - cx, y - cy


def direction(dx: float, dy: float, dead_zone: float = 4) -> str:
    """Vietnamese label for where the point sits relative to the box centre."""
    horiz = "phải" if dx > dead_zone else "trái" if dx < -dead_zone else ""
    vert = "dưới" if dy > dead_zone else "trên" if dy < -dead_zone else ""
    return "-".join(p for p in (horiz, vert) if p) or "giữa"


def score_point(
    point: tuple[float, float] | None,
    sent_size: tuple[int, int],
    orig_size: tuple[int, int],
    boxes: list[Box],
    near_px: float,
) -> dict:
    """Score one answer under every convention. point=None means the model did not point."""
    if point is None:
        return {c: {"result": "none"} for c in CONVENTIONS}
    out = {}
    for conv in CONVENTIONS:
        sx, sy = to_sent_pixels(point[0], point[1], conv, *sent_size)
        ox, oy = to_original(sx, sy, sent_size, orig_size)
        result, dist = classify(ox, oy, boxes, near_px)
        closest = min(boxes, key=lambda b: distance_to_box(ox, oy, b))
        dx, dy = offset_from_center(ox, oy, closest)
        out[conv] = {
            "result": result,
            "x": round(ox, 1),
            "y": round(oy, 1),
            "distance_px": round(dist, 1),
            "offset": [round(dx, 1), round(dy, 1)],
            "direction": direction(dx, dy),
        }
    return out
