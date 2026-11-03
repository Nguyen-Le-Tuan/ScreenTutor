"""A first look at the founder's two big tasks: the real Session and the real tutor on invented Zalo screens.

  .venv/bin/python -m tutor_eval.big_task run --yes       # about 30 paid calls, under $0.30
  .venv/bin/python -m tutor_eval.big_task summary tutor_eval/results/<stamp>-big

Rule, fixed before the first run (02/11). This is NOT T12: the screens are drawn by
tutor_eval/fake_zalo.py and every word on them is made up, so a pass says the session and
the prompt work together, not that they work on her real messages. T12 still needs the
founder's messages on Windows. Each of the two tasks runs 3 times; a simulated user
scrolls when told, says she has read when shown a region, and stops at the first click,
because there is nothing to click on a picture.
- P2 plan: in at least 5/6 runs a plan appears, naming at least 80% of the parts, with at
  most 1 part beyond them. (Draft R2.)
- P3 box: at least 80% of the read steps have IoU at least 0.5 with the true message box.
  (Draft R3.)
- P4 scroll: when the message runs past the bottom of the view the tutor says to scroll in
  at least 80% of those turns, and says it at most once when everything is already in view.
  (Draft R4.)
- P5 words: at least 90% of the sentences pass tutor_eval.run.say_problems, leaving out the
  check on the number of sentences on a turn that opens with "Việc này có N phần".
- No session error in any run.
A part counts as named when the plan contains one of its keywords, ignoring case.

Second attempt, rule changed before it ran. The first (20261102-1851xx-big, kept) got P2
6/6, P3 4/4, P5 11/13 and failed P4 with 3/10. Reading the runs, 7 of those 10 were turns
where the message that gives the task was fully in view and only other messages ran on:
reading it was right, so P4 counted the wrong thing. P4 now means: the message that gives
the task is cut off at the bottom of the view. Thresholds unchanged. Reported, not
scored: seconds until she saw each step.

Third attempt, rule fixed before it ran. The second (20261102-190812-big, kept) got P2 6/6,
P3 5/5, no errors, and failed P4 with 1/5 and P5 with 10/12. Both are real: a cut message was
framed instead of scrolled, and file names were spoken with underscores. The prompt gained
one clause for each. A third task is added, the founder's first example in earnest: the
same message further down the chat, so most of its steps start below the edge. So 3 tasks
of 3 runs, P2 needs at least 8/9, the other thresholds unchanged.

Fourth attempt, same rule. The third (20261102-191531-big) passed all: P2 8/9, P3 3/3, P4
9/9, P5 21/21, no errors. But the tutor said "two parts" before it had read to the end and
then planned five, which was also the one plan that failed. The app now holds back the plan
and the count on a scroll step; that is a change in behaviour, so the run is repeated.
Run 20261102-192309-big, the last of the night: P2 7/9 FAILED, P3 3/3, P4 9/9, P5 21/21, no
errors. One failure is real (principal 2 answered in one step, no plan), one is the keyword
check (a plan that merged two parts). Left as failed; not scored again.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from datetime import datetime
from pathlib import Path

from screentutor import screen
from screentutor.app import MACHINE_NOTES
from screentutor.gesture import describe
from screentutor.inputs import Click
from screentutor.session import Session
from screentutor.tutor import Tutor, _api_key
from tutor_eval.fake_zalo import H, HEADER_H, INPUT_H, LONG_CHAT, PRINCIPAL, STUDY, TASKBAR_H, W, view
from tutor_eval.run import say_problems

HERE = Path(__file__).parent
RUNS = 3
SCROLL_PX = 420
STATE = ("- Cửa sổ đang ở trước mặt: Zalo (Zalo.exe), tiêu đề \"Zalo\", đang phóng to toàn màn hình.\n" + MACHINE_NOTES)
TASKS = {
    "study": {"chat": STUDY, "message": 2, "question": "Học cái này trong Zalo",
              "parts": [("đăng nhập",), ("mô đun",), ("video",), ("kiểm tra",), ("chứng nhận",), ("gửi", "nộp")]},
    "study_long": {"chat": LONG_CHAT, "message": 5, "question": "Học cái này trong Zalo",
                   "parts": [("đăng nhập",), ("mô đun",), ("video",), ("kiểm tra",), ("chứng nhận",), ("gửi", "nộp")]},
    "principal": {"chat": PRINCIPAL, "message": 1, "question": "Thầy hiệu trưởng nhắn cái này thì mình phải làm gì?",
                  "parts": [("dự thảo", "quy chế"), ("phiếu", "ý kiến"), ("biểu mẫu", "link", "trực tuyến"), ("tổ trưởng", "nộp")]},
}


def iou(a, b) -> float:
    w = min(a[2], b[2]) - max(a[0], b[0])
    h = min(a[3], b[3]) - max(a[1], b[1])
    if w <= 0 or h <= 0:
        return 0.0
    inter = w * h
    return inter / ((a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter)


def message_cut(chat, message: int, top: int) -> bool:
    return chat.boxes[message][3] - top > H - TASKBAR_H - INPUT_H - HEADER_H


class Mom:
    """Does what a patient user does, and writes down each turn with what was true on the screen."""

    def __init__(self, chat, message: int):
        self.chat, self.message = chat, message
        self.top = 0
        self.turns = []

    def look(self):
        img, boxes = view(self.chat, self.top)
        self.turns.append({"top": self.top, "message_cut": message_cut(self.chat, self.message, self.top),
                           "true_box": boxes[self.message]})
        return img, STATE

    def wait_change(self, timeout_s, min_change, stop):
        if stop():
            return "stopped"
        self.top = min(self.top + SCROLL_PX, max(self.chat.canvas.height - (H - TASKBAR_H - INPUT_H - HEADER_H), 0))
        return "settled"

    def wait_click(self, since, timeout_s):
        return Click(time.monotonic(), 0, 0, "left") if timeout_s == 0 else None  # "I have read it"; real clicks end the run


def one(tutor: Tutor, spec: dict) -> dict:
    mom = Mom(spec["chat"], spec["message"])
    _, boxes = view(spec["chat"], 0)
    x1, y1, x2, y2 = boxes[spec["message"]]
    path = [(i * 0.015, (x1 + x2) // 2, min((y1 + y2) // 2, 700)) for i in range(60)]   # she rests the mouse on the message
    shown, said = {}, []

    def say(text, on_sound=None):
        said.append(text)
        if on_sound:
            on_sound()   # no voice here: the step goes up as the words are written down

    s = Session(tutor=tutor, look=mom.look, encode=screen.png_data_url, show=lambda x, y, c=False: None, hide=lambda: None,
                say=say, wait_click=mom.wait_click, settle=lambda c: "unchanged", pause=lambda t: None,
                wait_change=mom.wait_change, pointer=describe(path, (W, H)),
                show_box=lambda box, c: shown.__setitem__(len(said), box))
    steps = s.run(spec["question"], max_steps=8)
    turns = []
    for i, st in enumerate(steps):
        t = mom.turns[i] if i < len(mom.turns) else {}
        turns.append({**t, "n": st.n, "target": st.target, "say": st.say, "latency_s": st.latency_s, "error": st.error,
                      "goal_done": st.goal_done, "shown_s": st.shown_s})
    return {"steps": turns, "plan": s.plan, "notes": s.notes, "mode": s.mode, "boxes": list(shown.values()), "said": said}


def cmd_run(args) -> None:
    print(f"Sẽ chạy {len(TASKS) * RUNS} lượt việc lớn, mỗi lượt vài lần gọi Spark.")
    if not args.yes:
        sys.exit("Thêm --yes để thực sự gọi API (tốn tiền).")
    out = HERE / "results" / (datetime.now().strftime("%Y%m%d-%H%M%S") + "-big")
    out.mkdir(parents=True)
    tutor = Tutor(_api_key())
    rows = []
    try:
        for name, spec in TASKS.items():
            for run in range(1, RUNS + 1):
                r = one(tutor, spec)
                rows.append({"task": name, "run": run, **r})
                print(f"{name} {run}: {[(s['target'], round(s['latency_s'], 1)) for s in r['steps']]} plan={r['plan']}", flush=True)
                (out / "runs.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    finally:
        tutor.close()
    print(summarize(out))


def summarize(out: Path) -> str:
    rows = json.loads((out / "runs.json").read_text(encoding="utf-8"))
    plans_ok, ious, should, did, extra, says, ok_says, errors, lat, shown = 0, [], 0, 0, 0, 0, 0, 0, [], []
    for r in rows:
        spec = TASKS[r["task"]]
        plan = " | ".join(r["plan"]).lower()
        named = sum(any(k in plan for k in keys) for keys in spec["parts"])
        extras = sum(not any(k in p.lower() for keys in spec["parts"] for k in keys) for p in r["plan"])
        plans_ok += bool(r["plan"]) and named >= 0.8 * len(spec["parts"]) and extras <= 1
        reads = [s for s in r["steps"] if s["target"] == "read"]
        for s, box in zip(reads, r["boxes"]):
            if s.get("true_box"):
                ious.append(iou(box, s["true_box"]))
        for s in r["steps"]:
            lat.append(s["latency_s"])
            errors += bool(s["error"])
            if s.get("shown_s"):
                shown.append(s["shown_s"])
            if s.get("message_cut") and not s["goal_done"]:
                should += 1
                did += s["target"] == "scroll"
            elif s["target"] == "scroll":
                extra += 1
            says += 1
            problems = say_problems(s["say"])
            if s["say"].startswith("Việc này có"):
                problems = [p for p in problems if not p.endswith(" câu")]
            ok_says += not problems
    p3 = sum(x >= 0.5 for x in ious)
    lines = [f"# Việc lớn trên màn hình giả ({out.name})", "",
             f"P2 kế hoạch đủ phần: {plans_ok}/{len(rows)} (cần ≥ {len(rows) - 1}/{len(rows)})",
             f"P3 khung đọc IoU ≥ 0,5: {p3}/{len(ious)} (cần ≥ 80%), IoU {[round(x, 2) for x in ious]}",
             f"P4 bảo kéo khi còn tiếp: {did}/{should} (cần ≥ 80%); bảo kéo khi đã hết: {extra} (tối đa 1)",
             f"P5 câu nói qua kiểm tra: {ok_says}/{says} (cần ≥ 90%)",
             f"Lỗi phiên: {errors}. Trễ trung vị mỗi lượt: {statistics.median(lat):.1f} s; "
             f"tới khi mẹ thấy bước: {statistics.median(shown or [0]):.1f} s", ""]
    for r in rows:
        lines.append(f"- {r['task']} {r['run']}: {[s['target'] for s in r['steps']]} | {r['mode']} | plan: {r['plan']}")
        lines += [f"    {s['target']}: {s['say']}" for s in r["steps"]]
    text = "\n".join(lines)
    (out / "summary.md").write_text(text + "\n", encoding="utf-8")
    return text


def main(argv=None) -> None:
    p = argparse.ArgumentParser(prog="python -m tutor_eval.big_task")
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--yes", action="store_true", help="xác nhận gọi API có tính phí")
    s = sub.add_parser("summary")
    s.add_argument("dir")
    args = p.parse_args(argv)
    if args.cmd == "summary":
        print(summarize(Path(args.dir)))
    else:
        cmd_run(args)


if __name__ == "__main__":
    main()
