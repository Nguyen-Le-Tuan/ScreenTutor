import json
import time

from screentutor.history import History, StepRecord, TaskRecord
from screentutor.memory import (HIDDEN, MAX_CONTEXT, Fact, Index, Memory, Note, is_clean, learn, local_note, overlap,
                                plain, record_text, scrub, terms)
from screentutor.tutor import KNOWN_BLOCK, Tutor, build_prompt

NOW = 1_800_000_000.0
DAY = 86400


def test_words_are_kept_with_and_without_accents_and_small_words_are_dropped():
    assert plain("Giáo Án Đại Số") == "giao an dai so"
    t = terms("Mẹ muốn xuất giáo án ra PDF")
    assert "giao" in t and "giáo" in t and "xuat" in t and "pdf" in t and "muon" not in t and "me" not in t
    assert "giao_an" in t


def test_a_question_finds_its_task_with_wrong_or_missing_accents():
    idx = Index()
    idx.add("a", "Xuất giáo án ra PDF gửi tiệm in", NOW - DAY, True)
    idx.add("b", "Mở bảng tính kê khai thi đua trong Zalo", NOW - DAY, True)
    assert idx.search("xuat giao an ra pdf", now=NOW)[0][0] == "a"
    assert idx.search("xuất giáo ăn ra PDF", now=NOW)[0][0] == "a"       # speech got an accent wrong
    assert idx.search("bang tinh ke khai", now=NOW)[0][0] == "b"


def test_nothing_similar_gives_nothing():
    idx = Index()
    idx.add("a", "Xuất giáo án ra PDF gửi tiệm in", NOW, True)
    idx.add("b", "Mở bảng tính kê khai thi đua trong Zalo", NOW, True)
    assert idx.search("Đổi hình nền máy tính thành màu xanh", now=NOW) == []
    assert idx.search("mẹ muốn làm cái này", now=NOW) == []              # only small words
    assert Index().search("giáo án", now=NOW) == []


def test_recent_and_finished_tasks_come_first_when_all_else_is_equal():
    idx = Index()
    idx.add("old", "Xuất giáo án ra PDF", NOW - 300 * DAY, True)
    idx.add("new", "Xuất giáo án ra PDF", NOW - DAY, True)
    assert idx.search("xuất giáo án PDF", now=NOW)[0][0] == "new"
    idx = Index()
    idx.add("left", "Xuất giáo án ra PDF", NOW, False)
    idx.add("done", "Xuất giáo án ra PDF", NOW, True)
    assert idx.search("xuất giáo án PDF", now=NOW)[0][0] == "done"


def test_a_task_can_be_replaced_and_removed():
    idx = Index()
    idx.add("a", "giáo án", NOW)
    idx.add("a", "bảng tính", NOW)
    assert idx.search("giáo án", now=NOW) == [] and idx.search("bảng tính", now=NOW)
    idx.remove("a")
    assert idx.search("bảng tính", now=NOW) == [] and not idx.length


def test_passwords_numbers_and_names_do_not_get_through():
    for text in ("mật khẩu là Hoa@1975", "password: abc123", "Mật khẩu của cô là 123456", "Số điện thoại 0912 345 678",
                 "gọi 0912345678 nhé", "+84 912 345 678", "email cogiao@example.com", "CCCD 012345678901",
                 "Nguyễn Thị Hoa điểm kém", "học sinh Trần Văn Nam nghỉ học", "em Lan lớp 7A", "mã OTP 456123"):
        assert not is_clean(text), text
        assert HIDDEN in scrub(text)


def test_ordinary_work_goes_through_unchanged():
    for text in ("Xuất giáo án ra PDF gửi tiệm in", "Hay nhận giáo án qua Zalo nhóm tổ", "Lớp 7A có 38 học sinh",
                 "Báo cáo tháng 11 năm 2026", "Mở Word trong thư mục Downloads", "Tải file từ Google Sheet"):
        assert is_clean(text), text


def _rec(id="t1", question="Xuất giáo án ra PDF", outcome="done", started=NOW):
    return TaskRecord(id, started, question, ["Mở File", "Chọn Export"], 2, [StepRecord("Bạn bấm File.")], outcome)


def test_the_record_sent_for_the_summary_is_filtered_and_short():
    rec = _rec(question="Gửi điểm em Lan cho số 0912345678")
    text = record_text(rec)
    assert "0912345678" not in text and "Lan" not in text and "Bạn bấm File." in text and "Mở File" in text
    rec.steps = [StepRecord("x" * 300) for _ in range(20)]
    assert len(record_text(rec)) <= 1500


def test_a_fact_is_used_only_once_it_has_come_up_again(tmp_path):
    m = Memory(tmp_path, clock=lambda: NOW)
    m.remember(Note("t1", "Xuất PDF", started_at=NOW, outcome="done"), ["Hay xuất giáo án ra PDF để gửi tiệm in"])
    assert m.context("đổi hình nền") is None
    m.remember(Note("t2", "Xuất PDF lần nữa", started_at=NOW, outcome="done"), ["Thường xuất giáo án ra PDF để gửi tiệm in"])
    assert len(m.facts) == 1 and m.facts[0].seen == 2 and m.facts[0].tasks == ["t1", "t2"]
    assert "tiệm in" in m.context("đổi hình nền")
    m.remember(Note("t2", "Xuất PDF lần nữa", started_at=NOW, outcome="done"), ["Hay xuất giáo án ra PDF để gửi tiệm in"])
    assert m.facts[0].seen == 2                                          # the same task is one sighting


