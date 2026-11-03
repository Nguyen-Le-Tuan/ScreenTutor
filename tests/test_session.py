from PIL import Image

from screentutor.inputs import Click
from screentutor.session import (MAX_PART_STEPS, MAX_PLAN_STEPS, READ_DONE, READ_WAIT_S, RING_FLIGHT_S, SCROLL_WAIT_S,
                                 ClickBox, Session)
from screentutor.still import BIG_CHANGE, CHANGE_MIN
from screentutor.tutor import Reply


class FakeTutor:
    def __init__(self, replies):
        self.replies, self.calls, self.turns = list(replies), [], []

    def ask(self, question, data_url, state, pointer=None, on_mark=None, on_say=None, known=None):
        self.pointer, self.known = pointer, known
        self.calls.append(("ask", question, None, None))
        return self.replies.pop(0)

    def follow_up(self, goal, last_say, data_url, state, changed, plan=None, part=None, notes="", acted="click",
                  on_mark=None, on_say=None):
        self.calls.append(("follow_up", goal, last_say, changed))
        self.turns.append({"plan": plan, "part": part, "notes": notes, "acted": acted})
        return self.replies.pop(0)


CLICK = Click(1.0, 1, 1, "left")


def _go(say, part=None, plan=(), notes="", target="click", point=(100, 100), **kw):
    return Reply(say=say, found=True, point=point, part=part, plan=list(plan), notes=notes, target=target,
                 step_done=True, goal_done=False, **kw)


def _session(tutor, clicks, outcomes, waits=(), changes=()):
    log = []
    clicks, outcomes, waits, changes = list(clicks), list(outcomes), list(waits), list(changes)

    def wait_change(timeout_s, min_change, stop):
        log.append(("change", timeout_s, min_change))
        return "stopped" if stop() else changes.pop(0)

    s = Session(
        tutor=tutor, look=lambda: (Image.new("RGB", (1920, 1080)), "state"), encode=lambda img: "data:",
        show=lambda x, y, caution=False: log.append(("show", x, y) if not caution else ("show!", x, y)),
        hide=lambda: log.append(("hide",)),
        say=lambda text: log.append(("say", text)),
        wait_click=lambda since, timeout: clicks.pop(0) if clicks else None,
        settle=lambda click: outcomes.pop(0), pause=lambda s: None,
        wait_screen=lambda: (log.append(("wait",)), waits.pop(0))[1], wait_change=wait_change)
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


def test_the_first_turn_gets_what_her_mouse_pointed_at():
    tutor = FakeTutor([Reply(say="Bạn mở Zalo trước nhé.", found=False)])
    s, _ = _session(tutor, [], [])
    s.pointer = "khoanh quanh vùng (250, 278)-(750, 556) trên lưới 0-1000"
    s.run("Học cái này")
    assert tutor.pointer == s.pointer


def test_the_first_turn_gets_what_is_known_about_her():
    tutor = FakeTutor([Reply(say="Bạn mở Zalo trước nhé.", found=False)])
    s, _ = _session(tutor, [], [])
    s.known = "- Hay gửi file cho tiệm in"
    s.run("Gửi file")
    assert tutor.known == "- Hay gửi file cho tiệm in"


def test_a_task_left_half_done_goes_on_from_the_part_it_had_reached():
    plans = []
    tutor = FakeTutor([_go("Bạn bấm vào biểu tượng Zalo.", part=2),
                       Reply(say="Xong rồi bạn nhé.", target="none", part=3, step_done=True, goal_done=True)])
    s, log = _session(tutor, [CLICK], ["settled"])
    s.plan, s.part, s.notes = ["Mở Word", "Mở Zalo", "Gửi file"], 2, "Gửi cho tổ trưởng."
    s.on_plan = lambda plan, part: plans.append(part)
    steps = s.run("Gửi giáo án cho tổ trưởng", last_say="Bạn bấm vào nút Lưu.")
    assert tutor.calls[0] == ("follow_up", "Gửi giáo án cho tổ trưởng", "Bạn bấm vào nút Lưu.", None)
    assert tutor.turns[0] == {"plan": ["Mở Word", "Mở Zalo", "Gửi file"], "part": 2, "notes": "Gửi cho tổ trưởng.",
                              "acted": "resume"}
    assert plans[:1] == [2] and steps[-1].goal_done and plans[-1] == 3    # the card first, then the last part


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


