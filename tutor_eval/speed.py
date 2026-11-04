"""E1 (03/11): does sending fewer pixels, or asking for less thinking, make the tutor answer sooner?

The founder asked whether the tutor could attend only to what changed on the screen. Spark runs
on Meta's servers and takes the whole image, so what can change on our side is what we send and
how much it is asked to think. Half-size is the floor of any "whole screen small + the changed
part sharp" scheme (that sends half-size and more), so if half-size is not faster, cropping to
the change is not either.

Variants, each sent for every one of the 12 real cases (tutor_eval.run's cases and states),
interleaved within each case so a slow minute of the network hits all of them alike:
  png        full-size PNG, effort minimal: what the app sends now
  half       half-size PNG (960x540)
  jpeg       full-size JPEG, quality 85
  half_jpeg  half-size JPEG, quality 85
  low        full-size PNG, effort low
  none       full-size PNG, no reasoning_effort sent (the model's default)
The answer is on the 0-1000 grid whatever the size, so hits are scored the same way.

  .venv/bin/python -m tutor_eval.speed run --runs 3      # 12 x 6 x 3 = 216 calls, about $1.7
  .venv/bin/python -m tutor_eval.speed summary tutor_eval/results/<stamp>-speed

Rule, fixed before the run (03/11; Claude's proposal, the founder allowed paid tests freely):
- A variant replaces what the app sends only if it hits at least 10/12 in every run AND its
  median time until the mark can show (ring_s) is at least 0.5 s below png's in the same run.
- Reported, not scored: input tokens (so the image's share of them), output and reasoning tokens,
  bytes sent, time until the sentence is complete.

Result (20261103-184214-speed), stopped after 98 of 216 calls: round 1 complete, round 2 at 5 cases.
It was conclusive and the API had slowed under three parallel runs. Round 1 hits: png 12, half 7,
jpeg 11, half_jpeg 6, low 11, none 12. Median until the mark: png 4.30 s, half 5.12 s, jpeg 3.96 s,
half_jpeg 4.97 s, low 7.59 s, none 17.66 s. The image is about 2,050 of the 3,570 input tokens;
halving it halves them and is slower and half as accurate. The time follows the thinking: 319
reasoning tokens at minimal, 656 at low, 1,834 with none. No variant passes; the app keeps
full-size PNG at minimal.
"""

from __future__ import annotations

import argparse
import base64
import io
import json
import statistics
import sys
import time
from datetime import datetime
from pathlib import Path

from PIL import Image

from grounding_test import config as gconfig
from grounding_test.datasets import load_cases
from grounding_test.scoring import score_point
from screentutor.tutor import Tutor, _api_key
from tutor_eval.run import load_states

HERE = Path(__file__).parent
VARIANTS = ("png", "half", "jpeg", "half_jpeg", "low", "none")
MIN_HITS, MIN_GAIN_S = 10, 0.5


