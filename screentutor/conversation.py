"""What the dynamic island says: the talk of the current task, cut to fit (A3, founder 02/11).

Her words sit on the right and the tutor's on the left, as in a messaging app. Each question
is a task of its own, a side question too, so what is kept about her stays clean (founder,
02/11). Closed, the island shows one line: her last words while she speaks, the start of the
tutor's sentence while it speaks. No Qt here: widths come from a measure function, so all of
it is tested without a screen.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

Measure = Callable[[str], float]
ELLIPSIS = "…"
LINE_H = 21          # px per line at the 15 px body font
PAD_X, PAD_Y = 10, 6
GAP = 6
SHARE = 0.82         # a bubble takes at most this share of the width, so the sides stay readable
INDENT = 18          # plan items: room for the part marker


@dataclass
class Message:
    who: str                       # "me" (her) or "tutor"
    text: str = ""
    plan: tuple[str, ...] = ()     # a tutor message that lists the parts of a big task
    part: int = 0                  # with a plan: the part being done


@dataclass
class Task:
    """One question and everything said for it."""
    messages: list[Message] = field(default_factory=list)

    def hear(self, text: str) -> None:
        """Her question as heard so far; partial transcripts replace each other."""
        if self.messages and self.messages[0].who == "me":
            self.messages[0].text = text
        else:
            self.messages.insert(0, Message("me", text))

    def say(self, text: str) -> None:
        self.messages.append(Message("tutor", text))

    def plan(self, parts: list[str], part: int = 0) -> None:
        for m in self.messages:
            if m.plan:
                m.plan, m.part = tuple(parts), part
                return
        self.messages.append(Message("tutor", f"Việc này có {len(parts)} phần:", tuple(parts), part))

    @property
    def question(self) -> str:
        return self.messages[0].text if self.messages and self.messages[0].who == "me" else ""

    def last_said(self) -> str:
        for m in reversed(self.messages):
            if m.who == "tutor" and not m.plan:
                return m.text
        return ""


def fit_start(text: str, width: float, measure: Measure) -> str:
    """The start of the text that fits, closed with an ellipsis."""
    if measure(text) <= width:
        return text
    lo, hi = 0, len(text)
    while lo < hi:
        k = (lo + hi + 1) // 2
        if measure(text[:k].rstrip() + ELLIPSIS) <= width:
            lo = k
        else:
            hi = k - 1
    cut = text[:lo]
    space = cut.rfind(" ")
    if lo < len(text) and text[lo] != " " and space >= 0.7 * len(cut):  # end on a whole word when that costs little
        cut = cut[:space]
    return cut.rstrip() + ELLIPSIS if cut.strip() else ""


def fit_end(text: str, width: float, measure: Measure) -> str:
    """The end of the text that fits, opened with an ellipsis: her latest words."""
    if measure(text) <= width:
        return text
    lo, hi = 0, len(text)
    while lo < hi:
        k = (lo + hi + 1) // 2
        if measure(ELLIPSIS + text[len(text) - k:].lstrip()) <= width:
            lo = k
        else:
            hi = k - 1
    start = len(text) - lo
    cut = text[start:] if lo else ""
    space = cut.find(" ")
    if start > 0 and text[start - 1] != " " and 0 <= space <= 0.3 * len(cut):  # it began inside a word
        cut = cut[space + 1:]
    return ELLIPSIS + cut.lstrip() if cut.strip() else ""


def wrap(text: str, width: float, measure: Measure) -> list[str]:
    """Greedy word wrap; a word wider than the line is split by letters."""
    lines: list[str] = []
    line = ""
    for word in text.split():
        trial = f"{line} {word}" if line else word
        if measure(trial) <= width:
            line = trial
            continue
        if line:
            lines.append(line)
        while measure(word) > width and len(word) > 1:
            k = len(word)
            while k > 1 and measure(word[:k]) > width:
                k -= 1
            lines.append(word[:k])
            word = word[k:]
        line = word
    if line:
        lines.append(line)
    return lines or [""]


def collapsed_text(state: str, task: Task | None, label: str, width: float, measure: Measure) -> str:
    """The one line of the closed island (founder, 02/11: only the start of what the tutor says)."""
    if state == "idle" or task is None and state not in ("thinking", "loading", "error"):
        return ""
    if state == "listening":
        return fit_end(task.question, width, measure) if task and task.question else label
    if state in ("thinking", "loading"):
        return label
    said = task.last_said() if task else ""
    return fit_start(said, width, measure) if said else label


@dataclass(frozen=True)
class Bubble:
    who: str
    lines: tuple[str, ...]
    x: float
    y: float
    w: float
    h: float
    current: bool = False
    plan: tuple[str, ...] = ()
    part: int = 0


def layout(messages: list[Message], width: float, measure: Measure, current: bool = False) -> tuple[list[Bubble], float]:
    """Bubbles from the top down: hers flush right, the tutor's flush left.

    `current` marks the tutor's latest sentence (it is being said, or waits for her click).
    Returns the bubbles and the total height.
    """
    inner = width * SHARE - 2 * PAD_X
    last_tutor = max((i for i, m in enumerate(messages) if m.who == "tutor" and not m.plan), default=-1)
    out: list[Bubble] = []
    y = 0.0
    for i, m in enumerate(messages):
        if m.plan:
            items = [wrap(f"{n + 1}. {p}", inner - INDENT, measure) for n, p in enumerate(m.plan)]
            lines = [m.text] + [line for item in items for line in item]
            text_w = max([measure(m.text)] + [measure(line) + INDENT for item in items for line in item])
        else:
            lines = wrap(m.text, inner, measure)
            text_w = max(measure(line) for line in lines)
        w = min(width * SHARE, text_w + 2 * PAD_X)
        h = len(lines) * LINE_H + 2 * PAD_Y
        x = width - w if m.who == "me" else 0.0
        out.append(Bubble(m.who, tuple(lines), x, y, w, h, current and i == last_tutor, m.plan, m.part))
        y += h + GAP
    return out, max(0.0, y - GAP)


def newest_that_fit(bubbles: list[Bubble], max_h: float, keep_first: bool = False) -> tuple[list[Bubble], float]:
    """Drop the oldest bubbles until the rest fit, and stack them again from 0.

    `keep_first` keeps her question on top even when older answers have to go.
    """
    first = bubbles[:1] if keep_first else []
    rest = bubbles[len(first):]
    total = first[0].h if first else 0.0
    keep: list[Bubble] = []
    for b in reversed(rest):
        need = b.h + (GAP if keep or first else 0)
        if (keep or first) and total + need > max_h:
            break
        keep.insert(0, b)
        total += need
    out, y = [], 0.0
    for b in first + keep:
        out.append(Bubble(b.who, b.lines, b.x, y, b.w, b.h, b.current, b.plan, b.part))
        y += b.h + GAP
    return out, (y - GAP if out else 0.0)


def plan_progress(task: Task | None) -> str:
    """"Phần 1/3" for the header of the open island, when the task has parts."""
    for m in task.messages if task else []:
        if m.plan:
            return f"Phần {m.part + 1}/{len(m.plan)}"
    return ""


def natural_width(messages: list[Message], measure: Measure) -> float:
    """How wide the open island wants to be: enough for the longest line, no more (founder, 02/11)."""
    widths = [measure(m.text) for m in messages] + [measure(f"{n + 1}. {p}") + INDENT for m in messages
                                                    for n, p in enumerate(m.plan)]
    return (max(widths, default=0.0) + 2 * PAD_X) / SHARE
