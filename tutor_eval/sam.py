"""T11: can SAM 3.1 turn Spark's point into a tight outline of the thing to click?

  .venv/bin/python -m tutor_eval.sam run --yes     # 24 images, about $0.06
  .venv/bin/python -m tutor_eval.sam summary tutor_eval/results/<stamp>-sam

Rule, fixed before the run (02/11/2026); the thresholds are Claude's, not the founder's:
- Setup: Spark's 24 answers from the T4 run 20261102-090950 (12 real cases x 2), so no
  new Spark call. Each point goes to SAM 3.1 once, through screentutor.segment: boxes
  of four sizes around the point in one request, full-size PNG, as the app would send.
  The sizes, MIN_CONFIDENCE, MAX_AREA and choose() were set on the synthetic calibration
  image only; no real case was sent to SAM before this rule.
- Only points that hit in T4 are scored: SAM cannot repair a wrong point.
- A chosen box is "right" when, against the closest frozen label box, IoU >= 0.5, or
  one box lies at least 90% inside the other and their areas differ at most 4 times.
  Otherwise it is "too big" or "too small" by area. No box chosen = "ring": the app
  keeps the plain ring, which is safe.
- (1) Trust: at least 90% of the outlines shown are right.
- (2) Coverage: an outline is shown for at least 60% of the scored points.
- (3) Speed: SAM median at most 1.5 s, p90 at most 2.5 s. The ring and the voice do not
  wait for SAM; the outline replaces the ring when it arrives.
- All three pass: the app draws the outline, and the plain ring remains the fallback.
  Any fails: the ring stays as it is and SAM is left out.
- Not scored by code: how the outlines look. Claude reads sheet.png and reports.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageDraw

from grounding_test.datasets import CASES_DIR, load_cases, prepare_image
from screentutor.listen import _api_key
from screentutor.segment import Found, Segmenter, choose

HERE = Path(__file__).parent
T4_RUN = HERE / "results" / "20261102-090950"
MIN_RIGHT, MIN_SHOWN, MAX_MEDIAN_S, MAX_P90_S = 0.90, 0.60, 1.5, 2.5


def _overlap(a: tuple, b: tuple) -> int:
    return max(min(a[2], b[2]) - max(a[0], b[0]), 0) * max(min(a[3], b[3]) - max(a[1], b[1]), 0)


def _area(b: tuple) -> int:
    return max(b[2] - b[0], 0) * max(b[3] - b[1], 0)


def judge(box: tuple, labels: list[tuple]) -> tuple[str, float]:
    """("right" | "too big" | "too small", IoU) against the label box closest to it."""
    label = max(labels, key=lambda b: (_overlap(box, b), -_area(b)))
    inter = _overlap(box, label)
    union = _area(box) + _area(label) - inter
    iou = inter / union if union else 0.0
    ratio = max(_area(box), _area(label)) / max(min(_area(box), _area(label)), 1)
    inside = inter / max(min(_area(box), _area(label)), 1)
    if iou >= 0.5 or (inside >= 0.9 and ratio <= 4):
        return "right", iou
    return ("too big" if _area(box) > _area(label) else "too small"), iou


def percentile(values: list[float], q: float) -> float:
    ordered = sorted(values)
    return ordered[min(int(q * len(ordered)), len(ordered) - 1)]


def cmd_run(args) -> None:
    if not args.yes:
        sys.exit("Thêm --yes để chạy (24 ảnh, khoảng $0.06).")
    items = {it.item_id: it for it in load_cases()[0]}
    calls = [json.loads(line) for line in (T4_RUN / "calls.jsonl").read_text(encoding="utf-8").splitlines()]
    out = HERE / "results" / (datetime.now().strftime("%Y%m%d-%H%M%S") + "-sam")
    out.mkdir(parents=True)
    seg = Segmenter(_api_key())
    rows = []
    try:
        for c in calls:
            case = c["item_id"]
            data_url, sent, _ = prepare_image(CASES_DIR / f"{case}.png")
            row = {"case": case, "run": c["run"], "t4": c["result"], "point": None, "boxes": [], "chosen": None}
            if c.get("point"):
                x, y = round(c["point"][0] * sent[0] / 1000), round(c["point"][1] * sent[1] / 1000)
                row["point"] = [x, y]
                try:
                    found, row["latency_s"] = seg.around((x, y), sent, data_url)
                except Exception as e:
                    row["error"] = f"{type(e).__name__}: {e}"
                    found = []
                row["boxes"] = [vars(f) for f in found]
                pick = choose(found, (x, y), sent)
                if pick:
                    row["chosen"] = vars(pick)
                    row["verdict"], row["iou"] = judge((pick.x1, pick.y1, pick.x2, pick.y2), items[case].boxes)
            rows.append(row)
            print(case, c["run"], c["result"], row.get("verdict", "ring"), row.get("latency_s"), flush=True)
    finally:
        seg.close()
    (out / "rows.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    report(out, rows, items)
    print(f"Đã lưu {out}")


def report(out: Path, rows: list[dict], items: dict) -> None:
    scored = [r for r in rows if r["t4"] == "hit"]
    shown = [r for r in scored if r["chosen"]]
    right = [r for r in shown if r["verdict"] == "right"]
    times = [r["latency_s"] for r in rows if "latency_s" in r]
    median, p90 = statistics.median(times), percentile(times, 0.9)
    trust, cover = len(right) / max(len(shown), 1), len(shown) / max(len(scored), 1)
    lines = [
        f"# T11: SAM 3.1 quanh điểm của Spark ({out.name})", "",
        "| Điều kiện | Kết quả | Ngưỡng | |", "|---|---|---|---|",
        f"| (1) Viền đúng trên số viền hiện | {len(right)}/{len(shown)} ({trust:.0%}) | ≥ 90% | "
        f"{'đạt' if trust >= MIN_RIGHT else 'TRƯỢT'} |",
        f"| (2) Có viền trên số điểm trúng | {len(shown)}/{len(scored)} ({cover:.0%}) | ≥ 60% | "
        f"{'đạt' if cover >= MIN_SHOWN else 'TRƯỢT'} |",
        f"| (3) Trễ trung vị / p90 | {median:.2f} s / {p90:.2f} s | ≤ 1,5 s / ≤ 2,5 s | "
        f"{'đạt' if median <= MAX_MEDIAN_S and p90 <= MAX_P90_S else 'TRƯỢT'} |", "",
        "| Ca | Lần | T4 | Kết luận | IoU | c | Khung |", "|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        c = r["chosen"] or {}
        box = f"{c['x1']},{c['y1']},{c['x2']},{c['y2']}" if c else "—"
        iou = f"{r['iou']:.2f}" if "iou" in r else "—"
        conf = f"{c['confidence']:.2f}" if c else "—"
        lines.append(f"| {r['case']} | {r['run']} | {r['t4']} | {r.get('verdict', r.get('error', 'vòng'))} | {iou} "
                     f"| {conf} | {box} |")
    text = "\n".join(lines) + "\n"
    (out / "summary.md").write_text(text, encoding="utf-8")
    print(text)
    sheet(out / "sheet.png", rows, items)


def sheet(path: Path, rows: list[dict], items: dict, tile: tuple[int, int] = (460, 260), cols: int = 4) -> None:
    """Each answer of run 1 cropped around the point: labels green, the chosen box red, the point blue."""
    picked = [r for r in rows if r["run"] == 1 and r["point"]]
    canvas = Image.new("RGB", (tile[0] * cols, tile[1] * ((len(picked) + cols - 1) // cols)), "white")
    for i, r in enumerate(picked):
        with Image.open(CASES_DIR / f"{r['case']}.png") as src:
            img = src.convert("RGB")
        d = ImageDraw.Draw(img)
        for b in items[r["case"]].boxes:
            d.rectangle(b, outline=(0, 170, 0), width=1)
        if r["chosen"]:
            c = Found(**r["chosen"])
            d.rectangle((c.x1, c.y1, c.x2, c.y2), outline=(230, 0, 0), width=2)
        x, y = r["point"]
        d.ellipse((x - 3, y - 3, x + 3, y + 3), fill=(0, 80, 255))
        cw, ch = tile[0] - 6, tile[1] - 24
        x1, y1 = min(max(x - cw // 2, 0), img.width - cw), min(max(y - ch // 2, 0), img.height - ch)
        col, row = i % cols, i // cols
        canvas.paste(img.crop((x1, y1, x1 + cw, y1 + ch)), (col * tile[0] + 3, row * tile[1] + 21))
        ImageDraw.Draw(canvas).text((col * tile[0] + 6, row * tile[1] + 5),
                                    f"{r['case']} {r.get('verdict', 'ring')}", fill=(0, 0, 0))
    canvas.save(path)


def cmd_summary(args) -> None:
    items = {it.item_id: it for it in load_cases()[0]}
    out = Path(args.dir)
    report(out, json.loads((out / "rows.json").read_text(encoding="utf-8")), items)


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(prog="python -m tutor_eval.sam")
    sub = ap.add_subparsers(dest="cmd", required=True)
    run = sub.add_parser("run")
    run.add_argument("--yes", action="store_true")
    run.set_defaults(fn=cmd_run)
    summary = sub.add_parser("summary")
    summary.add_argument("dir")
    summary.set_defaults(fn=cmd_summary)
    args = ap.parse_args(argv)
    args.fn(args)


if __name__ == "__main__":
    main()
