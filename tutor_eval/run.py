"""T4: can one Spark M2 call both point and write the sentence the tutor says, without losing accuracy?

  .venv/bin/python -m tutor_eval.run plan
  .venv/bin/python -m tutor_eval.run run --yes            # 24 paid calls, about $0.15
  .venv/bin/python -m tutor_eval.run summary tutor_eval/results/<stamp>

Rule, fixed before the run (31/10/2026):
- Setup: the 12 real cases with their frozen labels, Spark M2 (muse-spark-1.3),
  reasoning_effort low, 2 runs each = 24 calls, prompt = screentutor.tutor.build_prompt.
  The 6 cases in cases/state_t1.json (01, 03, 04, 07, 10, 12) get that state text;
  the other 6 go without state, as in the runs of 29/10.
- (1) Pointing: at least 10/12 hits in each run (the Decision 3 threshold).
  The same setup with the pointing-only prompt on 29/10 hit 11/12 in each run
  (only case_03, which landed between the URL and the title).
- (2) Latency: median of the 24 calls at most 5.0 s (founder's limit). The
  pointing-only prompt had a median of 2.39 s (no state) and 2.42 s (state).
- (3) Spoken sentence: at least 22/24 calls pass every automatic check:
  not empty, at most 2 sentences, at most 40 syllables, says "mẹ", no symbols,
  emoji or coordinates.
- All three pass: the MVP uses this single call. (1) fails: try two calls in
  parallel (the measured pointing prompt + a separate sentence prompt) under the
  same rule. (2) fails: cut the sentence to one and rerun. (3) fails alone: fix
  the sentence rules and rerun.
- Not scored by code: whether the sentences sound right for mom. The founder
  reads say_review.txt.

Rerun rule, fixed before the second run (31/10/2026). Run 20261031-134029 passed
(1) with 11/11 and (2) with 4.05 s, and failed (3) with 21/24: three answers had
no Vietnamese diacritics. Read by eye, it also called mom "con" twice, said
"giúp con" 7 times and promised to open things for her twice. The sentence rules
now ask for full diacritics, forbid those three, and say mom does the clicking.
The pointing text is unchanged. Four checks are added to (3): no diacritics,
calls mom "con", "giúp con", promises to act for her. Thresholds unchanged.

Third rule, fixed before the third run (31/10/2026). The rerun 20261031-134317
passed all three (10/11, 3.99 s, 24/24), but 12/24 sentences had the tutor
talk about itself as "con", mostly awkwardly. The founder decided the tutor
calls the user "bạn" and itself "mình". The sentence rules now say so and ask
for no sentences about itself; the pointing text is unchanged. In (3), "says
mẹ" becomes "says bạn"; the "con" checks become: calls the user "mẹ" or the
tutor "con", asks a favour ("giúp mình", "nhờ bạn", "mời bạn"), promises to
act for her. Thresholds unchanged. Reported but not scored: how many
sentences say "mình".

Fourth rule, fixed before the 02/11 rerun. After the Windows trip the prompt gained
three sentence rules (no talk about itself, a needed earlier step comes first,
and caution=true with the consequence said when a click sends something or
replaces a file), and (3) gained a "nói về mình" check. The pointing text is
unchanged. Thresholds (1)-(3) unchanged; added (4): caution=true in at most
1/24 calls, since no step in these 12 cases sends or replaces anything. If (1)
or (2) fail, the three new rules are taken out again.

Fifth rule, fixed before the 02/11 evening run: the part of T12 that needs no new
data, R5 and R6 of the plan's section 7.2, on the task prompt of B1 (tutor.ask with
task rules). The founder allowed paid tests on 02/11. Same 12 cases, 2 runs, same
states; MACHINE_NOTES stay out, as in every earlier T4.
- R5a pointing: at least 10/12 hits in each run.
- R5b speech: 24/24 calls pass every automatic check.
- R5c latency: median at most 6.4 s (5.0 s measured 4.9 s before B1).
- R6: caution=true in 0 of 24 calls.
Reported, not scored: mode, target, plan, box, output and reasoning tokens.
If R5a fails the B1 block is shortened or taken out. If only R5c fails the block is
shortened and the run repeated as a new attempt, reported as such. Thresholds stay.

Sixth rule, fixed before the second attempt of the same evening. The first attempt
(20261102-183850) got R5a 12/10, R5b 23/24 (failed), R5c 11.12 s (failed), R6 0 flags.
Changed since: the B1 block cut to about 40%, effort "minimal", and the answer streamed
with the keys that show the step first. Same 12 cases, 2 runs, thresholds of the fifth
rule unchanged, the failed attempt stays on record. Added before this run and scored
on its own, not instead of R5c:
- R5d: median time until X and Y are in, when the ring can show, at most 5.0 s, the
  founder's limit in the first rule above. Reported, not scored: until say is complete.

Seventh rule, fixed before the third attempt of the same evening. The second attempt
(20261102-185140) got R5a 10/11, R5b 23/24 (failed), R5c 6.21 s, R5d 3.90 s, R6 0, but
case_04 missed twice, and 5 repeats showed why: minimal hit 1/5 where low hit 4/5. That
case is the link that opened behind Zalo, the reason the Windows state exists, and a
total over 12 cases hides it. So the prompt now says the rule in words, only for when she
says she already clicked, and asks the sentences not to talk about the tutor. Same 12
cases, 2 runs, thresholds unchanged. Added before this run:
- R5e: 5 more calls on case_04 hit at least 4/5, what low reached.
Run 20261102-190252 of this rule is void, not a result: from the 4th call on this machine
could not resolve the API's name (21 of 24 calls, 0 tokens). The rule is unchanged.
Run 20261102-190505 passed all: R5a 11/11, R5b 24/24, R5c 5.98 s, R5d 3.83 s, R5e 5/5, R6 0.

Eighth rule, fixed before the next run. The big-task test found two real faults: a message
cut at the bottom was framed instead of scrolled, and file names were spoken with their
underscores. The prompt gained one clause for each. Any change to the prompt repeats this
test: same 12 cases, 2 runs, all of R5a-e and R6 unchanged.
"""

