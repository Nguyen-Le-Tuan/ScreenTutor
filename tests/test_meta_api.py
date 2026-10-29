from grounding_test.meta_api import vision_prompt

# Prompt used for stages 0 and 1 (before state support), kept to prove it did not change.
STAGE1_PROMPT = (
    "Đây là ảnh chụp toàn màn hình một máy tính Windows.\n"
    "Người dùng hỏi: \"Bấm vào đâu?\"\n"
    "Hãy xác định phần tử giao diện cần bấm để làm đúng điều người dùng hỏi, rồi trả về "
    "toạ độ tâm của phần tử đó trên thang chuẩn hoá 0-1000: x=0 là mép trái, x=1000 là mép phải, "
    "y=0 là mép trên, y=1000 là mép dưới. Nếu không thấy phần tử phù hợp, đặt found=false."
)


def test_prompt_without_state_is_unchanged():
    assert vision_prompt("Bấm vào đâu?") == STAGE1_PROMPT


def test_state_goes_between_screen_line_and_question():
    text = vision_prompt("Bấm vào đâu?", "- Cửa sổ đang ở trước mặt: Zalo")
    first, rest = text.split("\n", 1)
    assert first == "Đây là ảnh chụp toàn màn hình một máy tính Windows."
    assert rest.index("- Cửa sổ đang ở trước mặt: Zalo") < rest.index("Người dùng hỏi:")
