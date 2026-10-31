"""Transcribe recordings with Muse Voice Transcribe and write a sheet to score by ear.

  python -m stt_eval.transcribe stt_eval/audio/*.m4a          # mom's voice notes (T3)
  python -m stt_eval.transcribe --refs refs.tsv stt_eval/audio/*.wav

Each file runs twice: "auto" (language auto-detected) and "vi+kw" (Vietnamese
bias plus app words). Any format ffmpeg reads is converted to WAV, mono,
16-bit, 24 kHz, the only input the batch endpoint accepts.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import tempfile
import time
from datetime import datetime
from pathlib import Path

import httpx
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parent.parent
RESULTS_DIR = Path(__file__).parent / "results"
URL = "https://api.meta.ai/v1/asr/transcribe"
MODEL = "muse-voice-transcribe-1.0"
USD_PER_HOUR = 0.18

# Words mom says about her computer work; a bias, not a guarantee of spelling.
KEYWORDS = ["Zalo", "Word", "Excel", "PDF", "file", "giáo án", "tổ trưởng", "Google Sheet",
            "Brave", "Chrome", "Downloads", "thư mục", "bảng tính", "Save As"]
# Everyday words of a mother asking her child; added after T3 showed "mẹ" heard as "mày".
FAMILY_WORDS = ["mẹ", "con", "ấn", "bấm", "mở", "gửi", "lưu", "tab", "link"]
CONFIGS = {
    "auto": {},
    "vi+kw": {"languageBias": ["Vietnamese"], "keywords": KEYWORDS},
    "vi+kw+me": {"languageBias": ["Vietnamese"], "keywords": KEYWORDS + FAMILY_WORDS},
}


def to_wav(src: Path, dst: Path) -> None:
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(src), "-ac", "1", "-ar", "24000",
                    "-c:a", "pcm_s16le", "-map_metadata", "-1", str(dst)], check=True)


def transcribe(client: httpx.Client, wav: Path, extra: dict) -> dict:
    request = {"model": MODEL, "audioEncoding": "WAV", "mode": "PUSH_TO_TALK", **extra}
    t = time.perf_counter()
    r = client.post(URL, files={
        "request": (None, json.dumps(request, ensure_ascii=False), "application/json"),
        "audio": (wav.name, wav.read_bytes(), "audio/wav"),
    }, headers={"Accept": "application/json"})
    latency = time.perf_counter() - t
    if r.is_error:
        return {"error": f"HTTP {r.status_code}: {r.text[:300]}", "latency_s": round(latency, 2)}
    body = r.json()
    return {"transcript": body.get("transcript", ""), "audio_ms": body.get("audioDurationMs"),
            "session": body.get("sessionId"), "latency_s": round(latency, 2)}


def load_refs(path: Path | None) -> dict[str, str]:
    """Optional file: file name, then a tab or spaces, then what was actually said."""
    if not path:
        return {}
    refs = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        parts = line.strip().split(None, 1)
        if len(parts) == 2:
            refs[parts[0]] = parts[1].strip()
    return refs


def main(argv=None) -> None:
    p = argparse.ArgumentParser(prog="python -m stt_eval.transcribe")
    p.add_argument("files", nargs="+", type=Path)
    p.add_argument("--refs", type=Path, help="TSV: tên file <tab> câu nói thật")
    p.add_argument("--label", default="", help="gắn vào tên thư mục kết quả, ví dụ 'me' hoặc 'tts'")
    p.add_argument("--config", choices=list(CONFIGS), help="chỉ chạy một cấu hình")
    args = p.parse_args(argv)
    configs = {args.config: CONFIGS[args.config]} if args.config else CONFIGS

    load_dotenv(REPO_ROOT / ".env")
    key = os.environ.get("MODEL_API_KEY", "").strip()
    if not key:
        raise SystemExit("Chưa có MODEL_API_KEY trong .env")
    refs = load_refs(args.refs)

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    out_dir = RESULTS_DIR / f"{stamp}{'-' + args.label if args.label else ''}"
    out_dir.mkdir(parents=True)
    rows, total_ms = [], 0
    with httpx.Client(timeout=120, headers={"Authorization": f"Bearer {key}"}) as client, \
            tempfile.TemporaryDirectory() as tmp:
        for src in args.files:
            wav = Path(tmp) / (src.stem + ".wav")
            to_wav(src, wav)
            row = {"file": src.name, "ref": refs.get(src.name, "")}
            for name, extra in configs.items():
                res = transcribe(client, wav, extra)
                row[name] = res
                total_ms += res.get("audio_ms") or 0
                print(f"{src.name} [{name}] {res.get('latency_s')}s: {res.get('transcript', res.get('error'))}")
            rows.append(row)

    (out_dir / "transcripts.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = ["# Phiếu chấm nhận giọng (T3)", "",
             f"Model `{MODEL}`, chế độ PUSH_TO_TALK. 'auto' = tự nhận ngôn ngữ; "
             "'vi+kw' = gợi ý tiếng Việt + từ khoá app.",
             f"Âm thanh đã gửi: {total_ms / 1000:.1f} s, chi phí khoảng ${total_ms / 3.6e6 * USD_PER_HOUR:.4f}.", "",
             "Chấm mỗi cấu hình: **còn** (ý chính nguyên vẹn) / **một phần** / **mất**.", ""]
    for i, row in enumerate(rows, 1):
        lines += [f"## {i}. {row['file']}", "",
                  f"- Câu nói thật: {row['ref'] or '__________ (founder ghi theo trí nhớ khi nghe)'}"]
        for name in configs:
            r = row[name]
            lines.append(f"- {name} ({r.get('latency_s')} s): {r.get('transcript', r.get('error'))}")
            lines.append(f"  - Chấm: ______")
        lines.append("")
    (out_dir / "PHIEU_CHAM.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"Đã ghi {out_dir / 'PHIEU_CHAM.md'}")


if __name__ == "__main__":
    main()