from __future__ import annotations

import argparse
import collections
import json
import re
import statistics
import sys
import time
import unicodedata
from datetime import datetime
from pathlib import Path

from grounding_test import config as gconfig
from grounding_test.datasets import CASES_DIR, load_cases, prepare_image
from grounding_test.scoring import score_point
from screentutor.tutor import EFFORT, MODEL, Tutor, _api_key

HERE = Path(__file__).parent
STATE_FILE = CASES_DIR / "state_t1.json"
RUNS = 2
MIN_HITS = gconfig.ADOPT_MIN_HITS
LATENCY_LIMIT_S = gconfig.LATENCY_LIMIT_S
MIN_SAY_OK = 22
MAX_SENTENCES = 2
MAX_SYLLABLES = 40
EST_COST_PER_CALL = 0.008
T12_SAY_OK, T12_LATENCY_S = 24, 6.4   # R5b, R5c of the plan's T12
T12_RING_S = 5.0                      # R5d
STATE_CASE, STATE_REPEATS, STATE_MIN = "case_04", 5, 4   # R5e

# Hits out of 2 for the pointing-only prompt, effort low, 29/10 (with state where state_t1.json has it).
BASELINE_HITS = {"case_01": 2, "case_02": 2, "case_03": 0, "case_04": 2, "case_05": 2, "case_06": 2,
                 "case_07": 2, "case_08": 2, "case_09": 2, "case_10": 2, "case_11": 2, "case_12": 2}

MARKUP = set("*#`•[]{}<>|_")
COORDS = re.compile(r"\d+\s*[,;]\s*\d+|t(?:oạ|ọa)\s*độ", re.IGNORECASE)
FAMILY_WORDS = re.compile(r"\bmẹ\b|\b(?:nhé|nha|nhá|ạ|cho|giúp|nhờ|mời)\s+con\b|(?:^|[.,!?]\s*)con\b"
                          r"|\bcon\s+(?:sẽ|mời|nhờ|chỉ|thấy|hướng|dặn)\b", re.IGNORECASE)