# B2: the plan, the parts, reading and scrolling

def test_says_the_plan_on_the_first_turn_and_walks_through_the_parts():
    plans, seen = [], []
    tutor = FakeTutor([
        Reply(say="Việc này có hai phần. Bạn bấm File.", found=True, point=(15, 74), mode="guide", target="click",
              plan=["Xuất PDF", "Gửi cho tiệm in"]),
        _go("Bạn bấm Export.", part=1),
        _go("Xong phần một. Bạn mở Zalo.", part=2),
        Reply(say="Xong rồi bạn nhé.", found=False, target="none", part=2, step_done=True, goal_done=True)])
    s, log = _session(tutor, [CLICK, CLICK, CLICK], ["settled"] * 3)
    s.on_plan = lambda plan, part: plans.append((list(plan), part))
    s.status = seen.append
    steps = s.run("Xuất PDF rồi gửi tiệm in")
    assert plans == [(["Xuất PDF", "Gửi cho tiệm in"], 1), (["Xuất PDF", "Gửi cho tiệm in"], 2)]  # only when it changes
    assert s.mode == "guide" and steps[-1].goal_done and seen[-1] == "done"
    assert [t["part"] for t in tutor.turns] == [1, 1, 2]
    assert all(t["plan"] == ["Xuất PDF", "Gửi cho tiệm in"] and t["acted"] == "click" for t in tutor.turns)


def test_a_new_plan_or_new_notes_replace_the_old_ones_and_empty_ones_do_not():
    tutor = FakeTutor([
        Reply(say="Bạn bấm A.", found=True, point=(1, 1), plan=["A", "B"], target="click", notes="Ghi chú một."),
        _go("Bạn bấm B.", part=2),
        _go("Bạn bấm C.", part=3, plan=["A", "B", "C"], notes="Ghi chú hai."),
        _go("Bạn bấm D.", part=9)])  # a part past the end stays on the last one
    s, _ = _session(tutor, [CLICK] * 3, ["settled"] * 3)
    s.run("x")
    assert [(t["plan"], t["part"], t["notes"]) for t in tutor.turns] == [
        (["A", "B"], 1, "Ghi chú một."), (["A", "B"], 2, "Ghi chú một."), (["A", "B", "C"], 3, "Ghi chú hai.")]
    assert s.part == 3


def test_a_read_step_shows_the_box_and_adds_how_to_say_she_is_done():
    boxes = []
    tutor = FakeTutor([
        Reply(say="Bạn đọc tin này nhé.", found=True, point=(500, 500), target="read", box=(250, 250, 750, 750)),
        Reply(say="Xong rồi.", found=False, target="none", step_done=True, goal_done=True)])
    s, log = _session(tutor, [CLICK], ["settled"])
    s.show_box = lambda box, caution: boxes.append((box, caution))
    s.run("Đọc tin này")
    assert boxes == [((480, 270, 1440, 810), False)] and not [x for x in log if x[0] == "show"]
    assert ("say", f"Bạn đọc tin này nhé. {READ_DONE}") in log
    assert ("change", READ_WAIT_S, BIG_CHANGE) in log
    assert tutor.calls[1][2] == "Bạn đọc tin này nhé." and tutor.turns[0]["acted"] == "read"  # her words stay the model's


