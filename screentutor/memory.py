"""Her own knowledge base, built from her tasks and kept on her machine (B5, founder 02/11).

Meta's API has no embedding model (GET /v1/models, 02/11), so the search runs here: BM25 over
her tasks, with every word indexed with its accents and without, because speech-to-text often
gets the accents wrong. Finding a task never touches the network.

Spark does the part that needs reading: after each task one call, words only and no picture,
turns the raw record into a short note (name, apps, main steps, result, keywords) and proposes
what the task says about her. Something she has shown once is not used yet; it has to come up
again in another task. Before anything is sent or kept, a filter on this machine takes out
passwords, phone numbers and names.

A new question gets at most 3 similar tasks and 5 things known about her, 700 characters in all,
and only when they really are similar: nothing is better than something unrelated.

Everything lives in history/memory/, gitignored, and "Xoá lịch sử" deletes it with the rest.
This sends words from her earlier tasks to Meta, so INSTALL section 7 has to say so.
"""

from __future__ import annotations

import json
import math
import re
import shutil
import threading
import time
import unicodedata
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .history import DIR as HISTORY_DIR
from .history import TaskRecord, when_label

K1, B = 1.5, 0.75            # BM25's usual values
MIN_COVER = 0.45             # share of the question's weight a task must match; below that it is not "similar"
RECENT_BONUS = 0.15          # a task from today counts this much more, half of that after 30 days
DONE_BONUS = 0.10            # a task that was finished counts this much more than one that was not
SHOWN_TASKS, SHOWN_FACTS = 3, 5
MAX_CONTEXT = 700            # characters of what is known, in all
MIN_SEEN = 2                 # a fact seen once is not used
SAME_FACT = 0.6              # overlap of words above which two facts are the same fact
MAX_RECORD = 1500            # characters of a task sent to be summarised

WORD = re.compile(r"[^\W_]+")
# Words that say nothing about which task it is, without accents. Her own way of asking is full of them.
STOP = frozenset("""
    a anh ban bam bay bi bo cac cai can cho chi chua co con cua cung da dang day de den di do duoc gi giup gium ha hay
    hoi khi khong la lai lam len lieu ma may me minh mot muon nao nay ne nen nha nhe nho nhu nhung o phai qua ra rat
    roi sao se sua tai the thi thoi tren tu tui va vao vay ve voi vua xem xin
""".split())


def plain(text: str) -> str:
    """Lower case, no accents: "Giáo Án" -> "giao an"."""
    text = unicodedata.normalize("NFD", unicodedata.normalize("NFC", text).lower().replace("đ", "d"))
    return "".join(c for c in text if not unicodedata.combining(c))


def terms(text: str) -> list[str]:
    """What gets indexed: each word without accents, with its accents when it has them, and word pairs."""
    words = WORD.findall(unicodedata.normalize("NFC", text).lower())
    kept = [(w, plain(w)) for w in words if plain(w) not in STOP]
    out = [t for w, b in kept for t in ((b, w) if w != b else (b,))]
    return out + [f"{a[1]}_{b[1]}" for a, b in zip(kept, kept[1:])]


