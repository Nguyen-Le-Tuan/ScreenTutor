"""Thin HTTP client for the two ways of asking a Meta model where to click.

M1, computer use: Responses API with the built-in computer tool. We read the
first pointing action and never execute anything.
M2, image understanding: Chat Completions with a JSON-schema answer.

Raw responses are kept with each call so an unexpected response shape can be
inspected instead of guessed at.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field

import httpx

from . import config

CU_INSTRUCTIONS = (
    "Bạn đang giúp một người dùng lớn tuổi thao tác trên máy tính Windows. "
    "Dựa vào ảnh chụp màn hình, hãy thực hiện đúng MỘT hành động tiếp theo cần thiết "
    "để làm điều người dùng yêu cầu."
)

VISION_PROMPT = (
    "Đây là ảnh chụp toàn màn hình một máy tính Windows.\n"
    "{state}"
    "Người dùng hỏi: \"{question}\"\n"
    "Hãy xác định phần tử giao diện cần bấm để làm đúng điều người dùng hỏi, rồi trả về "
    "toạ độ tâm của phần tử đó trên thang chuẩn hoá 0-1000: x=0 là mép trái, x=1000 là mép phải, "
    "y=0 là mép trên, y=1000 là mép dưới. Nếu không thấy phần tử phù hợp, đặt found=false."
)

# Optional Windows state sent as text next to the screenshot (Decision 2, test T1).
STATE_BLOCK = (
    "Trạng thái Windows do chương trình đọc trực tiếp từ hệ điều hành, đáng tin cậy "
    "và có thể cho biết những điều ảnh chụp không thấy:\n{state}\n"
)


def vision_prompt(question: str, state: str | None = None) -> str:
    """Without state the text is identical to the stage 0/1 prompt."""
    return VISION_PROMPT.format(question=question, state=STATE_BLOCK.format(state=state) if state else "")

POINT_SCHEMA = {
    "type": "object",
    "properties": {
        "found": {"type": "boolean"},
        "x": {"type": "number"},
        "y": {"type": "number"},
        "element": {"type": "string"},
    },
    "required": ["found", "x", "y", "element"],
    "additionalProperties": False,
}

POINTING_ACTIONS = ("click", "double_click")
RETRY_STATUSES = (429, 500, 502, 503, 504)


class ApiError(Exception):
    pass


@dataclass
class CallResult:
    point: tuple[float, float] | None = None
    action_type: str | None = None  # click, double_click, move, screenshot, json, ...
    found: bool | None = None       # M2 only
    text: str = ""
    safety_checks: list = field(default_factory=list)
    latency_s: float = 0.0          # successful attempts only, summed over hops
    usage: dict = field(default_factory=lambda: {"input": 0, "output": 0, "cached": 0, "reasoning": 0})
    raw: list = field(default_factory=list)
    hops: int = 0
    error: str | None = None


class MetaAPI:
    def __init__(self, api_key: str, base_url: str = config.BASE_URL, timeout: float = config.REQUEST_TIMEOUT_S):
        if not api_key:
            raise ValueError("MODEL_API_KEY is empty")
        self._http = httpx.Client(
            base_url=base_url,
            timeout=timeout,
            headers={"Authorization": f"Bearer {api_key}"},
        )

    def close(self) -> None:
        self._http.close()

    def list_models(self) -> list[str]:
        r = self._http.get("/models")
        _raise_for_status(r)
        return sorted(m["id"] for m in r.json().get("data", []))

    def _post(self, path: str, body: dict, max_attempts: int = 4) -> tuple[dict, float]:
        delay = 0.5
        for attempt in range(1, max_attempts + 1):
            started = time.perf_counter()
            r = self._http.post(path, json=body)
            elapsed = time.perf_counter() - started
            if r.status_code in RETRY_STATUSES and attempt < max_attempts:
                time.sleep(_retry_after(r, delay))
                delay *= 2
                continue
            _raise_for_status(r)
            return r.json(), elapsed
        raise ApiError("unreachable")

    def computer_use_point(self, model: str, data_url: str, question: str, effort: str | None = None) -> CallResult:
        """M1: one request with the screenshot; if the model only asks for a screenshot, hand it back once."""
        res = CallResult()
        body = {
            "model": model,
            "instructions": CU_INSTRUCTIONS,
            "tools": [{"type": "computer"}],
            "input": [{"role": "user", "content": [
                {"type": "input_text", "text": question},
                {"type": "input_image", "image_url": data_url},
            ]}],
        }
        for hop in range(2):
            if effort:
                body["reasoning"] = {"effort": effort}
            resp, elapsed = self._post("/responses", body)
            res.raw.append(resp)
            res.latency_s += elapsed
            res.hops = hop + 1
            _add_responses_usage(res, resp)
            res.text += _message_text(resp)

            call = _first_item(resp, "computer_call")
            if call is None:
                return res  # answered in words, no action
            res.safety_checks = call.get("pending_safety_checks") or []
            actions = call.get("actions") or ([call["action"]] if call.get("action") else [])
            res.point, res.action_type = _pointing_action(actions)
            if res.point is not None or res.safety_checks or res.action_type != "screenshot" or hop == 1:
                return res
            body = {
                "model": model,
                "instructions": CU_INSTRUCTIONS,
                "tools": [{"type": "computer"}],
                "previous_response_id": resp["id"],
                "input": [{
                    "type": "computer_call_output",
                    "call_id": call["call_id"],
                    "acknowledged_safety_checks": [],
                    "output": {"type": "computer_screenshot", "image_url": data_url},
                }],
            }
        return res

    def vision_point(self, model: str, data_url: str, question: str, state: str | None = None,
                     effort: str | None = None) -> CallResult:
        """M2: ask for a JSON point on the 0-1000 grid described in the image-understanding docs."""
        res = CallResult(action_type="json")
        body = {
            "model": model,
            "messages": [{"role": "user", "content": [
                {"type": "text", "text": vision_prompt(question, state)},
                {"type": "image_url", "image_url": {"url": data_url}},
            ]}],
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": "ui_point", "schema": POINT_SCHEMA},
            },
        }
        if effort:
            body["reasoning_effort"] = effort
        resp, elapsed = self._post("/chat/completions", body)
        res.raw.append(resp)
        res.latency_s = elapsed
        res.hops = 1
        u = resp.get("usage") or {}
        res.usage["input"] = u.get("prompt_tokens", 0)
        res.usage["output"] = u.get("completion_tokens", 0)
        res.usage["cached"] = (u.get("prompt_tokens_details") or {}).get("cached_tokens", 0)
        res.usage["reasoning"] = (u.get("completion_tokens_details") or {}).get("reasoning_tokens", 0)

        content = (resp.get("choices") or [{}])[0].get("message", {}).get("content") or ""
        res.text = content
        try:
            answer = json.loads(content)
        except json.JSONDecodeError:
            res.error = "answer is not valid JSON"
            return res
        res.found = bool(answer.get("found"))
        x, y = answer.get("x"), answer.get("y")
        if res.found and isinstance(x, (int, float)) and isinstance(y, (int, float)):
            res.point = (float(x), float(y))
        return res


def _raise_for_status(r: httpx.Response) -> None:
    if r.is_error:
        raise ApiError(f"HTTP {r.status_code}: {r.text[:500]}")


def _retry_after(r: httpx.Response, default: float) -> float:
    try:
        return max(float(r.headers.get("retry-after", default)), 0.0)
    except ValueError:
        return default


def _first_item(resp: dict, item_type: str) -> dict | None:
    return next((i for i in resp.get("output", []) if i.get("type") == item_type), None)


def _message_text(resp: dict) -> str:
    parts = []
    for item in resp.get("output", []):
        if item.get("type") == "message":
            for c in item.get("content", []):
                if c.get("type") in ("output_text", "text"):
                    parts.append(c.get("text", ""))
    return "\n".join(parts)


def _pointing_action(actions: list[dict]) -> tuple[tuple[float, float] | None, str | None]:
    """First click/double_click wins; a bare move counts as pointing too, but is labelled."""
    for kinds in (POINTING_ACTIONS, ("move",)):
        for a in actions:
            if a.get("type") in kinds and "x" in a and "y" in a:
                return (float(a["x"]), float(a["y"])), a["type"]
    types = [a.get("type") for a in actions]
    if types and all(t in ("screenshot", "wait") for t in types):
        return None, "screenshot"
    return None, (types[0] if types else None)


def _add_responses_usage(res: CallResult, resp: dict) -> None:
    u = resp.get("usage") or {}
    res.usage["input"] += u.get("input_tokens", 0)
    res.usage["output"] += u.get("output_tokens", 0)
    res.usage["cached"] += (u.get("input_tokens_details") or {}).get("cached_tokens", 0)
    res.usage["reasoning"] += (u.get("output_tokens_details") or {}).get("reasoning_tokens", 0)
