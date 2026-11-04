"""E2 (03/11): does asking twice at once, and taking whichever answers first, make the tutor sooner?

E1 found that pixels are not where the time goes: half-size images halved the input tokens but
missed half the targets and were no faster, and the time follows the model's thinking. That
thinking time varies a lot from call to call, so two identical calls sent together and raced
could cut the slow ones, at twice the cost. Whether the server slows each call down when two run
at once is part of what this measures.

For each of the 12 cases (tutor_eval.run's cases and states), per round, interleaved:
  single  one call, as the app does now
  pair    two identical calls at the same moment; the mark time is the first of the two to know X, Y

  .venv/bin/python -m tutor_eval.hedge run --runs 3      # 12 x 3 x 3 = 108 calls, about $0.9
  .venv/bin/python -m tutor_eval.hedge summary tutor_eval/results/<stamp>-hedge

Rule, fixed before the run (03/11; Claude's proposal): racing two calls is adopted only if its
median time until the mark (the first of the pair) is at least 0.5 s below single's, and the
answer that won hits at least 10/12 in every round.

Result (20261103-190520-hedge), 36 singles and 36 pairs: the mark at a median of 3.24 s raced, 4.11 s
single (0.87 s sooner); p90 4.94 s against 6.08 s, and the two slowest singles (9.3 s, 9.9 s) have no
match among the pairs (slowest 5.7 s). Hits per round: single 12, 12, 11; raced 11, 12, 11. Each call of a
pair alone: median 3.80 s, so two at once did not slow the server. Passes: tutor.HEDGE is on.
The harness calls Tutor(hedge=False) on both sides of a pair, so it measures the race itself.
"""

from __future__ import annotations

import argparse
import json
import statistics
import threading
import time
from datetime import datetime
from pathlib import Path

from grounding_test import config as gconfig
from grounding_test.datasets import load_cases, prepare_image
from grounding_test.scoring import score_point
from screentutor.tutor import Tutor, _api_key
from tutor_eval.run import load_states

HERE = Path(__file__).parent
MIN_GAIN_S, MIN_HITS = 0.5, 10


def timed(tutor: Tutor, question: str, url: str, state: str | None) -> dict:
    started, seen = time.perf_counter(), {}
    reply = tutor.ask(question, url, state, on_mark=lambda _r: seen.setdefault("ring", time.perf_counter() - started))
    return {"reply": reply, "ring": seen.get("ring", 99.0), "total": time.perf_counter() - started}


def cmd_run(args) -> None:
    items, problems = load_cases()
    states = load_states()
    out = HERE / "results" / (datetime.now().strftime("%Y%m%d-%H%M%S") + "-hedge")
    out.mkdir(parents=True)
    tutors = [Tutor(_api_key(), hedge=False), Tutor(_api_key(), hedge=False)]   # one connection pool each
    try:
        with (out / "calls.jsonl").open("w", encoding="utf-8") as log:
            for run in range(1, args.runs + 1):
                for it in items:
                    url, sent, orig = prepare_image(it.image_path)
                    state = states.get(it.item_id)
                    for kind in ("single", "pair"):
                        if kind == "single":
                            results = [timed(tutors[0], it.question_vi, url, state)]
                        else:
                            results = [None, None]

                            def go(i):
                                results[i] = timed(tutors[i], it.question_vi, url, state)
                            threads = [threading.Thread(target=go, args=(i,)) for i in (0, 1)]
                            for t in threads:
                                t.start()
                            for t in threads:
                                t.join()
                        first = min(results, key=lambda r: r["ring"])
                        hit = score_point(first["reply"].point, sent, orig, it.boxes, gconfig.NEAR_PX)["norm1000"]["result"]
                        rec = {"kind": kind, "run": run, "item_id": it.item_id, "result": hit,
                               "rings": [round(r["ring"], 3) for r in results], "ring": round(first["ring"], 3),
                               "errors": [r["reply"].error for r in results if r["reply"].error]}
                        log.write(json.dumps(rec, ensure_ascii=False) + "\n")
                        log.flush()
                        print(f"{kind:6} {it.item_id} lần {run}: {hit} mark {rec['rings']}", flush=True)
    finally:
        for t in tutors:
            t.close()
    print(f"Đã ghi: {summarize(out)}")


def summarize(out: Path) -> Path:
    rows = [json.loads(x) for x in (out / "calls.jsonl").read_text(encoding="utf-8").splitlines() if x]
    runs = sorted({r["run"] for r in rows})
    single = [r for r in rows if r["kind"] == "single"]
    pair = [r for r in rows if r["kind"] == "pair"]
    med_single = statistics.median(r["ring"] for r in single)
    med_pair = statistics.median(r["ring"] for r in pair)
    each_in_pair = statistics.median(x for r in pair for x in r["rings"])
    hits = [sum(r["result"] == "hit" for r in pair if r["run"] == run) for run in runs]
    passed = med_single - med_pair >= MIN_GAIN_S and all(h >= MIN_HITS for h in hits)
    p90 = lambda xs: sorted(xs)[int(len(xs) * 0.9) - 1]   # noqa: E731
    lines = [f"# E2: hỏi hai lần cùng lúc, lấy câu về trước ({out.name})", "",
             f"| | Vòng hiện (trung vị) | p90 | Trúng mỗi lượt |", "|---|---|---|---|",
             f"| một lần (như app bây giờ) | {med_single:.2f} s | {p90([r['ring'] for r in single]):.2f} s "
             f"| {', '.join(str(sum(r['result'] == 'hit' for r in single if r['run'] == run)) for run in runs)} |",
             f"| hai lần, lấy câu về trước | {med_pair:.2f} s | {p90([r['ring'] for r in pair]):.2f} s "
             f"| {', '.join(map(str, hits))} |", "",
             f"Mỗi lần gọi trong cặp, tính riêng: trung vị {each_in_pair:.2f} s (so với {med_single:.2f} s khi gọi một mình: "
             f"máy chủ có làm chậm khi hai lần cùng chạy không).", "",
             f"Luật: nhanh hơn ít nhất {MIN_GAIN_S} s và trúng ≥ {MIN_HITS}/12 mỗi lượt: **{'ĐẠT' if passed else 'KHÔNG ĐẠT'}**."]
    path = out / "summary.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def main(argv=None) -> None:
    p = argparse.ArgumentParser(prog="python -m tutor_eval.hedge")
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
    main()