ASKS_FAVOUR = re.compile(r"\bgiúp mình\b|\b(?:nhờ|mời)\s+bạn\b", re.IGNORECASE)
ACTS_FOR_HER = re.compile(r"\b(?:mình|con)\s+(?:sẽ\s+)?(?:mở|bấm|làm|gửi|lưu|tắt|tạo)\b", re.IGNORECASE)
SELF = re.compile(r"\bmình\b", re.IGNORECASE)
SELF_TALK = re.compile(r"\bmình\s+(?:nói|chỉ|nhắc|dặn|thấy|hướng dẫn|giải thích)\b", re.IGNORECASE)  # T5 (02/11)


def say_problems(say: str) -> list[str]:
    """Automatic checks on the spoken sentence; empty list = passes."""
    say = unicodedata.normalize("NFC", say)
    if not say.strip():
        return ["trống"]
    problems = []
    sentences = [s for s in re.split(r"[.!?]+(?:\s+|$)", say) if s.strip()]
    if len(sentences) > MAX_SENTENCES:
        problems.append(f"{len(sentences)} câu")
    syllables = len(say.split())
    if syllables > MAX_SYLLABLES:
        problems.append(f"{syllables} âm tiết")
    if say.isascii():
        problems.append("không dấu")
    elif not re.search(r"\bbạn\b", say, re.IGNORECASE):
        problems.append("không gọi bạn")
    if FAMILY_WORDS.search(say):
        problems.append("gọi mẹ hoặc xưng con")
    if ASKS_FAVOUR.search(say):
        problems.append("nhờ vả")
    if ACTS_FOR_HER.search(say):
        problems.append("hứa làm hộ")
    if SELF_TALK.search(say):
        problems.append("nói về mình")
    if "\n" in say or any(c in MARKUP for c in say):
        problems.append("có ký hiệu")
    if any(ord(c) > 0xFFFF for c in say):
        problems.append("có emoji")
    if COORDS.search(say):
        problems.append("nhắc toạ độ")
    return problems


def load_states() -> dict[str, str]:
    data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    return {k: v for k, v in data.items() if not k.startswith("_")}


def cmd_plan(_args) -> list:
    items, problems = load_cases()
    if problems:
        sys.exit("Thiếu dữ liệu ca thật:\n" + "\n".join(problems))
    states = load_states()
    for it in items:
        print(f"  {it.item_id} {'có trạng thái' if it.item_id in states else 'không trạng thái':16} {it.question_vi}")
    n = len(items) * RUNS
    print(f"Tổng: {n} lần gọi {MODEL}, effort low, chi phí ước tính khoảng ${n * EST_COST_PER_CALL:.2f}.")
    return items


def cmd_run(args) -> None:
    items = cmd_plan(args)
    if not args.yes:
        sys.exit("Thêm --yes để thực sự gọi API (tốn tiền).")
    states = load_states()
    out = HERE / "results" / datetime.now().strftime("%Y%m%d-%H%M%S")
    (out / "raw").mkdir(parents=True)
    tutor = Tutor(_api_key())
    n = 0
    try:
        with (out / "calls.jsonl").open("w", encoding="utf-8") as log:
            for it in items:
                data_url, sent_size, orig_size = prepare_image(it.image_path)
                state = states.get(it.item_id)
                for run in range(1, RUNS + 1):
                    n += 1
                    started, seen = time.perf_counter(), {}
                    reply = tutor.ask(it.question_vi, data_url, state,
                                      on_mark=lambda _r: seen.setdefault("ring", time.perf_counter() - started),
                                      on_say=lambda _t: seen.setdefault("say", time.perf_counter() - started))
                    scores = score_point(reply.point, sent_size, orig_size, it.boxes, gconfig.NEAR_PX)
                    raw_file = f"raw/{n:03d}.json"
                    (out / raw_file).write_text(json.dumps(reply.raw, ensure_ascii=False, indent=2),
                                                encoding="utf-8")
                    rec = {
                        "item_id": it.item_id, "run": run, "question": it.question_vi, "state": state,
                        "found": reply.found, "point": reply.point, "element": reply.element,
                        "say": reply.say, "say_problems": say_problems(reply.say), "caution": reply.caution,
                        "result": scores["norm1000"]["result"], "distance_px": scores["norm1000"].get("distance_px"),
                        "mode": reply.mode, "target": reply.target, "plan": reply.plan, "box": reply.box,
                        "notes": reply.notes, "ring_s": round(seen.get("ring", 99), 3),
                        "say_s": round(seen.get("say", 99), 3),
                        "latency_s": round(reply.latency_s, 3), "usage": reply.usage, "error": reply.error,
                        "raw_file": raw_file,
                    }
                    log.write(json.dumps(rec, ensure_ascii=False) + "\n")
                    log.flush()
                    print(f"[{n}/{len(items) * RUNS}] {it.item_id} lần {run}: {rec['result']} "
                          f"({reply.latency_s:.1f}s) {reply.error or ''}{reply.say}")
            it = next(i for i in items if i.item_id == STATE_CASE)
            data_url, sent_size, orig_size = prepare_image(it.image_path)
            extra = []
            for _ in range(STATE_REPEATS):
                reply = tutor.ask(it.question_vi, data_url, states.get(STATE_CASE), on_mark=lambda _r: None)
                extra.append(score_point(reply.point, sent_size, orig_size, it.boxes, gconfig.NEAR_PX)["norm1000"]["result"])
            (out / "state_case.json").write_text(json.dumps(extra), encoding="utf-8")
    finally:
        tutor.close()
    print(f"Đã ghi: {summarize(out)}")


