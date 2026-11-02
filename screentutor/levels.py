"""How loud: the island's sound bars follow her microphone and the tutor's voice (A6).

A level is 0 for silence and 1 for a loud voice, from the RMS of a short block in dBFS.
The meter rises fast and falls slower, so the bars move with the syllables without flicker.
"""

from __future__ import annotations

import math

import numpy as np

FLOOR_DB, CEIL_DB = -50.0, -12.0   # a quiet room reads 0; speaking close to a laptop mic reads near 1
ATTACK, RELEASE = 0.6, 0.18        # share of the gap closed per block, going up and going down
BLOCK_S = 0.04


def level_of(samples) -> float:
    """Float samples in -1..1 to a level 0..1."""
    x = np.asarray(samples, dtype=np.float32).ravel()
    if x.size == 0:
        return 0.0
    rms = float(np.sqrt(np.mean(np.square(x, dtype=np.float64))))
    if rms <= 0:
        return 0.0
    db = 20 * math.log10(rms)
    return min(1.0, max(0.0, (db - FLOOR_DB) / (CEIL_DB - FLOOR_DB)))


def level_of_int16(data: bytes) -> float:
    return level_of(np.frombuffer(data, dtype="<i2").astype(np.float32) / 32768.0)


class Meter:
    """The smoothed level; written by the audio thread, read by the island's frame clock."""

    def __init__(self):
        self.value = 0.0

    def feed(self, level: float) -> float:
        rate = ATTACK if level > self.value else RELEASE
        self.value += (level - self.value) * rate
        return self.value

    def reset(self) -> None:
        self.value = 0.0


def blocks(chunks, rate: int, block_s: float = BLOCK_S):
    """Cut a stream of float arrays into blocks of block_s; the last one may be shorter."""
    size = max(1, round(rate * block_s))
    for chunk in chunks:
        x = np.asarray(chunk, dtype=np.float32).ravel()
        for i in range(0, x.size, size):
            yield x[i:i + size]
