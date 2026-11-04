"""W-6 (03/11): can the model tell a detour of the big task from another task? (founder's choice c)

In T13 the "Làm tiếp" offer never came. In D3 the big task was the principal's message (4 parts), and
the side question "bây giờ tôi muốn tải file Excel trước thì làm thế nào?" got a plan of its own (2 parts),
so the app took it for another task and offered nothing. The founder chose: let the model say whether a
side question with its own plan was a detour of the big task (then offer "Làm tiếp") or another task
(then do not). The question is words only (tutor.aside_body), asked once the side task is done.

Cases: D-1 is D3's own two questions (the plans are rebuilt from what the tutor said in the video and
the T12 labels). The others are Claude's, written with this rule and before any run: five detours and six
other tasks, one of them in the same app as the big task. Each case 5 times.

  .venv/bin/python -m tutor_eval.aside run --runs 5        # 18 x 5 = 90 calls, words only, a few cents
  .venv/bin/python -m tutor_eval.aside summary tutor_eval/results/<stamp>-aside

Rules, fixed before the run (03/11; Claude's proposal):
  A-1  every detour case says aside=true in at least 4 of 5, and at least 23 of 25 in all
  A-2  every other-task case says aside=false in at least 4 of 5, and at least 28 of 30 in all
       (an offer of a task she did not mean to come back to is what the founder asked to stop, 03/11)
  A-3  at most 1 of 55 answers cannot be had (no answer, or not true/false)
  A-4  p90 of the time per call at most 5 s: the offer waits for the last sentence and 3.2 s anyway

Round 1 (20261103-215823-aside, prompt of commit e8f7280: questions and plans only): FAILED A-1. D-1, the one
real case, said "another task" 5 times in 5; the ten cases of Claude's were all right 5 of 5. A-2 30/30, A-3 0/55,
A-4 median 2.26 s, p90 2.97 s. Seen from the words, downloading "the Excel file" is not in the 4 parts of the big
task (the plan does not name the files sent with the message), and the model did not take "trước" as coming back.

Round 2 (changed after round 1, so D-1 is no longer an independent case): the prompt also has the tutor's last
sentence in the big task and its first sentence in the side task (what the app has in the history), and says that
"trước", "khoan đã", "tạm" about a small thing usually mean coming back. Every case gets its two sentences; D-1's
are D3's (the big one as heard; the side one rebuilt, the recording cut it off at "ở bên"). Five guard cases are
added before the run, so that the new words cannot pass by matching words: G-2, G-3 put "trước", "khoan đã" on
other tasks, G-5 is downloading a file sent somewhere else; G-1, G-4 are detours. The rules stay the same, at the
same shares: each case at least 4 of 5; detours at least 23/25 of all (33 of 35), other tasks at least 28/30
(42 of 45); at most 1 answer missing; p90 at most 5 s.

Round 2 (20261103-220349-aside, commit bbfcc49): FAILED A-1 and A-4. D-1 again 0 of 5 (detours 30/35, 33 needed);
every other case 5 of 5, the five guards too (A-2 45/45, A-3 0/80); median 3.29 s, p90 5.13 s (the longer prompt
thought more: 318 reasoning tokens against 220). Claude's reading: the model answers "does the big task need it?",
and in the T12 message none of the 4 parts uses the Excel file, so by that question "no" is fair. What the founder
called a detour is that she will come back.

Round 3, the last before asking the founder: aside asks whether she will likely come back to the big task after the
side question ("làm trước một việc nhỏ rồi quay lại", or tied to the big task's files, pages or apps). Two more
guards written before the run: G-6 deletes old files from Downloads (another task about files), G-7 prints the
certificate first (a detour that the big task's parts do not need). Same rules, same shares: detours at least
37 of 40, other tasks at least 47 of 50; at most 1 answer missing; p90 at most 5 s.
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
    big_said: str
    side: str
    side_plan: list[str]
    side_said: str
    detour: bool


OPEN_EXPLORER = "Bạn bấm vào biểu tượng thư mục màu vàng trên thanh dưới để mở File Explorer."
CASES = [
    Case("D-1 excel_first", PRINCIPAL, 1, "Việc này có bốn phần, bạn bấm vào nút mũi tên tải xuống ở phía bên phải của "
         "dòng file dự thảo quy chế để tải về máy đọc trước.",
         "bây giờ tôi muốn tải file Excel trước thì làm thế nào?", ["Tải file bảng tổng hợp về máy", "Mở file vừa tải"],
         "Lần này có hai phần. Bạn bấm vào nút mũi tên tải xuống ở bên phải dòng file bảng tổng hợp.", True),
    Case("D-2 password", TRAINING, 1, "Bạn bấm vào thanh địa chỉ ở trên cùng của Brave rồi dán địa chỉ trang bồi dưỡng.",
         "tôi quên mật khẩu tài khoản giáo viên thì lấy lại thế nào?",
         ["Mở trang đăng nhập", "Bấm quên mật khẩu", "Làm theo hướng dẫn trên trang"],
         "Bạn bấm vào chữ Quên mật khẩu ở dưới ô mật khẩu.", True),
    Case("D-3 fix_title", LESSON, 2, "Bạn bấm vào chữ File ở góc trên bên trái của Word.",
         "khoan đã, tôi muốn sửa lại tên bài trong giáo án trước", ["Bấm vào dòng tên bài", "Gõ tên mới", "Lưu file"],
         "Bạn bấm vào dòng tên bài ở đầu trang giáo án.", True),
    Case("D-4 where_pdf", TRAINING, 5, "Bạn bấm vào nút Tải giấy chứng nhận màu xanh ở giữa trang.",
         "file PDF vừa tải về nằm ở đâu, mở thư mục cho tôi xem với", ["Mở File Explorer", "Vào thư mục Downloads"],
         OPEN_EXPLORER, True),
    Case("D-5 my_notes", PRINCIPAL, 3, "Bạn bấm vào ô đầu tiên của biểu mẫu để điền ý kiến.",
         "tôi muốn xem lại phiếu góp ý mình đã ghi để chép vào biểu mẫu", ["Mở thư mục Downloads", "Mở phiếu góp ý"],
         OPEN_EXPLORER, True),
    Case("X-1 wallpaper", PRINCIPAL, 2, "Bạn bấm vào file phiếu góp ý trong tin nhắn để mở ra.",
         "chỉ tôi cách đổi hình nền máy tính",
         ["Bấm chuột phải ra ngoài màn hình nền", "Chọn Personalize", "Chọn ảnh làm hình nền"],
         "Bạn bấm chuột phải vào chỗ trống trên màn hình nền.", False),
    Case("X-2 photo_daughter", TRAINING, 3, "Bạn bấm vào nút phát ở giữa video để xem bài giảng.",
         "tôi muốn gửi ảnh cho con gái qua Zalo", ["Mở chat với con gái", "Bấm biểu tượng ảnh", "Chọn ảnh rồi gửi"],
         "Bạn bấm vào biểu tượng Zalo trên thanh dưới để mở Zalo.", False),
    Case("X-3 print_marks", LESSON, 2, "Bạn bấm vào chữ Export ở cột bên trái.",
         "làm sao để in bảng điểm lớp 8A", ["Mở file bảng điểm", "Bấm File rồi Print", "Bấm Print"],
         "Bạn bấm vào biểu tượng thư mục màu vàng trên thanh dưới để tìm file bảng điểm.", False),
    Case("X-4 install_zoom", PRINCIPAL, 1, "Việc này có bốn phần, bạn bấm vào nút mũi tên tải xuống ở phía bên phải của "
         "dòng file dự thảo quy chế để tải về máy đọc trước.",
         "cài Zoom để tối nay họp phụ huynh như thế nào", ["Mở trình duyệt", "Tải Zoom về", "Cài đặt Zoom"],
         "Bạn bấm vào biểu tượng Brave trên thanh dưới để mở trình duyệt.", False),
    Case("X-5 trip_folder", TRAINING, 2, "Bạn bấm vào mô đun số 3 có tên Đánh giá học sinh theo năng lực.",
         "tôi muốn tạo một thư mục mới để cất ảnh du lịch", ["Mở File Explorer", "Tạo thư mục mới", "Đặt tên thư mục"],
         OPEN_EXPLORER, False),
    Case("X-6 birthday_same_app", LESSON, 3, "Bạn bấm vào nhóm Zalo của tổ ở danh sách bên trái.",
         "tôi muốn nhắn tin chúc mừng sinh nhật cô Lan trên Zalo", ["Mở chat với cô Lan", "Gõ lời chúc", "Bấm gửi"],
         "Bạn bấm vào ô tìm kiếm ở góc trên bên trái của Zalo rồi gõ tên cô Lan.", False),
    # round 2's guards, written before its run
    Case("G-1 find_group", LESSON, 3, "Bạn bấm vào biểu tượng Zalo trên thanh dưới để mở Zalo.",
         "nhóm Zalo của tổ tên là gì, tìm cho tôi với", ["Bấm ô tìm kiếm", "Gõ tên nhóm tổ"],
         "Bạn bấm vào ô tìm kiếm ở góc trên bên trái của Zalo.", True),
    Case("G-2 alarm_truoc", PRINCIPAL, 2, "Bạn bấm vào file phiếu góp ý trong tin nhắn để mở ra.",
         "trước khi quên, chỉ tôi cách đặt báo thức trên máy tính", ["Mở ứng dụng Clock", "Thêm báo thức mới"],
         "Bạn bấm vào nút Start ở góc dưới bên trái rồi gõ chữ Clock.", False),
    Case("G-3 bus_khoan_da", TRAINING, 3, "Bạn bấm vào nút phát ở giữa video để xem bài giảng.",
         "khoan đã, tôi muốn đặt vé xe về quê cuối tuần", ["Mở trình duyệt", "Vào trang bán vé xe", "Chọn chuyến"],
         "Bạn bấm vào biểu tượng Brave trên thanh dưới để mở trình duyệt.", False),
    Case("G-4 word_hung_tam", LESSON, 2, "Bạn bấm vào chữ File ở góc trên bên trái của Word.",
         "tạm dừng đã, Word bị treo không bấm được gì thì làm sao", ["Đóng Word bị treo", "Mở lại giáo án"],
         "Bạn bấm vào dấu X màu đỏ ở góc trên bên phải để đóng Word.", True),
    Case("G-5 other_file", PRINCIPAL, 2, "Bạn bấm vào file phiếu góp ý trong tin nhắn để mở ra.",
         "tải cho tôi file ảnh kỷ yếu bạn cũ gửi trong nhóm lớp", ["Mở nhóm lớp cũ", "Tải file ảnh về"],
         "Bạn bấm vào nhóm lớp cũ ở danh sách chat bên trái.", False),
    # round 3's guards, written before its run
    Case("G-6 clean_downloads", PRINCIPAL, 1, "Việc này có bốn phần, bạn bấm vào nút mũi tên tải xuống ở phía bên phải "
         "của dòng file dự thảo quy chế để tải về máy đọc trước.",
         "tôi muốn xoá bớt file cũ trong Downloads cho nhẹ máy", ["Mở thư mục Downloads", "Chọn file cũ", "Xoá file"],
         OPEN_EXPLORER, False),
    Case("G-7 print_first", TRAINING, 6, "Bạn bấm vào nhóm Zalo của tổ ở danh sách bên trái.",
         "tôi muốn in giấy chứng nhận ra giấy trước đã", ["Mở file giấy chứng nhận", "Bấm in"],
         OPEN_EXPLORER, True),
]
MIN_EACH, MAX_NONE, MAX_P90_S = 4, 1, 5.0
DETOUR_SHARE, OTHER_SHARE = (23, 25), (28, 30)   # round 1's 23 of 25 and 28 of 30, kept as shares for round 2


def at_least(share: tuple[int, int], n: int) -> int:
    return -(-share[0] * n // share[1])


def cmd_run(args) -> None:
    out = HERE / "results" / (datetime.now().strftime("%Y%m%d-%H%M%S") + "-aside")
    out.mkdir(parents=True)
    tutor = Tutor(_api_key(), hedge=False)
    try:
        with (out / "calls.jsonl").open("w", encoding="utf-8") as log:
            for run in range(1, args.runs + 1):
                for c in CASES:
                    body = aside_body(c.big[0], c.big[1], c.part, c.big_said, c.side, c.side_plan, c.side_said,
                                      tutor.model, tutor.effort)
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
    for c in [c for c in CASES if any(r["case"] == c.id for r in rows)]:   # round 1 had no guards
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
    rules = [("A-1", each_ok[True] and sum(map(right, detour)) >= at_least(DETOUR_SHARE, len(detour)),
              f"chen ngang đúng {sum(map(right, detour))}/{len(detour)} (cần {at_least(DETOUR_SHARE, len(detour))})"),
             ("A-2", each_ok[False] and sum(map(right, other)) >= at_least(OTHER_SHARE, len(other)),
              f"việc khác đúng {sum(map(right, other))}/{len(other)} (cần {at_least(OTHER_SHARE, len(other))})"),
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
