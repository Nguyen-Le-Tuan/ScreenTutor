"""C2 (03/11): would screentutor.fresh have caught the turns where the screen moved on? Replayed on video.

For each turn of a T13 recording that points somewhere and speaks (tutor_eval.voice_sync), two
frames: S, just before the edge glow comes up (the moment of the tutor's screenshot), and G,
0.6 s before the voice (when C1 hands the sentence to the voice: the moment C2 checks). At G
the old ring is already on the screen, so its disc is left out of both, as it will be on
Windows; the mouse pointer is in these recordings but not in the app's own screenshots.

  .venv/bin/python -m tutor_eval.stale_replay sheets tutor_eval/t12_data/D1.mp4 ...   # S and G, to label by eye
  .venv/bin/python -m tutor_eval.stale_replay score  tutor_eval/t12_data/D1.mp4 ...   # the numbers, against STALE

Frames and sheets go to tutor_eval/t12_data/replay/ (gitignored: they show her real chats).

Labels: by eye from the sheets, written down before the numbers were printed (03/11).
Rule (Claude's proposal; the thresholds come from these same 29 turns, so this is not an
independent test; T15 on Windows is):
- R-1: every stale turn is caught.
- R-2: at most one fresh turn is flagged (a false alarm costs a silent second look, ~4 s).

Result (03/11), with screentutor.fresh as committed: 5 of 5 stale turns caught, 1 of 24 fresh
turns flagged (D1 #6: the mouse lit up the target's own row in Explorer while a taskbar preview
closed). Both rules pass. The recordings show the mouse pointer and the app's grabs do not, and
the target's disc is left out here because the old ring covers it at G; on Windows it is left
out too, so the numbers mean the same thing.
"""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from screentutor.fresh import compare, region_box
from tutor_eval.voice_sync import FPS, glowing, read_audio, read_video, turns

OUT = Path("tutor_eval/t12_data/replay")
# The turns where the screen at G was no longer the one at S, by eye, before any number (03/11).
# Numbered as in the sheets: the turns of each video that point somewhere and speak, from 0.
STALE = {
    ("D1.mp4", 4): "the Zalo toast 'Mở thư mục' has gone, a WPS popup has come up",
    ("D4.mp4", 1): "she clicked Create PDF/XPS herself: the Save As dialog is open",
    ("D4.mp4", 3): "the Confirm Save As box is on top; the tutor says 'click Publish again'",
    ("D3.mp4", 2): "the Zalo toast has gone",
    ("D3.mp4", 6): "the Zalo toast has gone",
}
# Fresh but wrong (not C2's business): D2 #5-#9 point at the plain text that is not a link.
BEFORE_VOICE_S = 0.6       # say-ready to first sound, measured on the T13 videos (0.2-0.7 s)
ISLAND = (0.3, 0.7, 200)   # the island's widest reach: x from 30% to 70% of the width, down to y=200
BUTTON = 140               # the round button's corner, bottom right


def frame(video: str, t: float) -> Image.Image:
    raw = subprocess.run(["ffmpeg", "-loglevel", "error", "-ss", f"{t:.2f}", "-i", video, "-frames:v", "1",
                          "-f", "image2pipe", "-vcodec", "png", "-"], capture_output=True, check=True).stdout
    from io import BytesIO
    return Image.open(BytesIO(raw)).convert("RGB")


def ours(size: tuple[int, int]) -> list[tuple[int, int, int, int]]:
    w, h = size
    return [(round(w * ISLAND[0]), 0, round(w * ISLAND[1]), ISLAND[2]), (w - BUTTON, h - BUTTON, w, h)]


def ring_centre(s: Image.Image, g: Image.Image) -> tuple[int, int] | None:
    """Where the ring is in G: the pointer-coloured pixels that are not in S."""
    def red(img):
        a = np.asarray(img, dtype=np.int16)
        r, gg, b = a[..., 0], a[..., 1], a[..., 2]
        return ((r > 205) & (gg > 35) & (gg < 125) & (b < 115)) | ((r > 215) & (gg > 140) & (gg < 205) & (b < 80))
    new = red(g) & ~red(s)
    new[:48], new[-30:], new[:, :48], new[:, -48:] = False, False, False, False   # the island, the edge
    ys, xs = np.nonzero(new)
    if len(xs) < 30:
        return None
    return int(np.median(xs)), int(np.median(ys))


