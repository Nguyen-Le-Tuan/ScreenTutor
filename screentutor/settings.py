"""Her settings, in settings.json next to the app (C:\\ScreenTutor\\settings.json).

Founder, 02/11: the round button can be switched off without changing code, so nothing has to
be pushed and merged for it; the island's colour goes here too (A9). The file is optional and
gitignored: without it, or with a broken one, the defaults hold. Changes apply while the app
runs: the app polls the file's time stamp.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, fields
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PATH = ROOT / "settings.json"


@dataclass
class Settings:
    show_button: bool = True        # the round microphone button at the bottom right
    island_color: str = "#000000"   # the island's base colour; 80% of it when closed
    edge_glow: bool = True          # the light around the screen while the tutor looks; off on a slow machine


def load(path: Path = PATH) -> Settings:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return Settings()
    except (OSError, ValueError) as e:
        print(f"Không đọc được {path.name} ({e}); dùng cài đặt mặc định.", flush=True)
        return Settings()
    out = Settings()
    if not isinstance(raw, dict):
        return out
    for f in fields(Settings):
        value = raw.get(f.name)
        if isinstance(value, type(getattr(out, f.name))):  # a wrong type keeps the default for that key
            setattr(out, f.name, value)
    return out


def save(settings: Settings, path: Path = PATH) -> None:
    path.write_text(json.dumps(asdict(settings), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


class Watch:
    """Tells when settings.json has changed since the last look."""

    def __init__(self, path: Path = PATH):
        self.path = path
        self._stamp = self._now()

    def _now(self):
        try:
            st = self.path.stat()
            return st.st_mtime_ns, st.st_size
        except FileNotFoundError:
            return None

    def poll(self) -> Settings | None:
        """The new settings when the file changed (or appeared, or went away), else None."""
        stamp = self._now()
        if stamp == self._stamp:
            return None
        self._stamp = stamp
        return load(self.path)
