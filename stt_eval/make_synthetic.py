"""Synthesise mom-style questions with VieNeu to smoke-test the transcription client.

Run with the TTS venv:  tts_eval/.venv/bin/python stt_eval/make_synthetic.py
Clean synthetic speech is an upper bound, not a stand-in for mom's real voice (T3).
"""

import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent / "tts_eval"))
import vieneu_local  # noqa: E402

QUESTIONS = [
    "Cái file giáo án mẹ sửa hôm qua nó nằm ở đâu rồi con?",
    "Sao mẹ mở file ra lại thấy trắng trơn vậy?",
    "Giờ mẹ muốn gửi file này cho cô tổ trưởng qua Zalo thì làm sao?",
    "Mẹ lưu mà máy nó báo lỗi tên file, giờ làm sao?",
    "Chuyển cái file Word này ra PDF thì bấm vào đâu?",
    "Phần của mẹ trong bảng tính nằm ở chỗ nào?",
    "Mẹ bấm vào cái link rồi mà không thấy gì hết.",
    "Cái file tải về từ Zalo nó nằm trong thư mục nào?",
]
VOICES = {"bac": "Ngọc Huyền", "nam": "Thùy Dung"}


def main() -> None:
    out = HERE / "audio_synth"
    out.mkdir(exist_ok=True)
    tts = vieneu_local.load("int8")
    refs = []
    for tag, voice in VOICES.items():
        for i, q in enumerate(QUESTIONS, 1):
            name = f"tts_{tag}_{i:02d}.wav"
            tts.save(tts.infer(q, voice=voice), out / name)
            refs.append(f"{name}\t{q}")
    (out / "refs.tsv").write_text("\n".join(refs) + "\n", encoding="utf-8")
    print(f"Đã tạo {len(refs)} file trong {out}")


if __name__ == "__main__":
    main()
