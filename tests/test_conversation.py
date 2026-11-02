from screentutor import conversation as conv


def measure(s: str) -> float:
    return 10.0 * len(s)  # every letter 10 px wide


def test_fit_start_keeps_the_beginning_and_never_overflows():
    text = "Bấm nút Create PDF ở giữa màn hình"
    assert conv.fit_start(text, 1000, measure) == text
    for width in (60, 95, 150, 200):
        cut = conv.fit_start(text, width, measure)
        assert measure(cut) <= width and cut.endswith(conv.ELLIPSIS)
        assert text.startswith(cut[:-1].rstrip())
    assert conv.fit_start(text, 5, measure) == ""


def test_fit_start_ends_on_a_whole_word_when_it_costs_little():
    assert conv.fit_start("Bấm chữ File ở góc trên", 130, measure) == "Bấm chữ File…"


def test_fit_end_keeps_her_latest_words():
    text = "Mẹ muốn xuất giáo án ra PDF rồi gửi cho tiệm in"
    cut = conv.fit_end(text, 200, measure)
    assert cut.startswith(conv.ELLIPSIS) and text.endswith(cut[1:]) and measure(cut) <= 200
    assert cut == "…rồi gửi cho tiệm in"  # 20 letters: exactly 200 px
    assert conv.fit_end("ngắn", 200, measure) == "ngắn"


def test_wrap_breaks_between_words_and_splits_only_a_too_long_word():
    lines = conv.wrap("một hai ba bốn năm", 70, measure)
    assert lines == ["một hai", "ba bốn", "năm"]
    assert all(measure(line) <= 70 for line in lines)
    assert conv.wrap("abcdefghij", 40, measure) == ["abcd", "efgh", "ij"]
    assert conv.wrap("", 40, measure) == [""]


def test_task_keeps_her_question_first_and_the_plan_in_one_message():
    task = conv.Task()
    task.hear("Mẹ muốn")
    task.hear("Mẹ muốn xuất PDF")  # a fuller partial replaces the first
    task.say("Bấm File.")
    task.plan(["Xuất PDF", "Gửi file"])
    task.plan(["Xuất PDF", "Gửi file"], part=1)
    assert [m.who for m in task.messages] == ["me", "tutor", "tutor"]
    assert task.question == "Mẹ muốn xuất PDF"
    assert task.messages[2].plan == ("Xuất PDF", "Gửi file") and task.messages[2].part == 1
    assert task.last_said() == "Bấm File."


def test_collapsed_text_follows_the_state():
    task = conv.Task()
    task.hear("Mẹ muốn xuất giáo án ra PDF rồi gửi cho tiệm in")
    task.say("Bấm nút Create PDF ở giữa màn hình")
    assert conv.collapsed_text("idle", task, "Sẵn sàng", 200, measure) == ""
    assert conv.collapsed_text("listening", task, "Đang nghe", 200, measure).startswith(conv.ELLIPSIS)
    assert conv.collapsed_text("thinking", task, "Đang xem màn hình", 200, measure) == "Đang xem màn hình"
    speaking = conv.collapsed_text("speaking", task, "Đang nói", 200, measure)
    assert speaking.startswith("Bấm nút") and speaking.endswith(conv.ELLIPSIS)
    assert conv.collapsed_text("error", None, "Chưa nghe rõ", 200, measure) == "Chưa nghe rõ"
    assert conv.collapsed_text("speaking", None, "Đang nói", 200, measure) == ""


def test_layout_puts_her_on_the_right_and_the_tutor_on_the_left():
    task = conv.Task()
    task.hear("Mẹ muốn xuất PDF")
    task.plan(["Xuất PDF", "Gửi file"])
    task.say("Bấm File.")
    task.say("Bấm Export ở cột bên trái của màn hình Word.")
    bubbles, height = conv.layout(task.messages, 400, measure, current=True)
    me, plan, first, last = bubbles
    assert me.who == "me" and abs(me.x + me.w - 400) < 1e-6
    assert plan.x == first.x == last.x == 0 and plan.plan == ("Xuất PDF", "Gửi file")
    assert all(b.w <= 400 * conv.SHARE + 1e-6 for b in bubbles)
    assert [b.current for b in bubbles] == [False, False, False, True]  # only the latest sentence
    assert all(a.y + a.h + conv.GAP == b.y for a, b in zip(bubbles, bubbles[1:]))
    assert height == last.y + last.h
    assert len(plan.lines) == 3  # the heading and one line per part


def test_newest_that_fit_drops_the_oldest_first():
    task = conv.Task()
    task.hear("câu hỏi")
    for i in range(6):
        task.say(f"bước {i}")
    bubbles, _ = conv.layout(task.messages, 400, measure)
    kept, height = conv.newest_that_fit(bubbles, 100)
    assert kept[-1].lines == ("bước 5",) and kept[0].y == 0
    assert height <= 100 and len(kept) < len(bubbles)
    one, _ = conv.newest_that_fit(bubbles, 1)  # always shows at least the newest
    assert len(one) == 1


def test_natural_width_grows_with_the_longest_line():
    short = [conv.Message("me", "ngắn")]
    long = [conv.Message("me", "một câu dài hơn nhiều")]
    assert conv.natural_width(long, measure) > conv.natural_width(short, measure)
    assert conv.natural_width([], measure) > 0


def test_cuts_drop_a_broken_word_but_keep_a_whole_one():
    assert conv.fit_end("xuất giáo án ra PDF", 100, measure) == "…án ra PDF"  # "án" is a whole syllable
    assert conv.fit_end("abcdefgh ijklmnop", 100, measure) == "…ijklmnop"  # a lone "h" of "abcdefgh" goes
    assert conv.fit_end("abc defgh ij", 70, measure) == "…fgh ij"          # dropping "fgh" would cost too much
    assert conv.fit_end("abc def ghi", 80, measure) == "…def ghi"
    assert conv.fit_start("abc def ghi", 80, measure) == "abc def…"
    assert conv.fit_start("abcdefgh ijklmnop", 100, measure) == "abcdefgh…"  # a lone "i" of "ijklmnop" goes


def test_newest_that_fit_can_keep_her_question_on_top():
    task = conv.Task()
    task.hear("câu hỏi của mẹ")
    for i in range(6):
        task.say(f"bước {i}")
    bubbles, _ = conv.layout(task.messages, 400, measure)
    kept, height = conv.newest_that_fit(bubbles, 120, keep_first=True)
    assert kept[0].who == "me" and kept[-1].lines == ("bước 5",)
    assert kept[0].y == 0 and all(a.y + a.h + conv.GAP == b.y for a, b in zip(kept, kept[1:]))
    assert height <= 120


def test_plan_progress():
    task = conv.Task()
    assert conv.plan_progress(task) == "" and conv.plan_progress(None) == ""
    task.plan(["a", "b", "c"], part=1)
    assert conv.plan_progress(task) == "Phần 2/3"
