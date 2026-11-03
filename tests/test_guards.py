import os
import unicodedata

from screentutor import guards
from screentutor.guards import FRESH_S, TempCopy, ZaloCopy, opened_copy, sentence, temp_copies
from screentutor.state import WindowInfo, zalo_temp_dir
from tutor_eval.run import say_problems

NOW = 1_000_000.0
OLD = NOW - 3 * 86400
WORD_RO = WindowInfo("Giao an mau.docx  -  Read-Only - Word", "WINWORD.EXE")
COPY = TempCopy("Giao an mau.docx", OLD)


def test_word_showing_a_read_only_copy_from_zalo_is_caught():
    assert opened_copy(WORD_RO, [COPY], NOW) == COPY


def test_a_name_with_or_without_its_extension_and_in_other_words():
    for title in ("Giao an mau [Read-Only] - Word", "Giao an mau.docx (Chỉ đọc) - Word",
                  "Giao an mau.docx [Protected View] - Word", "GIAO AN MAU.DOCX - READ ONLY - WORD"):
        assert opened_copy(WindowInfo(title, "winword.exe"), [COPY], NOW) == COPY, title


def test_a_vietnamese_name_matches_in_either_unicode_form():
    nfd = unicodedata.normalize("NFD", "Giáo án mẫu Âm nhạc.docx")
    title = unicodedata.normalize("NFC", "Giáo án mẫu Âm nhạc.docx - Read-Only - Word")
    assert opened_copy(WindowInfo(title, "WINWORD.EXE"), [TempCopy(nfd, OLD)], NOW) is not None


def test_a_file_that_just_appeared_counts_whatever_the_title_says():
    plain = WindowInfo("Giao an mau.docx - Word", "WINWORD.EXE")
    assert opened_copy(plain, [TempCopy("Giao an mau.docx", NOW - 30)], NOW) is not None
    assert opened_copy(plain, [TempCopy("Giao an mau.docx", NOW - FRESH_S - 1)], NOW) is None


def test_her_real_copy_of_the_same_name_is_left_alone():
    # the point of the advice: she downloaded it properly and opens that one, days later
    assert opened_copy(WindowInfo("Giao an mau.docx - Word", "WINWORD.EXE"), [COPY], NOW) is None


def test_other_windows_and_other_files_are_left_alone():
    assert opened_copy(None, [COPY], NOW) is None
    assert opened_copy(WindowInfo("Giao an mau.docx - Read-Only", "brave.exe"), [COPY], NOW) is None
    assert opened_copy(WindowInfo("Bao cao.docx  -  Read-Only - Word", "WINWORD.EXE"), [COPY], NOW) is None
    assert opened_copy(WORD_RO, [], NOW) is None


def test_a_very_short_name_does_not_match_every_title():
    assert opened_copy(WORD_RO, [TempCopy("an.docx", NOW)], NOW) is None


def test_each_file_is_mentioned_once():
    guard = ZaloCopy()
    assert guard.check(WORD_RO, [COPY], NOW) == COPY
    assert guard.check(WORD_RO, [COPY], NOW + 2) is None     # she is still there
    assert guard.check(WORD_RO, [COPY], NOW + 900) is None   # she came back to it
    other = TempCopy("Bao cao.docx", OLD)
    title = WindowInfo("Bao cao.docx - Read-Only - Word", "WINWORD.EXE")
    assert guard.check(title, [COPY, other], NOW + 901) == other


def test_a_new_run_of_the_app_may_say_it_again():
    assert ZaloCopy().check(WORD_RO, [COPY], NOW) == COPY


def test_the_folder_is_read_one_level_down_and_a_missing_one_is_no_trouble(tmp_path):
    (tmp_path / "a.docx").write_text("x")
    (tmp_path / "~$a.docx").write_text("x")          # Word's lock file
    sub = tmp_path / "1234"
    sub.mkdir()
    (sub / "b.xlsx").write_text("x")
    deep = sub / "deep"
    deep.mkdir()
    (deep / "c.docx").write_text("x")
    os.utime(tmp_path / "a.docx", (OLD, OLD))
    found = {c.name: c for c in temp_copies(tmp_path)}
    assert set(found) == {"a.docx", "b.xlsx"} and found["a.docx"].born >= OLD
    assert temp_copies(tmp_path / "nothing") == []


def test_what_it_says_follows_the_rules_for_speech_and_the_button_setting():
    for shown in (True, False):
        assert say_problems(sentence(shown)) == []
    assert "nút tròn" in sentence(True) and "Ctrl" in sentence(False)
    assert "bản tạm" in sentence(True) and "file thật" in sentence(True) and "tải file về" in sentence(True)


def test_the_temp_folder_is_where_t5_saw_it():
    assert str(zalo_temp_dir("/t")).replace("\\", "/") == "/t/Zalo Temp/TempDownloads"
    assert zalo_temp_dir("") is None
    assert guards.EVERY_S <= 3
