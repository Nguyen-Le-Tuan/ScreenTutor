"""Load VieNeu-TTS v3 Turbo (ONNX, CPU) from real files under tts_eval/models/.

VieNeu fetches its ONNX graphs into the Hugging Face cache. On Linux that cache
stores files behind symlinks, and onnxruntime >= 1.31 refuses external weight
files that resolve outside the model folder ("External data path escapes model
directory"). Downloading into a plain folder avoids that on every OS.
"""

from __future__ import annotations

from pathlib import Path

MODELS = Path(__file__).parent / "models"


def _fetch_local(repo: str, files: list[str], subfolder: str | None) -> Path:
    """Same contract as OnnxV3LiteEngine._fetch, but into MODELS/<repo>/ without symlinks."""
    from huggingface_hub import hf_hub_download

    root = MODELS / repo.split("/")[-1]
    for fn in files:
        try:
            hf_hub_download(repo, fn, repo_type="model", subfolder=subfolder or None, local_dir=root)
        except Exception:
            if fn.endswith(".json"):
                continue  # optional metadata, as in VieNeu's own fetch
            raise
    return root / subfolder if subfolder else root


def load(precision: str = "fp32", threads: int = 0):
    """precision: "fp32" (default quality) or "int8" (needs AVX-VNNI)."""
    from vieneu import Vieneu
    from vieneu._v3_turbo_engine.onnx_runtime_lite import OnnxV3LiteEngine

    OnnxV3LiteEngine._fetch = staticmethod(_fetch_local)
    return Vieneu(backend="onnx", precision=precision, threads=threads)
