"""Her tasks, one file each, kept on her machine in C:\\ScreenTutor\\history\\ (A8, founder 02/11).

Every question is a task of its own, a side question too, so what is kept about her stays
clean. A task holds her question as heard, the tutor's sentences, what each step pointed at,
and how it ended. No screenshots and no sound: those stay in tutor_runs/ as before. The
folder is gitignored, and the pinned island can delete it all.

Later, B5 indexes these files into her own knowledge base, and B7 resumes a task left half done.
"""

from __future__ import annotations

import json
import os
import secrets
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

from .settings import ROOT

DIR = ROOT / "history"
KEEP = 500                       # the newest tasks kept; older files are removed
OUTCOMES = ("done", "unfinished", "stopped", "error", "interrupted")


@dataclass
class StepRecord:
    say: str
    element: str = ""
    step_done: bool | None = None
    goal_done: bool | None = None
    caution: bool = False
    latency_s: float = 0.0
    at: float = 0.0


@dataclass
class TaskRecord:
    id: str
    started_at: float
    question: str
    plan: list[str] = field(default_factory=list)
    part: int = 0
    steps: list[StepRecord] = field(default_factory=list)
    outcome: str = "unfinished"   # until finish(): the app may close in the middle
    ended_at: float | None = None

    @property
    def title(self) -> str:
        return self.question.strip() or "(không nghe rõ câu hỏi)"


def _from_dict(d: dict) -> TaskRecord:
    steps = [StepRecord(**{k: v for k, v in s.items() if k in StepRecord.__dataclass_fields__}) for s in d.get("steps", [])]
    keep = {k: v for k, v in d.items() if k in TaskRecord.__dataclass_fields__ and k != "steps"}
    return TaskRecord(steps=steps, **keep)


class History:
    def __init__(self, root: Path = DIR, clock=time.time, keep: int = KEEP):
        self.root = Path(root)
        self._clock = clock
        self.keep = keep

    def start(self, question: str) -> TaskRecord:
        now = self._clock()
        rec = TaskRecord(datetime.fromtimestamp(now).strftime("%Y%m%d-%H%M%S-") + secrets.token_hex(2), now, question)
        self.write(rec)
        self._trim()
        return rec

    def add_step(self, rec: TaskRecord, say: str, element: str = "", step_done=None, goal_done=None,
                 caution: bool = False, latency_s: float = 0.0) -> None:
        rec.steps.append(StepRecord(say, element, step_done, goal_done, caution, round(latency_s, 2), self._clock()))
        self.write(rec)

    def set_plan(self, rec: TaskRecord, plan: list[str], part: int) -> None:
        rec.plan, rec.part = list(plan), part
        self.write(rec)

    def finish(self, rec: TaskRecord, outcome: str) -> None:
        rec.outcome = outcome if outcome in OUTCOMES else "stopped"
        rec.ended_at = self._clock()
        self.write(rec)

    def write(self, rec: TaskRecord) -> None:
        """Whole file at once (write a temporary file, then replace), so a crash never leaves half a task."""
        self.root.mkdir(parents=True, exist_ok=True)
        path = self.root / f"{rec.id}.json"
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(asdict(rec), ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, path)

    def tasks(self) -> list[TaskRecord]:
        """All readable tasks, newest first; a broken file is skipped, never fatal."""
        out = []
        for f in self.root.glob("*.json") if self.root.is_dir() else []:
            try:
                out.append(_from_dict(json.loads(f.read_text(encoding="utf-8"))))
            except (OSError, ValueError, TypeError) as e:
                print(f"Bỏ qua file lịch sử hỏng {f.name}: {e}", flush=True)
        return sorted(out, key=lambda r: r.started_at, reverse=True)

    def recent(self, n: int = 3) -> list[TaskRecord]:
        return self.tasks()[:n]

    def clear(self) -> int:
        """Delete every task (the pinned island's "Xoá lịch sử"). Returns how many files went."""
        n = 0
        for f in list(self.root.glob("*.json")) + list(self.root.glob("*.tmp")) if self.root.is_dir() else []:
            f.unlink(missing_ok=True)
            n += f.suffix == ".json"
        return n

    def _trim(self) -> None:
        files = sorted(self.root.glob("*.json"))  # ids start with the time, so names sort by age
        for f in files[:max(0, len(files) - self.keep)]:
            f.unlink(missing_ok=True)


def when_label(ts: float, now: float) -> str:
    """"hôm nay 14:05", "hôm qua", "3 ngày trước": for the list of tasks in the pinned island."""
    then, today = datetime.fromtimestamp(ts), datetime.fromtimestamp(now)
    days = (today.date() - then.date()).days
    if days <= 0:
        return f"hôm nay {then:%H:%M}"
    if days == 1:
        return "hôm qua"
    return f"{days} ngày trước"
