import json

from PIL import Image

from grounding_test.meta_api import vision_prompt
from screentutor import screen
from screentutor.tutor import (EFFORT, MODEL, SAY_RULES, EarlyAnswer, Reply, build_body, build_follow_up_body,
                               build_follow_up_prompt, build_prompt, parse_reply, spoken, task_rules)
from tutor_eval.run import say_problems

STATE = "- Cửa sổ đang ở trước mặt: Zalo (Zalo.exe), tiêu đề \"Zalo\", đang phóng to toàn màn hình."


def _resp(answer: dict | str) -> dict:
    content = answer if isinstance(answer, str) else json.dumps(answer, ensure_ascii=False)
    return {"choices": [{"message": {"content": content}}],
            "usage": {"prompt_tokens": 3000, "completion_tokens": 400,
                      "completion_tokens_details": {"reasoning_tokens": 300}}}


def test_pointing_part_is_the_measured_prompt():
    for state in (None, STATE):
        assert build_prompt("Mẹ bấm vào đâu?", state, task=False) == vision_prompt("Mẹ bấm vào đâu?", state) + SAY_RULES
        v2 = build_prompt("Mẹ bấm vào đâu?", state)  # B1: the measured text and the speech rules come first, unchanged
        assert v2 == vision_prompt("Mẹ bấm vào đâu?", state) + SAY_RULES + task_rules()


def test_body_uses_spark_and_asks_for_say():
    body = build_body("Mẹ bấm vào đâu?", "data:image/png;base64,AAAA", STATE)
    assert body["model"] == MODEL == "muse-spark-1.3"
    assert body["reasoning_effort"] == EFFORT == "minimal"
    schema = body["response_format"]["json_schema"]["schema"]
    assert set(schema["required"]) == {"found", "X", "Y", "element", "say", "Caution", "mode", "Target", "Box",
                                       "task_plan", "task_notes"}
    assert schema["properties"]["Box"]["required"] == ["x1", "y1", "x2", "y2"]
    assert sorted(schema["required"]).index("Y") < sorted(schema["required"]).index("say")      # the API sorts the keys
    assert sorted(schema["required"]).index("say") < sorted(schema["required"]).index("task_plan")
    assert body["messages"][0]["content"][1]["image_url"]["url"].startswith("data:image/png")
    v1 = build_body("Mẹ bấm vào đâu?", "data:", STATE, task=False)["response_format"]["json_schema"]["schema"]
    assert set(v1["required"]) == {"found", "x", "y", "element", "say", "caution"}


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


def test_follow_up_keeps_the_pointing_text_and_adds_the_last_step():
    last = "Bạn bấm vào chữ File ở góc trên bên trái."
    text = build_follow_up_prompt("Mẹ muốn xuất ra PDF", last, STATE, screen_changed=False, task=False)
    assert text.startswith(vision_prompt("Mẹ muốn xuất ra PDF", STATE))
    assert last in text and "màn hình không thay đổi" in text and text.endswith(SAY_RULES)
    v2 = build_follow_up_prompt("Mẹ muốn xuất ra PDF", last, STATE, screen_changed=False)
    assert v2.startswith(text) and "part:" in v2 and "mode:" not in v2  # no re-deciding the mode
    assert "Chương trình đo được" not in build_follow_up_prompt("x", last)  # no measurement claimed when unknown


def test_a_later_turn_says_what_she_did_and_the_click_sentence_stays_as_measured():
    click = "Sau đó người dùng đã bấm chuột; ảnh trên được chụp khi màn hình đã đứng yên."
    measured = click + " Chương trình đo được: sau cú bấm, màn hình đã thay đổi.\n"
    assert measured in build_follow_up_prompt("x", "Bạn bấm File.", screen_changed=True, task=False)
    assert measured in build_follow_up_prompt("x", "Bạn bấm File.", screen_changed=True)
    read = build_follow_up_prompt("x", "Bạn đọc đoạn này.", screen_changed=False, acted="read")
    assert click not in read and "báo đã đọc xong" in read and "màn hình không thay đổi" in read
    moved = build_follow_up_prompt("x", "Bạn kéo xuống nhé.", screen_changed=True, acted="moved")
    assert "bấm chuột" not in moved.split("Lượt trước")[1].split("step_done")[0]
    assert "cú bấm nào" in moved and "Chương trình đo được" not in moved
    body = build_follow_up_body("x", "y", "data:image/png;base64,AAAA", screen_changed=True, acted="moved")
    assert "cú bấm nào" in body["messages"][0]["content"][0]["text"]