def encode(path: Path, variant: str) -> tuple[str, tuple[int, int], tuple[int, int], int]:
    """(data URL, size sent, original size, bytes) for a variant."""
    with Image.open(path) as img:
        img = img.convert("RGB")
        orig = img.size
        if variant.startswith("half"):
            img = img.resize((orig[0] // 2, orig[1] // 2), Image.Resampling.LANCZOS)
        buf = io.BytesIO()
        jpeg = variant.endswith("jpeg")
        img.save(buf, format="JPEG", quality=85) if jpeg else img.save(buf, format="PNG")
        raw = buf.getvalue()
    mime = "jpeg" if jpeg else "png"
    return f"data:image/{mime};base64," + base64.b64encode(raw).decode("ascii"), img.size, orig, len(raw)


def cmd_run(args) -> None:
    items, problems = load_cases()
    if problems or len(items) != 12:
        sys.exit(f"Cần đủ 12 ca: {problems}")
    states = load_states()
    out = HERE / "results" / (datetime.now().strftime("%Y%m%d-%H%M%S") + "-speed")
    out.mkdir(parents=True)
    tutors = {"low": Tutor(_api_key(), effort="low"), "none": Tutor(_api_key(), effort=None)}
    default = Tutor(_api_key())
    n, total = 0, len(items) * len(VARIANTS) * args.runs
    try:
        with (out / "calls.jsonl").open("w", encoding="utf-8") as log:
            for run in range(1, args.runs + 1):
                for it in items:
                    for variant in VARIANTS:
                        n += 1
                        data_url, sent, orig, size = encode(it.image_path, "png" if variant in ("low", "none")
                                                            else variant)
                        tutor = tutors.get(variant, default)
                        started, seen = time.perf_counter(), {}
                        reply = tutor.ask(it.question_vi, data_url, states.get(it.item_id),
                                          on_mark=lambda _r: seen.setdefault("ring", time.perf_counter() - started),
                                          on_say=lambda _t: seen.setdefault("say", time.perf_counter() - started))
                        score = score_point(reply.point, sent, orig, it.boxes, gconfig.NEAR_PX)["norm1000"]
                        rec = {"variant": variant, "run": run, "item_id": it.item_id, "result": score["result"],
                               "ring_s": round(seen.get("ring", 99), 3), "say_s": round(seen.get("say", 99), 3),
                               "latency_s": round(reply.latency_s, 3), "usage": reply.usage, "bytes": size,
                               "error": reply.error}
                        log.write(json.dumps(rec, ensure_ascii=False) + "\n")
                        log.flush()
                        print(f"[{n}/{total}] {variant:9} {it.item_id} lần {run}: {rec['result']} "
                              f"mark {rec['ring_s']:.2f}s total {reply.latency_s:.2f}s {reply.error or ''}", flush=True)
    finally:
        for t in (*tutors.values(), default):
            t.close()
    print(f"Đã ghi: {summarize(out)}")


def summarize(out: Path) -> Path:
    rows = [json.loads(line) for line in (out / "calls.jsonl").read_text(encoding="utf-8").splitlines() if line]
    runs = sorted({r["run"] for r in rows})
    med = lambda xs: statistics.median(xs) if xs else float("nan")   # noqa: E731
    base = {run: med([r["ring_s"] for r in rows if r["variant"] == "png" and r["run"] == run and not r["error"]])
            for run in runs}
    lines = [f"# E1: ít pixel hơn, hay ít suy nghĩ hơn, có làm tutor trả lời sớm hơn không ({out.name})", "",
             f"{len(rows)} lần gọi, {len(runs)} lượt, 12 ca. Luật: trúng ≥ {MIN_HITS}/12 mỗi lượt VÀ vòng hiện sớm hơn png "
             f"≥ {MIN_GAIN_S} s (trung vị, cùng lượt).", "",
             "| Kiểu | Trúng mỗi lượt | Vòng hiện (trung vị) | Câu xong | Token vào | Token ra (suy nghĩ) | Byte gửi | Lỗi | Kết luận |",
             "|---|---|---|---|---|---|---|---|---|"]
    for v in VARIANTS:
        rs = [r for r in rows if r["variant"] == v]
        ok = [r for r in rs if not r["error"]]
        hits = [sum(r["result"] == "hit" for r in rs if r["run"] == run) for run in runs]
        gains = [base[run] - med([r["ring_s"] for r in ok if r["run"] == run]) for run in runs]
        passed = v != "png" and all(h >= MIN_HITS for h in hits) and all(g >= MIN_GAIN_S for g in gains)
        u = [r["usage"] for r in ok if r.get("usage")]
        lines.append(f"| {v} | {', '.join(map(str, hits))} | {med([r['ring_s'] for r in ok]):.2f} s "
                     f"| {med([r['say_s'] for r in ok]):.2f} s | {med([x['input'] for x in u]):.0f} "
                     f"| {med([x['output'] for x in u]):.0f} ({med([x['reasoning'] for x in u]):.0f}) "
                     f"| {med([r['bytes'] for r in rs]) / 1024:.0f} KB | {len(rs) - len(ok)} "
                     f"| {'—' if v == 'png' else ('ĐẠT' if passed else 'không')} |")
    path = out / "summary.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def main(argv=None) -> None:
    p = argparse.ArgumentParser(prog="python -m tutor_eval.speed")
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--runs", type=int, default=3)
    s = sub.add_parser("summary")
    s.add_argument("dir")
    args = p.parse_args(argv)
    if args.cmd == "summary":
        print(f"Đã ghi: {summarize(Path(args.dir))}")
    else:
        cmd_run(args)


if __name__ == "__main__":
    sys.exit(main())