def summarize(out: Path) -> Path:
    rows = [json.loads(line) for line in (out / "calls.jsonl").open(encoding="utf-8")]
    runs = sorted({r["run"] for r in rows})
    hits = {k: sum(r["result"] == "hit" for r in rows if r["run"] == k) for k in runs}
    n_items = len({r["item_id"] for r in rows})
    lat = sorted(r["latency_s"] for r in rows if not r["error"])
    med = statistics.median(lat) if lat else float("inf")
    p90 = lat[min(len(lat) - 1, int(0.9 * len(lat)))] if lat else float("inf")
    say_ok = sum(not r["say_problems"] for r in rows)
    price = gconfig.PRICES[MODEL]
    cost = sum(r["usage"]["input"] * price["input"] + r["usage"]["output"] * price["output"] for r in rows) / 1e6

    ok1 = n_items == gconfig.CASES_TOTAL and all(h >= MIN_HITS for h in hits.values())
    ok2 = med <= LATENCY_LIMIT_S
    ok3 = say_ok >= MIN_SAY_OK
    mark = {True: "đạt", False: "KHÔNG đạt"}
    extra = json.loads((out / "state_case.json").read_text()) if (out / "state_case.json").exists() else []
    lines = [
        f"# T4: một lần gọi vừa trỏ vừa soạn câu nói ({out.name})", "",
        f"Model {MODEL}, effort {EFFORT}, {len(rows)} lần gọi, chi phí khoảng ${cost:.3f}.", "",
        "| Điều kiện | Kết quả | Ngưỡng | |", "|---|---|---|---|",
        f"| (1) Trúng mỗi lần chạy | {' / '.join(str(hits[k]) for k in runs)} trên {n_items} | ≥ {MIN_HITS}/12 "
        f"(mốc 29/10: 11) | {mark[ok1]} |",
        f"| (2) Trễ trung vị / p90 | {med:.2f} s / {p90:.2f} s | ≤ {LATENCY_LIMIT_S:.0f} s (mốc 2,39 s) | {mark[ok2]} |",
        f"| (3) Câu nói qua kiểm tra tự động | {say_ok}/{len(rows)} | ≥ {MIN_SAY_OK}/24 | {mark[ok3]} |",
        f"| Câu có chữ \"mình\" (không chấm) | {sum(bool(SELF.search(r['say'])) for r in rows)}/{len(rows)} | | |",
        f"| (4) caution bật (từ 02/11) | {sum(bool(r.get('caution')) for r in rows)}/{len(rows)} | ≤ 1/24 | |",
        "", f"**Theo luật đặt trước: {'đạt cả ba' if ok1 and ok2 and ok3 else 'chưa đạt'}.**", "",
        f"T12 (02/11): R5a {' / '.join(str(hits[k]) for k in runs)} (≥ {MIN_HITS}) {mark[ok1]}; "
        f"R5b {say_ok}/{len(rows)} (cần {T12_SAY_OK}) {mark[say_ok >= T12_SAY_OK]}; "
        f"R5c {med:.2f} s (≤ {T12_LATENCY_S}) {mark[med <= T12_LATENCY_S]}; "
        f"R6 {sum(bool(r.get('caution')) for r in rows)} cờ (cần 0) "
        f"{mark[not any(r.get('caution') for r in rows)]}.",
        f"R5d vòng hiện: trung vị {statistics.median(r.get('ring_s', 99) for r in rows):.2f} s (≤ {T12_RING_S}) "
        f"{mark[statistics.median(r.get('ring_s', 99) for r in rows) <= T12_RING_S]}; "
        f"câu nói xong: trung vị {statistics.median(r.get('say_s', 99) for r in rows):.2f} s.",
        f"R5e {STATE_CASE} lặp {len(extra)} lần: {extra.count('hit')} trúng (cần ≥ {STATE_MIN}) "
        f"{mark[extra.count('hit') >= STATE_MIN]}.",
        f"Không chấm: mode {sorted(collections.Counter(r.get('mode') or '?' for r in rows).items())}, "
        f"target {sorted(collections.Counter(r.get('target') or '?' for r in rows).items())}, "
        f"có plan {sum(bool(r.get('plan')) for r in rows)}, có box {sum(bool(r.get('box')) for r in rows)}, "
        f"token ra trung vị {statistics.median(r['usage']['output'] for r in rows):.0f}, "
        f"suy luận {statistics.median(r['usage']['reasoning'] for r in rows):.0f}.", "",
        "| Ca | Trạng thái | Mốc 29/10 | " + " | ".join(f"Lần {k}" for k in runs) + " | Trễ | Chỉ vào |",
        "|---|---|---|" + "---|" * len(runs) + "---|---|",
    ]
    by_item = {}
    for r in rows:
        by_item.setdefault(r["item_id"], []).append(r)
    for cid, rs in sorted(by_item.items()):
        rs.sort(key=lambda r: r["run"])
        res = " | ".join(r["result"] + (f" ({r['distance_px']:.0f} px)" if r["result"] != "hit" and r["distance_px"]
                                        else "") for r in rs)
        lines.append(f"| {cid} | {'có' if rs[0]['state'] else 'không'} | {BASELINE_HITS.get(cid, '?')}/2 | {res} | "
                     + ", ".join(f"{r['latency_s']:.1f}" for r in rs) + f" s | {rs[0]['element']} |")
    bad = [r for r in rows if r["say_problems"] or r["error"]]
    if bad:
        lines += ["", "Câu không qua kiểm tra tự động:", ""]
        lines += [f"- {r['item_id']} lần {r['run']}: {', '.join(r['say_problems']) or r['error']}: {r['say']}"
                  for r in bad]
    (out / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    review = ["CÂU TUTOR SẼ NÓI (việc của founder: đọc to từng câu, đóng vai mẹ nghe)", "",
              "Với mỗi câu ghi: dễ hiểu / hơi khó / khó, và câu nào nghe sai giọng (trêu, ra lệnh, dài).", ""]
    for cid, rs in sorted(by_item.items()):
        review.append(f"{cid}. Mẹ hỏi: {rs[0]['question']}")
        review += [f"   Lần {r['run']} ({r['result']}): {r['say']}" for r in rs]
        review.append("   Nhận xét: ")
        review.append("")
    (out / "say_review.txt").write_text("\n".join(review), encoding="utf-8")
    print("\n".join(lines[:10]))
    return out / "summary.md"


def main(argv=None) -> None:
    p = argparse.ArgumentParser(prog="python -m tutor_eval.run")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("plan")
    r = sub.add_parser("run")
    r.add_argument("--yes", action="store_true", help="xác nhận gọi API có tính phí")
    s = sub.add_parser("summary")
    s.add_argument("dir")
    args = p.parse_args(argv)
    if args.cmd == "summary":
        print(f"Đã ghi: {summarize(Path(args.dir))}")
    else:
        {"plan": cmd_plan, "run": cmd_run}[args.cmd](args)


if __name__ == "__main__":
    main()
