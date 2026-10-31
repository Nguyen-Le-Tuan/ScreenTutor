"""T6a: after the user clicks, can Spark M2 tell whether the step and the task are done, and point at what is next?

  .venv/bin/python -m tutor_eval.steps plan
  .venv/bin/python -m tutor_eval.steps run --yes          # 24 paid calls, about $0.17
  .venv/bin/python -m tutor_eval.steps summary tutor_eval/results/<stamp>-steps

The 12 real screenshots chain into before/after pairs: clicking the Brave icon
(case_04) leads to Brave with the Sheet tabs (case_05), clicking a Sheet tab to
the open Sheet (case_06), clicking Downloads to the Downloads list (case_07),
clicking Export to the Export page (case_11). An unchanged screenshot stands for
a click that did nothing.

Rule, fixed before the run (31/10/2026):
- Setup: the 12 pairs below, Spark M2, effort low, 2 runs each = 24 calls,
  prompt = screentutor.tutor.build_follow_up_prompt. The "after" screenshot gets
  its state text from cases/state_t1.json when it has one. screen_changed is
  what the stillness watcher would measure: True for P and G pairs, False for N.
  - P (4 pairs): the step is done, the task is not; the next target has frozen labels.
  - G (3 pairs): the step and the task are done; pointing is not scored.
  - N (5 pairs): the screen did not change; the step is not done; the same target again.
- (1) Done or not: step_done right in at least 22/24 calls, and goal_done right
  in at least 22/24 calls.
- (2) Pointing: on the P and N pairs (18 calls), at least 15/18 hits.
- (3) Latency: median of the 24 calls at most 5.0 s.
- (4) Spoken sentence: at least 22/24 pass the T4 automatic checks.
- All pass: the app uses this turn after each click. (1) fails: fix the prompt
  and rerun once; if it fails again, the tutor never decides "done" by itself
  and asks the user instead (fallback of Decision 2b). (2), (3) or (4) fail:
  fix and rerun under the same rule.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from datetime import datetime
from pathlib import Path

from grounding_test import config as gconfig
from grounding_test.datasets import CASES_DIR, load_cases, prepare_image
from grounding_test.scoring import score_point
from screentutor.tutor import MODEL, Tutor, _api_key
from tutor_eval.run import LATENCY_LIMIT_S, MIN_SAY_OK, load_states, say_problems

HERE = Path(__file__).parent
RUNS = 2
MIN_DONE_OK = 22
MIN_HITS = 15
EST_COST_PER_CALL = 0.007

# (pair id, screenshot after the click, user's goal, what the tutor said before the click,
#  screen changed, expected step_done, expected goal_done, case whose labels score the next point)
PAIRS = [
    ("P_export", "case_11", "Mẹ muốn xuất giáo án ra PDF thì làm sao?",
     "Bạn bấm vào chữ Export ở cột bên trái để mở phần xuất tài liệu.", True, True, False, "case_11"),
    ("P_brave", "case_05", "Mẹ bấm link rồi mà không thấy, giờ bấm vào đâu để xem?",
     "Bạn bấm vào biểu tượng sư tử màu đỏ ở thanh dưới cùng để mở trình duyệt Brave.", True, True, False, "case_05"),
    ("P_sheet_tab", "case_06", "Mẹ là cô Mẫu, phần của mẹ trong bảng tính cô gửi nằm ở đâu?",
     "Bạn bấm vào thẻ có chữ Bảng kê khai thi đua ở hàng trên cùng để mở bảng tính.", True, True, False, "case_06"),
    ("P_downloads", "case_07", "Mẹ muốn mở cái bản giáo án có số 1 ở cuối tên.",
     "Bạn bấm vào chữ Downloads ở cột bên trái để mở chỗ chứa file tải về.", True, True, False, "case_07"),
    ("G_downloads", "case_07", "Mẹ muốn vào chỗ chứa file tải về.",
     "Bạn bấm vào chữ Downloads ở cột bên trái để mở chỗ chứa file tải về.", True, True, True, None),
    ("G_sheet", "case_06", "Mẹ muốn mở cái bảng tính cô gửi.",
     "Bạn bấm vào thẻ có chữ Bảng kê khai thi đua ở hàng trên cùng để mở bảng tính.", True, True, True, None),
    ("G_folder", "case_07", "Mẹ muốn mở chỗ chứa cái file giáo án này.",
     "Bạn bấm vào biểu tượng thư mục nhỏ ngay bên phải tên file giáo án để mở thư mục chứa file.",
     True, True, True, None),
    ("N_file", "case_10", "Mẹ muốn xuất ra PDF thì bấm vào đâu trước?",
     "Bạn bấm vào chữ File ở góc trên bên trái để mở mục lưu và xuất tài liệu.", False, False, False, "case_10"),
    ("N_clip", "case_02", "Mẹ muốn gửi một cái file cho người này.",
     "Bạn bấm vào biểu tượng cái kẹp giấy ngay phía trên chỗ nhập tin nhắn để chọn file muốn gửi.",
     False, False, False, "case_02"),
    ("N_ok", "case_12", "Cái bảng báo lỗi này, mẹ muốn tắt nó đi.",
     "Bạn bấm vào nút OK ở góc dưới bên phải của bảng báo lỗi để tắt bảng đi.", False, False, False, "case_12"),
    ("N_downloads", "case_08", "Mẹ muốn vào chỗ chứa file tải về.",
     "Bạn bấm vào mục Downloads có mũi tên xanh ở cột bên trái để mở chỗ chứa file tải về.",
     False, False, False, "case_08"),
    ("N_co_mau", "case_06", "Mẹ là cô Mẫu, phần của mẹ trong bảng tính cô gửi nằm ở đâu?",
     "Bạn bấm vào chữ Cô Mẫu ở thanh dưới cùng bên trái để mở phần của bạn.", False, False, False, "case_06"),
]


def cmd_plan(_args):
    items, problems = load_cases()
    if problems:
        sys.exit("Thiếu dữ liệu ca thật:\n" + "\n".join(problems))
    states = load_states()
    for pid, after, goal, *_ in PAIRS:
        print(f"  {pid:12} sau = {after} {'(có trạng thái)' if after in states else '':16} {goal}")
    n = len(PAIRS) * RUNS
    print(f"Tổng: {n} lần gọi {MODEL}, effort low, chi phí ước tính khoảng ${n * EST_COST_PER_CALL:.2f}.")
    return {it.item_id: it for it in items}


def cmd_run(args) -> None:
    items = cmd_plan(args)
    if not args.yes:
        sys.exit("Thêm --yes để thực sự gọi API (tốn tiền).")
    states = load_states()
    out = HERE / "results" / (datetime.now().strftime("%Y%m%d-%H%M%S") + "-steps")
    (out / "raw").mkdir(parents=True)
    tutor = Tutor(_api_key())
    images = {}
    n = 0
    try:
        with (out / "calls.jsonl").open("w", encoding="utf-8") as log:
            for pid, after, goal, last_say, changed, want_step, want_goal, target in PAIRS:
                if after not in images:
                    images[after] = prepare_image(CASES_DIR / f"{after}.png")
                data_url, sent_size, orig_size = images[after]
                for run in range(1, RUNS + 1):
                    n += 1
                    reply = tutor.follow_up(goal, last_say, data_url, states.get(after), changed)
                    result = None
                    if target:
                        scores = score_point(reply.point, sent_size, orig_size, items[target].boxes,
                                             gconfig.NEAR_PX)
                        result = scores["norm1000"]["result"]
                    raw_file = f"raw/{n:03d}.json"
                    (out / raw_file).write_text(json.dumps(reply.raw, ensure_ascii=False, indent=2),
                                                encoding="utf-8")
                    rec = {
                        "pair": pid, "after": after, "run": run, "goal": goal, "last_say": last_say,
                        "screen_changed": changed, "want_step": want_step, "want_goal": want_goal,
                        "step_done": reply.step_done, "goal_done": reply.goal_done, "found": reply.found,
                        "point": reply.point, "element": reply.element, "result": result,
                        "say": reply.say, "say_problems": say_problems(reply.say),
                        "latency_s": round(reply.latency_s, 3), "usage": reply.usage, "error": reply.error,
                        "raw_file": raw_file,
                    }
                    log.write(json.dumps(rec, ensure_ascii=False) + "\n")
                    log.flush()
                    print(f"[{n}/{len(PAIRS) * RUNS}] {pid} lần {run}: bước {reply.step_done} việc {reply.goal_done} "
                          f"trỏ {result or '—'} ({reply.latency_s:.1f}s) {reply.error or ''}{reply.say}")
    finally:
        tutor.close()
    print(f"Đã ghi: {summarize(out)}")


def summarize(out: Path) -> Path:
    rows = [json.loads(line) for line in (out / "calls.jsonl").open(encoding="utf-8")]
    step_ok = sum(r["step_done"] == r["want_step"] for r in rows)
    goal_ok = sum(r["goal_done"] == r["want_goal"] for r in rows)
    pointed = [r for r in rows if r["result"] is not None]
    hits = sum(r["result"] == "hit" for r in pointed)
    lat = sorted(r["latency_s"] for r in rows if not r["error"])
    med = statistics.median(lat) if lat else float("inf")
    p90 = lat[min(len(lat) - 1, int(0.9 * len(lat)))] if lat else float("inf")
    say_ok = sum(not r["say_problems"] for r in rows)
    price = gconfig.PRICES[MODEL]
    cost = sum(r["usage"]["input"] * price["input"] + r["usage"]["output"] * price["output"] for r in rows) / 1e6

    ok1 = step_ok >= MIN_DONE_OK and goal_ok >= MIN_DONE_OK
    ok2 = hits >= MIN_HITS
    ok3 = med <= LATENCY_LIMIT_S
    ok4 = say_ok >= MIN_SAY_OK
    mark = {True: "đạt", False: "KHÔNG đạt"}
    lines = [
        f"# T6a: lượt kiểm bước sau cú bấm ({out.name})", "",
        f"Model {MODEL}, effort low, {len(rows)} lần gọi, chi phí khoảng ${cost:.3f}.", "",
        "| Điều kiện | Kết quả | Ngưỡng | |", "|---|---|---|---|",
        f"| (1) step_done đúng / goal_done đúng | {step_ok}/{len(rows)} / {goal_ok}/{len(rows)} | "
        f"≥ {MIN_DONE_OK}/24 mỗi loại | {mark[ok1]} |",
        f"| (2) Trỏ bước tiếp (P và N) | {hits}/{len(pointed)} | ≥ {MIN_HITS}/18 | {mark[ok2]} |",
        f"| (3) Trễ trung vị / p90 | {med:.2f} s / {p90:.2f} s | ≤ {LATENCY_LIMIT_S:.0f} s | {mark[ok3]} |",
        f"| (4) Câu nói qua kiểm tra tự động | {say_ok}/{len(rows)} | ≥ {MIN_SAY_OK}/24 | {mark[ok4]} |",
        "", f"**Theo luật đặt trước: {'đạt cả bốn' if ok1 and ok2 and ok3 and ok4 else 'chưa đạt'}.**", "",
        "| Cặp | Ảnh sau | Cần (bước / việc) | Lần 1 | Lần 2 |", "|---|---|---|---|---|",
    ]
    by_pair = {}
    for r in rows:
        by_pair.setdefault(r["pair"], []).append(r)
    for pid, rs in by_pair.items():
        rs.sort(key=lambda r: r["run"])
        cells = [f"{r['step_done']} / {r['goal_done']}" + (f", trỏ {r['result']}" if r["result"] else "")
                 + ("" if r["step_done"] == r["want_step"] and r["goal_done"] == r["want_goal"] else " ✗")
                 for r in rs]
        lines.append(f"| {pid} | {rs[0]['after']} | {rs[0]['want_step']} / {rs[0]['want_goal']} | "
                     + " | ".join(cells) + " |")
    lines += ["", "Câu tutor nói:", ""]
    lines += [f"- {r['pair']} lần {r['run']}: {r['say']}" + (f" ({', '.join(r['say_problems'])})"
                                                           if r["say_problems"] else "") for r in rows]
    (out / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines[:11]))
    return out / "summary.md"


def main(argv=None) -> None:
    p = argparse.ArgumentParser(prog="python -m tutor_eval.steps")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("plan")
    r = sub.add_parser("run")
    r.add_argument("--yes", action="store_true", help="xác nhận gọi API có tính phí")
    s = sub.add_parser("summary")
    s.add_argument("dir")
    args = p.parse_args(argv)
    if args.cmd == "summary":
        print(f"Đã ghi: {summarize(Path(args.dir))}")
    else:
        {"plan": cmd_plan, "run": cmd_run}[args.cmd](args)


if __name__ == "__main__":
    main()
