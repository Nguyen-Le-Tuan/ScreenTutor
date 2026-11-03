"""B7 with the real model: does a task picked up again go on from its part, or start over?

  .venv/bin/python -m tutor_eval.resume run --yes     # 5 paid calls, under $0.05

Rule, fixed before the first run (02/11). Made-up screen and made-up task. She had a plan of 6
parts and had reached part 2, then asked something else in Zalo, and says "làm tiếp" with Zalo
still in front. The tutor has the plan, the part, the notes and its last sentence.
- P1: goal_done is false in all 5 calls: the task is not finished.
- P2: part stays 2 in at least 4/5 calls.
- P3: the plan comes back empty or unchanged in at least 4/5 calls: no planning again.
- P4: the sentence does not announce the number of parts in at least 4/5 calls: no starting over.
Reported, not scored: what it points at, seconds until the step shows.
"""

from __future__ import annotations

import argparse
import statistics
import sys
import time

from screentutor import screen
from screentutor.app import MACHINE_NOTES
from screentutor.tutor import Tutor, _api_key
from tutor_eval.fake_zalo import STUDY, view

GOAL = "Học cái này trong Zalo"
PLAN = ["Vào trang bồi dưỡng đăng nhập", "Chọn mô đun số 3", "Xem hết video bài giảng", "Làm bài kiểm tra cuối",
        "Tải giấy chứng nhận PDF", "Gửi file vào nhóm Zalo"]
NOTES = "Trang boiduong-thunghiem.example; mô đun 3 Đánh giá học sinh; kiểm tra 20 câu, đạt 16; hạn 15 tháng 11."
LAST = "Bạn bấm vào mô đun số 3 ở giữa trang nhé."
STATE = ('- Cửa sổ đang ở trước mặt: Zalo (Zalo.exe), tiêu đề "Zalo", đang phóng to toàn màn hình.\n'
         '- Cửa sổ khác đang mở, từ trên xuống: 1) Brave (brave.exe), tiêu đề "Bồi dưỡng thường xuyên - Brave".\n'
         + MACHINE_NOTES)
RUNS = 5


def main(argv=None) -> None:
    p = argparse.ArgumentParser(prog="python -m tutor_eval.resume")
    r = p.add_subparsers(dest="cmd", required=True).add_parser("run")
    r.add_argument("--yes", action="store_true", help="xác nhận gọi API có tính phí")
    if not p.parse_args(argv).yes:
        sys.exit("Thêm --yes để thực sự gọi API (tốn tiền).")
    img, _ = view(STUDY, 0)
    url = screen.png_data_url(img)
    tutor = Tutor(_api_key())
    rows = []
    try:
        for _ in range(RUNS):
            started, seen = time.perf_counter(), []
            reply = tutor.follow_up(GOAL, LAST, url, STATE, None, plan=PLAN, part=2, notes=NOTES, acted="resume",
                                    on_mark=lambda _r: seen.append(time.perf_counter() - started))
            rows.append(reply)
            print(f"  phần {reply.part} | xong {reply.goal_done} | plan {reply.plan} | {reply.target} {reply.point} | "
                  f"{seen[0] if seen else 0:.1f}/{reply.latency_s:.1f} s | {reply.element[:30]} | {reply.say}", flush=True)
    finally:
        tutor.close()
    ok = {True: "đạt", False: "KHÔNG đạt"}
    p1 = sum(r.goal_done is False for r in rows)
    p2 = sum(r.part == 2 for r in rows)
    p3 = sum(not r.plan or r.plan == PLAN for r in rows)
    p4 = sum("phần." not in r.say.split(". ")[0] + "." for r in rows)
    print(f"P1 chưa báo xong: {p1}/{RUNS} {ok[p1 == RUNS]}; P2 giữ phần 2: {p2}/{RUNS} {ok[p2 >= 4]}; "
          f"P3 không lập lại kế hoạch: {p3}/{RUNS} {ok[p3 >= 4]}; P4 không đếm phần lại: {p4}/{RUNS} {ok[p4 >= 4]}; "
          f"trễ trung vị {statistics.median(r.latency_s for r in rows):.1f} s")


if __name__ == "__main__":
    main()
