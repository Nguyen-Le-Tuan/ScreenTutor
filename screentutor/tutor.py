"""One tutor turn: screenshot + Windows state + mom's question -> what to say and where to point.

Decision 3: Muse Spark 1.3 through image understanding (Chat Completions, JSON
answer on the 0-1000 grid), reasoning_effort "low". Decision 2a: the Windows
state summary goes next to the screenshot as text. This module only asks; it
never clicks or types.

The pointing instructions are the exact text that scored 10/12 on the real
cases (grounding_test.meta_api.vision_prompt); the spoken-answer rules are
appended after them, so the part that was measured stays unchanged.

  python -m screentutor.tutor --image case_04.png --state-file state.txt "Mẹ bấm vào đâu?"
  py -m screentutor.tutor --live --delay 5 "Mẹ muốn mở file giáo án thì bấm vào đâu?"   # Windows
  py -m screentutor.tutor --live --delay 5 --show 15 "Bấm vào đâu để tạo file PDF?"     # + vòng chỉ trên màn hình
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

import httpx

BASE_URL = "https://api.meta.ai/v1"
MODEL = "muse-spark-1.3"  # Standard tier; never a Contributor variant
EFFORT = "low"
TIMEOUT_S = 30
RETRY_STATUSES = (429, 500, 502, 503, 504)

POINT_PROMPT = (
    "Đây là ảnh chụp toàn màn hình một máy tính Windows.\n"
    "{state}"
    "Người dùng hỏi: \"{question}\"\n"
    "Hãy xác định phần tử giao diện cần bấm để làm đúng điều người dùng hỏi, rồi trả về "
    "toạ độ tâm của phần tử đó trên thang chuẩn hoá 0-1000: x=0 là mép trái, x=1000 là mép phải, "
    "y=0 là mép trên, y=1000 là mép dưới. Nếu không thấy phần tử phù hợp, đặt found=false."
)
STATE_BLOCK = (
    "Trạng thái Windows do chương trình đọc trực tiếp từ hệ điều hành, đáng tin cậy "
    "và có thể cho biết những điều ảnh chụp không thấy:\n{state}\n"
)
SAY_RULES = (
    "\n\nNgười dùng là một cô giáo lớn tuổi mới dùng máy tính. Trường say là đúng câu "
    "sẽ được đọc to cho người dùng nghe:\n"
    "- Viết tiếng Việt có dấu đầy đủ.\n"
    "- Gọi người dùng là \"bạn\", xưng \"mình\", dù người dùng tự xưng thế nào. Không gọi người dùng "
    "là \"mẹ\", \"cô\" hay \"con\". Giọng nhẹ nhàng, rõ ràng, không đùa.\n"
    "- Người dùng là người tự bấm: không nhờ, không mời, không nói \"giúp mình\", và không hứa là "
    "mình sẽ bấm hay mở hộ. Không thêm câu nói về bản thân.\n"
    "- Chỉ nói MỘT bước tiếp theo, tối đa hai câu ngắn.\n"
    "- Tả chỗ cần bấm bằng vị trí và hình dáng dễ thấy, ví dụ \"góc trên bên trái\", "
    "\"biểu tượng thư mục màu vàng\". Nếu trên nút có chữ tiếng Anh thì đọc đúng chữ đó.\n"
    "- Nếu hợp, thêm một vế ngắn để người dùng hiểu bấm vào đó để làm gì.\n"
    "- Nếu found=false, nói ngắn vì sao chưa thấy và người dùng nên làm gì, hoặc hỏi lại.\n"
    "- Không dùng ký hiệu, gạch đầu dòng, emoji hay toạ độ."
)

REPLY_SCHEMA = {
    "type": "object",
    "properties": {
        "found": {"type": "boolean"},
        "x": {"type": "number"},
        "y": {"type": "number"},
        "element": {"type": "string"},
        "say": {"type": "string"},
    },
    "required": ["found", "x", "y", "element", "say"],
    "additionalProperties": False,
}

# Later turns of the same task (step 4): the screenshot is taken after the user clicked and the screen settled.
FOLLOW_BLOCK = (
    "\n\nĐây là lượt tiếp theo của cùng việc đó. Lượt trước, tutor đã nói: \"{last_say}\" "
    "Sau đó người dùng đã bấm chuột; ảnh trên được chụp khi màn hình đã đứng yên.{changed}\n"
    "- step_done: true nếu màn hình cho thấy bước vừa hướng dẫn đã làm xong.\n"
    "- goal_done: true nếu điều người dùng hỏi đã làm xong hẳn. Khi đó đặt found=false và trong say "
    "chỉ báo ngắn là đã xong (thay cho quy tắc found=false bên dưới).\n"
    "- Nếu bước vừa rồi chưa xong, chỉ lại chỗ cần bấm và nói nhẹ nhàng để người dùng thử lại.\n"
    "- Nếu bước đã xong mà việc chưa xong, chỉ bước tiếp theo."
)
SCREEN_CHANGED = {True: " Chương trình đo được: sau cú bấm, màn hình đã thay đổi.",
                  False: " Chương trình đo được: sau cú bấm, màn hình không thay đổi.",
                  None: ""}
FOLLOW_SCHEMA = {
    "type": "object",
    "properties": {"step_done": {"type": "boolean"}, "goal_done": {"type": "boolean"},
                   **REPLY_SCHEMA["properties"]},
    "required": ["step_done", "goal_done", *REPLY_SCHEMA["required"]],
    "additionalProperties": False,
}


def point_prompt(question: str, state: str | None = None) -> str:
    """Identical to the measured grounding prompt."""
    return POINT_PROMPT.format(question=question, state=STATE_BLOCK.format(state=state) if state else "")


def build_prompt(question: str, state: str | None = None) -> str:
    return point_prompt(question, state) + SAY_RULES


def build_follow_up_prompt(goal: str, last_say: str, state: str | None = None,
                           screen_changed: bool | None = None) -> str:
    return (point_prompt(goal, state)
            + FOLLOW_BLOCK.format(last_say=last_say, changed=SCREEN_CHANGED[screen_changed]) + SAY_RULES)


def build_body(question: str, image_data_url: str, state: str | None = None,
               model: str = MODEL, effort: str | None = EFFORT) -> dict:
    return _body(build_prompt(question, state), image_data_url, "tutor_reply", REPLY_SCHEMA, model, effort)


def build_follow_up_body(goal: str, last_say: str, image_data_url: str, state: str | None = None,
                         screen_changed: bool | None = None, model: str = MODEL,
                         effort: str | None = EFFORT) -> dict:
    text = build_follow_up_prompt(goal, last_say, state, screen_changed)
    return _body(text, image_data_url, "tutor_follow_up", FOLLOW_SCHEMA, model, effort)


def _body(text: str, image_data_url: str, name: str, schema: dict, model: str, effort: str | None) -> dict:
    body = {
        "model": model,
        "messages": [{"role": "user", "content": [
            {"type": "text", "text": text},
            {"type": "image_url", "image_url": {"url": image_data_url}},
        ]}],
        "response_format": {"type": "json_schema", "json_schema": {"name": name, "schema": schema}},
    }
    if effort:
        body["reasoning_effort"] = effort
    return body


@dataclass
class Reply:
    say: str = ""
    found: bool = False
    point: tuple[float, float] | None = None  # 0-1000 grid, clamped
    element: str = ""
    step_done: bool | None = None  # later turns only
    goal_done: bool | None = None
    latency_s: float = 0.0
    usage: dict = field(default_factory=lambda: {"input": 0, "output": 0, "cached": 0, "reasoning": 0})
    raw: dict | None = None
    error: str | None = None

    def point_px(self, size: tuple[int, int]) -> tuple[int, int] | None:
        """Pixel of the screenshot that was sent. Screenshot pixels are physical screen pixels."""
        if self.point is None:
            return None
        w, h = size
        return min(round(self.point[0] * w / 1000), w - 1), min(round(self.point[1] * h / 1000), h - 1)


def parse_reply(resp: dict) -> Reply:
    res = Reply(raw=resp)
    u = resp.get("usage") or {}
    res.usage = {
        "input": u.get("prompt_tokens", 0),
        "output": u.get("completion_tokens", 0),
        "cached": (u.get("prompt_tokens_details") or {}).get("cached_tokens", 0),
        "reasoning": (u.get("completion_tokens_details") or {}).get("reasoning_tokens", 0),
    }
    content = (resp.get("choices") or [{}])[0].get("message", {}).get("content") or ""
    try:
        answer = json.loads(content)
    except json.JSONDecodeError:
        res.error = "answer is not valid JSON"
        return res
    res.say = str(answer.get("say") or "").strip()
    res.element = str(answer.get("element") or "").strip()
    res.found = bool(answer.get("found"))
    for key in ("step_done", "goal_done"):
        if key in answer:
            setattr(res, key, bool(answer[key]))
    x, y = answer.get("x"), answer.get("y")
    if res.found and isinstance(x, (int, float)) and isinstance(y, (int, float)):
        res.point = (min(max(float(x), 0.0), 1000.0), min(max(float(y), 0.0), 1000.0))
    return res


class Tutor:
    def __init__(self, api_key: str, model: str = MODEL, effort: str | None = EFFORT,
                 base_url: str = BASE_URL, timeout: float = TIMEOUT_S):
        if not api_key:
            raise ValueError("MODEL_API_KEY is empty")
        self.model, self.effort = model, effort
        self._http = httpx.Client(base_url=base_url, timeout=timeout,
                                  headers={"Authorization": f"Bearer {api_key}"})

    def close(self) -> None:
        self._http.close()

    def ask(self, question: str, image_data_url: str, state: str | None = None) -> Reply:
        return self._call(build_body(question, image_data_url, state, self.model, self.effort))

    def follow_up(self, goal: str, last_say: str, image_data_url: str, state: str | None = None,
                  screen_changed: bool | None = None) -> Reply:
        """After the user clicked and the screen settled: was the step done, is the task done, what next."""
        return self._call(build_follow_up_body(goal, last_say, image_data_url, state, screen_changed,
                                               self.model, self.effort))

    def _call(self, body: dict) -> Reply:
        try:
            resp, elapsed = self._post("/chat/completions", body)
        except (httpx.HTTPError, RuntimeError) as e:
            return Reply(error=str(e))
        res = parse_reply(resp)
        res.latency_s = elapsed
        return res

    def _post(self, path: str, body: dict, max_attempts: int = 3) -> tuple[dict, float]:
        delay = 0.5
        for attempt in range(1, max_attempts + 1):
            started = time.perf_counter()
            r = self._http.post(path, json=body)
            elapsed = time.perf_counter() - started
            if r.status_code in RETRY_STATUSES and attempt < max_attempts:
                time.sleep(delay)
                delay *= 2
                continue
            if r.is_error:
                raise RuntimeError(f"HTTP {r.status_code}: {r.text[:300]}")
            return r.json(), elapsed
        raise RuntimeError("unreachable")


def _api_key() -> str:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
    key = os.environ.get("MODEL_API_KEY", "").strip()
    if not key:
        sys.exit("Chưa có MODEL_API_KEY. Chép .env.example thành .env rồi điền key.")
    return key


def main(argv=None) -> None:
    from . import screen

    p = argparse.ArgumentParser(prog="python -m screentutor.tutor")
    p.add_argument("question", help="câu mẹ hỏi")
    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument("--image", help="ảnh màn hình có sẵn (.png)")
    src.add_argument("--live", action="store_true", help="Windows: chụp màn hình và đọc trạng thái ngay")
    p.add_argument("--state-file", help="file chữ chứa bản tóm tắt trạng thái (dùng với --image)")
    p.add_argument("--delay", type=int, default=0, help="chờ bấy nhiêu giây trước khi chụp (dùng với --live)")
    p.add_argument("--out", help="thư mục lưu ảnh, ảnh có đánh dấu và câu trả lời; mặc định tutor_runs/<giờ>")
    p.add_argument("--show", type=float, metavar="GIÂY",
                   help="Windows, cùng --live: hiện vòng chỉ chỗ trên màn hình bấy nhiêu giây")
    args = p.parse_args(argv)
    if args.show and not args.live:
        p.error("--show chỉ dùng cùng --live: vòng chỉ chỗ phải khớp với màn hình đang hiện")

    if args.live:
        from .state import format_vi, take_snapshot

        for left in range(args.delay, 0, -1):
            print(f"Chụp màn hình sau {left} giây... chuyển sang cửa sổ cần thử.", flush=True)
            time.sleep(1)
        img = screen.grab()
        state = format_vi(take_snapshot())
    else:
        img = screen.load(args.image)
        state = Path(args.state_file).read_text(encoding="utf-8").strip() if args.state_file else None

    tutor = Tutor(_api_key())
    try:
        reply = tutor.ask(args.question, screen.png_data_url(img), state)
    finally:
        tutor.close()

    out = Path(args.out or Path("tutor_runs") / datetime.now().strftime("%Y%m%d-%H%M%S"))
    out.mkdir(parents=True, exist_ok=True)
    px = reply.point_px(img.size)
    img.save(out / "screen.png")
    screen.mark(img, px).save(out / "pointed.png")
    data = {k: v for k, v in asdict(reply).items() if k != "raw"}
    data.update(question=args.question, state=state, image_size=img.size, point_px=px)
    (out / "reply.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "raw.json").write_text(json.dumps(reply.raw, ensure_ascii=False, indent=2), encoding="utf-8")

    if reply.error:
        print(f"Lỗi: {reply.error}")
    print(f"Tutor nói: {reply.say}")
    print(f"Chỉ vào: {reply.element or '—'} tại {px if px else 'không có'} trên ảnh {img.size[0]}x{img.size[1]}")
    print(f"Mất {reply.latency_s:.2f} s; token vào {reply.usage['input']}, ra {reply.usage['output']} "
          f"(suy luận {reply.usage['reasoning']})")
    print(f"Đã lưu {out}")
    if args.show and px:
        _show(px, args.show)


def _show(px: tuple[int, int], seconds: float) -> None:
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication

    from .overlay import Overlay

    app = QApplication.instance() or QApplication(sys.argv[:1])
    overlay = Overlay()
    overlay.point_at(*px, seconds=seconds)
    QTimer.singleShot(round(seconds * 1000) + 200, app.quit)
    app.exec()


if __name__ == "__main__":
    main()
