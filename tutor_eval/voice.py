"""T7a: hearing mom's real questions through the realtime API, as the app will.

  .venv/bin/python -m tutor_eval.voice run          # 8 recordings x 2 modes, about $0.02
  .venv/bin/python -m tutor_eval.voice summary tutor_eval/results/<stamp>-voice

Each recording is streamed at real-time pace, as if mom were speaking now.
ENDPOINTING (the "Hỏi" button) streams the whole recording plus 2.5 s of silence
and keeps every turn; the joining rule of screentutor.listen is then replayed
for several waits. PUSH_TO_TALK (Ctrl+Alt) streams the recording, then endStream.

Rule, fixed before the run (31/10/2026). On the first try, ENDPOINTING cut me_01
after its first sentence and lost the second, so the app joins turns that start
within G seconds of the previous one.
- Scoring: stt_eval.score.score_one against the founder's typed transcripts
  (stt_eval/audio/refs.tsv), the same "còn ý" rule as T3.
- (1) ENDPOINTING: G = the smallest of 0, 1.0, 1.5, 2.0 s for which at least
  7/8 questions keep their meaning (T3 threshold). No such G: the "Hỏi" button
  cannot rely on ENDPOINTING; the founder decides what replaces it.
- (2) With that G, the median wait from the end of her speech (the model's
  speechEnd) to the question being complete is at most 2.5 s.
- (3) PUSH_TO_TALK: at least 7/8 keep their meaning, and the median wait from
  endStream to the final text is at most 1.5 s.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import sys
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from screentutor.listen import _api_key, file_frames, listen
from stt_eval.score import score_one
from stt_eval.transcribe import load_refs

HERE = Path(__file__).parent
AUDIO = HERE.parent / "stt_eval" / "audio"
WAITS = (0.0, 1.0, 1.5, 2.0)
MIN_KEPT = 7
MAX_ENDPOINT_WAIT_S = 2.5
MAX_PTT_WAIT_S = 1.5


def replay(timeline: list, first_frame_at: float, g: float) -> tuple[str, float | None]:
    """The question the app would have taken with join wait g, and how long after her speech ended it was complete."""
    open_turns, parts, pending, speech_end = set(), [], None, None
    for t, kind, turn, text, audio_ms in timeline:
        if pending is not None and t - pending > g:
            break
        if kind == "speechStart":
            open_turns.add(turn)
            pending = None
        elif kind == "speechEnd" and audio_ms is not None:
            speech_end = first_frame_at + audio_ms / 1000
        elif kind == "speechComplete":
            if text.strip():
                parts.append(text.strip())
            open_turns.discard(turn)
            pending = None if open_turns else t
    if pending is None or speech_end is None:
        return " ".join(parts), None
    return " ".join(parts), pending + g - speech_end


def cmd_run(_args) -> None:
    refs = load_refs(AUDIO / "refs.tsv")
    files = sorted(AUDIO.glob("me_*.m4a"))
    if len(files) != 8 or any(f.name not in refs for f in files):
        sys.exit(f"Cần 8 file me_0X.m4a và refs.tsv trong {AUDIO}")
    key = _api_key()
    out = HERE / "results" / (datetime.now().strftime("%Y%m%d-%H%M%S") + "-voice")
    out.mkdir(parents=True)
    rows = []
    for f in files:
        ep = asyncio.run(listen(key, file_frames(f), "ENDPOINTING", join_within_s=None))
        ptt = asyncio.run(listen(key, file_frames(f, trailing_silence_s=0), "PUSH_TO_TALK"))
        rows.append({"file": f.name, "ref": refs[f.name], "endpointing": asdict(ep), "push_to_talk": asdict(ptt)})
        print(f"{f.name}: ENDPOINTING {ep.turns} đoạn {ep.error or ''}| PUSH_TO_TALK {ptt.wait_s and round(ptt.wait_s, 2)} s "
              f"{ptt.error or ''}")
    (out / "runs.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Đã ghi: {summarize(out)}")


def summarize(out: Path) -> Path:
    rows = json.loads((out / "runs.json").read_text(encoding="utf-8"))
    by_g = {}
    for g in WAITS:
        res = []
        for r in rows:
            ep = r["endpointing"]
            text, wait = replay(ep["timeline"], ep["first_frame_at"] or 0.0, g)
            res.append((r["file"], text, wait, score_one(r["ref"], text)))
        by_g[g] = res
    kept = {g: sum(s["verdict"] == "còn" for *_, s in res) for g, res in by_g.items()}
    chosen = next((g for g in WAITS if kept[g] >= MIN_KEPT), None)
    waits = [w for *_, w, _ in by_g[chosen] if w is not None] if chosen is not None else []
    ep_wait = statistics.median(waits) if waits else float("inf")
    ptt = [(r["file"], r["push_to_talk"], score_one(r["ref"], r["push_to_talk"]["text"] or "")) for r in rows]
    ptt_kept = sum(s["verdict"] == "còn" for *_, s in ptt)
    ptt_waits = [p["final_at"] - p["audio_end_at"] for _, p, _ in ptt if p["final_at"] and p["audio_end_at"]]
    ptt_wait = statistics.median(ptt_waits) if ptt_waits else float("inf")

    ok1, ok2 = chosen is not None, ep_wait <= MAX_ENDPOINT_WAIT_S
    ok3 = ptt_kept >= MIN_KEPT and ptt_wait <= MAX_PTT_WAIT_S
    mark = {True: "đạt", False: "KHÔNG đạt"}
    lines = [f"# T7a: nghe câu hỏi thật của mẹ qua realtime ({out.name})", "",
             "| Chờ ghép G | " + " | ".join(f"{g:g} s" for g in WAITS) + " |",
             "|---|" + "---|" * len(WAITS),
             "| Còn ý (trên 8) | " + " | ".join(str(kept[g]) for g in WAITS) + " |", "",
             "| Điều kiện | Kết quả | Ngưỡng | |", "|---|---|---|---|",
             f"| (1) ENDPOINTING: G nhỏ nhất giữ ≥ 7/8 | {chosen if chosen is not None else 'không có'} | "
             f"trong {WAITS} | {mark[ok1]} |",
             f"| (2) Chờ từ lúc ngừng nói tới khi xong câu (trung vị, với G đó) | {ep_wait:.2f} s | "
             f"≤ {MAX_ENDPOINT_WAIT_S} s | {mark[ok2]} |",
             f"| (3) PUSH_TO_TALK: còn ý / chờ sau endStream | {ptt_kept}/8 / {ptt_wait:.2f} s | "
             f"≥ 7/8 / ≤ {MAX_PTT_WAIT_S} s | {mark[ok3]} |", "",
             "| File | Số đoạn | Câu lấy được với G đã chọn | Còn ý | PUSH_TO_TALK |", "|---|---|---|---|---|"]
    for r, (_, text, wait, s), (_, p, ps) in zip(rows, by_g[chosen if chosen is not None else WAITS[-1]], ptt):
        lines.append(f"| {r['file']} | {r['endpointing']['turns']} | {text} | {s['verdict']} ({s['recall']:.0%}) | "
                     f"{ps['verdict']} ({ps['recall']:.0%}) |")
    (out / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines[:12]))
    return out / "summary.md"


def main(argv=None) -> None:
    p = argparse.ArgumentParser(prog="python -m tutor_eval.voice")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("run")
    s = sub.add_parser("summary")
    s.add_argument("dir")
    args = p.parse_args(argv)
    if args.cmd == "summary":
        print(f"Đã ghi: {summarize(Path(args.dir))}")
    else:
        cmd_run(args)


if __name__ == "__main__":
    main()
