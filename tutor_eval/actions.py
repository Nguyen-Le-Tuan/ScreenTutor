"""K (03/11): does the tutor teach more than clicks? Drag to select, keyboard shortcuts, typing into a box.

The founder's T13 notes: the tutor "cứ bắt ấn vào cái link format text" (a site address written as
plain text in a Zalo message, which is not a link), 5 times out of 5, "thay vì chỉ quét khối và
copy"; and in Word it selected all through Editing > Select All instead of Ctrl+A, and could not
tell the font size box from its drop-down arrow. Until K, a step could only be a click, a region
to read, or a scroll, so even a model that knew better had no way to say it.

Cases, on real screens from the T13 run (they show her real chat list, so the images stay in the
gitignored tutor_eval/t12_data/): one Zalo message from T12 with the plain-text address, frames
of the D2 and D4 recordings, and one doctored frame (the Word page with a selection tint laid
over its text, as after Ctrl+A). Each is asked REPEATS times; the expected step is scored by kind
and place, in the pixels of the image:

  K-1 link_first      Zalo, the address is plain text: select it (drag from its start to its end)
  K-2 link_retry      the same, after a click on it changed nothing: not that click again; drag
  K-3 copy            the address is selected: Ctrl+C
  K-4 paste_where     Brave is open, the address copied: the address bar (click it, Ctrl+L, Ctrl+T,
                      or type into it)
  K-5 bigger          Word, nothing selected, "make the letters bigger": select all first (Ctrl+A,
                      or a drag over the page); not Editing > Select
  K-6 size_15         Word, all selected, "font size 15": type 15 into the size box (its text part,
                      not the arrow)
  K-7 size_15_first   Word, nothing selected, "font size 15 for the whole lesson": select all first
  K-8 after_copy      the turn after Ctrl+C, which changes nothing on the screen: open the browser
                      (its icon on the taskbar), not Ctrl+C again (added before k3, with the retry rule
                      in mind: "the screen did not change, do not repeat")

  .venv/bin/python -m tutor_eval.actions run [--repeats 5]
  .venv/bin/python -m tutor_eval.actions summary tutor_eval/results/<stamp>-actions

Rule, fixed before the first run (03/11; Claude's proposal): with the K prompt, each of K-1..K-7
passes at 4/5 or better (K-8, added later, the same).

Changed after the first K run (20261103-184731-actions-k1), reported as such, thresholds unchanged:
- K-1/K-2 are scored after screentutor.textsnap moves the drag's ends to the edges of the words they
  fall in, as the app does before it shows the drag, and pass only if the selection is exactly the
  address (the first run's 45 px slack passed drags that would have copied a broken address).
  From k3 on, the model also writes the words to select, and textsnap counts them from the start.

Results, each case 5 times on the same frames (03/11):
- baseline, the prompt before K (20261103-*-actions-baseline): 1 of 7 cases passes (K-4, a click on the
  address bar). After a click on the plain-text address changed nothing it said to click it again 5
  times in 5, the loop of the founder's T13 run; Ctrl+C, Ctrl+A and typing never came.
- k1 (K prompt, 45 px slack): K-1 3/5, K-2 4/5, K-3, K-4, K-5, K-7 5/5, K-6 0/5 (the case's fault, above).
- k2 stopped at 21 of 35 calls: superseded by k3, kept as a partial record.
- k3 (words to select, snapped scoring, K-8 added): all 8 pass, 39 of 40 calls; the miss was K-6
  pointing at the size box as a click. The 12 cases of tutor_eval.run on this prompt, run beside the
  old prompt in the same minutes: R5a 11/11 (old 11/11), R5b 24/24 (old 22/24), R5c 6.18 s (old
  6.16 s), R5d 3.96 s (old 3.59 s), R5e 5/5, R6 0: every rule passes; the mark comes ~0.4 s later.
- K-6 as first written asked the model to notice a selection laid over the page by hand; it did not
  see one (0/5) and selected all first, which was right for what it saw. It is now the turn after
  she pressed Ctrl+A, on the same frame, which is how the step comes in the app. The prompt that existed before K is run once first, as the baseline;
it is expected to fail where it has no step of the right kind. The 12 cases of tutor_eval.run
are rerun with the K prompt, with their rules unchanged (R5a-e, R6).
"""

