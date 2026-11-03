"""Is the screen still the one the tutor looked at? (C2, 03/11)

The tutor takes 3-5 s to answer, and she does not wait. In the T13 videos it pointed at a
Zalo toast ("Đã tải xong · Mở thư mục") that had gone 2-4 s before the voice said so, and
told her to click Create PDF/XPS when she had already clicked it and its dialog was open.
So the answer is checked against a fresh look before it is said, and the place it points at
is watched while she has not clicked yet.

Two numbers, between the screenshot the tutor answered and a fresh grab:
  region  the share of the area around the target that changed, the mark's own disc left out
          (the ring or the dot sits there, and its pulse would count as a change)
  whole   the share of the screen's signature cells that changed (still.signature), the edge
          band (where the glow lives) and our own widgets left out
Both images get the same parts blacked out, so the mask never counts as a change.

Thresholds from tutor_eval/stale_replay.py (03/11), on the 29 pointing turns of the T13 videos:
all 5 stale turns caught (region 0.04-0.34, or the whole screen 0.03-0.22 when a box came up
away from the target), 1 fresh turn flagged (the mouse lit up the target's row in Explorer as a
taskbar preview closed: region 0.10, whole 0.034). The next highest fresh turns: region 0.018,
whole 0.011. Chosen on those same turns, so not an independent test; T15 on Windows is.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from PIL import Image, ImageDraw

from .still import changed_fraction, signature

REGION_HALF = (160, 80)   # physical px either side of the target: a toast or a dialog is wider than its button
MARK_R = 75               # the ring's pulse reaches 52 logical px, 65 physical at 125%; with its stroke, 75
EDGE_PX = 48              # the glow's 36 logical px at 125%, and a little
REDUCE = 4                # the region is compared in 4x4 averages: text changes, anti-aliasing does not
TOL = 32                  # grey levels a cell may drift without counting as changed (a row lit by the mouse is ~20)
REGION_MIN = 0.03         # stale: this share of the region changed...
WHOLE_MIN = 0.02          # ...or this share of the whole screen


@dataclass
class Change:
    region: float | None   # None: nothing left of the region once the masks are out (a taskbar icon)
    whole: float

    @property
    def stale(self) -> bool:
        return (self.region is not None and self.region >= REGION_MIN) or self.whole >= WHOLE_MIN


def _mask(size: tuple[int, int], ignore: list[tuple[int, int, int, int]], disc: tuple[int, int] | None) -> Image.Image:
    """255 where the screen is compared, 0 over what moves by itself: our widgets, the edge band, the mark."""
    out = Image.new("L", size, 255)
    d = ImageDraw.Draw(out)
    w, h = size
    for x1, y1, x2, y2 in ignore:
        d.rectangle((x1, y1, x2, y2), fill=0)
    for band in ((0, 0, w, EDGE_PX), (0, h - EDGE_PX, w, h), (0, 0, EDGE_PX, h), (w - EDGE_PX, 0, w, h)):
        d.rectangle(band, fill=0)
    if disc is not None:
        x, y = disc
        d.ellipse((x - MARK_R, y - MARK_R, x + MARK_R, y + MARK_R), fill=0)
    return out


def region_box(target: tuple[int, int], size: tuple[int, int]) -> tuple[int, int, int, int]:
    x, y = target
    return (max(x - REGION_HALF[0], 0), max(y - REGION_HALF[1], 0),
            min(x + REGION_HALF[0], size[0]), min(y + REGION_HALF[1], size[1]))


def compare(before: Image.Image, after: Image.Image, target: tuple[int, int] | None,
            ignore: list[tuple[int, int, int, int]] = (), disc: bool = True) -> Change:
    """How much changed between two screenshots of the same screen. disc: the mark is (or may be) on the target."""
    mask = _mask(before.size, list(ignore), target if disc else None)
    black = Image.new("L", before.size, 0)
    a = Image.composite(before.convert("L"), black, mask)
    b = Image.composite(after.convert("L"), black, mask)
    whole = changed_fraction(signature(a), signature(b), TOL)
    if target is None:
        return Change(None, whole)
    box = region_box(target, before.size)
    if box[2] - box[0] < REDUCE or box[3] - box[1] < REDUCE:
        return Change(None, whole)
    ga, gb, keep = (np.asarray(im.crop(box).reduce(REDUCE), dtype=np.int16) for im in (a, b, mask))
    keep = keep > 128                   # a 4x4 cell mostly outside the masks
    if keep.sum() < 50:
        return Change(None, whole)
    return Change(float(((np.abs(ga - gb) > TOL) & keep).sum() / keep.sum()), whole)
