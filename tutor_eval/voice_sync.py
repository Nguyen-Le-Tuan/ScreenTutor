"""C1 (03/11): does the mark go up with the voice? Measured on a screen recording with sound.

Each turn's looking ends when the edge glow fades (the island leaves "thinking"). After that,
the voice is the first 50 ms of sound, and the mark is the first frame where the pointer's red
or amber shows up away from the screen edge (the glow, which has red and orange in it, lives
in the outer 45 px; the island's red icon too), compared with the frames just before the fade,
when no mark is up yet. A ring on the taskbar still shows its upper half and its pulses there.

Before C1 the mark went up as the glow faded and the voice came later: in the T13 videos
(D1-D4) this script finds 29 turns with both, the voice a median of 2.85 s after the mark
(the transcript's times gave 3.0 s over 28). After C1 both should come together.

  .venv/bin/python -m tutor_eval.voice_sync tutor_eval/t12_data/D1.mp4 [more.mp4 ...]   # any OS with ffmpeg

Rule, fixed before the Windows run (03/11; Claude's proposal). lead = voice - mark, over the turns
that point somewhere:
- S-1: the median lead is at most 0.5 s (T13: 2.85 s).
- S-2: no turn has a lead above 1.0 s (T13: 26 of 29).
- S-3: no turn has the mark more than 0.5 s after the voice (lead below -0.5 s; T13: none).
- S-4: no turn shows a mark with no voice at all: she clicked before the tutor spoke and cut it
  off (T13: D4 at 24.2 s, the Export step, and D3 at 49.2 s).
Turns that show nothing (the "done" sentence) are listed and not counted.
"""

from __future__ import annotations

import argparse
import statistics
import subprocess
import sys

import numpy as np

FPS = 10
W, H = 960, 540                  # the frames are read at half size
EDGE = 24                        # px at half size: the glow's 45 px and the island stay outside what is counted
MARK_MIN = 40                    # pointer-coloured px at half size more than just before the fade
BEFORE = (8, 3)                  # frames before the fade that show the screen without a mark
MARK_WITHIN_S = 4.0              # session.SOUND_WAIT_S: later than this, red on the screen is something else
MARK_STAYS = 3                   # frames: the mark stays up until her click; a flash of red is not it
MIN_OFF_S = 0.8                 # a real turn keeps the glow off at least this long; its turning colours dip briefly
AUDIO_STEP_S = 0.05
VOICE_DB = 45.0                  # the recordings are digital silence between sounds
LOOK_AHEAD_S = 8.0               # a turn's voice and mark come within this long after the glow fades


def _pointer(f: np.ndarray) -> int:
    """Pixels in the ring's red (255, 69, 58) or amber (255, 176, 0)."""
    f = f.astype(np.int16)
    r, g, b = f[..., 0], f[..., 1], f[..., 2]
    red = (r > 205) & (g > 35) & (g < 125) & (b < 115)
    amber = (r > 215) & (g > 140) & (g < 205) & (b < 80)
    return int((red | amber).sum())