from __future__ import annotations

import argparse
import base64
import io
import json
import time
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageDraw

from screentutor.app import MACHINE_NOTES
from screentutor.textsnap import snap_drag
from screentutor.tutor import FOLLOW_ACTED, Tutor, _api_key

HERE = Path(__file__).parent
DATA = HERE / "t12_data"
REPLAY = DATA / "replay"
REPEATS = 5
PASS = 4

ADDRESS = (925, 428, 1215, 458)          # "boiduong-thunghiem.example" in t12_viec1_3.png
ADDRESS_EDGES = (932, 1203)              # its first and last inked column, measured 03/11
ADDRESS_SELECTED = (925, 697, 1210, 722)  # the same words, selected, in act_selected.png
ADDRESS_BAR = (175, 60, 1665, 100)        # Brave's address bar in act_brave.png
SIZE_BOX = (280, 108, 322, 136)           # the text part of Word's font size box in act_word.png
SIZE_ARROW = (322, 108, 338, 136)         # its drop-down arrow
PAGE = (540, 340, 1390, 1000)             # the text of the Word page
BROWSERS = [(772, 1025, 818, 1071), (883, 1025, 929, 1071)]   # Brave and Chrome on the taskbar of act_selected.png

ZALO = '- Cửa sổ đang ở trước mặt: Zalo (Zalo.exe), tiêu đề "Zalo - Nguyễn Lê Tuấn", đang phóng to toàn màn hình.'
BRAVE = ('- Cửa sổ đang ở trước mặt: Brave (brave.exe), tiêu đề "Bảng kê khai thi đua - Tổ Nghệ Thuật - Google '
         'Trang tính - Brave", đang phóng to toàn màn hình.\n- Cửa sổ khác đang mở: Zalo (Zalo.exe).')
WORD = ('- Cửa sổ đang ở trước mặt: Word (WINWORD.EXE), tiêu đề "Giáo án mẫu Âm nhạc 8.docx - Word", đang phóng to '
        'toàn màn hình.')
GOAL_LINK = "Mở trang bồi dưỡng trong tin nhắn này giúp tôi"


@dataclass
class Case:
    key: str
    image: str
    question: str
    state: str
    expect: str                 # what passes, in words, for the summary
    follow: dict | None = None  # follow_up arguments: last_say, changed, acted, notes
    plan: list[str] = field(default_factory=list)


CASES = [
    Case("K-1 link_first", "t12_viec1_3.png", GOAL_LINK, ZALO, "drag từ đầu tới cuối địa chỉ chữ thường"),
    Case("K-2 link_retry", "t12_viec1_3.png", GOAL_LINK, ZALO, "không bấm lại chữ đó; drag trên nó",
         {"last_say": "Bạn bấm vào dòng chữ boiduong-thunghiem.example trong tin nhắn để mở trang bồi dưỡng.",
          "changed": False, "acted": "click"}),
    Case("K-3 copy", "replay/act_selected.png", GOAL_LINK, ZALO, "keys Ctrl+C",
         {"last_say": "Bạn nhấn giữ chuột ở đầu chữ boiduong, kéo tới hết chữ example rồi thả ra để bôi đen địa chỉ.",
          "changed": True, "acted": "dragged"}),
    Case("K-4 paste_where", "replay/act_brave.png", GOAL_LINK, BRAVE,
         "thanh địa chỉ: click vào nó, Ctrl+L, Ctrl+T, hoặc gõ vào nó",
         {"last_say": "Bạn bấm vào biểu tượng sư tử đỏ ở thanh dưới màn hình để mở trình duyệt Brave.",
          "changed": True, "acted": "click",
          "notes": "Đã bôi đen và sao chép (Ctrl+C) địa chỉ boiduong-thunghiem.example từ tin nhắn Zalo."}),
    Case("K-5 bigger", "replay/act_word.png", "Tôi muốn làm chữ to hơn", WORD, "Ctrl+A, hoặc drag trên trang"),
    Case("K-6 size_15", "replay/act_word_selected.png", "Tôi muốn đổi cỡ chữ thành 15", WORD,
         "type 15 vào phần chữ của ô cỡ chữ (không phải mũi tên)",
         {"last_say": "Bạn bấm giữ phím Ctrl rồi bấm phím A để chọn hết chữ.", "changed": True, "acted": "keys"}),
    Case("K-8 after_copy", "replay/act_selected.png", GOAL_LINK, ZALO, "mở trình duyệt (biểu tượng trên thanh dưới)",
         {"last_say": "Bạn bấm giữ phím Ctrl rồi bấm phím C để sao chép địa chỉ vừa bôi đen.", "changed": False,
          "acted": "keys"}),
    Case("K-7 size_15_first", "replay/act_word.png", "Tôi muốn đổi cỡ chữ cả bài thành 15", WORD,
         "Ctrl+A, hoặc drag trên trang"),
]