def moments(video: str) -> list[dict]:
    glow, pointer = read_video(video)
    on = glowing(glow)
    starts = [i for i in range(1, len(on)) if on[i] and not on[i - 1]]
    rows = []
    for r in turns(glow, pointer, read_audio(video)):
        if r["mark"] is None or r["voice"] is None:
            continue
        off = round(r["faded"] * FPS)
        start = max((i for i in starts if i < off), default=0)
        rows.append({"video": Path(video).name, "s": (start - 1) / FPS, "g": r["voice"] - BEFORE_VOICE_S,
                     "voice": r["voice"]})
    return rows


def sheets(videos: list[str]) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for video in videos:
        rows = moments(video)
        sheet = Image.new("RGB", (1440, 270 * len(rows)), "white")
        d = ImageDraw.Draw(sheet)
        for k, row in enumerate(rows):
            s, g = frame(video, row["s"]), frame(video, row["g"])
            centre = ring_centre(s, g)
            y = 270 * k
            sheet.paste(s.resize((480, 270)), (0, y))
            sheet.paste(g.resize((480, 270)), (480, y))
            if centre:
                box = region_box(centre, s.size)
                wide = (box[0] - 80, box[1] - 60, box[2] + 80, box[3] + 60)
                sheet.paste(s.crop(wide).resize((240, 135)), (960, y))
                sheet.paste(g.crop(wide).resize((240, 135)), (1200, y))
            d.rectangle([0, y, 330, y + 26], fill="yellow")
            d.text((4, y + 3), f"{row['video']} #{k} S={row['s']:.1f} G={row['g']:.1f} voice={row['voice']:.1f}",
                   fill="black", font_size=18)
        sheet.save(OUT / f"{Path(video).stem}_sheet.jpg", quality=85)
        print(f"{video}: {len(rows)} lượt -> {OUT / (Path(video).stem + '_sheet.jpg')}")


def measure(videos: list[str]) -> list[dict]:
    rows = []
    for video in videos:
        for k, row in enumerate(moments(video)):
            s, g = frame(video, row["s"]), frame(video, row["g"])
            centre = ring_centre(s, g)
            change = compare(s, g, centre, ours(s.size))
            rows.append({**row, "k": k, "centre": centre, "region": change.region, "whole": change.whole,
                         "flagged": change.stale, "stale": (row["video"], k) in STALE})
    return rows


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(prog="python -m tutor_eval.stale_replay")
    ap.add_argument("what", choices=["sheets", "score"])
    ap.add_argument("videos", nargs="+")
    args = ap.parse_args(argv)
    if args.what == "sheets":
        sheets(args.videos)
        return
    rows = measure(args.videos)
    for r in rows:
        region = "—" if r["region"] is None else f"{r['region']:.3f}"
        flag = "BÁO CŨ" if r["flagged"] else ""
        print(f"{r['video']} #{r['k']}  {'CŨ ' if r['stale'] else 'mới'}  vùng {region:>6}  cả màn {r['whole']:.4f}"
              f"  {flag}")
    print("\n".join(verdict(rows)))


def verdict(rows: list[dict]) -> list[str]:
    stale = [r for r in rows if r["stale"]]
    false = sum(r["flagged"] and not r["stale"] for r in rows)
    caught = sum(r["flagged"] for r in stale)
    return [f"R-1 bắt được {caught}/{len(stale)} lượt cũ: {'ĐẠT' if caught == len(stale) else 'TRƯỢT'}",
            f"R-2 báo nhầm {false}/{len(rows) - len(stale)} lượt mới (≤ 1): {'ĐẠT' if false <= 1 else 'TRƯỢT'}"]


if __name__ == "__main__":
    main()
