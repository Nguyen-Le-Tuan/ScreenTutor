from PIL import Image

from screentutor.app import masked
from screentutor.still import changed_fraction, signature


def test_our_own_widgets_never_count_as_the_screen_moving():
    a = Image.new("RGB", (1920, 1080), "white")
    b = a.copy()
    b.paste((37, 99, 235), (1650, 960, 1900, 1030))          # the Hỏi button changes colour and words
    rects = [(1640, 950, 1910, 1040)]
    assert changed_fraction(signature(a), signature(b)) > 0.002
    assert changed_fraction(signature(masked(a, rects)), signature(masked(b, rects))) == 0
    assert masked(a, []) is a


from screentutor import conversation as conv
from screentutor.app import Feed, inside, to_physical
from screentutor.levels import Meter


class FakeIsland:
    def __init__(self):
        self.states, self.avoid, self.level_source, self.mode, self.changed = [], [], None, "pinned", 0

    def set_state(self, state, task=None):
        self.states.append((state, task.question if task else None, len(task.messages) if task else 0))

    def task_changed(self):
        self.changed += 1

    def set_avoid(self, point):
        self.avoid.append(None if point is None else (point.x(), point.y()))

    def set_mode(self, mode):
        self.mode = mode

    def peek(self, seconds):
        self.peeks = getattr(self, "peeks", []) + [seconds]


class FakeButton:
    def __init__(self):
        self.states, self.level_source = [], None

    def set_state(self, state):
        self.states.append(state)


def test_feed_shows_speaking_over_the_session_state_and_returns_to_it(qt_app):
    isl, btn, voice, mic = FakeIsland(), FakeButton(), Meter(), Meter()
    feed = Feed(isl, btn, voice, dpr=1.25)
    feed.listen(mic)
    mic.value = 0.4
    assert isl.states[-1][0] == "listening" and isl.level_source() == 0.4 and btn.level_source() == 0.4
    feed.hear("Mẹ muốn xuất PDF")
    assert feed.task.question == "Mẹ muốn xuất PDF" and isl.changed == 1
    feed.status("thinking")
    assert isl.level_source is None
    feed.say_start("Bạn bấm File.", 1)
    feed.status("turn")                      # the session moves on while the sentence still plays
    voice.value = 0.7
    assert isl.states[-1][0] == "speaking" and isl.level_source() == 0.7
    feed.say_end(1)
    assert isl.states[-1][0] == "turn" and btn.states[-1] == "turn"
    assert isl.states[-1][1:] == ("Mẹ muốn xuất PDF", 2)  # her question and the tutor's sentence


def test_a_cut_off_sentence_does_not_end_the_next_one():
    isl = FakeIsland()
    feed = Feed(isl)
    feed.status("turn")
    feed.say_start("Câu cũ.", 1)
    feed.say_start("Câu mới.", 2)  # a click cut the first one off and a new one started
    feed.say_end(1)
    assert feed.shown() == "speaking"
    feed.say_end(2)
    assert feed.shown() == "turn"


def test_feed_passes_the_ring_in_logical_pixels_and_closes_a_pinned_island(qt_app):
    isl = FakeIsland()
    feed = Feed(isl, dpr=1.25)
    feed.ring(1250, 625, False)
    feed.unring()
    assert isl.avoid == [(1000.0, 500.0), None]
    feed.collapse()
    assert isl.mode == "collapsed"


def test_each_question_is_a_new_task():
    isl = FakeIsland()
    feed = Feed(isl)
    feed.listen()
    feed.hear("câu một")
    first = feed.task
    feed.listen()
    assert feed.task is not first and feed.task.messages == []


def test_boxes_turn_physical_and_catch_clicks():
    assert to_physical((100, 10, 40, 20), 1.25) == (125, 12, 175, 38)
    assert to_physical(None, 1.25) is None
    assert inside((125, 12, 175, 38), 150, 20) and not inside((125, 12, 175, 38), 200, 20)
    assert not inside(None, 1, 1)


def test_the_path_over_our_own_button_points_at_nothing():
    from screentutor.app import pointing

    size, button = (1920, 1080), (1800, 960, 1890, 1050)
    at_content = [(i * 0.015, 900, 500) for i in range(60)]
    on_button = [(1 + i * 0.015, 1850, 1000) for i in range(400)]        # she talks with the mouse on the button
    assert pointing(at_content + on_button, size, [button]) == "dừng ở (469, 463) trên lưới 0-1000"
    assert pointing(on_button, size, [button]) is None
    assert pointing(on_button, size, []) == "dừng ở (964, 926) trên lưới 0-1000"  # what the filter is there for