def doctored_selection() -> Path:
    """act_word.png with the page's text tinted as Word shows a selection: the screen after Ctrl+A."""
    out = REPLAY / "act_word_selected.png"
    if not out.exists():
        img = Image.open(REPLAY / "act_word.png").convert("RGB")
        tint = Image.new("RGB", img.size, (176, 196, 226))
        mask = Image.new("L", img.size, 0)
        ImageDraw.Draw(mask).rectangle(PAGE, fill=110)
        Image.composite(tint, img, mask).save(out)
    return out


def data_url(path: Path) -> tuple[str, tuple[int, int]]:
    with Image.open(path) as img:
        img = img.convert("RGB")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii"), img.size


def _px(grid, size):
    return None if grid is None else (grid[0] * size[0] / 1000, grid[1] * size[1] / 1000)


def _inside(p, box, slack=0) -> bool:
    return p is not None and box[0] - slack <= p[0] <= box[2] + slack and box[1] - slack <= p[1] <= box[3] + slack


def _keys(reply) -> str:
    return (getattr(reply, "keys", "") or "").replace(" ", "").lower()


def _drag_over(reply, image, size, box, edges) -> bool:
    """After snapping to the words, as the app does: the selection is exactly the words from edges[0] to edges[1]."""
    a, b = _px(reply.point, size), _px(getattr(reply, "end", None), size)
    if reply.target != "drag" or a is None or b is None:
        return False
    a, b = sorted(snap_drag(image, (round(a[0]), round(a[1])), (round(b[0]), round(b[1])), getattr(reply, "keys", "")))
    on_line = all(box[1] - 6 <= p[1] <= box[3] + 6 for p in (a, b))
    return on_line and edges[0] - 7 <= a[0] <= edges[0] and edges[1] <= b[0] <= edges[1] + 5


def score(case: Case, reply, size, image=None) -> str:
    """'pass', or a short word on what it did instead."""
    p, keys = _px(reply.point, size), _keys(reply)
    k = case.key.split()[0]
    if reply.error:
        return "error"
    if k in ("K-1", "K-2"):
        if image is not None and _drag_over(reply, image, size, ADDRESS, ADDRESS_EDGES):
            return "pass"
        return "click on the text" if reply.target == "click" and _inside(p, ADDRESS, 10) else reply.target or "?"
    if k == "K-3":
        return "pass" if reply.target == "keys" and keys == "ctrl+c" else f"{reply.target} {keys}".strip()
    if k == "K-4":
        if reply.target == "keys" and keys in ("ctrl+l", "ctrl+t", "alt+d", "f6"):
            return "pass"
        if reply.target in ("click", "type") and _inside(p, ADDRESS_BAR, 8):
            return "pass"
        return f"{reply.target} {keys}".strip()
    if k in ("K-5", "K-7"):
        if reply.target == "keys" and keys == "ctrl+a":
            return "pass"
        if reply.target == "drag" and _inside(p, PAGE, 20) and _inside(_px(getattr(reply, "end", None), size), PAGE, 20):
            return "pass"
        return f"{reply.target} {keys}".strip()
    if k == "K-8":
        if reply.target == "click" and any(_inside(p, b, 6) for b in BROWSERS):
            return "pass"
        return "Ctrl+C again" if keys == "ctrl+c" else f"{reply.target} {keys}".strip()
    if k == "K-6":
        if reply.target == "type" and _inside(p, SIZE_BOX, 4) and keys.strip(".") in ("15",):
            return "pass"
        if _inside(p, SIZE_ARROW, 2):
            return f"{reply.target} on the arrow"
        return f"{reply.target} {keys}".strip()
    return "?"