def test_follow_up_body_asks_for_step_and_goal():
    body = build_follow_up_body("Mẹ muốn xuất ra PDF", "Bạn bấm File.", "data:image/png;base64,AAAA")
    schema = body["response_format"]["json_schema"]["schema"]
    assert {"Step_done", "Goal_done", "say", "X", "Y", "task_part", "Target", "Box", "task_plan",
            "task_notes"} <= set(schema["required"])
    assert "mode" not in schema["properties"]
    assert body["reasoning_effort"] == "minimal"


def test_parse_reply_reads_step_and_goal_only_when_present():
    r = parse_reply(_resp({"step_done": True, "goal_done": False, "found": True, "x": 10, "y": 20,
                           "element": "Export", "say": "Bạn bấm vào chữ Export nhé."}))
    assert (r.step_done, r.goal_done, r.point) == (True, False, (10.0, 20.0))
    first = parse_reply(_resp({"found": False, "x": 0, "y": 0, "element": "", "say": "Bạn mở Zalo trước nhé."}))
    assert first.step_done is None and first.goal_done is None


def test_point_px_maps_grid_to_screenshot_pixels():
    assert Reply(point=(500, 500)).point_px((1920, 1080)) == (960, 540)
    assert Reply(point=(1000, 1000)).point_px((1920, 1080)) == (1919, 1079)
    assert Reply().point_px((1920, 1080)) is None


def test_say_checks():
    assert say_problems("Bạn bấm vào chữ File ở góc trên bên trái nhé. Chỗ này mở các lệnh lưu và xuất file.") == []
    assert say_problems("Bạn mở file Giáo án mẫu Âm nhạc 8 (1).docx trong Downloads nhé.") == []
    assert say_problems("Bạn bấm vào hình con sư tử màu cam ở thanh dưới cùng nhé.") == []
    assert say_problems("") == ["trống"]
    assert "3 câu" in say_problems("Bạn bấm đây. Rồi bấm kia. Xong rồi.")
    assert "không gọi bạn" in say_problems("Bấm vào nút OK.")
    assert "có ký hiệu" in say_problems("Bạn bấm **File** nhé.")
    assert "nhắc toạ độ" in say_problems("Bạn bấm vào chỗ 512, 380 nhé.")
    assert any(p.endswith("âm tiết") for p in say_problems("Bạn " + "bấm " * 45))
    assert say_problems("Ban bam vao chu File nhe.") == ["không dấu"]
    for family in ("Mẹ bấm vào chữ File nhé, bạn nhé.", "Bạn bấm vào chữ Cô Mẫu nha con.",
                   "Con chỉ bạn nè. Bạn bấm vào chữ Downloads.", "Bạn bấm nút OK cho con nhé."):
        assert "gọi mẹ hoặc xưng con" in say_problems(family), family
    assert "nhờ vả" in say_problems("Bạn bấm vào nút OK giúp mình nhé.")
    assert "nhờ vả" in say_problems("Mình nhờ bạn bấm vào nút OK nhé.")
    assert "hứa làm hộ" in say_problems("Bạn chờ chút, mình sẽ mở bảng tính cho bạn xem.")
    assert "nói về mình" in say_problems("Bạn bấm vào khung màu xanh nhé, mình nói kỹ vậy cho dễ tìm.")


