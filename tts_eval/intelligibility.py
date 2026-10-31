"""Is int8 VieNeu as intelligible as fp32? Render, then let Muse Voice Transcribe listen.

  tts_eval/.venv/bin/python tts_eval/intelligibility.py render     # wavs + refs.tsv in out/intel/
  .venv/bin/python -m stt_eval.transcribe --config vi+kw+me --label intel \
      --refs tts_eval/out/intel/refs.tsv tts_eval/out/intel/*.wav
  .venv/bin/python tts_eval/intelligibility.py score stt_eval/results/<stamp>-intel

Rule, fixed before the run (30/10/2026): voice Hải Đăng, the 6 bench sentences, 3 renders
each per precision. Choose int8 if its mean syllable error rate is at most 3 percentage
points above fp32's; otherwise list the alternatives for the founder. Speed is already
measured: int8 is about 2x faster on this CPU (RTF 0.48 vs 0.90).
"""

from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path

HERE = Path(__file__).parent
OUT = HERE / "out" / "intel"
VOICE = "Hải Đăng"
RENDERS = 3
MARGIN = 0.03


def render() -> None:
    import vieneu_local
    from bench import SENTENCES

    OUT.mkdir(parents=True, exist_ok=True)
    refs = []
    for precision in ("fp32", "int8"):
        tts = vieneu_local.load(precision)
        for sid, text in SENTENCES.items():
            for k in range(1, RENDERS + 1):
                name = f"{precision}_{sid}_{k}.wav"
                tts.save(tts.infer(text, voice=VOICE), OUT / name)
                refs.append(f"{name}\t{text}")
        del tts
    (OUT / "refs.tsv").write_text("\n".join(refs) + "\n", encoding="utf-8")
    print(f"Đã tạo {len(refs)} file trong {OUT}")


def score(results_dir: Path) -> None:
    sys.path.insert(0, str(HERE.parent))
    from stt_eval.score import score_one

    rows = json.loads((results_dir / "transcripts.json").read_text(encoding="utf-8"))
    config = next(k for k, v in rows[0].items() if isinstance(v, dict))
    by = {"fp32": [], "int8": []}
    for r in rows:
        s = score_one(r["ref"], r[config].get("transcript", ""))
        by[r["file"].split("_")[0]].append((r["file"], s, r[config].get("transcript", "")))
    means = {p: statistics.mean(s["wer"] for _, s, _ in v) for p, v in by.items()}
    for p, v in by.items():
        kept = sum(s["verdict"] == "còn" for _, s, _ in v)
        print(f"{p}: WER trung bình {means[p]:.1%}, còn ý {kept}/{len(v)}")
    for p, v in by.items():
        for f, s, t in v:
            if s["wer"] > 0.15:
                print(f"  {f} WER {s['wer']:.0%}: {t}")
    ok = means["int8"] <= means["fp32"] + MARGIN
    print(f"Luật: int8 <= fp32 + {MARGIN:.0%} -> {'CHỐT int8' if ok else 'KHÔNG đạt, cần xem phương án khác'}")


if __name__ == "__main__":
    if sys.argv[1:2] == ["render"]:
        render()
    elif sys.argv[1:2] == ["score"] and len(sys.argv) == 3:
        score(Path(sys.argv[2]))
    else:
        raise SystemExit(__doc__)
