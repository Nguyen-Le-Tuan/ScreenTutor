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


def test_outcome_of_a_task():
    from screentutor.app import outcome_of
    from screentutor.session import Step

    done = [Step(1, "File", (1, 1)), Step(2, "Xong", None, True, True)]
    assert outcome_of(done, cancelled=False) == "done"
    assert outcome_of(done, cancelled=True) == "interrupted"  # a new question cut it off
    assert outcome_of([Step(1, "", None, error="timeout")], False) == "error"
    assert outcome_of([Step(1, "Bạn mở Zalo trước nhé.", None)], False) == "stopped"
    assert outcome_of([], False) == "stopped"


def test_feed_hands_the_recent_tasks_to_the_island():
    class Isl(FakeIsland):
        def update(self):
            self.updated = True

    isl = Isl()
    Feed(isl).recent([("hôm qua", "Mở link bảng tính")])
    assert isl.recent == [("hôm qua", "Mở link bảng tính")] and isl.updated