def test_mark_draws_only_when_there_is_a_point():
    img = Image.new("RGB", (200, 100), "white")
    marked = screen.mark(img, (100, 50))
    assert marked.size == img.size and marked.getpixel((100 + 22, 50)) != (255, 255, 255)
    assert screen.mark(img, None).tobytes() == img.tobytes()
    assert img.getpixel((122, 50)) == (255, 255, 255)  # original untouched


def test_answer_without_diacritics_is_asked_again_once():
    from screentutor.tutor import Tutor

    answers = [_resp({"found": True, "x": 1, "y": 1, "element": "OK", "say": "Ban bam vao nut OK nhe."}),
               _resp({"found": True, "x": 1, "y": 1, "element": "OK", "say": "Bạn bấm vào nút OK nhé."})]
    t = Tutor("sk-test")
    t._post = lambda path, body: (answers.pop(0), 2.0)
    r = t.ask("Tắt bảng lỗi", "data:")
    assert r.say == "Bạn bấm vào nút OK nhé." and r.latency_s == 4.0 and answers == []
    t._post = lambda path, body: (_resp({"found": False, "x": 0, "y": 0, "element": "", "say": "Ban oi"}), 1.0)
    assert t.ask("x", "data:").say == "Ban oi"  # asked twice, then given up: the session still goes on
    t.close()


def _v2(**kw):
    base = {"found": True, "x": 500, "y": 400, "element": "tin nhắn", "say": "Bạn đọc tin nhắn trong khung sáng.",
            "caution": False, "mode": "guide", "target": "click", "box": {"x1": 0, "y1": 0, "x2": 0, "y2": 0},
            "plan": [], "notes": ""}
    base.update(kw)
    return parse_reply(_resp(base))


def test_first_turn_reads_mode_plan_and_notes():
    r = _v2(plan=["  Đọc hướng dẫn ", "", "Đăng nhập trang học"], notes=" Bước 1 mở link. ")
    assert (r.mode, r.plan, r.notes, r.target) == ("guide", ["Đọc hướng dẫn", "Đăng nhập trang học"], "Bước 1 mở link.",
                                                   "click")
    long = _v2(plan=[f"phần {i} " + "chữ " * 20 for i in range(9)])
    assert len(long.plan) == 6 and all(len(p.split()) <= 12 for p in long.plan)
    assert _v2(mode="hmm", plan=[]).mode == "answer" and _v2(mode="hmm", plan=["a", "b"]).mode == "guide"


def test_read_target_comes_with_a_box_in_order_and_on_the_grid():
    r = _v2(target="read", box={"x1": 700, "y1": 900, "x2": 300, "y2": -50})
    assert r.target == "read" and r.box == (300.0, 0.0, 700.0, 900.0)
    assert r.box_px((1920, 1080)) == (576, 0, 1344, 972)
    centre = _v2(target="read", found=False, x=0, y=0, box={"x1": 100, "y1": 100, "x2": 300, "y2": 500})
    assert centre.found and centre.point == (200.0, 300.0)  # no point given: the middle of the box
    flat = _v2(target="read")  # four zeros: no box, so a plain ring at the point
    assert flat.target == "click" and flat.box is None and flat.point == (500.0, 400.0)


def test_other_targets_drop_the_box_and_none_drops_the_point():
    s = _v2(target="scroll", box={"x1": 1, "y1": 1, "x2": 900, "y2": 900})
    assert s.target == "scroll" and s.box is None and s.point == (500.0, 400.0)
    n = _v2(target="none")
    assert n.target == "none" and n.point is None and not n.found
    odd = _v2(target="banana")
    assert odd.target == "click"
    lost = _v2(target="click", found=False)
    assert lost.target == "none" and lost.point is None


def test_later_turn_reads_the_part():
    r = _v2(step_done=True, goal_done=False, part=2)
    assert r.part == 2
    assert _v2(part=0).part == 0 and _v2(part=True).part is None


def test_v1_answers_still_parse_as_before():
    r = parse_reply(_resp({"found": True, "x": 10, "y": 20, "element": "File", "say": "Bạn bấm File.",
                           "caution": False}))
    assert (r.mode, r.plan, r.target, r.box, r.notes, r.part) == ("", [], "", None, "", None)
    assert r.point == (10.0, 20.0)


