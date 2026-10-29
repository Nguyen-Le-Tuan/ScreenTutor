"""Measure VieNeu speed on this machine and render voice samples for listening.

  .venv/bin/python bench.py speed                     # fp32 vs int8, writes results/speed_<stamp>.md
  .venv/bin/python bench.py voices --precision int8   # all preset voices, writes out/voices/*.wav + out/nghe_thu.html

Sentences are what the tutor would actually say: short, with English UI words
(File, Export, Save, Downloads), a file name with "(1).docx" and a time.
"""

from __future__ import annotations

import argparse
import html
import json
import statistics
import time
from datetime import datetime
from pathlib import Path

import numpy as np

import vieneu_local

HERE = Path(__file__).parent
SR = 48_000
SPEED_VOICE = "Ngọc Huyền"

SENTENCES = {
    "S1": "Mẹ bấm vào biểu tượng thư mục màu vàng nhé.",
    "S2": "Giờ mẹ bấm vào chữ File ở góc trên bên trái, rồi chọn Export.",
    "S3": "Trang bảng tính đang mở trong Brave, nằm phía sau Zalo. Mẹ bấm vào biểu tượng Brave dưới thanh taskbar nhé.",
    "S4": "Tên file không được có dấu hỏi hay dấu ngoặc kép. Mẹ xoá hai dấu đó rồi bấm Save lại nhé.",
    "S5": "File Giáo án mẫu Âm nhạc 8 (1).docx mẹ sửa lúc chín giờ tối qua, nằm trong thư mục Downloads.",
    "S6": "Mẹ có muốn gửi file này cho cô tổ trưởng không? Mẹ nói có hoặc không nhé.",
}
VOICE_SENTENCES = ("S3", "S5")


def stream_once(tts, text: str, voice: str) -> dict:
    t0 = time.perf_counter()
    first = None
    chunks = []
    for chunk in tts.infer_stream(text, voice=voice):
        if first is None:
            first = time.perf_counter() - t0
        chunks.append(np.asarray(chunk).reshape(-1))
    total = time.perf_counter() - t0
    audio = np.concatenate(chunks) if chunks else np.zeros(0)
    dur = len(audio) / SR
    return {"ttfa_s": first, "total_s": total, "audio_s": dur, "rtf": total / dur if dur else None, "audio": audio}


def cmd_speed(args) -> None:
    rows, loads = [], {}
    for precision in ("fp32", "int8"):
        t = time.perf_counter()
        tts = vieneu_local.load(precision)
        loads[precision] = time.perf_counter() - t
        stream_once(tts, "Xin chào mẹ.", SPEED_VOICE)  # warm-up, not measured
        for sid, text in SENTENCES.items():
            for rep in (1, 2):
                r = stream_once(tts, text, SPEED_VOICE)
                rows.append({"precision": precision, "sentence": sid, "rep": rep,
                             **{k: round(v, 3) for k, v in r.items() if k != "audio" and v is not None}})
                print(f"{precision} {sid} #{rep}: first audio {r['ttfa_s']:.2f}s, "
                      f"total {r['total_s']:.2f}s for {r['audio_s']:.1f}s audio (RTF {r['rtf']:.2f})")
        del tts

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    out = HERE / "results" / f"speed_{stamp}.md"
    out.parent.mkdir(exist_ok=True)
    lines = [f"# VieNeu v3 Turbo, CPU (ONNX), {stamp}", "",
             f"Giọng đo tốc độ: {SPEED_VOICE}. Mỗi câu chạy 2 lần sau một lần khởi động.", "",
             "| Bản | Nạp model | Âm thanh đầu tiên (trung vị / lớn nhất) | RTF trung vị |", "|---|---|---|---|"]
    for p in ("fp32", "int8"):
        rs = [r for r in rows if r["precision"] == p]
        ttfa = [r["ttfa_s"] for r in rs]
        lines.append(f"| {p} | {loads[p]:.1f} s | {statistics.median(ttfa):.2f} s / {max(ttfa):.2f} s | "
                     f"{statistics.median(r['rtf'] for r in rs):.2f} |")
    lines += ["", "| Bản | Câu | Lần | Âm thanh đầu tiên (s) | Tạo xong (s) | Độ dài âm thanh (s) | RTF |",
              "|---|---|---|---|---|---|---|"]
    lines += [f"| {r['precision']} | {r['sentence']} | {r['rep']} | {r['ttfa_s']} | {r['total_s']} | "
              f"{r['audio_s']} | {r['rtf']} |" for r in rows]
    lines += ["", "Câu thử:", ""] + [f"- {k}: {v}" for k, v in SENTENCES.items()]
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    (out.with_suffix(".json")).write_text(json.dumps({"loads": loads, "rows": rows}, ensure_ascii=False, indent=2),
                                          encoding="utf-8")
    print(f"Đã ghi {out}")


