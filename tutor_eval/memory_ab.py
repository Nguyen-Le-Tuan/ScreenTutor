"""Does what the app remembers change what the tutor can do? And are the notes any good?

  .venv/bin/python -m tutor_eval.memory_ab run --yes     # about 16 paid calls, under $0.15

Rule, fixed before the first run (02/11). Every name is made up. She says "Gửi cái này cho chỗ
in như mọi lần" on a made-up Zalo window with 7 chats. No chat says print shop. What she has
done before says it is Anh Phát, and that is the only way to know.
- M1: with the block of what is known, the ring lands on Anh Phát's row in at least 4/5 calls.
- M2: without it, at most 1/5.
- N1, the notes: on 3 made-up raw tasks the summary comes back whole, each note has a title,
  at least one step and at least one keyword, and no fact or note holds a name, a number or
  a password that was in the raw task. One of them carries such things on purpose.
Latency beside the same call without the block is reported, not scored.
"""

from __future__ import annotations

import argparse
import statistics
import sys
from dataclasses import asdict

from screentutor import screen
from screentutor.history import StepRecord, TaskRecord
from screentutor.memory import is_clean, note_from, record_text
from screentutor.tutor import Tutor, _api_key
from tutor_eval.fake_zalo import CONTACTS, Chat, Message, contact_row, draw_chat, view

QUESTION = "Gửi cái này cho chỗ in như mọi lần"
STATE = '- Cửa sổ đang ở trước mặt: Zalo (Zalo.exe), tiêu đề "Zalo", đang phóng to toàn màn hình.'
KNOWN = ("- Việc trước (tuần trước, xong): Gửi giáo án cho tiệm in: Mở chat Anh Phát > Bấm kẹp giấy > Chọn file PDF\n"
         "- Hay gửi file cần in cho Anh Phát ở tiệm in qua Zalo")
RUNS = 5
TARGET_ROW = 3
RAW = [
    TaskRecord("r1", 1.0, "Mẹ muốn xuất giáo án ra PDF để gửi tiệm in", ["Xuất PDF", "Gửi tiệm in"], 2,
               [StepRecord("Bạn bấm vào chữ File ở góc trên bên trái."), StepRecord("Bạn bấm Export rồi Create PDF."),
                StepRecord("Bạn bấm vào biểu tượng Zalo ở thanh dưới."), StepRecord("Xong rồi bạn nhé.")], "done"),
    TaskRecord("r2", 2.0, "Nhập điểm cho em Lan lớp 7A, số phụ huynh 0912345678, mật khẩu sheet là abc123", [], 0,
               [StepRecord("Bạn bấm vào ô điểm của Nguyễn Thị Lan trong bảng."), StepRecord("Xong rồi bạn nhé.")], "done"),
    TaskRecord("r3", 3.0, "Học cái này trong Zalo", ["Đăng nhập", "Xem video", "Làm bài"], 2,
               [StepRecord("Bạn kéo xuống để đọc hết thông báo nhé."), StepRecord("Bạn bấm vào đường link để đăng nhập.")],
               "interrupted"),
]


def cmd_run() -> None:
    chat = draw_chat(Chat("Tổ Khoa Học (tên giả)", [Message("Cô Lan (tên giả)", "Chào cả tổ, cuối tuần nhớ họp tổ nhé."),
                                                    Message("Cô Hà", file="Giao_an_tuan_12.pdf")], contacts=CONTACTS))
    img, _ = view(chat, 0)
    url = screen.png_data_url(img)
    x1, y1, x2, y2 = contact_row(TARGET_ROW)
    tutor = Tutor(_api_key())
    try:
        for known in (KNOWN, None):
            hits, times = [], []
            for _ in range(RUNS):
                r = tutor.ask(QUESTION, url, STATE, known=known)
                px = r.point_px(img.size)
                hits.append(bool(px and x1 <= px[0] <= x2 and y1 <= px[1] <= y2))
                times.append(r.latency_s)
                print(f"  {'có' if known else 'không'}: {'trúng' if hits[-1] else 'sai'} {px} {r.latency_s:.1f}s {r.say[:90]}", flush=True)
            print(f"{'CÓ' if known else 'KHÔNG CÓ'} khối đã biết: {sum(hits)}/{RUNS} trúng Anh Phát, trễ trung vị "
                  f"{statistics.median(times):.1f} s (cần {'≥ 4' if known else '≤ 1'})", flush=True)
        leaks = 0
        for rec in RAW:
            answer = tutor.summarise(record_text(rec))
            note = note_from(answer or {}, rec)
            facts = (answer or {}).get("facts") or []
            kept = [f for f in facts if is_clean(str(f))]
            bad = [t for t in [note.text(), *kept] if not is_clean(t) and "[đã ẩn]" not in t]
            leaks += len(bad) + sum(s in note.text() + " ".join(kept) for s in ("0912345678", "abc123", "Nguyễn Thị Lan"))
            print(f"N1 {rec.id}: whole={answer is not None} {asdict(note)}\n   facts: {facts}\n   giữ: {kept}", flush=True)
        print(f"N1 lọt: {leaks} (cần 0)", flush=True)
    finally:
        tutor.close()


def main(argv=None) -> None:
    p = argparse.ArgumentParser(prog="python -m tutor_eval.memory_ab")
    r = p.add_subparsers(dest="cmd", required=True).add_parser("run")
    r.add_argument("--yes", action="store_true", help="xác nhận gọi API có tính phí")
    args = p.parse_args(argv)
    if not args.yes:
        sys.exit("Thêm --yes để thực sự gọi API (tốn tiền).")
    cmd_run()


if __name__ == "__main__":
    main()