def test_until_the_real_box_exists_a_read_step_draws_a_ring_at_its_centre():
    tutor = FakeTutor([Reply(say="Bạn đọc tin này.", found=True, point=(500, 500), target="read",
                             box=(250, 250, 750, 750))])
    s, log = _session(tutor, [], [], changes=["unchanged"])
    s.run("Đọc tin này")
    assert ("show", 960, 540) in log and log[-1] == ("hide",)


def test_a_click_ends_the_read_and_a_big_change_that_stood_still_ends_it_too():
    read = Reply(say="Bạn đọc tin này.", found=True, point=(500, 500), target="read", box=(250, 250, 750, 750))
    done = Reply(say="Xong.", found=False, target="none", step_done=True, goal_done=True)
    tutor = FakeTutor([read, done])
    s, _ = _session(tutor, [CLICK], ["unchanged"])
    s.run("x")
    assert tutor.turns[0]["acted"] == "read" and tutor.calls[1][3] is False   # she clicked, the screen stayed
    tutor = FakeTutor([read, done])
    s, _ = _session(tutor, [], [], changes=["settled"])
    s.run("x")
    assert tutor.turns[0]["acted"] == "moved" and tutor.calls[1][3] is True    # she scrolled on by herself


def test_nothing_happening_ends_a_read_or_a_scroll_quietly():
    for reply in (Reply(say="Bạn đọc tin này.", found=True, point=(500, 500), target="read", box=(250, 250, 750, 750)),
                  Reply(say="Bạn kéo xuống nhé.", found=True, point=(500, 500), target="scroll")):
        seen = []
        tutor = FakeTutor([reply])
        s, log = _session(tutor, [], [], changes=["unchanged"])
        s.status = seen.append
        s.run("x")
        assert len(tutor.calls) == 1 and log[-1] == ("hide",) and seen[-1] == "idle"


def test_scroll_waits_for_the_screen_and_the_notes_go_to_the_next_turn():
    tutor = FakeTutor([
        Reply(say="Bạn kéo xuống nhé.", found=True, point=(500, 500), mode="guide", target="scroll",
              notes="Bước một đăng nhập."),
        Reply(say="Xong rồi.", found=False, target="none", step_done=True, goal_done=True)])
    s, log = _session(tutor, [], [], changes=["settled"])
    s.run("Học cái này")
    assert ("change", SCROLL_WAIT_S, CHANGE_MIN) in log
    assert tutor.turns == [{"plan": None, "part": None, "notes": "Bước một đăng nhập.", "acted": "moved"}]
    assert tutor.calls[1][3] is True


def test_the_scroll_point_goes_to_its_own_callback_when_there_is_one():
    points = []
    tutor = FakeTutor([Reply(say="Bạn kéo xuống nhé.", found=True, point=(500, 500), target="scroll")])
    s, log = _session(tutor, [], [], changes=["unchanged"])
    s.show_scroll = points.append
    s.run("x")
    assert points == [(960, 540)] and not [x for x in log if x[0] == "show"]


def test_nothing_watches_the_screen_until_the_ring_has_landed():
    # measured 02/11: the ring's flight alone crosses CHANGE_MIN, so the scroll step would end by itself
    order = []
    tutor = FakeTutor([Reply(say="Bạn kéo xuống nhé.", found=True, point=(500, 500), target="scroll")])
    s, _ = _session(tutor, [], [])
    s.pause = lambda seconds: order.append(seconds)
    s.wait_change = lambda timeout_s, min_change, stop: (order.append("watch"), "unchanged")[1]
    s.run("x")
    assert order == [RING_FLIGHT_S, "watch"]