class Index:
    """BM25 on this machine. Holds a few hundred short notes, so plain dicts are fast enough."""

    def __init__(self):
        self.postings: dict[str, dict[str, int]] = defaultdict(dict)
        self.length: dict[str, int] = {}
        self.when: dict[str, float] = {}
        self.done: dict[str, bool] = {}
        self._total = 0

    def add(self, doc: str, text: str, when: float = 0.0, done: bool = False) -> None:
        self.remove(doc)
        counts = Counter(terms(text))
        for term, n in counts.items():
            self.postings[term][doc] = n
        self.length[doc] = sum(counts.values())
        self._total += self.length[doc]
        self.when[doc], self.done[doc] = when, done

    def remove(self, doc: str) -> None:
        if doc in self.length:
            for term in [t for t, posting in self.postings.items() if doc in posting]:
                del self.postings[term][doc]
                if not self.postings[term]:
                    del self.postings[term]
            self._total -= self.length.pop(doc)
            self.when.pop(doc), self.done.pop(doc)

    def _idf(self, term: str) -> float:
        n, df = len(self.length), len(self.postings.get(term, ()))
        return math.log(1 + (n - df + 0.5) / (df + 0.5))

    def search(self, query: str, k: int = SHOWN_TASKS, now: float | None = None) -> list[tuple[str, float]]:
        """The tasks that really are similar, best first; none is a fine answer."""
        wanted = set(terms(query))
        if not wanted or not self.length:
            return []
        now = time.time() if now is None else now
        avg = self._total / len(self.length)
        weight = {t: self._idf(t) for t in wanted}
        plain_words = {t for t in wanted if "_" not in t and plain(t) == t}  # pairs and accents rank; they do not decide
        whole = sum(weight[t] for t in plain_words)
        scores: dict[str, float] = defaultdict(float)
        matched: dict[str, float] = defaultdict(float)
        for term in wanted:
            for doc, tf in self.postings.get(term, {}).items():
                scores[doc] += weight[term] * tf * (K1 + 1) / (tf + K1 * (1 - B + B * self.length[doc] / avg))
                if term in plain_words:
                    matched[doc] += weight[term]
        ranked = []
        for doc, score in scores.items():
            if whole == 0 or matched[doc] / whole < MIN_COVER:
                continue
            age_days = max(now - self.when[doc], 0.0) / 86400
            bonus = 1 + RECENT_BONUS * 0.5 ** (age_days / 30) + (DONE_BONUS if self.done[doc] else 0.0)
            ranked.append((doc, score * bonus))
        return sorted(ranked, key=lambda d: d[1], reverse=True)[:k]


# --- the filter: nothing below leaves the machine or goes into the knowledge base --------------

HIDDEN = "[đã ẩn]"
UP = "A-ZÀÁÂÃÈÉÊÌÍÒÓÔÕÙÚÝĂĐĨŨƠƯẠẢẤẦẨẪẬẮẰẲẴẶẸẺẼẾỀỂỄỆỈỊỌỎỐỒỔỖỘỚỜỞỠỢỤỦỨỪỬỮỰỲỴỶỸ"
LOW = "a-zàáâãèéêìíòóôõùúýăđĩũơưạảấầẩẫậắằẳẵặẹẻẽếềểễệỉịọỏốồổỗộớờởỡợụủứừửữựỳỵỷỹ"
NAME_WORD = f"[{UP}][{LOW}]+"
FAMILY = "Nguyễn|Trần|Lê|Phạm|Hoàng|Huỳnh|Phan|Vũ|Võ|Đặng|Bùi|Đỗ|Hồ|Ngô|Dương|Lý|Đinh|Mai|Trương|Đoàn|Lâm|Cao|Tô"
FILTERS = [
    re.compile(r"(?i)(?:mật\s*khẩu|mat\s*khau|mk|password|passcode|pass|otp|mã\s*(?:xác\s*(?:nhận|thực)|otp|pin)|pin)"
               r"\s*(?:mới\s*|của\s+\S+\s+)?(?:là|la|:|=|-)?\s*\S+"),
    re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"),                                        # e-mail
    re.compile(r"(?<![\d.,])(?:\+?84|0)[ .-]?\d(?:[ .-]?\d){7,9}(?![\d])"),          # a Vietnamese phone number
    re.compile(r"(?<!\d)\d{9,}(?!\d)"),                                             # an ID or bank account
    re.compile(rf"(?:{FAMILY})(?:\s+{NAME_WORD}){{1,3}}"),                          # a full name
    re.compile(rf"(?i:\b(?:em|cháu|bé|học sinh|hs)\s+)(?={NAME_WORD})\S+(?:\s+{NAME_WORD})*"),  # "em Lan", "học sinh Tuấn Anh"
]


RESUME_WORDS = ("lam tiep", "tiep tuc")
RESUME_REST = frozenset("""
    cai cho cu da dang di do hoi hom hom lai lam luc me minh muon nay nao nay nhe nha oi phan thoi tiep truoc tuc viec
""".split())


def asks_to_resume(text: str) -> bool:
    """"Làm tiếp", "tiếp tục việc lúc nãy", with or without accents. "Tiếp tục phát video" is a question of its own."""
    bare = " ".join(WORD.findall(plain(text)))
    return any(w in bare for w in RESUME_WORDS) and set(bare.split()) <= RESUME_REST


