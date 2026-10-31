from PIL import Image

from screentutor.inputs import Click
from screentutor.session import ClickBox, Session
from screentutor.tutor import Reply


class FakeTutor:
    def __init__(self, replies):
        self.replies, self.calls = list(replies), []

    def ask(self, question, data_url, state):
        self.calls.append(("ask", question, None, None))
        return self.replies.pop(0)

    def follow_up(self, goal, last_say, data_url, state, changed):
        self.calls.append(("follow_up", goal, last_say, changed))
        return self.replies.pop(0)


def _session(tutor, clicks, outcomes):
    log = []
    clicks, outcomes = list(clicks), list(outcomes)
    s = Session(
        tutor=tutor, look=lambda: (Image.new("RGB", (1920, 1080)), "state"), encode=lambda img: "data:",
        show=lambda x, y: log.append(("show", x, y)), hide=lambda: log.append(("hide",)),
        say=lambda text: log.append(("say", text)),
        wait_click=lambda since, timeout: clicks.pop(0) if clicks else None,
        settle=lambda click: outcomes.pop(0), pause=lambda s: None)
    return s, log


def test_walks_steps_until_the_task_is_done():
    tutor = FakeTutor([
        Reply(say="Bạn bấm vào chữ File.", found=True, point=(15, 74)),
        Reply(say="Bạn bấm vào chữ Export.", found=True, point=(20, 560), step_done=True, goal_done=False),
        Reply(say="Xong rồi bạn nhé.", step_done=True, goal_done=True)])
    s, log = _session(tutor, [Click(1.0, 29, 80, "left"), Click(2.0, 38, 605, "left")], ["settled", "settled"])
    steps = s.run("Mẹ muốn xuất ra PDF")
    assert [x for x in log if x[0] != "say"] == [("show", 29, 80), ("hide",), ("show", 38, 605), ("hide",)]
    assert [x[1] for x in log if x[0] == "say"] == ["Bạn bấm vào chữ File.", "Bạn bấm vào chữ Export.",
                                                   "Xong rồi bạn nhé."]
    assert tutor.calls[1] == ("follow_up", "Mẹ muốn xuất ra PDF", "Bạn bấm vào chữ File.", True)
    assert [st.settle for st in steps] == [None, "settled", "settled"] and steps[-1].goal_done


def test_unchanged_screen_is_reported_to_the_check_turn():
    tutor = FakeTutor([Reply(say="Bạn bấm OK.", found=True, point=(580, 487)),
                       Reply(say="Bạn bấm lại vào nút OK nhé.", found=True, point=(580, 487), step_done=False),
                       Reply(say="Xong rồi.", step_done=True, goal_done=True)])
    s, _ = _session(tutor, [Click(1.0, 1, 1, "left"), Click(2.0, 1114, 526, "left")], ["unchanged", "settled"])
    s.run("Tắt bảng lỗi")
    assert [c[3] for c in tutor.calls] == [None, False, True]


def test_stops_when_nothing_to_point_at_or_no_click():
    tutor = FakeTutor([Reply(say="Bạn mở Zalo trước nhé.", found=False)])
    s, log = _session(tutor, [], [])
    assert len(s.run("Gửi file")) == 1 and not [x for x in log if x[0] == "show"]
    tutor = FakeTutor([Reply(say="Bạn bấm File.", found=True, point=(15, 74))])
    s, log = _session(tutor, [], [])
    s.run("Xuất PDF")
    assert log[-1] == ("hide",) and len(tutor.calls) == 1


def test_api_error_says_so_and_stops():
    tutor = FakeTutor([Reply(error="HTTP 503")])
    s, log = _session(tutor, [], [])
    s.run("Xuất PDF")
    assert log == [("say", "Mình chưa xem được màn hình. Bạn hỏi lại nhé.")]


def test_click_box_returns_only_clicks_after_the_ring_appeared():
    box = ClickBox()
    box.put(Click(1.0, 5, 5, "left"))
    box.put(Click(3.0, 7, 7, "left"))
    assert box.wait(since=2.0, timeout_s=0.01) == Click(3.0, 7, 7, "left")
    assert box.wait(since=2.0, timeout_s=0.01) is None
