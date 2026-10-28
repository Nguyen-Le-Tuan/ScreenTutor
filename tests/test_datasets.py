import json

from grounding_test.datasets import load_calibration, load_cases, prepare_image


def test_calibration_has_five_targets_per_image():
    items = load_calibration()
    assert len(items) == 10
    assert {i.item_id.split("/")[1] for i in items} == {"A", "B", "C", "D", "E"}
    # Targets B and E sit right of x=1000 on the wide image: they separate pixels from 0-1000.
    wide = {i.item_id: i for i in items if i.item_id.startswith("cal_1920x1080")}
    assert wide["cal_1920x1080/B"].boxes[0][0] > 1000
    assert wide["cal_1920x1080/E"].boxes[0][0] > 1000


def test_cases_template_reports_what_is_missing(tmp_path):
    cases = {"cases": [
        {"id": "case_x", "file": "missing.png", "question_vi": "?", "boxes": [], "size_class": None},
        {"id": "case_y", "file": "y.png", "question_vi": "?", "boxes": [[5, 5, 1, 1]], "size_class": "nhỏ"},
    ]}
    (tmp_path / "y.png").write_bytes(b"")
    f = tmp_path / "cases.json"
    f.write_text(json.dumps(cases), encoding="utf-8")
    items, problems = load_cases(f)
    assert items == []
    assert any("case_x" in p and "chưa có ảnh" in p for p in problems)
    assert any("case_y" in p and "khung không hợp lệ" in p for p in problems)


def test_prepare_image_resizes_and_reports_both_sizes():
    item = load_calibration()[0]
    url, sent, orig = prepare_image(item.image_path, (683, 384))
    assert url.startswith("data:image/png;base64,")
    assert sent == (683, 384)
    assert orig in ((1366, 768), (1920, 1080))