# Founder 03/11: "tutor biết khi nào dừng". Said to the model, "tôi muốn dừng hướng dẫn" made it ask back 3 times in 6
# and once point at Zalo's close button; and since W-6 a one-turn answer is followed by "Làm tiếp". So a short request
# to stop never goes to the model. Accents are kept: "dừng" (stop) is not "dùng" (use).
QUIT_WORDS = frozenset(("dừng", "ngừng", "thôi", "nghỉ", "hủy", "huỷ"))
QUIT_PAIRS = (("không", "nữa"), ("để", "sau"), ("đủ", "rồi"), ("khi", "khác"))   # "không làm nữa", "để khi khác"
QUIT_REST = frozenset("""
    tôi mình mẹ con em bạn muốn cho đã đi lại nhé nhá nha ạ à ơi bây giờ hướng dẫn việc này đó nữa không làm cần ở đây
    luôn rồi hết được cái chỉ xin cảm ơn giúp vậy thì là nào đủ để sau tạm tắt đang cả mà mệt khi khác thôi
""".split()) | QUIT_WORDS
QUIT_MAX_WORDS = 12


def asks_to_stop(text: str) -> bool:
    """"Dừng", "thôi không làm nữa", "để sau nhé": she wants the tutor to stop, nothing else. A thing to stop on the
    screen ("tạm dừng video", "dừng tải file") is a question of its own, and goes to the model as any other."""
    words = WORD.findall(unicodedata.normalize("NFC", text).lower())
    if not words or len(words) > QUIT_MAX_WORDS or not set(words) <= QUIT_REST:
        return False
    return bool(QUIT_WORDS & set(words)) or any(a in words and b in words for a, b in QUIT_PAIRS)


def scrub(text: str) -> str:
    for pattern in FILTERS:
        text = pattern.sub(HIDDEN, text)
    return text


def is_clean(text: str) -> bool:
    return scrub(text) == text


# --- what is kept -----------------------------------------------------------------------------

@dataclass
class Note:
    """One task, short and searchable (B5a)."""
    id: str
    title: str
    apps: list[str] = field(default_factory=list)
    path: list[str] = field(default_factory=list)
    result: str = ""
    keywords: list[str] = field(default_factory=list)
    started_at: float = 0.0
    outcome: str = ""

    def text(self) -> str:
        return " ".join([self.title, *self.apps, *self.path, self.result, *self.keywords])


@dataclass
class Fact:
    """One thing known about her (B5c). `seen` counts the tasks that showed it, listed in `tasks`."""
    text: str
    seen: int = 1
    tasks: list[str] = field(default_factory=list)
    last: float = 0.0


def record_text(rec: TaskRecord) -> str:
    """The task as words for the summary, through the filter."""
    lines = [f"Câu hỏi: {rec.question}"]
    if rec.plan:
        lines.append("Kế hoạch: " + "; ".join(rec.plan))
    lines += [f"Tutor nói: {s.say}" for s in rec.steps]
    lines.append(f"Kết quả: {rec.outcome}")
    return scrub("\n".join(lines))[:MAX_RECORD]


def local_note(rec: TaskRecord) -> Note:
    """A note with no model at all: an unfinished task, or one whose summary failed, can still be found."""
    return Note(rec.id, scrub(rec.title), path=[scrub(p) for p in rec.plan], keywords=[scrub(s.say) for s in rec.steps[:3]],
                started_at=rec.started_at, outcome=rec.outcome)


def note_from(answer: dict, rec: TaskRecord) -> Note:
    def strings(key: str, n: int) -> list[str]:
        value = answer.get(key)
        return [scrub(str(v)) for v in value[:n]] if isinstance(value, list) else []

    return Note(rec.id, scrub(str(answer.get("title") or rec.title)), strings("apps", 6), strings("path", 6),
                scrub(str(answer.get("result") or "")), strings("keywords", 8), rec.started_at, rec.outcome)


def overlap(a: str, b: str) -> float:
    x, y = {plain(w) for w in WORD.findall(a)} - STOP, {plain(w) for w in WORD.findall(b)} - STOP
    return len(x & y) / len(x | y) if x | y else 0.0


