"""T11 only, not part of the app: a tight outline around Spark's point with SAM 3.1.

Spark gives one point. On the calibration image (02/11) a bare point prompt made
SAM pick the smallest thing under it, one letter on the button. So each call
sends boxes of four sizes around the point, as four objects of one image (one
price; the API takes up to 16), and keeps the answer SAM is surest of. choose()
refuses what it cannot trust.

Protocol (dev.meta.ai docs, read 02/11): POST /responses with the prompt as tokens
in input_text; the answer is text with one <|box;...|> per object.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass

import httpx

from screentutor.tutor import BASE_URL

MODEL = "sam-3.1"
REACH = ((30, 16), (80, 30), (160, 50), (320, 60))   # half width, half height of the boxes sent, physical px
MIN_CONFIDENCE = 0.6
MAX_AREA = 0.06       # share of the screen; a panel or a window is not something to click
POINT_TOL = 4         # px; a box edge may sit this far inside the point
TIMEOUT_S = 5.0

_BOX = re.compile(r"<\|box;x1=(-?\d+);y1=(-?\d+);x2=(-?\d+);y2=(-?\d+);w=\d+;h=\d+(?:;c=([\d.]+))?\|>")


@dataclass
class Found:
    x1: int
    y1: int
    x2: int
    y2: int
    confidence: float = 0.0

    @property
    def area(self) -> int:
        return max(self.x2 - self.x1, 0) * max(self.y2 - self.y1, 0)

    def holds(self, x: float, y: float, tol: int = POINT_TOL) -> bool:
        return self.x1 - tol <= x <= self.x2 + tol and self.y1 - tol <= y <= self.y2 + tol


def build_prompt(point: tuple[int, int], size: tuple[int, int]) -> str:
    """Boxes of every REACH around the point, clipped to the image. Object ids start at 1."""
    x, y = point
    w, h = size
    tokens = []
    for n, (rx, ry) in enumerate(REACH, 1):
        x1, y1, x2, y2 = max(x - rx, 0), max(y - ry, 0), min(x + rx, w - 1), min(y + ry, h - 1)
        tokens.append(f"{n}<|box;x1={x1};y1={y1};x2={x2};y2={y2};w={w};h={h}|>")
    return "<0f>" + ",".join(tokens)


def build_body(point: tuple[int, int], size: tuple[int, int], image_data_url: str) -> dict:
    return {
        "model": MODEL,
        "input": [{"type": "message", "role": "user", "content": [
            {"type": "input_text", "text": build_prompt(point, size)},
            {"type": "input_image", "image_url": image_data_url},
        ]}],
        "metadata": {"include_confidence": "true", "mask_encoding": "one_bit"},
    }


def parse_boxes(text: str) -> list[Found]:
    return [Found(int(x1), int(y1), int(x2), int(y2), float(c or 0)) for x1, y1, x2, y2, c in _BOX.findall(text)]


def choose(found: list[Found], point: tuple[int, int], size: tuple[int, int]) -> Found | None:
    """The answer SAM is surest of, among those that hold the point and are small enough to be one control."""
    limit = MAX_AREA * size[0] * size[1]
    fair = [f for f in found if f.confidence >= MIN_CONFIDENCE and f.holds(*point) and 0 < f.area <= limit]
    return max(fair, key=lambda f: (f.confidence, -f.area), default=None)


class Segmenter:
    def __init__(self, api_key: str, base_url: str = BASE_URL, timeout: float = TIMEOUT_S):
        if not api_key:
            raise ValueError("MODEL_API_KEY is empty")
        self._http = httpx.Client(base_url=base_url, timeout=timeout,
                                  headers={"Authorization": f"Bearer {api_key}"})

    def close(self) -> None:
        self._http.close()

    def around(self, point: tuple[int, int], size: tuple[int, int], image_data_url: str) -> tuple[list[Found], float]:
        """Every box SAM answered, and the seconds it took. Raises on a network or API error."""
        started = time.perf_counter()
        r = self._http.post("/responses", json=build_body(point, size, image_data_url))
        elapsed = time.perf_counter() - started
        r.raise_for_status()
        text = "".join(part.get("text") or "" for item in r.json().get("output") or []
                       for part in item.get("content") or [])
        return parse_boxes(text), elapsed
