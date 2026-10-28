from grounding_test.report import call_cost, pick_convention, summarize
from grounding_test.scoring import score_point

BOX = (100, 100, 200, 140)


def _rec(item_id, run, point, size="vừa", stage="cases", latency=2.0, error=None):
    return {
        "stage": stage, "item_id": item_id, "size_class": size, "question": "?", "lang": "vi",
        "model": "spark", "model_id": "muse-spark-1.3", "method": "m1", "run": run,
        "sent_size": [2000, 2000], "orig_size": [2000, 2000], "resize": None,
        "raw_point": point, "action_type": "click", "found": None, "text": "",
        "safety_checks": [], "latency_s": latency, "usage": {"input": 2000, "output": 100, "cached": 0, "reasoning": 50},
        "hops": 1, "error": error, "scores": score_point(point, (2000, 2000), (2000, 2000), [BOX], 12),
        "raw_file": "raw/001.json",
    }


def test_pick_convention_prefers_more_hits():
    recs = [_rec("a", 1, (150, 120)), _rec("b", 1, (150, 120))]
    assert pick_convention(recs) == "pixel"


def test_cost_uses_price_table():
    assert round(call_cost(_rec("a", 1, (150, 120))), 6) == round((2000 * 1.25 + 100 * 4.25) / 1e6, 6)


def test_summary_renders_decision_for_cases():
    recs = [_rec(f"case_{i:02d}", run, (150, 120)) for i in range(1, 13) for run in (1, 2)]
    text = summarize(recs, {"stage": "cases", "started": "x", "lang": "vi"})
    assert "Đạt ngưỡng" in text
    assert "spark / M1" in text


def test_summary_handles_errors_and_missing_points():
    recs = [_rec("cal/A", 1, None, stage="calibration", error="HTTP 400: bad"), _rec("cal/B", 1, None, stage="calibration")]
    text = summarize(recs, None)
    assert "lỗi" in text
