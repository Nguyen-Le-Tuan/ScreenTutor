"""T8a: mom's real voice -> Muse realtime -> Spark M2 -> VieNeu, the app's chain without the Windows parts.

  .venv/bin/python -m tutor_eval.e2e run          # 4 pairs x 2 runs, about $0.06

Four of mom's recordings ask about a screen we have a labelled screenshot of:
me_06 (the link opened lots of tabs, she cannot find her name) on case_05,
me_04 (why can't I name it like this) on case_12, me_07 (the link will not open)
on case_04, me_05 (send a PDF to the print shop) on case_10.

Rule, fixed before the run (31/10/2026); the thresholds are Claude's, not the founder's:
- Each recording is streamed at real-time pace through screentutor.listen
  (ENDPOINTING, joining turns within 1.0 s), the question goes to Tutor.ask with
  the case's screenshot and state text (cases/state_t1.json, plus the app's
  note about its own widgets), and the answer goes through for_speech to VieNeu.
- (1) Pointing: at least 6/8 hits on the case's frozen labels.
- (2) Spoken sentence: at least 7/8 pass the T4 automatic checks.
- Measured, not scored: the wait from the end of her speech (the model's
  speechEnd) to the first sound of the answer, split into hearing, Spark and voice.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import time
from datetime import datetime
from pathlib import Path

from grounding_test import config as gconfig
from grounding_test.datasets import CASES_DIR, load_cases, prepare_image
from grounding_test.scoring import score_point
from screentutor.app import OWN_WIDGETS_NOTE
from screentutor.listen import _api_key, file_frames, listen
from screentutor.speak import VOICE, _load_engine, for_speech
from screentutor.tutor import Tutor
from tutor_eval.run import load_states, say_problems

HERE = Path(__file__).parent
AUDIO = HERE.parent / "stt_eval" / "audio"
PAIRS = [("me_06.m4a", "case_05"), ("me_04.m4a", "case_12"), ("me_07.m4a", "case_04"), ("me_05.m4a", "case_10")]
RUNS = 2
MIN_HITS = 6
MIN_SAY_OK = 7


def speech_end(heard) -> float | None:
    ends = [ms for _, kind, _, _, ms in heard.timeline if kind == "speechEnd" and ms is not None]
    return heard.first_frame_at + max(ends) / 1000 if ends and heard.first_frame_at else None


def cmd_run(_args) -> None:
    key = _api_key()
    items = {it.item_id: it for it in load_cases()[0]}
    states = load_states()
    engine = _load_engine()
    list(engine.infer_stream("Xin chào.", voice=VOICE))  # warm-up, as the app does at start-up
    tutor = Tutor(key)
    out = HERE / "results" / (datetime.now().strftime("%Y%m%d-%H%M%S") + "-e2e")
    out.mkdir(parents=True)
    rows = []
    try:
        for rec, case in PAIRS:
            data_url, sent, orig = prepare_image(CASES_DIR / f"{case}.png")
            state = (states.get(case, "") + "\n" + OWN_WIDGETS_NOTE).strip()
            for run in range(1, RUNS + 1):
                heard = asyncio.run(listen(key, file_frames(AUDIO / rec), "ENDPOINTING"))
                t_heard = time.monotonic()
                reply = tutor.ask(heard.text or "", data_url, state)
                t_reply = time.monotonic()
                first_sound = None
                for _ in engine.infer_stream(for_speech(reply.say), voice=VOICE):
                    first_sound = time.monotonic()
                    break
                end = speech_end(heard)
                result = score_point(reply.point, sent, orig, items[case].boxes, gconfig.NEAR_PX)["norm1000"]["result"]
                row = {"recording": rec, "case": case, "run": run, "heard": heard.text, "say": reply.say,
                       "spoken": for_speech(reply.say), "result": result, "element": reply.element,
                       "say_problems": say_problems(reply.say), "error": heard.error or reply.error,
                       "hear_s": round(heard.final_at - end, 2) if end and heard.final_at else None,
                       "spark_s": round(t_reply - t_heard, 2),
                       "voice_s": round(first_sound - t_reply, 2) if first_sound else None,
                       "total_s": round(first_sound - end, 2) if end and first_sound else None}
                rows.append(row)
                print(f"{rec} -> {case} lần {run}: {result} | nghe {row['hear_s']} s, Spark {row['spark_s']} s, "
                      f"giọng {row['voice_s']} s, tổng {row['total_s']} s\n   Nghe: {heard.text}\n   Nói: {reply.say}")
    finally:
        tutor.close()
    (out / "rows.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Đã ghi: {summarize(out)}")


def summarize(out: Path) -> Path:
    rows = json.loads((out / "rows.json").read_text(encoding="utf-8"))
    hits = sum(r["result"] == "hit" for r in rows)
    say_ok = sum(not r["say_problems"] for r in rows)
    med = lambda k: statistics.median(r[k] for r in rows if r[k] is not None)  # noqa: E731
    mark = {True: "đạt", False: "KHÔNG đạt"}
    lines = [f"# T8a: giọng thật của mẹ → chỉ chỗ → giọng đọc ({out.name})", "",
             "| Điều kiện | Kết quả | Ngưỡng | |", "|---|---|---|---|",
             f"| (1) Trỏ trúng | {hits}/{len(rows)} | ≥ {MIN_HITS}/8 | {mark[hits >= MIN_HITS]} |",
             f"| (2) Câu nói qua kiểm tra tự động | {say_ok}/{len(rows)} | ≥ {MIN_SAY_OK}/8 | {mark[say_ok >= MIN_SAY_OK]} |",
             "", "| Đo (trung vị) | Giây |", "|---|---|",
             f"| Nghe: từ lúc ngừng nói tới khi đủ câu hỏi | {med('hear_s'):.2f} |",
             f"| Spark M2: hỏi tới khi có câu trả lời | {med('spark_s'):.2f} |",
             f"| Giọng đọc: tới âm thanh đầu tiên | {med('voice_s'):.2f} |",
             f"| **Tổng: ngừng nói → nghe tiếng tutor** | **{med('total_s'):.2f}** |", "",
             "| Ghi âm | Ảnh | Lần | Trỏ | Tổng (s) | Nghe được | Tutor nói |", "|---|---|---|---|---|---|---|"]
    lines += [f"| {r['recording']} | {r['case']} | {r['run']} | {r['result']} | {r['total_s']} | {r['heard']} | {r['say']} |"
              for r in rows]
    (out / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines[:14]))
    return out / "summary.md"


def main(argv=None) -> None:
    p = argparse.ArgumentParser(prog="python -m tutor_eval.e2e")
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
