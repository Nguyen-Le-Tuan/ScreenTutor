"""Command line for the grounding test. Nothing here clicks or types on any computer.

  python -m grounding_test.run check                              # key + model access, no cost
  python -m grounding_test.run plan --stage calibration           # what would run, no network
  python -m grounding_test.run run --stage calibration --yes      # paid calls
  python -m grounding_test.run run --stage cases --yes
  python -m grounding_test.run run --stage cases --models spark --methods m1 --resize 1366x768 --yes
  python -m grounding_test.run run --stage cases --only case_01,case_06,case_09,case_11 --lang en --yes
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

import httpx
from dotenv import load_dotenv

from . import config
from .datasets import load_calibration, load_cases, parse_size, prepare_image
from .meta_api import ApiError, CallResult, MetaAPI
from .report import write_summary
from .scoring import score_point

REPO_ROOT = Path(__file__).resolve().parent.parent
RESULTS_DIR = Path(__file__).parent / "results"


def _api_key() -> str:
    load_dotenv(REPO_ROOT / ".env")
    key = os.environ.get("MODEL_API_KEY", "").strip()
    if not key:
        sys.exit("Chưa có MODEL_API_KEY. Chép .env.example thành .env rồi điền key.")
    return key


def _select(args) -> tuple[list, list[tuple[str, str]], list[str]]:
    if args.stage == "calibration":
        items, problems = load_calibration(), []
        if args.lang == "en":
            sys.exit("Ảnh hiệu chuẩn chỉ có câu hỏi tiếng Việt.")
    else:
        items, problems = load_cases()
    if args.only:
        wanted = {s.strip() for s in args.only.split(",") if s.strip()}
        items = [i for i in items if i.item_id in wanted or i.item_id.split("/")[0] in wanted]
    if args.lang == "en":
        skipped = [i.item_id for i in items if not i.question_en]
        items = [i for i in items if i.question_en]
        problems += [f"{s}: không có question_en, bỏ qua" for s in skipped]

    models = set(args.models.split(",")) if args.models else None
    methods = set(args.methods.split(",")) if args.methods else None
    combos = [(m, k) for m, k in config.DEFAULT_COMBOS
              if (models is None or m in models) and (methods is None or k in methods)]
    if models:
        unknown = models - set(config.MODELS)
        if unknown:
            sys.exit(f"Model không có trong config: {sorted(unknown)}")
    return items, combos, problems


def _estimate(n_calls_by_model: dict[str, int]) -> float:
    cost = 0.0
    for model_id, n in n_calls_by_model.items():
        p = config.PRICES[model_id]
        cost += n * (config.EST_INPUT_TOKENS * p["input"] + config.EST_OUTPUT_TOKENS * p["output"]) / 1e6
    return cost


def cmd_plan(args) -> tuple[list, list, int]:
    items, combos, problems = _select(args)
    n_calls = len(items) * len(combos) * args.runs
    by_model = {}
    for m, _ in combos:
        mid = config.MODELS[m]
        by_model[mid] = by_model.get(mid, 0) + len(items) * args.runs
    print(f"Giai đoạn: {args.stage}; ngôn ngữ: {args.lang}; resize: {args.resize or 'không'}; "
          f"số lần chạy mỗi câu: {args.runs}")
    print("Cách gọi: " + ", ".join(f"{m}/{k}" for m, k in combos))
    for it in items:
        q = it.question_en if args.lang == "en" else it.question_vi
        print(f"  {it.item_id:24} {it.size_class:4} {q}")
    for p in problems:
        print(f"  ! {p}")
    print(f"Tổng: {n_calls} lần gọi API, chi phí ước tính khoảng ${_estimate(by_model):.3f} "
          f"(giả định ~{config.EST_INPUT_TOKENS} token vào mỗi lần).")
    return items, combos, n_calls


def cmd_check(_args) -> None:
    api = MetaAPI(_api_key())
    try:
        available = api.list_models()
    finally:
        api.close()
    print(f"Key hợp lệ. API trả về {len(available)} model.")
    for short, model_id in config.MODELS.items():
        print(f"  {short:7} {model_id:18} {'có quyền dùng' if model_id in available else 'KHÔNG thấy trong danh sách'}")


def cmd_run(args) -> None:
    items, combos, n_calls = cmd_plan(args)
    if not items or not combos:
        sys.exit("Không có gì để chạy.")
    if not args.yes:
        sys.exit("Thêm --yes để thực sự gọi API (tốn tiền).")

    api = MetaAPI(_api_key())
    available = set(api.list_models())
    usable = [(m, k) for m, k in combos if config.MODELS[m] in available]
    for m, k in combos:
        if (m, k) not in usable:
            print(f"Bỏ qua {m}/{k}: key không có quyền dùng {config.MODELS[m]}.")
    if not usable:
        sys.exit("Không còn cách gọi nào dùng được.")

    resize = parse_size(args.resize) if args.resize else None
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    suffix = "".join([f"-{args.resize}" if args.resize else "", "-en" if args.lang == "en" else ""])
    out_dir = RESULTS_DIR / f"{stamp}-{args.stage}{suffix}"
    (out_dir / "raw").mkdir(parents=True)
    (out_dir / "run.json").write_text(json.dumps({
        "stage": args.stage, "started": stamp, "resize": args.resize, "lang": args.lang,
        "effort": args.effort, "runs": args.runs, "combos": usable,
        "items": [i.item_id for i in items],
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    images = {}
    total = len(items) * len(usable) * args.runs
    n = 0
    with (out_dir / "calls.jsonl").open("w", encoding="utf-8") as log:
        for it in items:
            if it.image_path not in images:
                images[it.image_path] = prepare_image(it.image_path, resize)
            data_url, sent_size, orig_size = images[it.image_path]
            question = it.question_en if args.lang == "en" else it.question_vi
            for model, method in usable:
                model_id = config.MODELS[model]
                for run in range(1, args.runs + 1):
                    n += 1
                    try:
                        if method == "m1":
                            res = api.computer_use_point(model_id, data_url, question, args.effort)
                        else:
                            res = api.vision_point(model_id, data_url, question)
                    except (ApiError, httpx.HTTPError) as e:
                        res = CallResult(error=str(e))
                    scores = score_point(res.point, sent_size, orig_size, it.boxes, config.NEAR_PX)
                    raw_file = f"raw/{n:03d}.json"
                    (out_dir / raw_file).write_text(json.dumps(res.raw, ensure_ascii=False, indent=2),
                                                    encoding="utf-8")
                    rec = {
                        "stage": it.stage, "item_id": it.item_id, "size_class": it.size_class,
                        "question": question, "lang": args.lang,
                        "model": model, "model_id": model_id, "method": method, "run": run,
                        "sent_size": sent_size, "orig_size": orig_size, "resize": args.resize,
                        "raw_point": res.point, "action_type": res.action_type, "found": res.found,
                        "text": res.text[:500], "safety_checks": res.safety_checks,
                        "latency_s": round(res.latency_s, 3), "usage": res.usage, "hops": res.hops,
                        "error": res.error, "scores": scores, "raw_file": raw_file,
                    }
                    log.write(json.dumps(rec, ensure_ascii=False) + "\n")
                    log.flush()
                    status = "lỗi" if res.error else (
                        f"pixel={scores['pixel']['result']} 0-1000={scores['norm1000']['result']}")
                    print(f"[{n}/{total}] {it.item_id} {model}/{method} lần {run}: {status} "
                          f"({res.latency_s:.1f}s, {res.action_type or '—'})")
    api.close()
    print(f"Đã ghi: {write_summary(out_dir)}")


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(prog="python -m grounding_test.run")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("check", help="kiểm tra key và quyền dùng model (không tốn tiền)")
    for name in ("plan", "run"):
        p = sub.add_parser(name)
        p.add_argument("--stage", choices=["calibration", "cases"], required=True)
        p.add_argument("--models", help="ví dụ: spark,wonder")
        p.add_argument("--methods", help="m1 (computer use), m2 (image understanding)")
        p.add_argument("--runs", type=int, default=2)
        p.add_argument("--resize", help="ví dụ: 1366x768")
        p.add_argument("--lang", choices=["vi", "en"], default="vi")
        p.add_argument("--only", help="danh sách mục, ví dụ: case_01,case_06 hoặc cal_1920x1080")
        p.add_argument("--effort", choices=["minimal", "low", "medium", "high"],
                       help="reasoning.effort cho M1; bỏ trống = mặc định của model")
        if name == "run":
            p.add_argument("--yes", action="store_true", help="xác nhận gọi API có tính phí")
    args = parser.parse_args(argv)
    {"check": cmd_check, "plan": cmd_plan, "run": cmd_run}[args.cmd](args)


if __name__ == "__main__":
    main()
