"""Hearing the user (MVP step 5): Muse Voice Transcribe over the realtime WebSocket.

Decision 4c: the user calls the tutor with the "Hỏi" button or by holding Ctrl+Alt.
  - "Hỏi" button  -> ENDPOINTING: the model notices when she stops talking (Decision 4d).
  - Ctrl+Alt held -> PUSH_TO_TALK: she talks while holding; letting go ends the question.
Settings are the T3 winner (30/10): Vietnamese bias plus app words and mom's own words,
8/8 of her real questions kept their meaning.

Protocol (dev.meta.ai docs, read 31/10): the key travels in the first JSON frame,
the server answers {"sessionId"}, then raw PCM16 mono 24 kHz in binary frames,
paced at real time; {"type": "endStream"} half-closes and the server flushes.

  python -m screentutor.listen stt_eval/audio/me_01.m4a              # a recording, as if spoken now
  py -m screentutor.listen --mic                                     # Windows: speak, it stops when you stop
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
import sys
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

URL = "wss://api.meta.ai/v1/asr/realtime"
MODEL = "muse-voice-transcribe-1.0"
RATE = 24_000
FRAME_MS = 80
FRAME_BYTES = RATE * 2 * FRAME_MS // 1000
KEYWORDS = ["Zalo", "Word", "Excel", "PDF", "file", "giáo án", "tổ trưởng", "Google Sheet", "Brave", "Chrome",
            "Downloads", "thư mục", "bảng tính", "Save As",
            "mẹ", "con", "ấn", "bấm", "mở", "gửi", "lưu", "tab", "link"]   # = stt_eval "vi+kw+me"
NO_SPEECH_S = 8.0      # ENDPOINTING: stop if she has not started talking by then
MAX_TURN_S = 45.0
TRAILING_SILENCE_S = 2.5
# ENDPOINTING ends a turn at every pause between sentences; on 31/10 it cut mom's me_01 after its first
# sentence and lost the half that said what was wrong. So after a turn ends, wait this long for more speech
# and join it to the same question. T7a (31/10, rule fixed before the run): without joining 5/8 of her real
# questions kept their meaning, with 1.0 s all 8; her pauses inside a question were 0.40-0.72 s.
JOIN_WITHIN_S = 1.0


def handshake(api_key: str, mode: str) -> dict:
    return {"authorization": {"accessToken": f"Bearer {api_key}"}, "audioEncoding": "PCM_24KHZ", "model": MODEL,
            "mode": mode, "partialMode": "CUMULATIVE", "emitAudioProgress": False,
            "languageBias": ["Vietnamese"], "keywords": KEYWORDS}


@dataclass
class Heard:
    text: str | None = None              # what she said, None if nothing usable
    partial: str = ""                    # what is heard so far, for the dynamic island while she talks
    parts: list[str] = field(default_factory=list)  # ENDPOINTING: one entry per finished turn
    turns: int = 0
    speech_started: bool = False
    first_frame_at: float | None = None
    audio_end_at: float | None = None    # when the last real audio frame went out (recordings only)
    final_at: float | None = None
    error: str | None = None
    session: str | None = None
    timeline: list = field(default_factory=list)  # (time, type, turnId, transcript, audioProcessedMs)

    @property
    def wait_s(self) -> float | None:
        """From the end of her audio to the final text. Negative: the model was done before the audio ran out."""
        if self.audio_end_at is None or self.final_at is None:
            return None
        return self.final_at - self.audio_end_at


class TurnCollector:
    """Server events -> Heard. Pure logic, no network.

    ENDPOINTING: turns are collected; the question is complete when close() is called, which the
    listener does once no new speech has started within JOIN_WITHIN_S of the last finished turn.
    PUSH_TO_TALK: the final transcript completes it."""

    def __init__(self, mode: str, on_partial=None, clock=time.monotonic):
        self.mode, self.on_partial, self.clock = mode, on_partial, clock
        self.heard = Heard()
        self.open_turns: set = set()
        self.pending_since: float | None = None   # a turn finished and no other is open

    def feed(self, event: dict) -> bool:
        """True when the question is complete without waiting (an error, or PUSH_TO_TALK's final text)."""
        kind = event.get("type")
        h = self.heard
        now = self.clock()
        h.timeline.append((now, kind, event.get("turnId"), event.get("transcript") or "",
                           event.get("audioProcessedMs")))
        if kind == "error":
            h.error = event.get("message", "error")
            return True
        if kind == "speechStart":
            h.speech_started = True
            self.open_turns.add(event.get("turnId"))
            self.pending_since = None
        elif kind == "transcript":
            text = (event.get("transcript") or "").strip()
            if text:
                h.partial = " ".join(h.parts + [text]) if self.mode == "ENDPOINTING" else text
                if self.on_partial:
                    self.on_partial(h.partial)
            if self.mode == "PUSH_TO_TALK" and event.get("final"):
                return self._finish(text)
        elif kind == "speechComplete" and self.mode == "ENDPOINTING":
            h.turns += 1
            text = (event.get("transcript") or "").strip()
            if text:
                h.parts.append(text)
                h.partial = " ".join(h.parts)
            self.open_turns.discard(event.get("turnId"))
            self.pending_since = None if self.open_turns else now
        return False

    def close(self) -> None:
        if self.heard.text is None and self.heard.parts:
            self._finish(" ".join(self.heard.parts))

    def _finish(self, text: str) -> bool:
        self.heard.text = text or None
        self.heard.final_at = self.clock()
        return True


async def file_frames(path: Path, trailing_silence_s: float = TRAILING_SILENCE_S):
    """A recording as if spoken now: PCM frames at real-time pace, then silence (a live mic keeps sending too)."""
    pcm = subprocess.run(["ffmpeg", "-loglevel", "error", "-i", str(path), "-ac", "1", "-ar", str(RATE),
                          "-f", "s16le", "-"], check=True, capture_output=True).stdout
    for i in range(0, len(pcm), FRAME_BYTES):
        yield pcm[i:i + FRAME_BYTES], False
        await asyncio.sleep(FRAME_MS / 1000)
    for _ in range(round(trailing_silence_s * 1000 / FRAME_MS)):
        yield bytes(FRAME_BYTES), True
        await asyncio.sleep(FRAME_MS / 1000)


async def mic_frames(stop: threading.Event):
    """The default microphone, 80 ms frames, until stop is set."""
    import sounddevice as sd

    loop = asyncio.get_running_loop()
    q: asyncio.Queue = asyncio.Queue()

    def cb(data, frames, t, status):
        loop.call_soon_threadsafe(q.put_nowait, bytes(data))

    with sd.RawInputStream(samplerate=RATE, channels=1, dtype="int16", blocksize=FRAME_BYTES // 2, callback=cb):
        while not stop.is_set():
            try:
                yield await asyncio.wait_for(q.get(), timeout=0.2), False
            except asyncio.TimeoutError:
                continue


async def listen(api_key: str, frames, mode: str = "ENDPOINTING", on_partial=None,
                 stop: threading.Event | None = None, join_within_s: float | None = JOIN_WITHIN_S) -> Heard:
    """Stream frames until the question is complete. stop (PUSH_TO_TALK: Ctrl+Alt let go) ends the audio.

    join_within_s=None streams everything and keeps every turn: T7a uses it to replay the
    joining rule offline for several waits."""
    import websockets

    collector = TurnCollector(mode, on_partial)
    h = collector.heard
    done = asyncio.Event()
    started = time.monotonic()
    try:
        async with websockets.connect(f"{URL}?sessionId=screentutor-{uuid.uuid4()}", open_timeout=15,
                                      max_size=None) as ws:
            await ws.send(json.dumps(handshake(api_key, mode), ensure_ascii=False))
            ack = json.loads(await asyncio.wait_for(ws.recv(), timeout=10))
            if "sessionId" not in ack:
                h.error = f"handshake failed: {ack}"
                return h
            h.session = ack["sessionId"]

            async def send():
                async for frame, is_padding in frames:
                    if done.is_set() or (stop is not None and stop.is_set()):
                        break
                    now = time.monotonic()
                    if h.first_frame_at is None:
                        h.first_frame_at = now
                    if not is_padding:
                        h.audio_end_at = now
                    await ws.send(frame)
                    if mode == "ENDPOINTING" and not h.speech_started and now - started > NO_SPEECH_S:
                        break
                    if now - started > MAX_TURN_S:
                        break
                await ws.send(json.dumps({"type": "endStream"}))

            async def receive():
                while True:
                    timeout = None
                    if mode == "ENDPOINTING" and join_within_s is not None and collector.pending_since is not None:
                        timeout = max(0.0, join_within_s - (time.monotonic() - collector.pending_since))
                    try:
                        message = await asyncio.wait_for(ws.recv(), timeout)
                    except (asyncio.TimeoutError, websockets.ConnectionClosed):
                        return
                    if isinstance(message, bytes):
                        continue
                    if collector.feed(json.loads(message)):
                        return

            sender = asyncio.create_task(send())
            await receive()
            collector.close()
            done.set()
            await asyncio.wait_for(sender, timeout=5)
    except Exception as e:  # network, handshake, close codes: the caller says "mình chưa nghe rõ"
        h.error = h.error or f"{type(e).__name__}: {e}"
    collector.close()
    return h


def _api_key() -> str:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
    key = os.environ.get("MODEL_API_KEY", "").strip()
    if not key:
        sys.exit("Chưa có MODEL_API_KEY. Chép .env.example thành .env rồi điền key.")
    return key


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(prog="python -m screentutor.listen")
    ap.add_argument("file", nargs="?", type=Path, help="file ghi âm (m4a, wav...) phát như đang nói")
    ap.add_argument("--mic", action="store_true", help="nghe từ micro (ENDPOINTING: tự dừng khi ngừng nói)")
    ap.add_argument("--mode", choices=["ENDPOINTING", "PUSH_TO_TALK"], default="ENDPOINTING")
    args = ap.parse_args(argv)
    if not (args.file or args.mic):
        ap.error("cần một file ghi âm hoặc --mic")
    stop = threading.Event()
    frames = mic_frames(stop) if args.mic else file_frames(args.file)
    if args.mic:
        print("Đang nghe... nói câu hỏi, ngừng nói thì tự dừng." if args.mode == "ENDPOINTING"
              else "Đang nghe... bấm Enter khi nói xong.")
        if args.mode == "PUSH_TO_TALK":
            threading.Thread(target=lambda: (input(), stop.set()), daemon=True).start()
    heard = asyncio.run(listen(_api_key(), frames, args.mode, on_partial=lambda t: print(f"  … {t}"), stop=stop))
    stop.set()
    print(f"Nghe được: {heard.text!r}" + (f"  (lỗi: {heard.error})" if heard.error else ""))
    if heard.wait_s is not None:
        print(f"Chờ sau khi hết file: {heard.wait_s:.2f} s; số đoạn nói: {heard.turns}")


if __name__ == "__main__":
    main()
