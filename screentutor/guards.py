"""The tutor speaks up when she has not asked (B4, founder 02/11).

The first guard: Word is showing the temporary copy Zalo opens when she clicks a file straight
in a message (T5 X-1, 02/11). Edits there never reach the real file, and the app can see this
when she cannot. The tutor says so once for each file, then invites her to ask, and the normal
session walks her through downloading it properly (F-7, founder's choice b).

Only what the machine itself says: the window in front and the names in one folder. No
screenshot is taken and nothing is sent, so "nothing is sent before she asks" stays true.

Two ways to know, because the exact words in Word's title bar have not been seen yet:
  - the title says read-only, and a file of that name is in Zalo's temporary folder;
  - Word just opened a name that appeared in that folder moments ago, whatever the title says.
A real copy of the same name, opened later and not read-only, matches neither.

No Qt and no Windows calls here: the app reads the window and the folder, so all of it is
tested with made-up snapshots.
"""

from __future__ import annotations

import os
import unicodedata
from dataclasses import dataclass
from pathlib import Path

EVERY_S = 2.0
FRESH_S = 120.0     # Claude's estimate: a click in Zalo and Word opening fall within this
MIN_NAME = 3        # a shorter name would match almost any title
READ_ONLY_MARKS = ("read-only", "read only", "chỉ đọc", "protected view", "dạng xem được bảo vệ")  # to check in T13b

SAY = "File này là bản tạm của Zalo, sửa ở đây sẽ không vào file thật. "   # awaiting the founder's approval
HOW_BUTTON = "Bạn bấm nút tròn rồi nói tải file về để được chỉ từng bước nhé."
HOW_KEYS = "Bạn giữ Ctrl và Alt rồi nói tải file về để được chỉ từng bước nhé."


@dataclass(frozen=True)
class TempCopy:
    name: str
    born: float        # when it appeared in the folder


def _plain(text: str) -> str:
    """Zalo's file names may be in another Unicode form than the title; capitals do not matter."""
    return unicodedata.normalize("NFC", text).casefold()


def temp_copies(folder: str | Path) -> list[TempCopy]:
    """The files in Zalo's temporary folder, one level of subfolders included. No folder, no files."""
    dirs, found = [Path(folder)], []
    try:
        dirs += [Path(e.path) for e in os.scandir(folder) if e.is_dir(follow_symlinks=False)]
    except OSError:
        return []
    for d in dirs:
        try:
            for e in os.scandir(d):
                if e.is_file(follow_symlinks=False) and not e.name.startswith("~$"):
                    st = e.stat()
                    found.append(TempCopy(e.name, max(st.st_mtime, getattr(st, "st_birthtime", 0) or 0)))
        except OSError:
            continue
    return found


def opened_copy(foreground, copies: list[TempCopy], now: float) -> TempCopy | None:
    """The temporary copy Word is showing in front of her, if it is one."""
    if foreground is None or foreground.exe.lower() != "winword.exe":
        return None
    title = _plain(foreground.title)
    read_only = any(mark in title for mark in READ_ONLY_MARKS)
    for copy in copies:
        stem = _plain(Path(copy.name).stem)
        if len(stem) >= MIN_NAME and stem in title and (read_only or now - copy.born <= FRESH_S):
            return copy
    return None


def sentence(button_shown: bool) -> str:
    return SAY + (HOW_BUTTON if button_shown else HOW_KEYS)


class ZaloCopy:
    """Says it once for each file: a tutor that repeats itself every time she comes back to Word is a nuisance."""

    def __init__(self):
        self.told: set[str] = set()

    def check(self, foreground, copies: list[TempCopy], now: float) -> TempCopy | None:
        copy = opened_copy(foreground, copies, now)
        if copy is None or _plain(copy.name) in self.told:
            return None
        self.told.add(_plain(copy.name))
        return copy
