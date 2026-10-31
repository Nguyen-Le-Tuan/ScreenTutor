import json

from PIL import Image

from grounding_test.meta_api import vision_prompt
from screentutor import screen
from screentutor.tutor import EFFORT, MODEL, SAY_RULES, Reply, build_body, build_prompt, parse_reply
from tutor_eval.run import say_problems

STATE = "- Cửa sổ đang ở trước mặt: Zalo (Zalo.exe), tiêu đề \"Zalo\", đang phóng to toàn màn hình."


def _resp(answer: dict | str) -> dict:
    content = answer if isinstance(answer, str) else json.dumps(answer, ensure_ascii=False)
    return {"choices": [{"message": {"content": content}}],
            "usage": {"prompt_tokens": 3000, "completion_tokens": 400,
                      "completion_tokens_details": {"reasoning_tokens": 300}}}


def test_pointing_part_is_the_measured_prompt():
    for state in (None, STATE):
        text = build_prompt("Mẹ bấm vào đâu?", state)
        assert text == vision_prompt("Mẹ bấm vào đâu?", state) + SAY_RULES


def test_body_uses_spark_low_effort_and_asks_for_say():
    body = build_body("Mẹ bấm vào đâu?", "data:image/png;base64,AAAA", STATE)
    assert body["model"] == MODEL == "muse-spark-1.3"
    assert body["reasoning_effort"] == EFFORT == "low"
    schema = body["response_format"]["json_schema"]["schema"]
    assert set(schema["required"]) == {"found", "x", "y", "element", "say"}
    assert body["messages"][0]["content"][1]["image_url"]["url"].startswith("data:image/png")


def test_parse_reply_reads_point_say_and_usage():
    r = parse_reply(_resp({"found": True, "x": 512.5, "y": 1200, "element": "File",
                           "say": "Mẹ bấm vào chữ File ở góc trên bên trái nhé."}))
    assert r.error is None and r.found
    assert r.point == (512.5, 1000.0)  # clamped to the grid
    assert r.say.startswith("Mẹ bấm") and r.element == "File"
    assert r.usage["input"] == 3000 and r.usage["reasoning"] == 300


def test_parse_reply_without_target_has_no_point():
    r = parse_reply(_resp({"found": False, "x": 0, "y": 0, "element": "", "say": "Mẹ mở Zalo trước nhé."}))
    assert r.point is None and r.say == "Mẹ mở Zalo trước nhé."


def test_parse_reply_bad_json_is_an_error():
    assert parse_reply(_resp("not json")).error == "answer is not valid JSON"


def test_point_px_maps_grid_to_screenshot_pixels():
    assert Reply(point=(500, 500)).point_px((1920, 1080)) == (960, 540)
    assert Reply(point=(1000, 1000)).point_px((1920, 1080)) == (1919, 1079)
    assert Reply().point_px((1920, 1080)) is None


def test_say_checks():
    assert say_problems("Mẹ bấm vào chữ File ở góc trên bên trái nhé. Chỗ này mở các lệnh lưu và xuất file.") == []
    assert say_problems("Mẹ mở file Giáo án mẫu Âm nhạc 8 (1).docx trong Downloads nhé.") == []
    assert say_problems("") == ["trống"]
    assert "3 câu" in say_problems("Mẹ bấm đây. Rồi bấm kia. Xong rồi.")
    assert "không gọi mẹ" in say_problems("Bấm vào nút OK.")
    assert "có ký hiệu" in say_problems("Mẹ bấm **File** nhé.")
    assert "nhắc toạ độ" in say_problems("Mẹ bấm vào chỗ 512, 380 nhé.")
    assert any(p.endswith("âm tiết") for p in say_problems("Mẹ " + "bấm " * 45))
    assert say_problems("Me bam vao chu File nhe.") == ["không dấu"]
    assert "gọi mẹ là con" in say_problems("Mẹ bấm vào chữ Cô Mẫu nha con.")
    assert "giúp con" in say_problems("Mẹ bấm vào nút OK giúp con nhé.")
    assert "hứa làm hộ" in say_problems("Mẹ chờ chút, con sẽ mở bảng tính cho mẹ xem.")
    assert say_problems("Mẹ bấm vào hình con sư tử màu cam ở thanh dưới cùng nhé.") == []


def test_mark_draws_only_when_there_is_a_point():
    img = Image.new("RGB", (200, 100), "white")
    marked = screen.mark(img, (100, 50))
    assert marked.size == img.size and marked.getpixel((100 + 22, 50)) != (255, 255, 255)
    assert screen.mark(img, None).tobytes() == img.tobytes()
    assert img.getpixel((122, 50)) == (255, 255, 255)  # original untouched
