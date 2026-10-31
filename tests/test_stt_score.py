from stt_eval.score import edit_distance, score_one, syllables


def test_syllables_normalise_case_punctuation_and_digits():
    assert syllables("Lớp 6, lớp 7?") == ["lớp", "sáu", "lớp", "bảy"]


def test_edit_distance_counts_syllable_edits():
    assert edit_distance(["a", "b", "c"], ["a", "x", "c", "d"]) == 2


def test_score_keeps_meaning_despite_fillers_and_repeats():
    s = score_one("ủa cái file giáo án nằm ở đâu vậy", "cái file file giáo án nằm ở đâu")
    assert s["verdict"] == "còn" and s["may"] == 0


def test_score_flags_lost_meaning_and_may():
    s = score_one("sao mẹ đặt tên không được", "sao mày ăn cơm chưa")
    assert s["verdict"] == "mất"
    assert s["may"] == 1