def glow_of(frame: np.ndarray) -> float:
    """How colourful the screen's rim is, the island and the taskbar left out: only the glow is."""
    rim = [frame[:5, 10:W * 3 // 10], frame[:5, W * 7 // 10:-10], frame[10:-40, :5], frame[10:-40, -5:]]
    return float(np.mean([(s.astype(np.int16).max(axis=2) - s.astype(np.int16).min(axis=2)).mean() for s in rim]))


def read_video(path: str) -> tuple[np.ndarray, np.ndarray]:
    """(glow, pointer away from the edges) per frame at FPS."""
    proc = subprocess.Popen(["ffmpeg", "-loglevel", "error", "-i", path, "-vf", f"fps={FPS},scale={W}:{H}",
                             "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], stdout=subprocess.PIPE)
    glow, pointer = [], []
    size = W * H * 3
    while True:
        buf = proc.stdout.read(size)
        if len(buf) < size:
            break
        frame = np.frombuffer(buf, np.uint8).reshape(H, W, 3)
        glow.append(glow_of(frame))
        pointer.append(_pointer(frame[EDGE:-EDGE, EDGE:-EDGE]))
    proc.wait()
    return np.array(glow), np.array(pointer)


def read_audio(path: str) -> np.ndarray:
    """Loudness in dB of each AUDIO_STEP_S window."""
    raw = subprocess.run(["ffmpeg", "-loglevel", "error", "-i", path, "-vn", "-ac", "1", "-ar", "16000",
                          "-f", "s16le", "-"], capture_output=True, check=True).stdout
    a = np.frombuffer(raw, np.int16).astype(float)
    n = round(16000 * AUDIO_STEP_S)
    k = len(a) // n
    return 20 * np.log10(np.sqrt((a[:k * n].reshape(k, n) ** 2).mean(axis=1)) + 1)


def glowing(glow: np.ndarray) -> np.ndarray:
    """Per frame: is the tutor looking? Dips shorter than MIN_OFF_S are its colours turning, not a turn ending."""
    lo, hi = np.percentile(glow, 10), np.percentile(glow, 90)
    if hi - lo < 8:
        raise ValueError("no edge glow in this recording: it cannot be cut into turns")
    on = glow > lo + 0.5 * (hi - lo)
    short = round(MIN_OFF_S * FPS)
    i = 0
    while i < len(on):
        if on[i]:
            i += 1
            continue
        j = i
        while j < len(on) and not on[j]:
            j += 1
        if 0 < i and j < len(on) and j - i < short:
            on[i:j] = True
        i = j
    return on


def turns(glow: np.ndarray, pointer: np.ndarray, loud: np.ndarray) -> list[dict]:
    """One row per glow fade: when it faded, when the voice came, when the mark went up (seconds, or None)."""
    on = glowing(glow)
    offs = [i for i in range(1, len(on)) if on[i - 1] and not on[i]]
    ons = [i for i in range(1, len(on)) if on[i] and not on[i - 1]] + [len(on)]
    rows = []
    for off in offs:
        end = min(min(i for i in ons if i > off), off + round(LOOK_AHEAD_S * FPS), len(pointer))
        before = pointer[max(off - BEFORE[0], 0):max(off - BEFORE[1], 1)]
        quiet = float(np.median(before)) if len(before) else 0.0
        last = min(end, off + round(MARK_WITHIN_S * FPS))
        up = [i for i in range(max(off - 2, 0), last) if (pointer[i:i + MARK_STAYS] >= quiet + MARK_MIN).all()]
        a0, a1 = round((off / FPS - 0.2) / AUDIO_STEP_S), round(end / FPS / AUDIO_STEP_S)
        heard = [j for j in range(max(a0, 0), min(a1, len(loud))) if loud[j] >= VOICE_DB]
        rows.append({"faded": off / FPS, "mark": up[0] / FPS if up else None,
                     "voice": heard[0] * AUDIO_STEP_S if heard else None})
    return rows


def verdict(rows: list[dict]) -> list[str]:
    leads = [r["voice"] - r["mark"] for r in rows if r["mark"] is not None and r["voice"] is not None]
    silent = sum(r["mark"] is not None and r["voice"] is None for r in rows)
    if not leads:
        return ["Không có lượt nào chỉ chỗ: không chấm được."]
    med = statistics.median(leads)
    return [f"{len(leads)} lượt có chỉ chỗ và có tiếng.",
            f"S-1 trung vị lệch {med:+.2f} s (≤ 0,5): {'ĐẠT' if med <= 0.5 else 'TRƯỢT'}",
            f"S-2 lượt lệch trên 1,0 s: {sum(x > 1.0 for x in leads)} (phải 0): "
            f"{'ĐẠT' if all(x <= 1.0 for x in leads) else 'TRƯỢT'}",
            f"S-3 lượt vòng tới sau tiếng quá 0,5 s: {sum(x < -0.5 for x in leads)} (phải 0): "
            f"{'ĐẠT' if all(x >= -0.5 for x in leads) else 'TRƯỢT'}",
            f"S-4 lượt có vòng mà không có tiếng: {silent} (phải 0): {'ĐẠT' if not silent else 'TRƯỢT'}"]


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(prog="python -m tutor_eval.voice_sync")
    ap.add_argument("videos", nargs="+", help="video quay màn hình có tiếng (mp4)")
    args = ap.parse_args(argv)
    every = []
    for path in args.videos:
        glow, pointer = read_video(path)
        try:
            rows = turns(glow, pointer, read_audio(path))
        except ValueError as e:
            sys.exit(f"{path}: {e}")
        for r in rows:
            mark, voice = r["mark"], r["voice"]
            lead = "—" if mark is None or voice is None else f"{voice - mark:+.1f} s"
            print(f"{path.rsplit('/', 1)[-1]}  viền tắt {r['faded']:6.1f}  vòng {'—' if mark is None else f'{mark:6.1f}'}"
                  f"  tiếng {'—' if voice is None else f'{voice:6.1f}'}  tiếng sau vòng {lead}")
        every += rows
    print()
    print("\n".join(verdict(every)))


if __name__ == "__main__":
    main()
