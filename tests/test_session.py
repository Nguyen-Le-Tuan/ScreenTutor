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


def _session(tutor, clicks, outcomes, waits=()):
    log = []
    clicks, outcomes, waits = list(clicks), list(outcomes), list(waits)
    s = Session(
        tutor=tutor, look=lambda: (Image.new("RGB", (1920, 1080)), "state"), encode=lambda img: "data:",
        show=lambda x, y, caution=False: log.append(("show", x, y) if not caution else ("show!", x, y)),
        hide=lambda: log.append(("hide",)),
        say=lambda text: log.append(("say", text)),
        wait_click=lambda since, timeout: clicks.pop(0) if clicks else None,
        settle=lambda click: outcomes.pop(0), pause=lambda s: None,
        wait_screen=lambda: (log.append(("wait",)), waits.pop(0))[1])
    return s, log


def test_walks_steps_until_the_task_is_done():
    tutor = FakeTutor([
        Reply(say="Bạn bấm vào chữ File.", found=True, point=(15, 74)),
        Reply(say="Bạn bấm vào chữ Export.", found=True, point=(20, 560), step_done=True, goal_done=False),
        Reply(say="Xong rồi bạn nhé.", step_done=True, goal_done=True)])
    s, log = _session(tutor, [Click(1.0, 29, 80, "left"), Click(2.0, 38, 605, "left")], ["settled", "settled"])
    steps = s.run("Mẹ muốn xuất ra PDF")
    assert [x for x in log if x[0] != "say"] == [("show", 29, 80), ("hide",), ("show", 38, 605), ("hide",)]
    assert log[:2] == [("show", 29, 80), ("say", "Bạn bấm vào chữ File.")]  # ring first, then the words
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


def test_a_new_question_cancels_the_session():
    import threading

    cancel = threading.Event()
    tutor = FakeTutor([Reply(say="Bạn bấm File.", found=True, point=(15, 74)),
                       Reply(say="Bạn bấm Export.", found=True, point=(20, 560), step_done=True)])
    s, log = _session(tutor, [Click(1.0, 29, 80, "left")], ["settled"])
    s.cancel = cancel
    s.settle = lambda click: (cancel.set(), "settled")[1]   # she pressed Hỏi while the screen settled
    s.run("Xuất PDF")
    assert [x for x in log if x[0] == "show"] == [("show", 29, 80)] and len(tutor.calls) == 1  # no wasted call


def test_click_box_skips_clicks_on_our_own_button_and_stops_on_cancel():
    import threading

    box = ClickBox()
    box.put(Click(3.0, 1800, 1000, "left"))      # on the Hỏi button
    box.put(Click(3.5, 40, 80, "left"))
    on_button = lambda c: c.x > 1700 and c.y > 950  # noqa: E731
    assert box.wait(since=2.0, timeout_s=0.01, ignore=on_button) == Click(3.5, 40, 80, "left")
    cancel = threading.Event()
    cancel.set()
    assert box.wait(since=2.0, timeout_s=5, cancel=cancel) is None


def test_a_loading_screen_is_watched_again_instead_of_ending_the_session():
    tutor = FakeTutor([
        Reply(say="Bạn bấm vào link Bảng kê khai.", found=True, point=(610, 525)),
        Reply(say="Trang đang tải, bạn chờ một chút nhé.", found=False, step_done=True, goal_done=False),
        Reply(say="Bảng tính đã mở xong rồi.", step_done=True, goal_done=True)])
    s, log = _session(tutor, [Click(1.0, 1171, 567, "left")], ["settled"], waits=["settled"])
    steps = s.run("Link không mở lên")
    assert ("wait",) in log and steps[-1].goal_done and len(tutor.calls) == 3
    assert tutor.calls[2] == ("follow_up", "Link không mở lên", "Trang đang tải, bạn chờ một chút nhé.", True)


def test_waiting_gives_up_after_three_looks_and_asking_back_still_ends():
    from screentutor.session import MAX_WAITS

    loading = Reply(say="Bạn chờ một chút nhé.", found=False, step_done=True, goal_done=False)
    tutor = FakeTutor([Reply(say="Bạn bấm link.", found=True, point=(610, 525))] + [loading] * (MAX_WAITS + 1))
    s, log = _session(tutor, [Click(1.0, 1171, 567, "left")], ["settled"], waits=["unchanged"] * MAX_WAITS)
    s.run("Link không mở lên")
    assert log.count(("wait",)) == MAX_WAITS and len(tutor.calls) == MAX_WAITS + 2
    asks_back = FakeTutor([Reply(say="Bạn muốn mở file nào?", found=False)])  # first turn: no step to be done
    s, log = _session(asks_back, [], [], waits=["settled"])
    s.run("Mở file")
    assert ("wait",) not in log


def test_a_caution_step_is_shown_as_such():
    tutor = FakeTutor([Reply(say="Bấm Yes thì file PDF cũ cùng tên sẽ bị thay bằng file mới.", found=True,
                             point=(531, 486), caution=True)])
    s, log = _session(tutor, [], [])
    s.run("Xuất PDF")
    assert log[0] == ("show!", 1020, 525)


def test_tells_the_island_what_it_is_doing():
    seen = []
    tutor = FakeTutor([
        Reply(say="Bạn bấm vào chữ File.", found=True, point=(15, 74)),
        Reply(say="Bấm Yes thì file cũ sẽ bị thay.", found=True, point=(500, 500), caution=True, step_done=True,
              goal_done=False),
        Reply(say="Đợi trang tải nhé.", step_done=True, goal_done=False),
        Reply(say="Xong rồi bạn nhé.", step_done=True, goal_done=True)])
    s, _ = _session(tutor, [Click(1.0, 29, 80, "left"), Click(2.0, 960, 540, "left")], ["settled", "settled"],
                    waits=["settled"])
    s.status = seen.append
    s.run("Mẹ muốn xuất ra PDF")
    assert seen == ["thinking", "turn", "thinking", "caution", "thinking", "loading", "thinking", "done"]


def test_an_unfinished_task_ends_idle_and_an_error_says_so():
    seen = []
    s, _ = _session(FakeTutor([Reply(say="Bạn mở Zalo trước nhé.", found=False)]), [], [])
    s.status = seen.append
    s.run("Gửi file")
    assert seen == ["thinking", "idle"]
    seen.clear()
    s, _ = _session(FakeTutor([Reply(say="", error="timeout")]), [], [])
    s.status = seen.append
    s.run("Gửi file")
    assert seen == ["thinking", "error"]