def test_outcome_of_a_task():
    from screentutor.app import outcome_of
    from screentutor.session import Step

    done = [Step(1, "File", (1, 1)), Step(2, "Xong", None, True, True)]
    assert outcome_of(done, cancelled=False) == "done"
    assert outcome_of(done, cancelled=True) == "interrupted"  # a new question cut it off
    assert outcome_of([Step(1, "", None, error="timeout")], False) == "error"
    assert outcome_of([Step(1, "Bạn mở Zalo trước nhé.", None)], False) == "stopped"
    assert outcome_of([], False) == "stopped"


def test_feed_shows_the_parts_of_a_big_task():
    isl = FakeIsland()
    feed = Feed(isl)
    feed.listen()
    feed.hear("Học cái trong Zalo")
    feed.plan(["Đăng nhập", "Xem video", "Làm bài"], 0)   # no part yet: still the first
    assert conv.plan_progress(feed.task) == "Phần 1/3" and isl.changed == 2
    feed.plan(["Đăng nhập", "Xem video", "Làm bài"], 2)
    assert conv.plan_progress(feed.task) == "Phần 2/3" and isl.changed == 3
    assert isl.peeks == [5.0, 3.0]                         # longer the first time
    assert len([m for m in feed.task.messages if m.plan]) == 1
    Feed(FakeIsland()).plan(["A", "B"], 1)                  # no task yet: does not fail


def test_feed_hands_the_recent_tasks_to_the_island():
    class Isl(FakeIsland):
        def update(self):
            self.updated = True

    isl = Isl()
    Feed(isl).recent([("hôm qua", "Mở link bảng tính")])
    assert isl.recent == [("hôm qua", "Mở link bảng tính")] and isl.updated


def test_the_glow_never_outlasts_the_looking(qt_app):
    isl, glows = FakeIsland(), []
    feed = Feed(isl)
    feed.glow = glows.append
    feed.status("thinking")
    assert glows == []         # look() turns it on, after the screenshot
    feed.say_start("Bạn bấm File.", 1)
    assert glows == [False]


def test_a_frame_keeps_the_island_off_the_whole_box(qt_app):
    class Isl(FakeIsland):
        def set_avoid(self, point, box=None):
            self.seen = (point.x(), point.y(), box.x(), box.width())

    isl = Isl()
    Feed(isl, dpr=1.25).frame(125, 250, 625, 750)
    assert isl.seen == (300.0, 400.0, 100.0, 400.0)


def test_the_green_flash_comes_once_when_a_task_is_done(qt_app):
    isl, flashes = FakeIsland(), []
    feed = Feed(isl)
    feed.flash = lambda: flashes.append(1)
    feed.status("thinking")
    feed.say_start("Xong rồi bạn nhé.", 1)
    feed.status("done")           # still speaking: not yet
    assert flashes == []
    feed.say_end(1)
    assert flashes == [1]
    feed.status("done")
    assert flashes == [1]
    feed.status("idle")
    feed.status("done")
    assert flashes == [1, 1]      # the next task


def test_the_tutor_speaking_up_is_a_task_of_its_own_in_the_caution_colour(qt_app):
    isl = FakeIsland()
    feed = Feed(isl)
    feed.listen()
    feed.hear("câu trước")
    old = feed.task
    feed.notice()
    assert feed.task is not old and isl.states[-1][0] == "notice"
    feed.say_start("File này là bản tạm của Zalo.", 7)
    assert isl.states[-1][0] == "speaking"
    feed.say_end(7)
    assert isl.states[-1][0] == "notice" and feed.task.last_said() == "File này là bản tạm của Zalo."


def test_the_machine_notes_say_what_to_do_about_the_temporary_copy():
    from screentutor.app import MACHINE_NOTES

    assert "tải file về một thư mục thật" in MACHINE_NOTES and "không sửa trên bản tạm" in MACHINE_NOTES


def test_a_task_left_half_done_is_offered_and_taken_up_under_its_own_question(qt_app):
    isl = FakeIsland()
    feed = Feed(isl)
    feed.offer("Gửi giáo án cho tổ trưởng")
    assert isl.states[-1][0] == "offer" and feed.task.last_said() == "Làm tiếp: Gửi giáo án cho tổ trưởng"
    feed.back("Gửi giáo án cho tổ trưởng")
    assert isl.states[-1][0] == "thinking" and feed.task.question == "Gửi giáo án cho tổ trưởng"