def test_the_plan_is_made_after_reading_to_the_end():
    plans = []
    tutor = FakeTutor([
        Reply(say="Bạn kéo xuống nhé.", found=True, point=(500, 900), mode="guide", target="scroll", notes="Phần đầu."),
        _go("Bạn kéo tiếp nhé.", part=0, notes="Phần đầu. Phần giữa.", target="scroll"),
        _go("Việc này có hai phần. Bạn bấm Đăng nhập.", part=1, plan=["Đăng nhập", "Làm bài"]),
        Reply(say="Xong rồi.", found=False, target="none", part=2, step_done=True, goal_done=True)])
    s, _ = _session(tutor, [CLICK], ["settled"], changes=["settled", "settled"])
    s.on_plan = lambda plan, part: plans.append((list(plan), part))
    s.run("Học cái trong Zalo")
    assert plans == [(["Đăng nhập", "Làm bài"], 1), (["Đăng nhập", "Làm bài"], 2)]
    assert [t["plan"] for t in tutor.turns] == [None, None, ["Đăng nhập", "Làm bài"]]
    assert [t["notes"] for t in tutor.turns] == ["Phần đầu.", "Phần đầu. Phần giữa.", "Phần đầu. Phần giữa."]


def test_a_task_with_a_plan_stops_at_30_steps():
    parts = ["A", "B", "C", "D", "E", "F"]
    first = Reply(say="Bạn bấm.", found=True, point=(1, 1), plan=parts, target="click")
    tutor = FakeTutor([first] + [_go("Bạn bấm.", part=min(i // 6 + 1, 6)) for i in range(1, 60)])
    s, _ = _session(tutor, [CLICK] * 60, ["settled"] * 60)
    assert len(s.run("x")) == MAX_PLAN_STEPS == 30


def test_one_part_stops_at_12_steps_and_a_new_part_starts_counting_again():
    first = Reply(say="Bạn bấm.", found=True, point=(1, 1), plan=["A", "B"], target="click")
    tutor = FakeTutor([first] + [_go("Bạn bấm.", part=1) for _ in range(40)])
    s, _ = _session(tutor, [CLICK] * 40, ["settled"] * 40)
    assert len(s.run("x")) == MAX_PART_STEPS == 12
    tutor = FakeTutor([first] + [_go("Bạn bấm.", part=1) for _ in range(10)] + [_go("Bạn bấm.", part=2) for _ in range(40)])
    s, _ = _session(tutor, [CLICK] * 40, ["settled"] * 40)
    assert len(s.run("x")) == 11 + 12


def test_a_task_without_a_plan_keeps_the_old_limit():
    tutor = FakeTutor([Reply(say="Bạn bấm.", found=True, point=(1, 1), target="click")]
                      + [_go("Bạn bấm.") for _ in range(40)])
    s, _ = _session(tutor, [CLICK] * 40, ["settled"] * 40)
    assert len(s.run("x")) == 12


def test_a_task_that_ends_exactly_at_the_limit_still_says_so():
    tutor = FakeTutor([Reply(say="Bạn bấm.", found=True, point=(1, 1), target="click")]
                      + [_go("Bạn bấm.") for _ in range(11)]
                      + [Reply(say="Xong rồi bạn nhé.", target="none", step_done=True, goal_done=True)])
    s, log = _session(tutor, [CLICK] * 12, ["settled"] * 12)
    steps = s.run("x")
    assert steps[-1].goal_done and log[-1] == ("say", "Xong rồi bạn nhé.")


def test_a_video_is_not_a_failure():
    seen = []
    tutor = FakeTutor([
        Reply(say="Bạn bấm nút phát video.", found=True, point=(500, 500), target="click"),
        _go("Bạn xem hết video nhé.", target="read", box=(100, 100, 900, 900), point=(500, 500)),
        _go("Bạn kéo xuống nhé.", target="scroll", point=(500, 500)),
        Reply(say="Xong rồi.", found=False, target="none", step_done=True, goal_done=True)])
    s, _ = _session(tutor, [CLICK], ["timeout"], changes=["timeout", "timeout"])
    s.status = seen.append
    steps = s.run("Xem video bài giảng")
    assert "error" not in seen and seen[-1] == "done" and all(st.error is None for st in steps)
    assert [st.settle for st in steps] == [None, "timeout", "timeout", "timeout"]
    assert [c[3] for c in tutor.calls[1:]] == [True, True, True]  # the next turn looks at it all the same


def test_a_new_question_cancels_a_read_or_a_scroll_without_another_call():
    import threading

    for reply in (Reply(say="Bạn đọc.", found=True, point=(500, 500), target="read", box=(250, 250, 750, 750)),
                  Reply(say="Bạn kéo.", found=True, point=(500, 500), target="scroll")):
        cancel = threading.Event()
        tutor = FakeTutor([reply])
        s, log = _session(tutor, [], [])
        s.cancel = cancel
        s.wait_change = lambda timeout_s, min_change, stop: (cancel.set(), "stopped" if stop() else "?")[1]
        s.run("x")
        assert len(tutor.calls) == 1 and log[-1] == ("hide",)


def test_the_states_sent_to_the_island():
    seen = []
    tutor = FakeTutor([
        Reply(say="Bạn kéo xuống.", found=True, point=(500, 500), target="scroll"),
        _go("Bạn đọc tin này.", target="read", box=(250, 250, 750, 750), point=(500, 500)),
        _go("Bấm Gửi thì tin sẽ đi.", caution=True),
        Reply(say="Trang đang tải.", target="none", step_done=True, goal_done=False),
        Reply(say="Xong rồi.", found=False, target="none", step_done=True, goal_done=True)])
    s, _ = _session(tutor, [CLICK, CLICK], ["settled", "settled"], waits=["settled"], changes=["settled"])
    s.status = seen.append
    s.run("x")
    assert seen == ["thinking", "turn", "thinking", "reading", "thinking", "caution", "thinking", "loading", "thinking",
                    "done"]


def test_a_v1_answer_without_a_target_walks_as_before():
    tutor = FakeTutor([Reply(say="Bạn bấm File.", found=True, point=(15, 74)),
                       Reply(say="Xong.", step_done=True, goal_done=True)])
    s, log = _session(tutor, [CLICK], ["settled"])
    s.run("x")
    assert log[0] == ("show", 29, 80) and tutor.turns[0]["acted"] == "click"


def test_without_a_screen_watcher_a_read_or_scroll_step_falls_back_to_the_ring():
    tutor = FakeTutor([Reply(say="Bạn kéo xuống.", found=True, point=(500, 500), target="scroll")])
    s, log = _session(tutor, [], [])
    s.wait_change = None
    s.run("x")
    assert log[0] == ("show", 960, 540) and log[-1] == ("hide",)


def test_the_tick_appears_where_she_clicked_once_the_step_is_checked():
    ticks = []
    tutor = FakeTutor([Reply(say="Bạn bấm File.", found=True, point=(15, 74), target="click"),
                       Reply(say="Bạn bấm lại nhé.", found=True, point=(15, 74), target="click", step_done=False),
                       _go("Bạn bấm Export."),
                       Reply(say="Xong rồi.", target="none", step_done=True, goal_done=True)])
    s, _ = _session(tutor, [Click(1.0, 30, 80, "left"), Click(2.0, 31, 81, "left"), Click(3.0, 500, 600, "left")],
                    ["settled"] * 3)
    s.confirm = lambda x, y: ticks.append((x, y))
    s.run("x")
    assert ticks == [(31, 81), (500, 600)]    # not after the click the tutor found wrong


def test_a_read_or_a_scroll_gets_no_tick():
    ticks = []
    tutor = FakeTutor([Reply(say="Bạn đọc.", found=True, point=(500, 500), target="read", box=(250, 250, 750, 750)),
                       Reply(say="Xong.", target="none", step_done=True, goal_done=True)])
    s, _ = _session(tutor, [CLICK], ["settled"])
    s.confirm = lambda x, y: ticks.append((x, y))
    s.run("x")
    assert ticks == []


# The answer streams: the step goes on the screen before the turn is over

class StreamingTutor(FakeTutor):
    """Calls the early hooks as the real one does, then returns the whole reply."""

    def _early(self, on_mark, on_say):
        reply = self.replies[0]
        if on_mark and reply.point and not reply.error:
            on_mark(reply)
        if on_say and reply.say:
            on_say(reply.say)
        self.log.append(("reply",))

    def ask(self, question, data_url, state, pointer=None, on_mark=None, on_say=None, known=None):
        self._early(on_mark, on_say)
        return super().ask(question, data_url, state, pointer, known=known)

    def follow_up(self, goal, last_say, data_url, state, changed, plan=None, part=None, notes="", acted="click",
                  on_mark=None, on_say=None):
        self._early(on_mark, on_say)
        return super().follow_up(goal, last_say, data_url, state, changed, plan, part, notes, acted)


def _streaming(replies, clicks, outcomes, changes=()):
    tutor = StreamingTutor(replies)
    s, log = _session(tutor, clicks, outcomes, changes=changes)
    tutor.log = log
    return tutor, s, log


def test_the_ring_and_the_voice_come_before_the_answer_has_finished_and_only_once():
    _, s, log = _streaming([Reply(say="Bạn bấm File.", found=True, point=(15, 74), target="click"),
                            Reply(say="Xong rồi.", target="none", step_done=True, goal_done=True)], [CLICK], ["settled"])
    s.run("x")
    assert log == [("show", 29, 80), ("say", "Bạn bấm File."), ("reply",), ("hide",), ("say", "Xong rồi."), ("reply",)]


def test_a_read_step_shown_early_keeps_its_box_and_its_extra_sentence():
    boxes = []
    _, s, log = _streaming([Reply(say="Bạn đọc tin này.", found=True, point=(500, 500), target="read",
                                  box=(250, 250, 750, 750))], [], [], changes=["unchanged"])
    s.show_box = lambda box, caution: boxes.append(box)
    s.run("x")
    assert boxes == [(480, 270, 1440, 810)] and ("say", f"Bạn đọc tin này. {READ_DONE}") in log


def test_a_sentence_without_diacritics_waits_for_the_second_try():
    _, s, log = _streaming([Reply(say="Ban bam File.", found=True, point=(15, 74), target="click")], [], [])
    s._early_say("Ban bam File.")
    assert not s.spoken and not [x for x in log if x[0] == "say"]


def test_an_error_after_the_ring_went_up_takes_it_down():
    tutor = FakeTutor([Reply(say="Bạn bấm File.", found=True, point=(15, 74), target="click"), Reply(error="stream broke")])
    s, log = _session(tutor, [CLICK], ["settled"])
    real = tutor.follow_up

    def broken(*a, on_mark=None, on_say=None, **kw):
        on_mark(Reply(found=True, point=(20, 20), target="click"))
        return real(*a, **kw)

    tutor.follow_up = broken
    s.run("x")
    assert log[-2:] == [("hide",), ("say", "Mình chưa xem được màn hình. Bạn hỏi lại nhé.")]


def test_a_finished_task_shows_no_early_ring():
    _, s, log = _streaming([Reply(say="Xong rồi.", found=True, point=(10, 10), target="click", goal_done=True)], [], [])
    s.run("x")
    assert not [x for x in log if x[0] == "show"] and log[0] == ("say", "Xong rồi.")


def test_the_tick_comes_with_the_next_ring_and_only_once():
    ticks = []
    _, s, log = _streaming([Reply(say="Bạn bấm File.", found=True, point=(15, 74), target="click"),
                            _go("Bạn bấm Export."),
                            Reply(say="Xong.", target="none", step_done=True, goal_done=True)],
                           [Click(1.0, 30, 80, "left"), Click(2.0, 500, 600, "left")], ["settled", "settled"])
    s.confirm = lambda x, y: (ticks.append((x, y)), log.append(("tick",)))
    s.run("x")
    assert ticks == [(30, 80), (500, 600)]
    assert log.index(("tick",)) < log.index(("show", 192, 108))
