import numpy as np

from tutor_eval.voice_sync import AUDIO_STEP_S, FPS, VOICE_DB, glowing, turns, verdict


def _turn(n=100, glow_until=30, mark_at=None, voice_at=None):
    """n frames; the glow is on until glow_until; the mark and the voice start at those frames."""
    glow = np.where(np.arange(n) < glow_until, 100.0, 2.0)
    pointer = np.zeros(n, dtype=int)
    if mark_at is not None:
        pointer[mark_at:] = 300
    loud = np.zeros(round(n / FPS / AUDIO_STEP_S))
    if voice_at is not None:
        loud[round(voice_at / FPS / AUDIO_STEP_S):] = VOICE_DB + 10
    return glow, pointer, loud


def test_the_glow_turning_its_colours_is_not_a_turn_ending():
    glow = np.array([100.0] * 10 + [2.0] * 3 + [100.0] * 10 + [2.0] * 20)   # a 0.3 s dip, then a real end
    on = glowing(glow)
    assert on[:23].all() and not on[23:].any()


def test_before_c1_the_mark_comes_with_the_fade_and_the_voice_later():
    rows = turns(*_turn(mark_at=30, voice_at=60))
    assert rows == [{"faded": 3.0, "mark": 3.0, "voice": 6.0}]


def test_after_c1_the_mark_comes_with_the_voice():
    rows = turns(*_turn(mark_at=36, voice_at=36))
    assert rows[0]["mark"] == rows[0]["voice"] == 3.6


def test_red_that_stays_from_before_the_fade_is_not_a_mark():
    glow, pointer, loud = _turn(voice_at=34)
    pointer[:] = 300   # a red icon on the screen all along
    assert turns(glow, pointer, loud)[0]["mark"] is None


def test_red_long_after_the_fade_is_not_this_turn_s_mark():
    assert turns(*_turn(mark_at=80, voice_at=34))[0]["mark"] is None


def test_the_rules():
    together = [{"faded": 0, "mark": 1.0, "voice": 1.2}] * 5
    assert all("ĐẠT" in line for line in verdict(together)[1:])
    before = [{"faded": 0, "mark": 1.0, "voice": 4.0}] * 5 + [{"faded": 0, "mark": 1.0, "voice": None}]
    lines = verdict(before)
    assert "TRƯỢT" in lines[1] and "TRƯỢT" in lines[2] and "ĐẠT" in lines[3] and "TRƯỢT" in lines[4]
