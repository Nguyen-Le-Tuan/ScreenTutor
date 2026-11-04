"""W-6 (03/11): can the model tell a detour of the big task from another task? (founder's choice c)

In T13 the "Làm tiếp" offer never came. In D3 the big task was the principal's message (4 parts), and
the side question "bây giờ tôi muốn tải file Excel trước thì làm thế nào?" got a plan of its own (2 parts),
so the app took it for another task and offered nothing. The founder chose: let the model say whether a
side question with its own plan was a detour of the big task (then offer "Làm tiếp") or another task
(then do not). The question is words only (tutor.aside_body), asked once the side task is done.

Cases: D-1 is D3's own two questions (the plans are rebuilt from what the tutor said in the video and
the T12 labels). The others are Claude's, written with this rule and before any run: five detours and six
other tasks, one of them in the same app as the big task. Each case 5 times.

  .venv/bin/python -m tutor_eval.aside run --runs 5        # 11 x 5 = 55 calls, words only, a few cents
  .venv/bin/python -m tutor_eval.aside summary tutor_eval/results/<stamp>-aside

Rules, fixed before the run (03/11; Claude's proposal):
  A-1  every detour case says aside=true in at least 4 of 5, and at least 23 of 25 in all
  A-2  every other-task case says aside=false in at least 4 of 5, and at least 28 of 30 in all
       (an offer of a task she did not mean to come back to is what the founder asked to stop, 03/11)
  A-3  at most 1 of 55 answers cannot be had (no answer, or not true/false)
  A-4  p90 of the time per call at most 5 s: the offer waits for the last sentence and 3.2 s anyway
"""

from __future__ import annotations

import argparse
import json
import statistics
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from screentutor.tutor import Tutor, _api_key, aside_body

HERE = Path(__file__).parent

PRINCIPAL = ("tôi muốn làm theo theo nhóm này thì làm như thế nào?",   # D3 as heard (Muse ASR of the video)
             ["Đọc file dự thảo quy chế", "Ghi ý kiến vào phiếu góp ý", "Điền biểu mẫu trực tuyến",
              "Nộp phiếu cho tổ trưởng"])
TRAINING = ("Làm theo thông báo bồi dưỡng thường xuyên này giúp tôi",   # T12 Việc 1
            ["Đăng nhập trang bồi dưỡng", "Chọn mô đun 3", "Xem hết video", "Làm bài kiểm tra",
             "Tải giấy chứng nhận PDF", "Gửi vào nhóm Zalo của tổ"])
LESSON = ("Xuất giáo án ra PDF rồi gửi vào nhóm Zalo của tổ",
          ["Mở giáo án trong Word", "Xuất ra file PDF", "Gửi file PDF vào nhóm Zalo"])


@dataclass
class Case:
    id: str
    big: tuple[str, list[str]]
    part: int
    side: str
    side_plan: list[str]
    detour: bool


CASES = [
    Case("D-1 excel_first", PRINCIPAL, 1, "bây giờ tôi muốn tải file Excel trước thì làm thế nào?",
         ["Tải file bảng tổng hợp về máy", "Mở file vừa tải"], True),
    Case("D-2 password", TRAINING, 1, "tôi quên mật khẩu tài khoản giáo viên thì lấy lại thế nào?",
         ["Mở trang đăng nhập", "Bấm quên mật khẩu", "Làm theo hướng dẫn trên trang"], True),
    Case("D-3 fix_title", LESSON, 2, "khoan đã, tôi muốn sửa lại tên bài trong giáo án trước",
         ["Bấm vào dòng tên bài", "Gõ tên mới", "Lưu file"], True),
    Case("D-4 where_pdf", TRAINING, 5, "file PDF vừa tải về nằm ở đâu, mở thư mục cho tôi xem với",
         ["Mở File Explorer", "Vào thư mục Downloads"], True),
    Case("D-5 my_notes", PRINCIPAL, 3, "tôi muốn xem lại phiếu góp ý mình đã ghi để chép vào biểu mẫu",
         ["Mở thư mục Downloads", "Mở phiếu góp ý"], True),
    Case("X-1 wallpaper", PRINCIPAL, 2, "chỉ tôi cách đổi hình nền máy tính",
         ["Bấm chuột phải ra ngoài màn hình nền", "Chọn Personalize", "Chọn ảnh làm hình nền"], False),
    Case("X-2 photo_daughter", TRAINING, 3, "tôi muốn gửi ảnh cho con gái qua Zalo",
         ["Mở chat với con gái", "Bấm biểu tượng ảnh", "Chọn ảnh rồi gửi"], False),
    Case("X-3 print_marks", LESSON, 2, "làm sao để in bảng điểm lớp 8A",
         ["Mở file bảng điểm", "Bấm File rồi Print", "Bấm Print"], False),
    Case("X-4 install_zoom", PRINCIPAL, 1, "cài Zoom để tối nay họp phụ huynh như thế nào",
         ["Mở trình duyệt", "Tải Zoom về", "Cài đặt Zoom"], False),
    Case("X-5 trip_folder", TRAINING, 2, "tôi muốn tạo một thư mục mới để cất ảnh du lịch",
         ["Mở File Explorer", "Tạo thư mục mới", "Đặt tên thư mục"], False),
    Case("X-6 birthday_same_app", LESSON, 3, "tôi muốn nhắn tin chúc mừng sinh nhật cô Lan trên Zalo",
         ["Mở chat với cô Lan", "Gõ lời chúc", "Bấm gửi"], False),
]
MIN_EACH, MIN_DETOUR, MIN_OTHER, MAX_NONE, MAX_P90_S = 4, 23, 28, 1, 5.0


