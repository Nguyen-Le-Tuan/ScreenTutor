"""Can Windows UI Automation tell, at once, what she clicked? A probe on the real machine (03/11).

The idea, from vercel-labs/agent-desktop (Apache-2.0; only the idea, none of its code): the
accessibility tree knows every button, row and link with its name and its exact box. If it is
complete and fast for her apps, a click could be checked the moment it happens (she clicked
what the ring showed, or not) instead of after the screen settles and Spark answers, and the
ring could snap to the real box of the button. Whether Zalo, Word and Brave expose enough is
not known; that is what this measures. Nothing is clicked, typed or sent anywhere: it only reads.

  py -m pip install comtypes                 # once; not needed by the app itself
  py -m tutor_eval.uia_probe hover           # 90 s: rest the mouse on buttons, rows, links
  py -m tutor_eval.uia_probe click           # 90 s: click as she would, the element under each click
  py -m tutor_eval.uia_probe tree            # 5 s to bring a window to the front, then the whole tree
  .venv/bin/python -m tutor_eval.uia_probe summary tutor_runs/uia_probe-*.jsonl        # any OS, all runs together

Rule, fixed before the first run (03/11). Thresholds are Claude's proposal; the founder chose to
measure before deciding. Counted per app (Zalo, Word, Brave), over "targets": places where the
mouse rested at least 0.4 s (hover) or was clicked (click).
- U1 sees the control: at least 80% of targets give an element with a name and a box no bigger
  than 3% of the screen (a single control, not the whole chat pane or page).
- U2 is fast: reading the element at a point (name, type, box) takes a median of at most 30 ms
  and a 90th percentile of at most 100 ms.
- U3 finds by name (for showing the next step before Spark answers): finding an element by its
  name in the front window takes a median of at most 150 ms.
- Decision: the instant check is worth building (after the hackathon) for an app only if U1 and
  U2 pass for it; snapping the next ring in advance also needs U3. Failures are reported as such.

Output: tutor_runs/uia_probe-<time>.jsonl (gitignored). It holds names of chats, messages and files
from the screen, so it stays on this machine and is never committed.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path

REST_S = 0.4              # the mouse must rest this long on a spot to count as a target
SAMPLE_S = 0.05
RUN_S = 90
SMALL_SHARE = 0.03        # U1: a box at most 3% of the screen is one control
U1_MIN = 0.80
U2_MEDIAN_MS, U2_P90_MS = 30.0, 100.0
U3_MEDIAN_MS = 150.0
APPS = {"zalo.exe": "Zalo", "winword.exe": "Word", "brave.exe": "Brave"}


# --- pure part: runs and is tested on any OS ---------------------------------------------------

def p90(values: list[float]) -> float:
    s = sorted(values)
    return s[min(len(s) - 1, round(0.9 * (len(s) - 1)))] if s else 0.0


def app_of(exe: str) -> str:
    name = exe.replace("\\", "/").rsplit("/", 1)[-1].lower()
    return APPS.get(name, name or "?")


def small(row: dict, screen_area: float) -> bool:
    x1, y1, x2, y2 = row.get("rect") or (0, 0, 0, 0)
    area = max(0, x2 - x1) * max(0, y2 - y1)
    return 0 < area <= SMALL_SHARE * screen_area


def summarise(rows: list[dict], screen_area: float) -> dict:
    """Per app: targets, how many U1 counts, point-read times; and find-by-name times. With pass/fail."""
    out: dict[str, dict] = {}
    for r in rows:
        if r.get("kind") not in ("hover", "click"):
            continue
        a = out.setdefault(app_of(r.get("exe", "")), {"targets": 0, "seen": 0, "ms": [], "find_ms": []})
        a["targets"] += 1
        a["seen"] += bool((r.get("name") or "").strip()) and small(r, screen_area)
        a["ms"].append(r["ms"])
    for r in rows:
        if r.get("kind") == "find":
            out.setdefault(app_of(r.get("exe", "")), {"targets": 0, "seen": 0, "ms": [], "find_ms": []})["find_ms"].append(r["ms"])
    for a in out.values():
        a["u1"] = a["seen"] / a["targets"] if a["targets"] else None
        a["u2_median"] = statistics.median(a["ms"]) if a["ms"] else None
        a["u2_p90"] = p90(a["ms"]) if a["ms"] else None
        a["u3_median"] = statistics.median(a["find_ms"]) if a["find_ms"] else None
        a["U1"] = a["u1"] is not None and a["u1"] >= U1_MIN
        a["U2"] = a["u2_median"] is not None and a["u2_median"] <= U2_MEDIAN_MS and a["u2_p90"] <= U2_P90_MS
        a["U3"] = a["u3_median"] is not None and a["u3_median"] <= U3_MEDIAN_MS
    return out


def report(summary: dict) -> str:
    lines = []
    for app, a in sorted(summary.items()):
        def fmt(v, unit=""):
            return "—" if v is None else (f"{v:.0%}" if unit == "%" else f"{v:.0f} ms")
        lines.append(f"{app}: {a['targets']} chỗ; U1 thấy đúng nút {fmt(a['u1'], '%')} "
                     f"{'ĐẠT' if a['U1'] else 'TRƯỢT'}; U2 đọc tại điểm trung vị {fmt(a['u2_median'])}, "
                     f"p90 {fmt(a['u2_p90'])} {'ĐẠT' if a['U2'] else 'TRƯỢT'}; U3 tìm theo tên "
                     f"{fmt(a['u3_median'])} {'ĐẠT' if a['U3'] else ('—' if a['u3_median'] is None else 'TRƯỢT')}")
    return "\n".join(lines) or "Chưa có dữ liệu."


# --- Windows part -------------------------------------------------------------------------------

class Uia:
    def __init__(self):
        import ctypes

        import comtypes
        import comtypes.client

        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # physical pixels, the same as UIA boxes and screenshots
        comtypes.CoInitialize()
        self.m = comtypes.client.GetModule("UIAutomationCore.dll")
        self.uia = comtypes.client.CreateObject(self.m.CUIAutomation, interface=self.m.IUIAutomation)
        self.user32 = ctypes.windll.user32
        self.ctypes = ctypes

    def point(self, x: int, y: int):
        from ctypes import wintypes

        return getattr(self.m, "tagPOINT", wintypes.POINT)(x, y)

    def cursor(self) -> tuple[int, int]:
        from ctypes import wintypes

        pt = wintypes.POINT()
        self.user32.GetCursorPos(self.ctypes.byref(pt))
        return pt.x, pt.y

    def left_down(self) -> bool:
        return bool(self.user32.GetAsyncKeyState(0x01) & 0x8000)

    def screen_area(self) -> float:
        return float(self.user32.GetSystemMetrics(0) * self.user32.GetSystemMetrics(1))

    def at(self, x: int, y: int) -> dict:
        from screentutor.winstate import _exe

        start = time.perf_counter()
        el = self.uia.ElementFromPoint(self.point(x, y))
        r = el.CurrentBoundingRectangle
        row = {"x": x, "y": y, "name": el.CurrentName or "", "type": el.CurrentLocalizedControlType or "",
               "framework": el.CurrentFrameworkId or "", "rect": [r.left, r.top, r.right, r.bottom]}
        row["ms"] = round((time.perf_counter() - start) * 1000, 2)
        row["exe"] = _exe(el.CurrentProcessId)
        return row

    def tree(self) -> list[dict]:
        from screentutor.winstate import _exe

        hwnd = self.user32.GetForegroundWindow()
        root = self.uia.ElementFromHandle(hwnd)
        exe = _exe(root.CurrentProcessId)
        start = time.perf_counter()
        found = root.FindAll(self.m.TreeScope_Descendants, self.uia.CreateTrueCondition())
        all_ms = (time.perf_counter() - start) * 1000
        names = []
        for i in range(found.Length):
            n = found.GetElement(i).CurrentName or ""
            if n.strip() and n not in names:
                names.append(n)
        rows = [{"kind": "tree", "exe": exe, "count": found.Length, "named": len(names), "ms": round(all_ms, 1)}]
        for n in names[:: max(1, len(names) // 8)][:8]:
            start = time.perf_counter()
            hit = root.FindFirst(self.m.TreeScope_Descendants,
                                 self.uia.CreatePropertyCondition(self.m.UIA_NamePropertyId, n))
            rows.append({"kind": "find", "exe": exe, "name": n, "found": hit is not None,
                         "ms": round((time.perf_counter() - start) * 1000, 1)})
        return rows


def run(mode: str, seconds: float) -> Path:
    uia = Uia()
    out = Path("tutor_runs") / f"uia_probe-{time.strftime('%Y%m%d-%H%M%S')}.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)
    rows: list[dict] = []
    if mode == "tree":
        for left in range(5, 0, -1):
            print(f"Đưa cửa sổ cần đo lên trước mặt... {left}", flush=True)
            time.sleep(1)
        rows = uia.tree()
    else:
        print(f"Bắt đầu {seconds:.0f} giây. " + ("Rê chuột và dừng 1 giây trên từng nút, dòng chat, link."
                                                if mode == "hover" else "Bấm như mẹ bấm."), flush=True)
        end = time.monotonic() + seconds
        last, since, done_here, was_down = None, time.monotonic(), False, False
        while time.monotonic() < end:
            pos = uia.cursor()
            now = time.monotonic()
            if mode == "hover":
                if pos != last:
                    last, since, done_here = pos, now, False
                elif not done_here and now - since >= REST_S:
                    rows.append({"kind": "hover", **uia.at(*pos)})
                    done_here = True
                    print(f"  {app_of(rows[-1]['exe'])}: {rows[-1]['type']} \"{rows[-1]['name'][:40]}\" "
                          f"{rows[-1]['ms']} ms", flush=True)
            else:
                down = uia.left_down()
                if down and not was_down:
                    rows.append({"kind": "click", **uia.at(*pos)})
                    print(f"  {app_of(rows[-1]['exe'])}: {rows[-1]['type']} \"{rows[-1]['name'][:40]}\" "
                          f"{rows[-1]['ms']} ms", flush=True)
                was_down = down
            time.sleep(SAMPLE_S if mode == "hover" else 0.01)
    with out.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"kind": "screen", "area": uia.screen_area()}) + "\n")
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"Đã lưu {out} (có tên chat và file trên màn hình: không commit, không gửi ai)")
    print(report(summarise(rows, uia.screen_area())))
    return out


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(prog="python -m tutor_eval.uia_probe")
    ap.add_argument("mode", choices=["hover", "click", "tree", "summary"])
    ap.add_argument("files", nargs="*", help="với summary: các file .jsonl đã lưu, gộp lại")
    ap.add_argument("--seconds", type=float, default=RUN_S)
    args = ap.parse_args(argv)
    if args.mode == "summary":
        rows, area = [], 1920 * 1080
        import glob

        names = [n for f in args.files for n in (sorted(glob.glob(f)) if "*" in f else [f])]  # PowerShell does not expand *
        for name in names:
            for line in Path(name).read_text(encoding="utf-8").splitlines():
                r = json.loads(line)
                if r.get("kind") == "screen":
                    area = r["area"]
                else:
                    rows.append(r)
        print(report(summarise(rows, area)))
        return
    if sys.platform != "win32":
        sys.exit("Chỉ đo được trên Windows.")
    try:
        import comtypes  # noqa: F401
    except ImportError:
        sys.exit("Cần comtypes: py -m pip install comtypes")
    run(args.mode, args.seconds)


if __name__ == "__main__":
    main()