class Memory:
    """The notes, the index and what is known about her. Worker threads read and write it, so one lock covers all."""

    def __init__(self, root: Path = HISTORY_DIR / "memory", clock=time.time):
        self.root = Path(root)
        self._clock = clock
        self._lock = threading.Lock()
        self.notes: dict[str, Note] = {}
        self.facts: list[Fact] = []
        self.index = Index()
        self.dropped: set[str] = set()   # tasks she told the tutor to stop; a summary still on its way is not kept

    def load(self, tasks: list[TaskRecord] = ()) -> None:
        """At start: the saved notes, a broken file skipped, and a plain note for tasks that have none."""
        with self._lock:
            for f in self.root.glob("note-*.json") if self.root.is_dir() else []:
                try:
                    self._keep(Note(**json.loads(f.read_text(encoding="utf-8"))))
                except (OSError, ValueError, TypeError) as e:
                    print(f"Bỏ qua ghi chú hỏng {f.name}: {e}", flush=True)
            try:
                self.facts = [Fact(**d) for d in json.loads((self.root / "profile.json").read_text(encoding="utf-8"))]
            except (OSError, ValueError, TypeError):
                self.facts = []
            for rec in tasks:
                if rec.id not in self.notes:
                    self._keep(local_note(rec))

    def _keep(self, note: Note) -> None:
        self.notes[note.id] = note
        self.index.add(note.id, note.text(), note.started_at, note.outcome == "done")

    def remember(self, note: Note, facts: list[str] = ()) -> None:
        """A finished task: its note goes in the index, what it says about her into the profile."""
        with self._lock:
            if note.id in self.dropped:
                return
            self._keep(note)
            self.root.mkdir(parents=True, exist_ok=True)
            self._write(f"note-{note.id}.json", asdict(note))
            for text in facts:
                self._learn(str(text).strip(), note.id)
            self._write("profile.json", [asdict(f) for f in self.facts])

    def _learn(self, text: str, task: str) -> None:
        if not text or not is_clean(text):
            return  # a fact with a name or a number in it is not kept at all
        for fact in self.facts:
            if overlap(fact.text, text) >= SAME_FACT:
                if task not in fact.tasks:
                    fact.seen += 1
                    fact.tasks.append(task)
                    fact.last = self._clock()
                return
        self.facts.append(Fact(text, 1, [task], self._clock()))

    def _write(self, name: str, data) -> None:
        path = self.root / name
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)

    def context(self, question: str) -> str | None:
        """What goes in the prompt for this question, or None when nothing is known that helps."""
        with self._lock:
            now = self._clock()
            lines = []
            for doc, _ in self.index.search(question, SHOWN_TASKS, now):
                n = self.notes[doc]
                steps = " > ".join(n.path[:4])
                done = {"done": "xong", "interrupted": "dở"}.get(n.outcome, "chưa xong")
                lines.append(f"- Việc trước ({when_label(n.started_at, now)}, {done}): {n.title}" + (f": {steps}" if steps else ""))
            usable = [f for f in self.facts if f.seen >= MIN_SEEN]
            usable.sort(key=lambda f: (f.seen, f.last), reverse=True)
            lines += [f"- {f.text}" for f in usable[:SHOWN_FACTS]]
        kept, size = [], 0
        for line in lines:
            if size + len(line) + 1 > MAX_CONTEXT:
                break
            kept.append(line)
            size += len(line) + 1
        return "\n".join(kept) or None

    def forget_task(self, task_id: str) -> None:
        """She told the tutor to stop (founder 03/11): the task's note goes, and what it taught about her counts one
        task less; a fact seen in that task alone is gone."""
        with self._lock:
            self.dropped.add(task_id)
            self.notes.pop(task_id, None)
            self.index.remove(task_id)
            (self.root / f"note-{task_id}.json").unlink(missing_ok=True)
            touched = [f for f in self.facts if task_id in f.tasks]
            for fact in touched:
                fact.tasks.remove(task_id)
                fact.seen -= 1
            if touched:
                self.facts = [f for f in self.facts if f.seen > 0]
                if self.root.is_dir():
                    self._write("profile.json", [asdict(f) for f in self.facts])

    def forget(self) -> None:
        """"Xoá lịch sử" takes all of this with it (founder, 02/11)."""
        with self._lock:
            self.notes, self.facts = {}, []
            self.index = Index()
            shutil.rmtree(self.root, ignore_errors=True)


def learn(memory: Memory, rec: TaskRecord, ask) -> None:
    """After a task: ask(text) gives back the summary as a dict, or None. No answer still leaves a plain note."""
    answer = ask(record_text(rec))
    if answer is None:
        memory.remember(local_note(rec))
    else:
        memory.remember(note_from(answer, rec), answer.get("facts") or [])