def cmd_run(args) -> None:
    out = HERE / "results" / (datetime.now().strftime("%Y%m%d-%H%M%S") + "-aside")
    out.mkdir(parents=True)
    tutor = Tutor(_api_key(), hedge=False)
    try:
        with (out / "calls.jsonl").open("w", encoding="utf-8") as log:
            for run in range(1, args.runs + 1):
                for c in CASES:
                    body = aside_body(c.big[0], c.big[1], c.part, c.side, c.side_plan, tutor.model, tutor.effort)
                    started, verdict, error, usage = time.perf_counter(), None, None, {}
                    try:
                        resp, _ = tutor._post("/chat/completions", body)
                        usage = resp.get("usage") or {}
                        got = json.loads(resp["choices"][0]["message"]["content"]).get("aside")
                        verdict = got if isinstance(got, bool) else None
                    except Exception as e:  # a failed call is a result here, counted by A-3
                        error = f"{type(e).__name__}: {e}"[:200]
                    rec = {"run": run, "case": c.id, "detour": c.detour, "aside": verdict, "error": error,
                           "s": round(time.perf_counter() - started, 3), "usage": usage}
                    log.write(json.dumps(rec, ensure_ascii=False) + "\n")
                    log.flush()
                    print(f"{c.id:22} lần {run}: aside={verdict} ({rec['s']:.2f} s){' ' + error if error else ''}",
                          flush=True)
    finally:
        tutor.close()
    print(f"Đã ghi: {summarize(out)}")


def summarize(out: Path) -> Path:
    rows = [json.loads(x) for x in (out / "calls.jsonl").read_text(encoding="utf-8").splitlines() if x]
    right = lambda r: r["aside"] is r["detour"]  # noqa: E731
    lines = [f"# W-6 (c): chen ngang hay việc khác ({out.name})", "", "| Ca | Đúng | Sai | Không có |", "|---|---|---|---|"]
    each_ok = {True: True, False: True}
    for c in CASES:
        mine = [r for r in rows if r["case"] == c.id]
        good = sum(right(r) for r in mine)
        none = sum(r["aside"] is None for r in mine)
        each_ok[c.detour] &= good >= MIN_EACH
        lines.append(f"| {c.id} ({'chen ngang' if c.detour else 'việc khác'}) | {good}/{len(mine)} "
                     f"| {len(mine) - good - none} | {none} |")
    detour = [r for r in rows if r["detour"]]
    other = [r for r in rows if not r["detour"]]
    secs = sorted(r["s"] for r in rows)
    p90 = secs[max(int(len(secs) * 0.9) - 1, 0)]
    none = sum(r["aside"] is None for r in rows)
    rules = [("A-1", each_ok[True] and sum(map(right, detour)) >= MIN_DETOUR,
              f"chen ngang đúng {sum(map(right, detour))}/{len(detour)}"),
             ("A-2", each_ok[False] and sum(map(right, other)) >= MIN_OTHER,
              f"việc khác đúng {sum(map(right, other))}/{len(other)}"),
             ("A-3", none <= MAX_NONE, f"không có câu trả lời {none}/{len(rows)}"),
             ("A-4", p90 <= MAX_P90_S, f"thời gian trung vị {statistics.median(secs):.2f} s, p90 {p90:.2f} s")]
    lines += ["", *[f"- {name}: {text}: **{'ĐẠT' if ok else 'TRƯỢT'}**" for name, ok, text in rules]]
    reasoning = [(r["usage"].get("completion_tokens_details") or {}).get("reasoning_tokens") for r in rows]
    reasoning = [x for x in reasoning if x is not None]
    if reasoning:
        lines.append(f"- token suy nghĩ: trung vị {statistics.median(reasoning):.0f}")
    path = out / "summary.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def main(argv=None) -> None:
    p = argparse.ArgumentParser(prog="python -m tutor_eval.aside")
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--runs", type=int, default=5)
    s = sub.add_parser("summary")
    s.add_argument("dir")
    args = p.parse_args(argv)
    if args.cmd == "summary":
        print(f"Đã ghi: {summarize(Path(args.dir))}")
    else:
        cmd_run(args)


if __name__ == "__main__":
    main()
