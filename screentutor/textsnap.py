"""Where a drag to select text should really start and end (K, 03/11).

Spark points to within 20-30 px, and selecting needs better: on the T13 screens it started a
drag inside the first word of a plain-text web address 6 times in 9, which would copy a broken
address. Words on a line are told apart by their gaps: on the real Zalo message at 125%, letters
sit 1-4 px apart and words 5-10 px (measured 03/11). So each end of the drag is moved to the
edge of the word it falls in: the start to where its word begins, the end to where its word
ends. The model still chooses which words; this only stops it cutting one in half.

The end the model gives went past the address into the next word 4 times in 9. So when it also
says which words to select ("boiduong-thunghiem.example": one word, no space), the end is found
by counting that many words on from the start, and its own end is used only when they do not fit
on the line.

Pure: a PIL image in, pixel points out.
"""

from __future__ import annotations

import numpy as np
from PIL import Image

GAP_PX = 5        # physical px of background between two words, at least
INK = 45          # grey levels from the line's background that count as writing
REACH_Y = 18      # how far up or down the model's point may be from the text line
REACH_X = 500     # how far along the line to look for the words


def _line(grey: np.ndarray, x1: int, x2: int, y: int) -> tuple[int, int] | None:
    """(top, bottom) of the line of writing nearest y, or None if there is none."""
    top, bottom = max(y - REACH_Y, 0), min(y + REACH_Y + 1, grey.shape[0])
    band = grey[top:bottom, x1:x2]
    if band.size == 0:
        return None
    ink = (np.abs(band - np.median(band)) > INK).sum(axis=1)
    rows = np.nonzero(ink >= max(3, ink.max() * 0.25))[0]
    if len(rows) == 0:
        return None
    # the run of inked rows closest to y
    runs, start = [], rows[0]
    for a, b in zip(rows, rows[1:]):
        if b != a + 1:
            runs.append((start, a))
            start = b
    runs.append((start, rows[-1]))
    t, b = min(runs, key=lambda r: abs((r[0] + r[1]) / 2 + top - y))
    return int(t + top), int(b + top)


def words(grey: np.ndarray, top: int, bottom: int, x1: int, x2: int) -> list[tuple[int, int]]:
    """(left, right) of each word between x1 and x2 on the line from top to bottom."""
    band = grey[top:bottom + 1, x1:x2]
    if band.size == 0:
        return []
    cols = (np.abs(band - np.median(band)) > INK).any(axis=0)
    runs, start, gap = [], None, 0
    for i, c in enumerate(cols):
        if c:
            if start is None:
                start = i
            gap = 0
            end = i
        elif start is not None:
            gap += 1
            if gap >= GAP_PX:
                runs.append((start + x1, end + x1))
                start, gap = None, 0
    if start is not None:
        runs.append((start + x1, end + x1))
    return runs


def _word(found: list[tuple[int, int]], x: int, edge: int) -> tuple[int, int]:
    """The word x falls well inside; on an edge or in a gap, the word whose start (edge 0) or end (1) is nearest:
    a drag that starts at the very end of the word before is meant for the next one (T13, 1 in 9)."""
    inside = [wd for wd in found if wd[0] + 3 <= x <= wd[1] - 3]
    return inside[0] if inside else min(found, key=lambda wd: abs(wd[edge] - x))


def snap_drag(img: Image.Image, start: tuple[int, int], end: tuple[int, int],
              text: str = "") -> tuple[tuple[int, int], tuple[int, int]]:
    """The drag moved to the edges of the words it starts and ends in; unchanged where no writing is found.
    text: the words to select; their count, from the start, decides where it ends."""
    grey = np.asarray(img.convert("L"), dtype=np.int16)
    w = grey.shape[1]

    def on_line(p):
        x1, x2 = max(p[0] - REACH_X, 0), min(p[0] + REACH_X, w)
        line = _line(grey, x1, x2, p[1])
        return (line, words(grey, line[0], line[1], x1, x2)) if line else (None, [])

    (line_a, words_a), (line_b, words_b) = on_line(start), on_line(end)
    a, b = start, end
    if line_a and words_a:
        first = _word(words_a, start[0], 0)
        a = (first[0] - 2, (line_a[0] + line_a[1]) // 2)
        n = len(text.split())
        i = words_a.index(first)
        if n and i + n <= len(words_a) and (not line_b or abs(line_b[0] - line_a[0]) <= 4):
            return a, (words_a[i + n - 1][1] + 2, a[1])
    if line_b and words_b:
        b = (_word(words_b, end[0], 1)[1] + 2, (line_b[0] + line_b[1]) // 2)
    return a, b