def run(repeats: int, label: str) -> Path:
    doctored_selection()
    out = HERE / "results" / (datetime.now().strftime("%Y%m%d-%H%M%S") + f"-actions-{label}")
    out.mkdir(parents=True)
    tutor = Tutor(_api_key())
    n = 0
    try:
        with (out / "calls.jsonl").open("w", encoding="utf-8") as log:
            for rep in range(1, repeats + 1):
                for case in CASES:
                    n += 1
                    url, size = data_url(DATA / case.image)
                    state = case.state + "\n" + MACHINE_NOTES
                    started = time.perf_counter()
                    if case.follow:
                        f = case.follow
                        acted = f["acted"] if f["acted"] in FOLLOW_ACTED else "click"   # before K a drag was a click
                        reply = tutor.follow_up(case.question, f["last_say"], url, state, f["changed"],
                                                notes=f.get("notes", ""), acted=acted)
                    else:
                        reply = tutor.ask(case.question, url, state)
                    result = score(case, reply, size, Image.open(DATA / case.image))
                    rec = {"case": case.key, "rep": rep, "result": result, "target": reply.target,
                           "point_px": _px(reply.point, size), "end_px": _px(getattr(reply, "end", None), size),
                           "keys": getattr(reply, "keys", ""), "say": reply.say, "element": reply.element,
                           "latency_s": round(time.perf_counter() - started, 2), "error": reply.error}
                    log.write(json.dumps(rec, ensure_ascii=False) + "\n")
                    log.flush()
                    print(f"[{n}/{repeats * len(CASES)}] {case.key}: {result} | {reply.target} {rec['keys']} | "
                          f"{reply.say}", flush=True)
    finally:
        tutor.close()
    return summarize(out)


def summarize(out: Path) -> Path:
    rows = [json.loads(x) for x in (out / "calls.jsonl").read_text(encoding="utf-8").splitlines() if x]
    lines = [f"# K: dạy hơn cả bấm chuột ({out.name})", "", f"Luật: mỗi ca đạt ít nhất {PASS}/{REPEATS}.", "",
             "| Ca | Cần | Đạt | Tutor đã làm gì |", "|---|---|---|---|"]
    for case in CASES:
        rs = [r for r in rows if r["case"] == case.key]
        ok = sum(r["result"] == "pass" for r in rs)
        others = Counter(r["result"] for r in rs if r["result"] != "pass")
        lines.append(f"| {case.key} | {case.expect} | {ok}/{len(rs)} {'ĐẠT' if ok >= PASS else 'TRƯỢT'} "
                     f"| {', '.join(f'{k} ×{v}' for k, v in others.items()) or '—'} |")
    lines += ["", "Câu tutor nói (lần đầu mỗi ca):", ""]
    for case in CASES:
        first = next((r for r in rows if r["case"] == case.key), None)
        if first:
            lines.append(f"- {case.key}: {first['say']}")
    path = out / "summary.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def main(argv=None) -> None:
    p = argparse.ArgumentParser(prog="python -m tutor_eval.actions")
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--repeats", type=int, default=REPEATS)
    r.add_argument("--label", default="k")
    s = sub.add_parser("summary")
    s.add_argument("dir")
    args = p.parse_args(argv)
    path = summarize(Path(args.dir)) if args.cmd == "summary" else run(args.repeats, args.label)
    print(f"Đã ghi: {path}")


if __name__ == "__main__":
    main()
