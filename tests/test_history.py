import json
from datetime import datetime

from screentutor import history
from screentutor.history import History, when_label


class Clock:
    def __init__(self, t=1_762_100_000.0):
        self.t = t

    def __call__(self):
        self.t += 1
        return self.t


def test_a_task_is_one_file_written_as_it_goes(tmp_path):
    h = History(tmp_path, clock=Clock())
    rec = h.start("Mẹ muốn xuất giáo án ra PDF")
    assert rec.outcome == "unfinished" and len(list(tmp_path.glob("*.json"))) == 1
    h.add_step(rec, "Bạn bấm vào chữ File.", "File", latency_s=4.912)
    h.add_step(rec, "Xong rồi bạn nhé.", step_done=True, goal_done=True)
    h.finish(rec, "done")
    data = json.loads((tmp_path / f"{rec.id}.json").read_text(encoding="utf-8"))
    assert data["question"] == "Mẹ muốn xuất giáo án ra PDF" and data["outcome"] == "done"
    assert [s["say"] for s in data["steps"]] == ["Bạn bấm vào chữ File.", "Xong rồi bạn nhé."]
    assert data["steps"][0]["latency_s"] == 4.91 and data["ended_at"] > data["started_at"]
    assert not list(tmp_path.glob("*.tmp"))


def test_no_pictures_or_sound_are_kept(tmp_path):
    h = History(tmp_path, clock=Clock())
    rec = h.start("câu hỏi")
    h.add_step(rec, "Bạn bấm File.")
    keys = set(json.loads((tmp_path / f"{rec.id}.json").read_text(encoding="utf-8")))
    steps = set(json.loads((tmp_path / f"{rec.id}.json").read_text(encoding="utf-8"))["steps"][0])
    assert not {"image", "screenshot", "audio", "png"} & (keys | steps)


def test_side_questions_are_their_own_tasks_newest_first(tmp_path):
    h = History(tmp_path, clock=Clock())
    big = h.start("Học cái trong Zalo")
    side = h.start("Nút lưu ở đâu")
    h.finish(big, "interrupted")
    h.finish(side, "done")
    assert [r.question for r in h.tasks()] == ["Nút lưu ở đâu", "Học cái trong Zalo"]
    assert [r.outcome for r in h.recent(1)] == ["done"]


def test_a_broken_file_is_skipped(tmp_path, capsys):
    h = History(tmp_path, clock=Clock())
    h.start("một")
    (tmp_path / "20990101-000000-zzzz.json").write_text("{ broken", encoding="utf-8")
    assert [r.question for r in h.tasks()] == ["một"]
    assert "hỏng" in capsys.readouterr().out
    assert History(tmp_path / "none").tasks() == []


def test_keeps_only_the_newest_and_clears_everything(tmp_path):
    h = History(tmp_path, clock=Clock(), keep=3)
    for i in range(5):
        h.start(f"câu {i}")
    assert [r.question for r in h.tasks()] == ["câu 4", "câu 3", "câu 2"]
    assert h.clear() == 3 and h.tasks() == []
    assert History(tmp_path / "none").clear() == 0


def test_unknown_outcome_becomes_stopped(tmp_path):
    h = History(tmp_path, clock=Clock())
    rec = h.start("câu")
    h.finish(rec, "whatever")
    assert h.tasks()[0].outcome == "stopped"


def test_when_label():
    now = datetime(2026, 11, 2, 21, 0).timestamp()
    assert when_label(datetime(2026, 11, 2, 14, 5).timestamp(), now) == "hôm nay 14:05"
    assert when_label(datetime(2026, 11, 1, 23, 59).timestamp(), now) == "hôm qua"
    assert when_label(datetime(2026, 10, 30, 8, 0).timestamp(), now) == "3 ngày trước"


def test_history_lives_next_to_the_app():
    assert history.DIR.name == "history" and history.DIR.parent == history.ROOT


def test_the_plan_and_the_part_are_kept(tmp_path):
    h = History(tmp_path)
    rec = h.start("Học cái trong Zalo")
    h.set_plan(rec, ["Đăng nhập", "Xem video", "Làm bài"], 2)
    back = h.tasks()[0]
    assert back.plan == ["Đăng nhập", "Xem video", "Làm bài"] and back.part == 2