def test_follow_up_carries_the_plan_the_part_and_the_notes():
    text = build_follow_up_prompt("Học cái trong Zalo", "Bạn kéo xuống nhé.", plan=["Đọc hướng dẫn", "Đăng nhập"],
                                  part=5, notes="Bước 1 mở link.")
    assert "1. Đọc hướng dẫn; 2. Đăng nhập" in text and "thuộc phần 2" in text  # the part is kept within the plan
    assert "Bước 1 mở link." in text
    bare = build_follow_up_prompt("x", "y")
    assert "đã được chia" not in bare and "đã đọc được ở các lượt trước" not in bare


def test_pointer_line_only_when_given():
    assert "chuột của người dùng" not in build_prompt("Học cái này")
    text = build_prompt("Học cái này", pointer="dừng ở (412, 530) trên lưới 0-1000")
    assert "chuột của người dùng dừng ở (412, 530)" in text


def test_password_rule_is_always_there():
    assert "mật khẩu" in build_prompt("x") and "mật khẩu" in build_follow_up_prompt("x", "y")


# The answer arrives bit by bit (T12 R5, 02/11)

ANSWER = {"Box": {"x1": 0, "x2": 0, "y1": 0, "y2": 0}, "Caution": False, "Goal_done": False, "Step_done": True,
          "Target": "click", "X": 150, "Y": 250, "element": "File", "found": True, "say": "Bạn bấm \"File\" nhé.",
          "task_notes": "", "task_part": 1, "task_plan": ["Mở File", "Xuất PDF"]}


def _bits(answer=ANSWER, size=7):
    text = json.dumps(answer, ensure_ascii=False)
    return [text[i:i + size] for i in range(0, len(text), size)]


def test_capital_and_task_keys_read_as_the_plain_fields():
    r = parse_reply(_resp(ANSWER))
    assert (r.point, r.target, r.step_done, r.goal_done, r.part) == ((150.0, 250.0), "click", True, False, 1)
    assert r.plan == ["Mở File", "Xuất PDF"] and r.say == 'Bạn bấm "File" nhé.' and r.box is None


def test_the_place_and_the_sentence_are_known_before_the_answer_ends():
    marks, says, order = [], [], []
    early = EarlyAnswer(lambda r: (marks.append(r), order.append("mark")), lambda t: (says.append(t), order.append("say")))
    text, seen_at = "", {}
    for i, bit in enumerate(_bits()):
        text += bit
        early.feed(text)
        for name, got in (("mark", marks), ("say", says)):
            if got:
                seen_at.setdefault(name, i)
    assert order == ["mark", "say"] and len(marks) == len(says) == 1
    assert marks[0].point == (150.0, 250.0) and marks[0].target == "click" and marks[0].step_done is True
    assert says == ['Bạn bấm "File" nhé.']
    assert seen_at["mark"] < seen_at["say"] < len(_bits()) - 2     # the plan is still on its way


def test_a_box_comes_with_the_mark_and_a_half_number_is_not_read():
    marks = []
    early = EarlyAnswer(marks.append)
    early.feed('{"Box": {"x1": 100, "x2": 700, "y1": 200, "y2": 800}, "Caution": false, "Target": "read", "X": 400, "Y": 50')
    assert marks == []                  # the 50 may be 500
    early.feed('{"Box": {"x1": 100, "x2": 700, "y1": 200, "y2": 800}, "Caution": false, "Target": "read", "X": 400, "Y": 500,')
    assert marks[0].box == (100.0, 200.0, 700.0, 800.0) and marks[0].target == "read"


