"""Score transcription runs against the references, without a human.

  python -m stt_eval.score stt_eval/results/*-me*

Rule, fixed before scoring (30/10/2026). Text is lower-cased, punctuation removed,
single digits spelled out ("6" -> "sáu"), then split into syllables.
  - WER: syllable error rate (substitutions + deletions + insertions) / reference length.
  - Content recall: share of the reference's content syllables (all syllables except a
    fixed list of fillers and function words) that appear in the transcript.
  - Verdict per recording: "còn" if recall >= 0.85, "một phần" if >= 0.60, else "mất".
  - "mày": count of the word in the transcript; mom never says it, so every one is an error.
Threshold agreed with the founder for T3: >= 7/8 "còn" -> speaking is the main way to ask.
"""

from __future__ import annotations

import json
import re
import statistics
import sys
from collections import Counter
from pathlib import Path

DIGITS = {"0": "không", "1": "một", "2": "hai", "3": "ba", "4": "bốn", "5": "năm",
          "6": "sáu", "7": "bảy", "8": "tám", "9": "chín"}
FILLERS = set("ủa à ừ ờ nè hả hen nha vậy đó này kia thì là mà cái nó rồi chứ lại cả với và "
              "nhưng của các những một cho xong luôn đi".split())
KEEP, PARTIAL = 0.85, 0.60


def syllables(text: str) -> list[str]:
    text = re.sub(r"\d", lambda m: f" {DIGITS[m.group()]} ", text.lower())
    return re.sub(r"[^\w\s]", " ", text).split()


def edit_distance(a: list[str], b: list[str]) -> int:
    prev = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        cur = [i]
        for j, y in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (x != y)))
        prev = cur
    return prev[-1]


def score_one(ref: str, hyp: str) -> dict:
    r, h = syllables(ref), syllables(hyp)
    content = [w for w in r if w not in FILLERS]
    have = Counter(h)
    hit = 0
    for w in content:
        if have[w] > 0:
            have[w] -= 1
            hit += 1
    recall = hit / len(content) if content else 1.0
    verdict = "còn" if recall >= KEEP else "một phần" if recall >= PARTIAL else "mất"
    return {"wer": edit_distance(r, h) / max(len(r), 1), "recall": recall, "verdict": verdict,
            "may": h.count("mày")}


def score_dirs(dirs: list[Path]) -> dict:
    """{config: [per-run summaries]} over every results folder given."""
    out: dict[str, list[dict]] = {}
    for d in dirs:
        rows = json.loads((d / "transcripts.json").read_text(encoding="utf-8"))
        configs = [k for k, v in rows[0].items() if isinstance(v, dict)]
        for c in configs:
            per = [score_one(r["ref"], r[c].get("transcript", "")) for r in rows]
            out.setdefault(c, []).append({
                "run": d.name, "n": len(per),
                "kept": sum(p["verdict"] == "còn" for p in per),
                "partial": sum(p["verdict"] == "một phần" for p in per),
                "lost": sum(p["verdict"] == "mất" for p in per),
                "wer": statistics.mean(p["wer"] for p in per),
                "recall": statistics.mean(p["recall"] for p in per),
                "may": sum(p["may"] for p in per),
                "items": [{"file": r["file"], **p} for r, p in zip(rows, per)],
            })
    return out


def main(argv=None) -> None:
    dirs = [Path(p) for p in (argv or sys.argv[1:])]
    if not dirs:
        raise SystemExit("Usage: python -m stt_eval.score <results folders>")
    result = score_dirs(dirs)
    print("| Cấu hình | Lần chạy | Còn / một phần / mất | WER âm tiết | Độ phủ từ nội dung | Số 'mày' |")
    print("|---|---|---|---|---|---|")
    for c, runs in result.items():
        for r in runs:
            print(f"| {c} | {r['run']} | {r['kept']} / {r['partial']} / {r['lost']} (trên {r['n']}) | "
                  f"{r['wer']:.1%} | {r['recall']:.1%} | {r['may']} |")
    for c, runs in result.items():
        worst = min(r["kept"] for r in runs)
        print(f"{c}: lần tệ nhất còn {worst}/{runs[0]['n']} -> "
              f"{'ĐẠT ngưỡng T3 (>= 7/8)' if worst >= 7 else 'chưa đạt ngưỡng T3'}")


if __name__ == "__main__":
    main()
