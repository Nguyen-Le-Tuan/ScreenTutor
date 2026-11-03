import json

from tutor_eval import uia_probe as U

AREA = 1920 * 1080


def row(kind="hover", exe=r"C:\Users\x\AppData\Local\Programs\Zalo\Zalo.exe", name="Gửi", rect=(10, 10, 60, 40), ms=12.0):
    return {"kind": kind, "exe": exe, "name": name, "rect": list(rect), "ms": ms}


def test_apps_are_named_by_their_exe():
    assert U.app_of(r"C:\Program Files\Microsoft Office\root\Office16\WINWORD.EXE") == "Word"
    assert U.app_of("/x/brave.exe") == "Brave" and U.app_of("") == "?" and U.app_of(r"C:\a\notepad.exe") == "notepad.exe"


def test_a_small_box_is_one_control_and_the_whole_pane_is_not():
    assert U.small(row(), AREA)
    assert not U.small(row(rect=(0, 0, 1500, 900)), AREA)     # the chat pane
    assert not U.small(row(rect=(0, 0, 0, 0)), AREA)          # no box at all


def test_rules_per_app():
    rows = [row() for _ in range(8)] + [row(name=""), row(rect=(0, 0, 1500, 900))]   # 8/10 seen
    rows += [row(exe="WINWORD.EXE", ms=ms) for ms in (5, 6, 7, 8, 9, 10, 11, 12, 13, 250)]
    rows += [row(kind="find", exe="WINWORD.EXE", ms=ms) for ms in (40, 60, 200)]
    s = U.summarise(rows, AREA)
    assert s["Zalo"]["u1"] == 0.8 and s["Zalo"]["U1"] and s["Zalo"]["U2"] and s["Zalo"]["u3_median"] is None
    assert not s["Zalo"]["U3"]
    w = s["Word"]
    assert w["U1"] and w["u2_median"] == 9.5 and w["u2_p90"] == 13 and w["U2"]   # one slow read does not sink it
    assert w["u3_median"] == 60 and w["U3"]
    slow = U.summarise([row(ms=40.0) for _ in range(5)], AREA)["Zalo"]
    assert not slow["U2"]


def test_report_and_summary_read_several_files(tmp_path, capsys):
    a, b = tmp_path / "a.jsonl", tmp_path / "b.jsonl"
    a.write_text(json.dumps({"kind": "screen", "area": AREA}) + "\n" + json.dumps(row()) + "\n", encoding="utf-8")
    b.write_text(json.dumps(row(kind="click")) + "\n", encoding="utf-8")
    U.main(["summary", str(a), str(b)])
    out = capsys.readouterr().out
    assert "Zalo: 2 chỗ" in out and "U1 thấy đúng nút 100% ĐẠT" in out
    assert U.report({}) == "Chưa có dữ liệu."