def test_the_tutor_streams_when_asked_and_gives_the_same_reply():
    import httpx

    from screentutor.tutor import Tutor

    def handler(request):
        body = json.loads(request.content)
        assert body["stream"] is True
        lines = [f"data: {json.dumps({'choices': [{'delta': {'content': b}}]})}" for b in _bits()]
        lines += ['data: {"choices": [], "usage": {"prompt_tokens": 9, "completion_tokens": 5}}', "data: [DONE]"]
        return httpx.Response(200, text="\n\n".join(lines))

    tutor = Tutor("k")
    tutor._http = httpx.Client(base_url="https://x", transport=httpx.MockTransport(handler))
    marks, says = [], []
    reply = tutor.ask("Xuất PDF", "data:", on_mark=marks.append, on_say=says.append)
    assert reply.say == 'Bạn bấm "File" nhé.' and reply.point == (150.0, 250.0) and reply.usage["input"] == 9
    assert len(marks) == len(says) == 1 and reply.latency_s >= 0


def test_a_dropped_line_is_tried_once_more():
    import httpx

    from screentutor.tutor import Tutor

    calls = []

    def handler(request):
        calls.append(1)
        if len(calls) == 1:
            raise httpx.ReadError("the line dropped")
        return httpx.Response(200, text=f"data: {json.dumps({'choices': [{'delta': {'content': json.dumps(ANSWER)}}]})}")

    tutor = Tutor("k")
    tutor._http = httpx.Client(base_url="https://x", transport=httpx.MockTransport(handler))
    reply = tutor.ask("x", "data:", on_say=lambda t: None)
    assert reply.error is None and len(calls) == 2 and reply.point == (150.0, 250.0)


def test_the_state_rule_and_the_rule_against_talking_about_itself_are_in_every_turn():
    assert "đã bấm rồi mà không thấy" in build_prompt("x") and "để mình hướng dẫn" in build_prompt("x")
    assert "để mình hướng dẫn" in build_follow_up_prompt("x", "y")
    assert "đã bấm rồi mà không thấy" not in build_prompt("x", task=False)  # the prompt T4 measured stays as it was


def test_a_cut_message_is_scrolled_first_and_file_names_are_spoken_plainly():
    text = build_prompt("x")
    assert "phải kéo xuống đọc hết trước khi read hay click" in text and "bỏ đuôi file" in text


def test_a_sentence_about_the_tutor_never_reaches_the_voice():
    say = "Bạn bấm vào thẻ tên Cô Mẫu ở thanh dưới cùng. Mình thấy thẻ đó nằm cạnh thẻ Tổng hợp."
    assert spoken(say) == "Bạn bấm vào thẻ tên Cô Mẫu ở thanh dưới cùng."
    assert spoken("Để mình hướng dẫn bước tiếp theo. Bạn bấm File.") == "Bạn bấm File."
    assert spoken("Mình thấy nút OK.") == "Mình thấy nút OK."        # never leaves her with nothing to hear
    assert spoken("Bạn bấm vào mình tượng.") == "Bạn bấm vào mình tượng."


def test_no_count_of_parts_and_no_plan_before_the_message_has_been_read():
    r = parse_reply(_resp({**ANSWER, "Target": "scroll", "say": "Việc này có 2 phần. Bạn kéo xuống nhé."}))
    assert r.say == "Bạn kéo xuống nhé." and r.plan == []
    r = parse_reply(_resp({**ANSWER, "say": "Việc này có 2 phần. Bạn bấm File."}))
    assert r.say == "Việc này có 2 phần. Bạn bấm File." and r.plan == ["Mở File", "Xuất PDF"]
    says = []
    early = EarlyAnswer(lambda r: None, says.append)
    early.feed(json.dumps({**ANSWER, "Target": "scroll", "say": "Việc này có ba phần. Bạn kéo xuống nhé."}, ensure_ascii=False))
    assert says == ["Bạn kéo xuống nhé."]


def test_a_failed_stream_is_an_error_not_a_crash():
    import httpx

    from screentutor.tutor import Tutor

    tutor = Tutor("k")
    tutor._http = httpx.Client(base_url="https://x", transport=httpx.MockTransport(lambda r: httpx.Response(400, text="bad")))
    assert "HTTP 400" in tutor.ask("x", "data:", on_say=print).error
