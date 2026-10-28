"""Load test items (calibration images and real cases) and prepare images for sending."""

from __future__ import annotations

import base64
import io
import json
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image

HERE = Path(__file__).parent
CALIBRATION_DIR = HERE / "calibration"
CASES_DIR = HERE / "cases"
CASES_FILE = CASES_DIR / "cases.json"

SIZE_CLASSES = ("nhỏ", "vừa", "lớn")


@dataclass
class Item:
    stage: str           # "calibration" or "cases"
    item_id: str         # e.g. "cal_1920x1080/B" or "case_01"
    image_path: Path
    question_vi: str
    boxes: list[tuple[int, int, int, int]]
    size_class: str
    question_en: str | None = None
    meta: dict = field(default_factory=dict)


def load_calibration(directory: Path = CALIBRATION_DIR) -> list[Item]:
    items = []
    for truth_file in sorted(directory.glob("*.truth.json")):
        truth = json.loads(truth_file.read_text(encoding="utf-8"))
        image = directory / truth["image"]
        stem = truth["image"].rsplit(".", 1)[0]
        for t in truth["targets"]:
            items.append(Item(
                stage="calibration",
                item_id=f"{stem}/{t['id']}",
                image_path=image,
                question_vi=t["question_vi"],
                boxes=[tuple(t["box_px"])],
                size_class=t["size_class"],
            ))
    return items


def load_cases(cases_file: Path = CASES_FILE) -> tuple[list[Item], list[str]]:
    """Return (ready items, problems). Items with missing image or labels are reported, not loaded."""
    data = json.loads(cases_file.read_text(encoding="utf-8"))
    items, problems = [], []
    for c in data["cases"]:
        cid = c["id"]
        image = cases_file.parent / c["file"]
        missing = []
        if not image.exists():
            missing.append(f"chưa có ảnh {c['file']}")
        if not c.get("boxes"):
            missing.append("chưa có khung đúng (boxes)")
        if c.get("size_class") not in SIZE_CLASSES:
            missing.append("chưa ghi cỡ (size_class: nhỏ/vừa/lớn)")
        if missing:
            problems.append(f"{cid}: " + "; ".join(missing))
            continue
        boxes = [tuple(b) for b in c["boxes"]]
        for b in boxes:
            if len(b) != 4 or not (b[0] < b[2] and b[1] < b[3]):
                problems.append(f"{cid}: khung không hợp lệ {list(b)} (cần x1<x2, y1<y2)")
                break
        else:
            items.append(Item(
                stage="cases",
                item_id=cid,
                image_path=image,
                question_vi=c["question_vi"],
                question_en=c.get("question_en") or None,
                boxes=boxes,
                size_class=c["size_class"],
                meta={"app": c.get("app"), "target": c.get("target")},
            ))
    return items, problems


def parse_size(text: str) -> tuple[int, int]:
    w, h = text.lower().split("x")
    return int(w), int(h)


def prepare_image(path: Path, resize: tuple[int, int] | None = None) -> tuple[str, tuple[int, int], tuple[int, int]]:
    """Return (PNG data URL, sent size, original size). Resizing keeps the target size exactly."""
    with Image.open(path) as img:
        img = img.convert("RGB")
        orig_size = img.size
        if resize and resize != orig_size:
            img = img.resize(resize, Image.Resampling.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        sent_size = img.size
    data_url = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")
    return data_url, sent_size, orig_size
