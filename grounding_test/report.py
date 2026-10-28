"""Summarise a results folder (calls.jsonl) into summary.md, in Vietnamese.

Usage: python -m grounding_test.report grounding_test/results/<folder>
"""

from __future__ import annotations

import json
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

from . import config
from .scoring import CONVENTIONS

RESULT_ORDER = ("hit", "near", "miss", "none")
RESULT_VI = {"hit": "trúng", "near": "sát", "miss": "trượt", "none": "không trỏ"}


def load_records(out_dir: Path) -> list[dict]:
    path = out_dir / "calls.jsonl"
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def call_cost(rec: dict) -> float:
    price = config.PRICES.get(rec["model_id"])
    if not price:
        return 0.0
    u = rec["usage"]
    uncached = max(u["input"] - u["cached"], 0)
    return (uncached * price["input"] + u["cached"] * price["cached"] + u["output"] * price["output"]) / 1e6


def pick_convention(recs: list[dict]) -> str:
    """The convention under which this model/method lands more hits (then nears)."""
    def score(conv):
        c = Counter(r["scores"][conv]["result"] for r in recs)
        return c["hit"], c["near"]
    ranked = sorted(CONVENTIONS, key=score, reverse=True)
    if score(ranked[0]) == score(ranked[1]):
        return "không rõ"
    return ranked[0]


def _latency_line(recs: list[dict]) -> str:
    lat = [r["latency_s"] for r in recs if not r.get("error")]
    if not lat:
        return "Độ trễ: không có lần gọi thành công."
    med = statistics.median(lat)
    p90 = statistics.quantiles(lat, n=10)[-1] if len(lat) >= 2 else lat[0]
    return f"Độ trễ: trung vị {med:.2f} s, p90 {p90:.2f} s (ngưỡng {config.LATENCY_LIMIT_S:.0f} s)."


def _usage_line(recs: list[dict]) -> str:
    ok = [r for r in recs if not r.get("error")]
    if not ok:
        return ""
    avg = lambda k: statistics.mean(r["usage"][k] for r in ok)
    cost = sum(call_cost(r) for r in recs)
    return (f"Token trung bình mỗi lần: vào {avg('input'):.0f}, ra {avg('output'):.0f} "
            f"(suy luận {avg('reasoning'):.0f}). Chi phí ước tính cả nhóm: ${cost:.4f}.")


def _decision(recs: list[dict], conv: str) -> list[str]:
    """Apply the pre-registered thresholds (plan section 8) to the 12 real cases."""
    runs = sorted({r["run"] for r in recs})
    hits_per_run = {run: sum(1 for r in recs if r["run"] == run and r["scores"][conv]["result"] == "hit")
                    for run in runs}
    min_hits = min(hits_per_run.values()) if hits_per_run else 0
    big = [r for r in recs if r["size_class"] in ("vừa", "lớn")]
    big_all_hit = bool(big) and all(r["scores"][conv]["result"] == "hit" for r in big)
    small_missed = any(r["scores"][conv]["result"] != "hit" for r in recs if r["size_class"] == "nhỏ")
    lat = [r["latency_s"] for r in recs if not r.get("error")]
    med = statistics.median(lat) if lat else float("inf")
    n_items = len({r["item_id"] for r in recs})

    lines = [f"Trúng theo từng lần chạy: {hits_per_run} trên {n_items} ảnh; thấp nhất {min_hits}.",
             f"Mọi mục tiêu cỡ vừa và lớn đều trúng ở mọi lần: {'có' if big_all_hit else 'không'}."]
    if n_items != config.CASES_TOTAL:
        lines.append(f"Lưu ý: mới có {n_items}/{config.CASES_TOTAL} ảnh, ngưỡng dưới đây chỉ để tham khảo.")
    if min_hits <= config.REJECT_MAX_HITS:
        verdict = "Không dùng toạ độ Meta làm cách grounding duy nhất; bàn lại UI Automation hoặc đổi model."
    elif min_hits >= config.ADOPT_MIN_HITS and big_all_hit and med <= config.LATENCY_LIMIT_S:
        verdict = "Đạt ngưỡng: dùng toạ độ Meta làm cách grounding chính cho MVP."
    elif big_all_hit and small_missed and med <= config.LATENCY_LIMIT_S:
        verdict = "Dùng toạ độ Meta, kèm bước tinh chỉnh cho mục tiêu nhỏ (thử sau)."
    elif med > config.LATENCY_LIMIT_S:
        verdict = "Độ trễ trung vị vượt 5 s: xem lại model hoặc reasoning.effort trước khi chốt."
    else:
        verdict = "Kết quả nằm giữa các ngưỡng: cần bàn thêm."
    lines.append(f"**Đề xuất theo ngưỡng đặt trước:** {verdict} (Founder quyết định.)")
    return lines


