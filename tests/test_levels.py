import math

import numpy as np

from screentutor import levels
from screentutor.levels import Meter, blocks, level_of, level_of_int16


def sine(amp, n=4800, rate=48000, f=220):
    t = np.arange(n) / rate
    return (amp * np.sin(2 * math.pi * f * t)).astype(np.float32)


def test_silence_is_zero_and_a_loud_voice_is_one():
    assert level_of(np.zeros(480)) == 0.0 and level_of([]) == 0.0
    assert level_of(sine(0.9)) == 1.0
    quiet = level_of(sine(10 ** (-30 / 20)))  # peak -30 dB: RMS about -33 dB
    assert 0.35 < quiet < 0.55


def test_int16_reads_like_float():
    x = sine(0.05)
    data = (x * 32767).astype("<i2").tobytes()
    assert abs(level_of_int16(data) - level_of(x)) < 0.01


def test_meter_rises_fast_and_falls_slower():
    m = Meter()
    up = m.feed(1.0)
    m2 = Meter()
    m2.value = 1.0
    down = 1.0 - m2.feed(0.0)
    assert up == levels.ATTACK and abs(down - levels.RELEASE) < 1e-9 and up > down
    m.reset()
    assert m.value == 0.0


def test_blocks_keep_every_sample():
    chunks = [np.ones(3000, np.float32), np.zeros(1000, np.float32)]
    out = list(blocks(chunks, 48000))
    assert [len(b) for b in out] == [1920, 1080, 1000]
    assert sum(len(b) for b in out) == 4000