def cmd_voices(args) -> None:
    tts = vieneu_local.load(args.precision)
    voices = tts.list_preset_voices()
    out_dir = HERE / "out" / "voices"
    out_dir.mkdir(parents=True, exist_ok=True)
    cards = []
    for i, (label, name) in enumerate(voices, 1):
        players = []
        for sid in VOICE_SENTENCES:
            fn = f"{i:02d}_{sid}.wav"
            audio = tts.infer(SENTENCES[sid], voice=name)
            tts.save(audio, out_dir / fn)
            players.append(f'<p><b>{sid}</b> <audio controls preload="none" src="voices/{fn}"></audio></p>')
        print(f"{i:02d} {name}")
        cards.append(f"<section><h2>{i:02d}. {html.escape(label)}</h2>{''.join(players)}</section>")
    page = (
        "<!doctype html><meta charset='utf-8'><title>Nghe thử giọng VieNeu</title>"
        "<style>body{font-family:sans-serif;max-width:760px;margin:24px auto;padding:0 16px}"
        "section{border-bottom:1px solid #ddd;padding:8px 0}h2{font-size:17px;margin:6px 0}</style>"
        f"<h1>Nghe thử giọng VieNeu ({args.precision})</h1>"
        + "".join(f"<p><b>{k}:</b> {html.escape(SENTENCES[k])}</p>" for k in VOICE_SENTENCES)
        + "".join(cards))
    (HERE / "out" / "nghe_thu.html").write_text(page, encoding="utf-8")
    print(f"Đã ghi {HERE / 'out' / 'nghe_thu.html'}")


AB_VOICES = ("Ngọc Huyền", "Trúc Ly", "Thùy Dung", "Hải Đăng")


def cmd_ab(args) -> None:
    """Same sentence and voice in fp32 and int8, to hear whether int8 sounds worse."""
    out_dir = HERE / "out" / "ab"
    out_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    for precision in ("fp32", "int8"):
        tts = vieneu_local.load(precision)
        for i, voice in enumerate(AB_VOICES, 1):
            tts.save(tts.infer(SENTENCES["S3"], voice=voice), out_dir / f"{i}_{precision}.wav")
        del tts
    for i, voice in enumerate(AB_VOICES, 1):
        rows.append(f"<section><h2>{i}. {html.escape(voice)}</h2>"
                    f"<p>Bản A <audio controls preload='none' src='ab/{i}_fp32.wav'></audio></p>"
                    f"<p>Bản B <audio controls preload='none' src='ab/{i}_int8.wav'></audio></p></section>")
    page = ("<!doctype html><meta charset='utf-8'><title>So sánh A và B</title>"
            "<style>body{font-family:sans-serif;max-width:760px;margin:24px auto;padding:0 16px}</style>"
            f"<h1>Nghe A và B: có nghe khác nhau không?</h1><p>{html.escape(SENTENCES['S3'])}</p>"
            + "".join(rows)
            + "<p><small>Đáp án nằm trong LISTENING_TEST.txt, mục cuối. Nghe xong mới xem.</small></p>")
    (HERE / "out" / "so_sanh_A_B.html").write_text(page, encoding="utf-8")
    print(f"Đã ghi {HERE / 'out' / 'so_sanh_A_B.html'}")


def main() -> None:
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("speed")
    v = sub.add_parser("voices")
    v.add_argument("--precision", choices=["fp32", "int8"], default="fp32")
    sub.add_parser("ab")
    args = p.parse_args()
    {"speed": cmd_speed, "voices": cmd_voices, "ab": cmd_ab}[args.cmd](args)


if __name__ == "__main__":
    main()
