"""One tutor turn: screenshot + Windows state + mom's question -> what to say and where to point.

Decision 3: Muse Spark 1.3 through image understanding (Chat Completions, JSON
answer on the 0-1000 grid), reasoning_effort "low". Decision 2a: the Windows
state summary goes next to the screenshot as text. This module only asks; it
never clicks or types.

The pointing instructions are the exact text that scored 10/12 on the real
cases (grounding_test.meta_api.vision_prompt); the spoken-answer rules are
appended after them, so the part that was measured stays unchanged.

B1 (02/11) appends a third block, after both: whether she wants one answer or a task
walked through, the parts of a big task (taken from the message on screen when the
school's message is the task), what the next step is (click, read a region, scroll on),
a box around what to read, and notes that carry a long message across screens. With
task_rules=False the prompt is exactly the one T4 measured, for comparison.

The answer streams (T12 R5, 02/11). The API writes JSON keys in sorted order whatever the
schema says, and capitals sort first, so the fields that show the step are capitalised and
the ones that can wait are named task_*: the ring appears as soon as X and Y are in, the
voice as soon as say is in, while the plan and the notes finish arriving.

B2 (02/11): a later turn says what she did. After a click the sentence is the measured
one; after a read step or a scroll it must not claim she clicked (founder's decision).

  python -m screentutor.tutor --image case_04.png --state-file state.txt "Mẹ bấm vào đâu?"
  py -m screentutor.tutor --live --delay 5 "Mẹ muốn mở file giáo án thì bấm vào đâu?"   # Windows
  py -m screentutor.tutor --live --delay 5 --show 15 "Bấm vào đâu để tạo file PDF?"     # + vòng chỉ trên màn hình
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

import httpx

BASE_URL = "https://api.meta.ai/v1"
MODEL = "muse-spark-1.3"  # Standard tier; never a Contributor variant
EFFORT = "minimal"  # T12 R5 (02/11): "low" thought 650 tokens on the task prompt; the 12 cases stayed on target at this
TIMEOUT_S = 30
RETRY_STATUSES = (429, 500, 502, 503, 504)
RETRY_LINE_S = 1.0

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
    "mình sẽ bấm hay mở hộ. Không thêm câu nói về bản thân, ví dụ \"mình nói kỹ vậy cho dễ tìm\".\n"
    "- Chỉ nói MỘT bước tiếp theo, tối đa hai câu ngắn. Nếu phải làm một việc khác trước thì mới bấm được "
    "(ví dụ bôi đen đoạn chữ trước khi đổi cỡ chữ), bước tiếp theo là việc đó.\n"
    "- Nếu bấm vào chỗ đó sẽ gửi tin nhắn hay file cho người khác, hoặc thay thế (ghi đè) một file đã có, "
    "đặt caution=true và nói rõ điều sẽ xảy ra, ví dụ \"Bấm Yes thì file PDF cũ cùng tên sẽ bị thay bằng "
    "file mới.\" Các bước khác đặt caution=false.\n"
    "- Tả chỗ cần bấm bằng vị trí và hình dáng dễ thấy, ví dụ \"góc trên bên trái\", "
    "\"biểu tượng thư mục màu vàng\". Nếu trên nút có chữ tiếng Anh thì đọc đúng chữ đó.\n"
    "- Nếu hợp, thêm một vế ngắn để người dùng hiểu bấm vào đó để làm gì.\n"
    "- Nếu found=false, nói ngắn vì sao chưa thấy và người dùng nên làm gì, hoặc hỏi lại.\n"
    "- Không dùng ký hiệu, gạch đầu dòng, emoji hay toạ độ."
)

# B1 (02/11): founder's ideas of 02/11, after the measured text and the speech rules. Kept this short on
# purpose: T12 R5 (02/11), the first long version took the median from 4.9 s to 11.1 s, nearly all of it thinking.
TASK_HEAD = "\n\nTrả lời thêm:\n"
POINTER_LINE = ("- Lúc hỏi, chuột của người dùng {pointer}; nếu người dùng nói \"cái này\", \"chỗ này\", đó là chỗ "
                "đang được chỉ.\n")
# Measured 02/11 on case_04 (the link that opened behind Zalo): at effort low the state text alone gave 4/5, at
# minimal 1/5, with this line 5/5. Without its first clause it also took her away from a link she had not clicked yet.
STATE_RULE = ("- Nếu người dùng nói đã bấm rồi mà không thấy, đối chiếu với trạng thái Windows: nếu thứ đó đã mở ở một cửa "
              "sổ nằm phía sau, chỉ vào biểu tượng của cửa sổ đó trên thanh tác vụ, không chỉ lại chỗ đã bấm.\n")
SAY_SELF_RULE = ("- Trong say không nói về việc mình làm, ví dụ không viết \"để mình hướng dẫn\". Tên file viết như lời "
                 "nói: bỏ đuôi file, thay dấu gạch bằng dấu cách.\n")
MODE_RULE = "- mode: \"answer\" nếu chỉ hỏi một điều; \"guide\" nếu là việc nhiều bước.\n"
PLAN_RULE = ("- task_plan: với guide, 2-6 phần theo thứ tự, mỗi phần tối đa 8 chữ; việc ghi trong tin nhắn đang hiện thì "
             "lấy từ chính tin đó; tin còn tiếp ở dưới thì để rỗng. Với answer để rỗng. Có task_plan thì say mở đầu "
             "\"Việc này có N phần.\"\n")
PLAN_FOLLOW = ("- task_plan: rỗng nếu kế hoạch không đổi. Chỉ điền khi vừa đọc hết nội dung giao việc: 2-6 phần, mỗi phần "
               "tối đa 8 chữ, lấy từ chính nội dung đó.\n")
TARGET_RULES = ("- Target: \"click\" (X, Y là tâm chỗ bấm); \"read\" (đọc một vùng; Box là khung vùng đó, X, Y là tâm); "
                "\"scroll\" (nội dung cần đọc bị cắt ở mép dưới; phải kéo xuống đọc hết trước khi read hay click; say bảo "
                "kéo xuống, X, Y là giữa vùng cần kéo); \"none\" (found=false). Không phải read thì Box bốn số 0.\n")
NOTES_RULE = "- task_notes: khi đọc nội dung dài, ghi tối đa 80 chữ điều cần nhớ; còn lại để rỗng.\n"
NOTES_FOLLOW = "- task_notes: nếu vừa đọc thêm, viết lại đủ ghi chú cũ cộng phần mới (tối đa 80 chữ); nếu không thì rỗng.\n"
PART_RULE = "- task_part: số thứ tự (từ 1) của phần chứa bước tiếp theo; xong hết thì bằng số phần; chưa có phần nào thì 0.\n"
LOGIN_RULE = "- Ô đăng nhập: chỉ ô để người dùng tự gõ; không đọc, nhắc hay đoán mật khẩu."
# B5 (02/11): what she has done before, found on her own machine. After everything that was measured.
KNOWN_BLOCK = ("\n\nNhững gì đã biết về người dùng, từ các việc trước trên máy này. Chỉ để tham khảo, màn hình hiện tại "
               "quan trọng hơn; không nhắc lại với người dùng:\n{known}")
LEARN_PROMPT = (
    "Đây là biên bản một việc người dùng, một cô giáo lớn tuổi, vừa làm trên máy tính cùng tutor:\n\n{record}\n\n"
    "Tóm lại thành ghi chú ngắn bằng tiếng Việt có dấu:\n"
    "- title: tên việc tối đa 10 chữ, viết như người ta gọi việc đó.\n"
    "- apps: các app đã đi qua.\n"
    "- path: tối đa 6 bước chính, mỗi bước tối đa 8 chữ.\n"
    "- result: một câu ngắn nói kết quả.\n"
    "- keywords: tối đa 8 từ khoá để tìm lại việc này, gồm cả cách nói khác của người dùng.\n"
    "- facts: 0 đến 3 điều bền vững về công việc hay thói quen của người dùng mà biên bản này cho thấy, mỗi điều một câu "
    "ngắn, ví dụ \"Hay nhận giáo án qua Zalo nhóm tổ\". Chỉ ghi điều có căn cứ trong biên bản. Không ghi mật khẩu, số "
    "điện thoại hay tên người."
)
LEARN_SCHEMA = {
    "type": "object",
    "properties": {"title": {"type": "string"}, "apps": {"type": "array", "items": {"type": "string"}},
                   "path": {"type": "array", "items": {"type": "string"}}, "result": {"type": "string"},
                   "keywords": {"type": "array", "items": {"type": "string"}},
                   "facts": {"type": "array", "items": {"type": "string"}}},
    "required": ["title", "apps", "path", "result", "keywords", "facts"],
    "additionalProperties": False,
}
FOLLOW_PLAN = "\n\nViệc này đã được chia thành các phần: {parts}. Bước vừa rồi thuộc phần {part}."
FOLLOW_NOTES = "\n\nNhững gì đã đọc được ở các lượt trước: \"{notes}\""
MODES = ("answer", "guide")
TARGETS = ("click", "read", "scroll", "none")
MAX_PARTS, MAX_PART_WORDS = 6, 12
BOX_SCHEMA = {
    "type": "object",
    "properties": {k: {"type": "number"} for k in ("x1", "y1", "x2", "y2")},
    "required": ["x1", "y1", "x2", "y2"],
    "additionalProperties": False,
}

REPLY_SCHEMA = {
    "type": "object",
    "properties": {
        "found": {"type": "boolean"},
        "x": {"type": "number"},
        "y": {"type": "number"},
        "element": {"type": "string"},
        "say": {"type": "string"},
        "caution": {"type": "boolean"},   # sends something or replaces a file (founder's rule, 27/10)
    },
    "required": ["found", "x", "y", "element", "say", "caution"],
    "additionalProperties": False,
}

# Later turns of the same task (step 4): the screenshot is taken after the user clicked and the screen settled.
FOLLOW_BLOCK = (
    "\n\nĐây là lượt tiếp theo của cùng việc đó. Lượt trước, tutor đã nói: \"{last_say}\" "
    "{acted}{changed}\n"
    "- step_done: true nếu màn hình cho thấy bước vừa hướng dẫn đã làm xong.\n"
    "- goal_done: true nếu điều người dùng hỏi đã làm xong hẳn. Khi đó đặt found=false và trong say "
    "chỉ báo ngắn là đã xong (thay cho quy tắc found=false bên dưới).\n"
    "- Nếu bước vừa rồi chưa xong, chỉ lại chỗ cần bấm và nói nhẹ nhàng để người dùng thử lại.\n"
    "- Nếu bước đã xong mà việc chưa xong, chỉ bước tiếp theo."
)
FOLLOW_ACTED = {
    "click": "Sau đó người dùng đã bấm chuột; ảnh trên được chụp khi màn hình đã đứng yên.",
    "read": "Sau đó người dùng bấm chuột để báo đã đọc xong; ảnh trên được chụp khi màn hình đã đứng yên.",
    "moved": "Sau đó màn hình đã thay đổi mà không có cú bấm nào, thường là người dùng đã kéo xuống; "
             "ảnh trên được chụp sau đó.",
}
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
_REPLY_PROPS = {
    "Box": BOX_SCHEMA, "Caution": {"type": "boolean"}, "Target": {"type": "string", "enum": list(TARGETS)},
    "X": {"type": "number"}, "Y": {"type": "number"},   # the keys up to here show the step
    "element": {"type": "string"}, "found": {"type": "boolean"}, "mode": {"type": "string", "enum": list(MODES)},
    "say": {"type": "string"},                          # then the voice; the rest can come last
    "task_notes": {"type": "string"}, "task_plan": {"type": "array", "items": {"type": "string"}},
}
REPLY_SCHEMA_V2 = {"type": "object", "properties": _REPLY_PROPS, "required": list(_REPLY_PROPS),
                   "additionalProperties": False}
_FOLLOW_PROPS = {**{k: v for k, v in _REPLY_PROPS.items() if k != "mode"}, "Goal_done": {"type": "boolean"},
                 "Step_done": {"type": "boolean"}, "task_part": {"type": "integer"}}
FOLLOW_SCHEMA_V2 = {"type": "object", "properties": _FOLLOW_PROPS, "required": list(_FOLLOW_PROPS),
                    "additionalProperties": False}


def point_prompt(question: str, state: str | None = None) -> str:
    """Identical to the measured grounding prompt."""
    return POINT_PROMPT.format(question=question, state=STATE_BLOCK.format(state=state) if state else "")


def task_rules(pointer: str | None = None) -> str:
    """The first turn: answer or guide, the parts, what the next step is, notes, logins."""
    head = TASK_HEAD + (POINTER_LINE.format(pointer=pointer) if pointer else "")
    return head + STATE_RULE + SAY_SELF_RULE + MODE_RULE + PLAN_RULE + TARGET_RULES + NOTES_RULE + LOGIN_RULE


def follow_task_rules(plan: list[str] | None, part: int | None, notes: str) -> str:
    """Later turns: where the task stands, then the same fields without re-planning."""
    text = ""
    if plan:
        parts = "; ".join(f"{i + 1}. {p}" for i, p in enumerate(plan))
        text += FOLLOW_PLAN.format(parts=parts, part=min(max(part or 1, 1), len(plan)))
    if notes:
        text += FOLLOW_NOTES.format(notes=notes)
    return text + TASK_HEAD + SAY_SELF_RULE + PART_RULE + PLAN_FOLLOW + TARGET_RULES + NOTES_FOLLOW + LOGIN_RULE


def build_prompt(question: str, state: str | None = None, task: bool = True, pointer: str | None = None,
                 known: str | None = None) -> str:
    text = point_prompt(question, state) + SAY_RULES + (task_rules(pointer) if task else "")
    return text + KNOWN_BLOCK.format(known=known) if known else text


def build_follow_up_prompt(goal: str, last_say: str, state: str | None = None,
                           screen_changed: bool | None = None, task: bool = True,
                           plan: list[str] | None = None, part: int | None = None, notes: str = "",
                           acted: str = "click") -> str:
    changed = "" if acted == "moved" else SCREEN_CHANGED[screen_changed]  # no click to talk about
    text = (point_prompt(goal, state)
            + FOLLOW_BLOCK.format(last_say=last_say, acted=FOLLOW_ACTED[acted], changed=changed) + SAY_RULES)
    return text + follow_task_rules(plan, part, notes) if task else text


def build_body(question: str, image_data_url: str, state: str | None = None,
               model: str = MODEL, effort: str | None = EFFORT, task: bool = True,
               pointer: str | None = None, known: str | None = None) -> dict:
    return _body(build_prompt(question, state, task, pointer, known), image_data_url, "tutor_reply",
                 REPLY_SCHEMA_V2 if task else REPLY_SCHEMA, model, effort)


def build_follow_up_body(goal: str, last_say: str, image_data_url: str, state: str | None = None,
                         screen_changed: bool | None = None, model: str = MODEL,
                         effort: str | None = EFFORT, task: bool = True, plan: list[str] | None = None,
                         part: int | None = None, notes: str = "", acted: str = "click") -> dict:
    text = build_follow_up_prompt(goal, last_say, state, screen_changed, task, plan, part, notes, acted)
    return _body(text, image_data_url, "tutor_follow_up", FOLLOW_SCHEMA_V2 if task else FOLLOW_SCHEMA, model, effort)


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
    caution: bool = False          # the click sends something or replaces a file
    step_done: bool | None = None  # later turns only
    goal_done: bool | None = None
    mode: str = ""                 # B1: "answer" or "guide" (first turn); "" from a v1 prompt
    plan: list[str] = field(default_factory=list)
    part: int | None = None        # later turns: the part (from 1) the next step belongs to
    target: str = ""               # "click", "read", "scroll" or "none"; "" from a v1 prompt
    box: tuple[float, float, float, float] | None = None  # target "read": x1, y1, x2, y2 on the grid
    notes: str = ""
    latency_s: float = 0.0
    usage: dict = field(default_factory=lambda: {"input": 0, "output": 0, "cached": 0, "reasoning": 0})
    raw: dict | None = None
    error: str | None = None

    def box_px(self, size: tuple[int, int]) -> tuple[int, int, int, int] | None:
        if self.box is None:
            return None
        w, h = size
        x1, y1, x2, y2 = self.box
        return round(x1 * w / 1000), round(y1 * h / 1000), min(round(x2 * w / 1000), w - 1), min(round(y2 * h / 1000), h - 1)

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
    return _read_answer(answer, res)


def _read_answer(answer: dict, res: Reply) -> Reply:
    answer = {k.lower().removeprefix("task_"): v for k, v in answer.items()}
    res.say = str(answer.get("say") or "").strip()
    res.element = str(answer.get("element") or "").strip()
    res.found = bool(answer.get("found"))
    res.caution = bool(answer.get("caution"))
    for key in ("step_done", "goal_done"):
        if key in answer:
            setattr(res, key, bool(answer[key]))
    x, y = answer.get("x"), answer.get("y")
    if res.found and isinstance(x, (int, float)) and isinstance(y, (int, float)):
        res.point = (_grid(x), _grid(y))
    _parse_task(answer, res)
    res.say = spoken(res.say, res.target)
    return res


_PARTS_SAID = re.compile(r"^Việc này có [^.]*phần\.\s*")
_ABOUT_ITSELF = re.compile(r"^(?:để )?mình\s+(?:nói|chỉ|nhắc|dặn|thấy|hướng dẫn|giải thích)\b", re.IGNORECASE)


def spoken(say: str, target: str = "") -> str:
    """What the voice says. Two things the prompt asks for and the model now and then forgets, so they are made
    sure of here: no sentence about the tutor itself (1 in 24 calls, T12 R5b), and no count of parts while the
    message has not been read to its end (said 2 parts, then 5, on the first big-task runs)."""
    if target == "scroll":
        say = _PARTS_SAID.sub("", say)
    return " ".join(s for s in re.split(r"(?<=[.!?])\s+", say) if not _ABOUT_ITSELF.match(s)) or say


def _grid(v) -> float:
    return min(max(float(v), 0.0), 1000.0)


def _parse_task(answer: dict, res: Reply) -> None:
    """B1 fields, read defensively: a wrong value falls back to what the v1 fields already say."""
    plan = answer.get("plan")
    if isinstance(plan, list):
        parts = [" ".join(str(p).split()[:MAX_PART_WORDS]) for p in plan if str(p).strip()]
        res.plan = parts[:MAX_PARTS]
    mode = answer.get("mode")
    if mode is not None:
        res.mode = mode if mode in MODES else ("guide" if res.plan else "answer")
    if isinstance(answer.get("part"), (int, float)) and not isinstance(answer.get("part"), bool):
        res.part = max(0, int(answer["part"]))  # 0: no parts yet (still reading)
    res.notes = str(answer.get("notes") or "").strip()
    box = answer.get("box")
    if isinstance(box, dict) and all(isinstance(box.get(k), (int, float)) for k in ("x1", "y1", "x2", "y2")):
        x1, x2 = sorted((_grid(box["x1"]), _grid(box["x2"])))
        y1, y2 = sorted((_grid(box["y1"]), _grid(box["y2"])))
        if x2 - x1 >= 5 and y2 - y1 >= 5:  # four zeros, or a sliver, is no box
            res.box = (x1, y1, x2, y2)
    target = answer.get("target")
    if target is None:
        return  # a v1 answer
    if target not in TARGETS:
        target = "click" if res.point else "none"
    if target == "read":
        if res.box is None:
            target = "click" if res.point else "none"  # nothing to frame: a plain ring, or nothing
        elif res.point is None:
            res.found = True
            res.point = ((res.box[0] + res.box[2]) / 2, (res.box[1] + res.box[3]) / 2)
    if target != "read":
        res.box = None
    if target == "none":
        res.point, res.found = None, False
    elif res.point is None:
        target = "none"  # a click or a scroll with nowhere to show it
    if target == "scroll":
        res.plan = []    # the plan comes from the whole message, once it has been read
    res.target = target


_KEY_Y = re.compile(r'"Y"\s*:\s*-?[\d.]+(?=\s*[,}])')
_KEY_SAY = re.compile(r'"say"\s*:\s*("(?:[^"\\]|\\.)*")')


class EarlyAnswer:
    """Reads the answer while it arrives. on_mark gets a partial Reply as soon as the step can be shown,
    on_say the sentence as soon as it is complete; each at most once, and neither if nothing can be read."""

    def __init__(self, on_mark=None, on_say=None):
        self.on_mark, self.on_say = on_mark, on_say
        self.marked = self.said = False
        self.target = ""

    def feed(self, text: str) -> None:
        if not self.marked and self.on_mark:
            m = _KEY_Y.search(text)
            if m:
                self.marked = True
                try:
                    head = json.loads(text[:m.end()] + "}")
                except json.JSONDecodeError:
                    head = None
                if head is not None:
                    self.target = str(head.get("Target") or "")
                    self.on_mark(_read_answer({**head, "found": self.target != "none"}, Reply()))
        if not self.said and self.on_say:
            m = _KEY_SAY.search(text)
            if m:
                self.said = True
                self.on_say(spoken(json.loads(m.group(1)).strip(), self.target))


class Tutor:
    def __init__(self, api_key: str, model: str = MODEL, effort: str | None = EFFORT,
                 base_url: str = BASE_URL, timeout: float = TIMEOUT_S, task: bool = True):
        if not api_key:
            raise ValueError("MODEL_API_KEY is empty")
        self.model, self.effort, self.task = model, effort, task
        self._http = httpx.Client(base_url=base_url, timeout=timeout,
                                  headers={"Authorization": f"Bearer {api_key}"})

    def close(self) -> None:
        self._http.close()

    def warm(self) -> None:
        """Open the connection (DNS, TLS) before the first question; the pool keeps it for the first answer."""
        try:
            self._http.get("/models")
        except httpx.HTTPError:
            pass

    def ask(self, question: str, image_data_url: str, state: str | None = None, pointer: str | None = None,
            on_mark=None, on_say=None, known: str | None = None) -> Reply:
        return self._call(build_body(question, image_data_url, state, self.model, self.effort, self.task, pointer, known),
                          on_mark, on_say)

    def follow_up(self, goal: str, last_say: str, image_data_url: str, state: str | None = None,
                  screen_changed: bool | None = None, plan: list[str] | None = None, part: int | None = None,
                  notes: str = "", acted: str = "click", on_mark=None, on_say=None) -> Reply:
        """After the user acted and the screen settled: was the step done, is the task done, what next."""
        return self._call(build_follow_up_body(goal, last_say, image_data_url, state, screen_changed, self.model,
                                               self.effort, self.task, plan, part, notes, acted), on_mark, on_say)

    def summarise(self, record: str) -> dict | None:
        """B5: a finished task as a short note. Words only, no picture. None when it cannot be had; nobody waits for this."""
        body = {"model": self.model, "reasoning_effort": self.effort,
                "messages": [{"role": "user", "content": LEARN_PROMPT.format(record=record)}],
                "response_format": {"type": "json_schema", "json_schema": {"name": "task_note", "schema": LEARN_SCHEMA}}}
        try:
            resp, _ = self._post("/chat/completions", body)
            return json.loads(resp["choices"][0]["message"]["content"])
        except (httpx.HTTPError, RuntimeError, ValueError, KeyError, IndexError):
            return None

    def _call(self, body: dict, on_mark=None, on_say=None) -> Reply:
        """One answer. A sentence without Vietnamese diacritics (4 of 104 so far, T4-T8a) would be read
        as nonsense by the voice, so that answer is asked for once more."""
        total = 0.0
        early = EarlyAnswer(on_mark, on_say) if on_mark or on_say else None
        for attempt in range(2):
            try:
                resp, elapsed = self._stream("/chat/completions", body, early) if early else \
                    self._post("/chat/completions", body)
            except (httpx.HTTPError, RuntimeError, ValueError) as e:
                if attempt == 0 and isinstance(e, httpx.TransportError):
                    time.sleep(RETRY_LINE_S)  # the line dropped (seen 02/11, her line is longer than ours): once more
                    continue
                return Reply(error=str(e))
            total += elapsed
            res = parse_reply(resp)
            res.latency_s = total
            if not (res.say and res.say.isascii()):
                break
        return res

    def _stream(self, path: str, body: dict, early: EarlyAnswer, max_attempts: int = 3) -> tuple[dict, float]:
        """As _post, reading the answer while it arrives."""
        delay = 0.5
        for attempt in range(1, max_attempts + 1):
            started = time.perf_counter()
            with self._http.stream("POST", path, json={**body, "stream": True,
                                                       "stream_options": {"include_usage": True}}) as r:
                if r.status_code in RETRY_STATUSES and attempt < max_attempts:
                    time.sleep(delay)
                    delay *= 2
                    continue
                if r.is_error:
                    raise RuntimeError(f"HTTP {r.status_code}: {r.read().decode(errors='replace')[:300]}")
                text, usage = "", {}
                for line in r.iter_lines():
                    if not line.startswith("data:") or line[5:].strip() == "[DONE]":
                        continue
                    chunk = json.loads(line[5:])
                    usage = chunk.get("usage") or usage
                    delta = ((chunk.get("choices") or [{}])[0].get("delta") or {}).get("content")
                    if delta:
                        text += delta
                        early.feed(text)
            return {"choices": [{"message": {"content": text}}], "usage": usage}, time.perf_counter() - started
        raise RuntimeError("unreachable")

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
