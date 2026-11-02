from tutor_eval.segment import Found, build_body, build_prompt, choose, parse_boxes

SIZE = (1920, 1080)


def test_prompt_has_one_box_per_reach_and_is_clipped_to_the_image():
    prompt = build_prompt((10, 1075), SIZE)
    assert prompt.startswith("<0f>1<|box;x1=0;y1=1059;x2=40;y2=1079;w=1920;h=1080|>,2<|box;")
    assert prompt.count("<|box;") == 4
    assert "4<|box;x1=0;y1=1015;x2=330;y2=1079;" in prompt


def test_body_sends_the_tokens_and_the_image():
    body = build_body((100, 100), SIZE, "data:image/png;base64,AAAA")
    content = body["input"][0]["content"]
    assert body["model"] == "sam-3.1"
    assert body["metadata"]["include_confidence"] == "true"
    assert content[0]["text"].startswith("<0f>1<|box;")
    assert content[1] == {"type": "input_image", "image_url": "data:image/png;base64,AAAA"}


def test_parse_reads_every_box_and_skips_the_mask():
    text = ("<0f>1<|box;x1=262;y1=175;x2=298;y2=196;w=1920;h=1080;c=0.35|><|mask;x=0;y=0;c=0.35;data=22,37,~!!!|>,"
            "2<|box;x1=153;y1=151;x2=416;y2=216;w=1920;h=1080;c=0.9|><|mask;x=0;y=0;data=1,1,!!|>")
    assert parse_boxes(text) == [Found(262, 175, 298, 196, 0.35), Found(153, 151, 416, 216, 0.9)]


def test_parse_of_an_empty_answer():
    assert parse_boxes("") == []


def test_choose_takes_the_surest_box():
    found = [Found(260, 173, 312, 196, 0.78), Found(153, 150, 415, 216, 0.95)]
    assert choose(found, (284, 183), SIZE) == found[1]


def test_choose_refuses_low_confidence():
    assert choose([Found(10, 10, 50, 50, 0.59)], (30, 30), SIZE) is None


def test_choose_refuses_a_box_away_from_the_point():
    assert choose([Found(10, 10, 50, 50, 0.9)], (100, 30), SIZE) is None


def test_choose_refuses_a_whole_panel():
    assert choose([Found(0, 0, 900, 500, 0.99)], (100, 100), SIZE) is None


def test_choose_prefers_the_smaller_box_on_a_tie():
    small, big = Found(10, 10, 50, 50, 0.9), Found(0, 0, 100, 100, 0.9)
    assert choose([big, small], (30, 30), SIZE) == small


def test_choose_with_nothing():
    assert choose([], (30, 30), SIZE) is None
