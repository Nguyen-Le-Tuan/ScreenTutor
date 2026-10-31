"""Windows state snapshot sent as text next to each screenshot (Decision 2a).

The sensors read the operating system, not the screen: which window is in
front, which windows sit behind it, which app opens links and files, where the
standard folders really are, and which files were just created or changed.
Each sensor fails loudly into `errors` instead of guessing.

  python -m screentutor.state                      # print the Vietnamese summary
  python -m screentutor.state --out t2_results/S-1 # also save S-1.txt and S-1.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

# exe name (lower case) -> name a person would say. Anything else shows the exe stem.
APP_NAMES = {
    "zalo.exe": "Zalo",
    "brave.exe": "Brave",
    "chrome.exe": "Google Chrome",
    "msedge.exe": "Microsoft Edge",
    "firefox.exe": "Firefox",
    "browser.exe": "Cốc Cốc",
    "winword.exe": "Word",
    "excel.exe": "Excel",
    "powerpnt.exe": "PowerPoint",
    "explorer.exe": "File Explorer",
    "foxitpdfreader.exe": "Foxit PDF Reader",
    "acrord32.exe": "Adobe Acrobat Reader",
    "acrobat.exe": "Adobe Acrobat",
    "notepad.exe": "Notepad",
    "mspaint.exe": "Paint",
    "photos.exe": "Photos",
    "microsoft.photos.exe": "Photos",
    "wps.exe": "WPS Office",
}

DOC_EXTENSIONS = {".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".pdf", ".txt",
                  ".jpg", ".jpeg", ".png", ".heic", ".zip", ".rar"}
PARTIAL_SUFFIXES = (".tmp", ".crdownload", ".part", ".partial", ".download")

MAX_WINDOWS = 8
MAX_FILES = 8
DEFAULT_HOURS = 72


@dataclass
class WindowInfo:
    title: str
    exe: str                     # file name, e.g. "WINWORD.EXE"
    minimized: bool = False
    maximized: bool = False
    owners: list[str] = field(default_factory=list)  # dialogs: owning windows' titles, nearest first
    kind: str = ""               # "shell" for the desktop or the taskbar, which are not apps
    debug: dict = field(default_factory=dict)        # raw flags for diagnosis; JSON only, not sent to the model

    @property
    def app(self) -> str:
        return app_name(self.exe)


@dataclass
class RecentFile:
    name: str
    folder_label: str            # e.g. "Downloads"
    path: str
    modified: float
    created: float | None = None


@dataclass
class Snapshot:
    taken_at: float = field(default_factory=time.time)
    foreground: WindowInfo | None = None
    windows: list[WindowInfo] = field(default_factory=list)   # top to bottom, foreground excluded
    defaults: dict[str, str] = field(default_factory=dict)     # "link" / ".docx" ... -> app name
    folders: dict[str, str] = field(default_factory=dict)      # "Downloads" -> path
    recent_files: list[RecentFile] = field(default_factory=list)
    hours: int = DEFAULT_HOURS
    timings_ms: dict[str, float] = field(default_factory=dict)
    errors: dict[str, str] = field(default_factory=dict)


def app_name(exe: str) -> str:
    if not exe:
        return "không rõ"
    return APP_NAMES.get(exe.lower(), Path(exe).stem)


def recent_files(folders: dict[str, str], since: float, limit: int = MAX_FILES,
                 depth: dict[str, int] | None = None) -> list[RecentFile]:
    """Documents and images created or changed after `since`, newest first.

    Only the folder itself is scanned, plus one level of subfolders where
    `depth[label]` is 1. Office lock files (~$...) and unfinished downloads are skipped.
    """
    found = []
    for label, root in folders.items():
        dirs = [Path(root)]
        if (depth or {}).get(label, 0) >= 1:
            try:
                dirs += [Path(e.path) for e in os.scandir(root) if e.is_dir(follow_symlinks=False)]
            except OSError:
                pass
        for d in dirs:
            try:
                entries = list(os.scandir(d))
            except OSError:
                continue
            for e in entries:
                name = e.name
                if name.startswith("~$") or name.lower().endswith(PARTIAL_SUFFIXES):
                    continue
                if Path(name).suffix.lower() not in DOC_EXTENSIONS:
                    continue
                try:
                    if not e.is_file(follow_symlinks=False):
                        continue
                    st = e.stat()
                except OSError:
                    continue
                created = getattr(st, "st_birthtime", None)
                newest = max(st.st_mtime, created or 0)
                if newest < since:
                    continue
                where = label if d == Path(root) else f"{label}\\{d.name}"
                found.append(RecentFile(name, where, e.path, st.st_mtime, created))
    found.sort(key=lambda f: max(f.modified, f.created or 0), reverse=True)
    return found[:limit]


def when_vi(ts: float, now: float) -> str:
    """'hôm nay 21:05', 'hôm qua 21:05' or '27/10 21:05'."""
    t, n = datetime.fromtimestamp(ts), datetime.fromtimestamp(now)
    hm = t.strftime("%H:%M")
    if t.date() == n.date():
        return f"hôm nay {hm}"
    if t.date() == (n - timedelta(days=1)).date():
        return f"hôm qua {hm}"
    return f"{t.strftime('%d/%m')} {hm}"


def _window_vi(w: WindowInfo) -> str:
    if w.kind == "shell":
        return f"{w.title}, không phải cửa sổ app nào"
    text = f'{w.app} ({w.exe}), tiêu đề "{w.title}"'
    if w.owners:
        text += ", là hộp thoại của " + ", nằm trên ".join(f'"{t}"' for t in w.owners)
    if w.minimized:
        text += ", đang thu nhỏ"
    elif w.maximized:
        text += ", đang phóng to"
    return text


def format_vi(s: Snapshot) -> str:
    """The text block that goes next to the screenshot. One fact per line."""
    lines = []
    if s.foreground:
        lines.append(f"- Cửa sổ đang ở trước mặt: {_window_vi(s.foreground)}.")
    if s.windows:
        shown = s.windows[:MAX_WINDOWS]
        more = len(s.windows) - len(shown)
        items = "; ".join(f"{i}) {_window_vi(w)}" for i, w in enumerate(shown, 1))
        lines.append(f"- Cửa sổ khác đang mở, từ trên xuống: {items}" + (f"; và {more} cửa sổ khác." if more else "."))
    if s.defaults:
        parts = [f"{'link' if k == 'link' else 'file ' + k}: {v}" for k, v in s.defaults.items()]
        lines.append("- App mở mặc định: " + "; ".join(parts) + ".")
    if s.folders:
        lines.append("- Thư mục chuẩn: " + "; ".join(f"{k} = {v}" for k, v in s.folders.items()) + ".")
    if s.recent_files:
        items = "; ".join(
            f'"{f.name}" trong {f.folder_label}, '
            + (f"tạo {when_vi(f.created, s.taken_at)}, " if f.created and abs(f.created - f.modified) > 60 else "")
            + f"sửa {when_vi(f.modified, s.taken_at)}"
            for f in s.recent_files)
        lines.append(f"- File mới hoặc vừa sửa trong {s.hours} giờ qua, mới nhất trước: {items}.")
    elif s.folders:
        lines.append(f"- Không có file tài liệu hay ảnh nào mới hoặc vừa sửa trong {s.hours} giờ qua ở các thư mục trên.")
    for name, err in s.errors.items():
        lines.append(f"- Không đọc được {name}: {err}")
    return "\n".join(lines)


def take_snapshot(hours: int = DEFAULT_HOURS) -> Snapshot:
    if sys.platform != "win32":
        raise RuntimeError("Cảm biến trạng thái chỉ chạy trên Windows.")
    from . import winstate

    snap = Snapshot(hours=hours)

    def run(name, fn):
        t = time.perf_counter()
        try:
            return fn()
        except Exception as e:  # one broken sensor must not hide the others
            snap.errors[name] = f"{type(e).__name__}: {e}"
            return None
        finally:
            snap.timings_ms[name] = round((time.perf_counter() - t) * 1000, 1)

    fg_hwnd = run("cửa sổ trước mặt", winstate.foreground_hwnd)
    windows = run("danh sách cửa sổ", winstate.list_windows) or []
    for hwnd, info in windows:
        if hwnd == fg_hwnd:
            snap.foreground = info
        else:
            snap.windows.append(info)
    if fg_hwnd and snap.foreground is None:  # e.g. a dialog, which the window list filters out
        snap.foreground = run("cửa sổ trước mặt", lambda: winstate.describe(fg_hwnd))
    snap.defaults = run("app mặc định", winstate.default_apps) or {}
    snap.folders = run("thư mục chuẩn", winstate.known_folders) or {}
    zalo = Path(snap.folders.get("Documents", "")) / "Zalo Received Files"
    if snap.folders and zalo.is_dir():
        snap.folders["Zalo Received Files"] = str(zalo)
    since = snap.taken_at - hours * 3600
    snap.recent_files = run("file mới", lambda: recent_files(
        snap.folders, since, depth={"Zalo Received Files": 1})) or []
    snap.timings_ms["tổng"] = round(sum(snap.timings_ms.values()), 1)
    return snap


def main(argv=None) -> None:
    p = argparse.ArgumentParser(prog="python -m screentutor.state")
    p.add_argument("--hours", type=int, default=DEFAULT_HOURS, help="file mới trong bao nhiêu giờ qua")
    p.add_argument("--out", help="lưu thêm <out>.txt và <out>.json, ví dụ t2_results/S-1")
    p.add_argument("--delay", type=int, default=0,
                   help="chờ bấy nhiêu giây trước khi đọc, để kịp chuyển sang cửa sổ cần thử")
    p.add_argument("--dump", help="chẩn đoán: ghi mọi cửa sổ có tiêu đề chứa chữ này vào file .json")
    args = p.parse_args(argv)

    for left in range(args.delay, 0, -1):
        print(f"Đọc trạng thái sau {left} giây... chuyển sang cửa sổ cần thử.", flush=True)
        time.sleep(1)
    snap = take_snapshot(args.hours)
    data = asdict(snap)
    if args.dump:
        from . import winstate
        data["dump"] = winstate.dump_windows(args.dump)
    text = format_vi(snap)
    timing = ", ".join(f"{k} {v} ms" for k, v in snap.timings_ms.items())
    report = f"{text}\n\n(Thời gian đọc: {timing})"
    if args.dump:
        report += f"\n(Chẩn đoán: {len(data['dump'])} cửa sổ có tiêu đề chứa \"{args.dump}\", xem file .json)"
    print(report)
    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.with_suffix(".txt").write_text(report + "\n", encoding="utf-8")
        out.with_suffix(".json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\nĐã lưu {out.with_suffix('.txt')} và {out.with_suffix('.json')}")


if __name__ == "__main__":
    main()