def test_a_fact_with_a_name_or_a_number_is_not_kept(tmp_path):
    m = Memory(tmp_path, clock=lambda: NOW)
    m.remember(Note("t1", "x", started_at=NOW), ["Hay gọi cho 0912345678", "Chấm bài cho em Lan", "Hay dùng Zalo nhóm tổ"])
    assert [f.text for f in m.facts] == ["Hay dùng Zalo nhóm tổ"]
    assert "0912345678" not in (tmp_path / "profile.json").read_text(encoding="utf-8")


def test_the_context_has_similar_tasks_and_stays_within_its_limit(tmp_path):
    m = Memory(tmp_path, clock=lambda: NOW)
    for i in range(6):
        m.remember(Note(f"t{i}", f"Xuất giáo án số {i} ra PDF", path=["Bấm File", "Chọn Export", "Tạo PDF"] * 12,
                        started_at=NOW - i * DAY, outcome="done"))
    text = m.context("xuất giáo án ra PDF")
    assert text.count("Việc trước") <= 3 and "Bấm File > Chọn Export" in text and len(text) <= MAX_CONTEXT
    assert "hôm nay" in text and "xong" in text


def test_notes_and_facts_survive_a_restart_and_a_broken_file_is_skipped(tmp_path):
    m = Memory(tmp_path, clock=lambda: NOW)
    m.remember(Note("t1", "Xuất giáo án ra PDF", started_at=NOW, outcome="done"), ["Hay gửi file cho tiệm in"])
    (tmp_path / "note-bad.json").write_text("{", encoding="utf-8")
    again = Memory(tmp_path, clock=lambda: NOW)
    again.load()
    assert "t1" in again.notes and again.facts[0].text == "Hay gửi file cho tiệm in"
    assert again.index.search("xuất giáo án", now=NOW)


def test_a_task_without_a_note_can_still_be_found(tmp_path):
    m = Memory(tmp_path, clock=lambda: NOW)
    m.load([_rec(question="Mở bảng kê khai thi đua")])
    assert m.index.search("bảng kê khai", now=NOW)[0][0] == "t1"


def test_learning_keeps_a_plain_note_when_the_summary_fails_and_filters_what_comes_back(tmp_path):
    m = Memory(tmp_path, clock=lambda: NOW)
    learn(m, _rec("a"), lambda text: None)
    assert m.notes["a"].title == "Xuất giáo án ra PDF"
    answer = {"title": "Xuất PDF cho Nguyễn Thị Hoa", "apps": ["Word"], "path": ["Mở File"], "result": "Xong",
              "keywords": ["pdf"], "facts": ["Hay xuất PDF"]}
    learn(m, _rec("b"), lambda text: answer)
    assert m.notes["b"].title == f"Xuất PDF cho {HIDDEN}" and m.notes["b"].apps == ["Word"] and m.facts[0].text == "Hay xuất PDF"


def test_clearing_the_history_takes_the_knowledge_base_with_it(tmp_path):
    h = History(tmp_path)
    rec = h.start("Xuất giáo án ra PDF")
    m = Memory(tmp_path / "memory", clock=lambda: NOW)
    m.remember(local_note(rec), ["Hay xuất PDF"])
    assert (tmp_path / "memory" / "profile.json").exists()
    assert h.clear() == 1 and not (tmp_path / "memory").exists()
    m.forget()
    assert m.context("xuất giáo án") is None and not m.facts and not m.notes


def test_notes_are_not_mistaken_for_tasks(tmp_path):
    h = History(tmp_path)
    rec = h.start("Xuất giáo án ra PDF")
    Memory(tmp_path / "memory").remember(local_note(rec))
    assert [r.id for r in h.tasks()] == [rec.id]


def test_finding_a_task_takes_under_50_ms_with_a_full_history():
    idx = Index()
    for i in range(500):
        idx.add(str(i), f"Xuất giáo án môn {i} ra PDF gửi tổ {i % 7} bằng Zalo rồi lưu vào thư mục {i % 13}", NOW - i * DAY, True)
    started = time.perf_counter()
    for _ in range(10):
        idx.search("xuất giáo án ra PDF gửi tổ trưởng", now=NOW)
    assert (time.perf_counter() - started) / 10 < 0.05


def test_the_prompt_carries_what_is_known_only_when_there_is_something():
    assert "Những gì đã biết" not in build_prompt("x")
    assert "Những gì đã biết" not in build_prompt("x", task=False)
    text = build_prompt("x", known="- Hay gửi file cho tiệm in")
    assert text.endswith("- Hay gửi file cho tiệm in") and text.startswith(build_prompt("x")) and "{known}" in KNOWN_BLOCK


def test_the_summary_is_words_only_and_a_failure_is_none():
    import httpx

    seen = {}

    def handler(request):
        seen.update(json.loads(request.content))
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps({"title": "Xuất PDF"})}}]})

    t = Tutor("k")
    t._http = httpx.Client(base_url="https://x", transport=httpx.MockTransport(handler))
    assert t.summarise("Câu hỏi: xuất PDF") == {"title": "Xuất PDF"}
    assert isinstance(seen["messages"][0]["content"], str) and "image" not in json.dumps(seen["messages"])
    t._http = httpx.Client(base_url="https://x", transport=httpx.MockTransport(lambda r: httpx.Response(400, text="no")))
    assert t.summarise("x") is None


def test_overlap_ignores_small_words():
    assert overlap("Hay gửi file cho tiệm in", "Thường gửi file cho tiệm in") >= 0.6
    assert overlap("Hay gửi file cho tiệm in", "Hay mở Zalo nhóm tổ") < 0.6
    assert Fact("x").seen == 1
