"""The tutor's voice (MVP step 5, Decision 4b): VieNeu-TTS v3 Turbo, int8, voice Hải Đăng, on the CPU.

Sound starts after about 0.2 s (int8 on the i5-12500H, 29/10) and is played while
the rest is still being made. stop() cuts it off, for when the user clicks or
asks something new.

for_speech() rewrites what a speech model reads badly: on 30/10 both fp32 and
int8 read "(1).docx" as "tám một đốt cách".

  python -m screentutor.speak "Bạn bấm vào nút OK ở file Giáo án 8 (1).docx"   # needs a sound card
"""

from __future__ import annotations

import re
import sys
import threading
from pathlib import Path

VOICE = "Hải Đăng"          # founder's choice, 30/10; backup "Quốc Tuấn"
PRECISION = "int8"          # founder's choice, 30/10
SAMPLE_RATE = 48_000
# Shared with the tts_eval bench, which already downloaded the models (plain files, no symlinks).
MODELS = Path(__file__).resolve().parent.parent / "tts_eval" / "models"

# "bản Word", not "file Word": the tutor's sentence usually says "file <name>" already.
FILE_KINDS = {"docx": "bản Word", "doc": "bản Word", "pdf": "bản PDF", "xlsx": "bản Excel", "xls": "bản Excel",
              "pptx": "bản PowerPoint", "ppt": "bản PowerPoint", "jpg": "ảnh", "jpeg": "ảnh",
              "png": "ảnh", "txt": "bản chữ", "zip": "file nén", "rar": "file nén"}
_EXT = re.compile(r"\.(" + "|".join(FILE_KINDS) + r")\b", re.IGNORECASE)
_COPY_NO = re.compile(r"\s*\((\d+)\)")
_OK = re.compile(r"\bO\s?K\b")
_TIME = re.compile(r"\b(\d{1,2}):(\d{2})\b")
_PDF_XPS = re.compile(r"\bPDF\s*/\s*XPS\b", re.IGNORECASE)  # "XPS" read aloud only confused the listener
_DROP = re.compile(r"[\"“”‘’'()\[\]{}*#_`<>→•]")


def for_speech(text: str) -> str:
    """Text the speech model reads the way a person would say it."""
    t = _EXT.sub(lambda m: ", " + FILE_KINDS[m.group(1).lower()], text)
    t = _COPY_NO.sub(lambda m: " số " + m.group(1), t)
    t = _OK.sub("ô kê", t)
    t = _PDF_XPS.sub("PDF", t)
    t = _TIME.sub(lambda m: f"{int(m.group(1))} giờ {int(m.group(2))}", t)
    t = t.replace("/", " ").replace("&", " và ").replace("...", ".").replace("…", ".")
    t = _DROP.sub("", t)
    t = re.sub(r"\s+([,.!?])", r"\1", t)
    t = re.sub(r",\s*,", ",", t)
    return re.sub(r"\s+", " ", t).strip()


def _load_engine(precision: str = PRECISION):
    """VieNeu with its ONNX files fetched into MODELS/<repo>/ instead of the Hugging Face cache."""
    from huggingface_hub import hf_hub_download
    from vieneu import Vieneu
    from vieneu._v3_turbo_engine.onnx_runtime_lite import OnnxV3LiteEngine

    def fetch(repo: str, files: list[str], subfolder: str | None) -> Path:
        root = MODELS / repo.split("/")[-1]
        for fn in files:
            try:
                hf_hub_download(repo, fn, repo_type="model", subfolder=subfolder or None, local_dir=root)
            except Exception:
                if fn.endswith(".json"):
                    continue  # optional metadata, as in VieNeu's own fetch
                raise
        return root / subfolder if subfolder else root

    OnnxV3LiteEngine._fetch = staticmethod(fetch)
    return Vieneu(backend="onnx", precision=precision)


class Speaker:
    """Speaks one sentence at a time. engine and play are injectable so the logic runs without a sound card."""

    def __init__(self, engine=None, play=None, voice: str = VOICE):
        self._engine = engine
        self._play = play          # play(chunks: iterator of float32 arrays, stop: Event) -> None
        self.voice = voice
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._load_lock = threading.Lock()

    def load(self) -> None:
        """Takes about 2 s; call it once at start-up, off the UI thread."""
        with self._load_lock:  # start-up loading and a first sentence may race
            if self._engine is None:
                self._engine = _load_engine()

    def speak(self, text: str) -> str:
        """Blocks until the sentence is spoken or stop() is called. Returns the text actually read."""
        spoken = for_speech(text)
        if not spoken:
            return spoken
        self.load()
        with self._lock:
            self._stop.clear()
            chunks = self._engine.infer_stream(spoken, voice=self.voice)
            (self._play or _play_sounddevice)(chunks, self._stop)
        return spoken

    def stop(self) -> None:
        self._stop.set()


def _play_sounddevice(chunks, stop: threading.Event) -> None:
    import numpy as np
    import sounddevice as sd

    with sd.OutputStream(samplerate=SAMPLE_RATE, channels=1, dtype="float32") as out:
        for chunk in chunks:
            if stop.is_set():
                out.abort()
                return
            out.write(np.asarray(chunk, dtype="float32").reshape(-1, 1))


def main(argv=None) -> None:
    text = " ".join(argv if argv is not None else sys.argv[1:]) or "Bạn bấm vào chữ File ở góc trên bên trái nhé."
    print(f"Đọc: {for_speech(text)}")
    Speaker().speak(text)


if __name__ == "__main__":
    main()