def summarize(records: list[dict], run_info: dict | None = None) -> str:
    out = ["# Kết quả thử grounding", ""]
    if run_info:
        out.append(f"Giai đoạn: **{run_info.get('stage')}**; bắt đầu {run_info.get('started')}; "
                   f"resize: {run_info.get('resize') or 'không'}; ngôn ngữ câu hỏi: {run_info.get('lang')}; "
                   f"effort: {run_info.get('effort') or 'mặc định'}.")
    total_cost = sum(call_cost(r) for r in records)
    errors = sum(1 for r in records if r.get("error"))
    out += [f"Tổng số lần gọi: {len(records)} (lỗi: {errors}). Chi phí ước tính: ${total_cost:.4f}.", ""]

    groups = defaultdict(list)
    for r in records:
        groups[(r["model"], r["method"])].append(r)

    for (model, method), recs in sorted(groups.items()):
        conv = pick_convention(recs)
        out += [f"## {model} / {method.upper()}", ""]
        out.append("| Quy ước | " + " | ".join(RESULT_VI[k] for k in RESULT_ORDER) + " |")
        out.append("|---|" + "---|" * len(RESULT_ORDER))
        for c in CONVENTIONS:
            cnt = Counter(r["scores"][c]["result"] for r in recs)
            out.append(f"| {c} | " + " | ".join(str(cnt[k]) for k in RESULT_ORDER) + " |")
        out += ["", f"Quy ước khớp hơn: **{conv}**.", ""]

        show = conv if conv in CONVENTIONS else "pixel"
        out.append("| Mục | Cỡ | Lần | Kết quả | Cách khung (px) | Lệch về | Hành động | Điểm gốc model trả | Giây |")
        out.append("|---|---|---|---|---|---|---|---|---|")
        for r in sorted(recs, key=lambda r: (r["item_id"], r["run"])):
            s = r["scores"][show]
            raw = r.get("raw_point")
            raw_txt = f"{raw[0]:.0f}, {raw[1]:.0f}" if raw else "—"
            res = "lỗi" if r.get("error") else RESULT_VI[s["result"]]
            out.append(f"| {r['item_id']} | {r['size_class']} | {r['run']} | {res} | "
                       f"{s.get('distance_px', '—')} | {s.get('direction', '—')} | {r.get('action_type') or '—'} | "
                       f"{raw_txt} | {r['latency_s']:.2f} |")
        out += ["", _latency_line(recs), _usage_line(recs)]
        checks = sum(1 for r in recs if r.get("safety_checks"))
        if checks:
            out.append(f"Có pending_safety_checks ở {checks} lần gọi.")
        errs = [r for r in recs if r.get("error")]
        if errs:
            out.append(f"Lỗi ({len(errs)}): " + "; ".join(sorted({r['error'][:120] for r in errs})))
        if recs[0]["stage"] == "cases" and conv in CONVENTIONS:
            out += [""] + _decision(recs, conv)
        out.append("")
    return "\n".join(out)


def write_summary(out_dir: Path) -> Path:
    info_file = out_dir / "run.json"
    run_info = json.loads(info_file.read_text(encoding="utf-8")) if info_file.exists() else None
    text = summarize(load_records(out_dir), run_info)
    path = out_dir / "summary.md"
    path.write_text(text, encoding="utf-8")
    return path


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("Usage: python -m grounding_test.report <results folder>")
    print(write_summary(Path(sys.argv[1])))
