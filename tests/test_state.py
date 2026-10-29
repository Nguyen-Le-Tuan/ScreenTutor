import os
import sys
import time
from datetime import datetime

import pytest

from screentutor.state import (RecentFile, Snapshot, WindowInfo, app_name, format_vi, recent_files,
                               take_snapshot, when_vi)


def test_app_name_maps_known_exes_and_falls_back_to_stem():
    assert app_name("WINWORD.EXE") == "Word"
    assert app_name("brave.exe") == "Brave"
    assert app_name("SomeTool.exe") == "SomeTool"
    assert app_name("") == "không rõ"


def test_when_vi_uses_today_and_yesterday():
    now = datetime(2026, 10, 29, 10, 0).timestamp()
    assert when_vi(datetime(2026, 10, 29, 8, 5).timestamp(), now) == "hôm nay 08:05"
    assert when_vi(datetime(2026, 10, 28, 21, 5).timestamp(), now) == "hôm qua 21:05"
    assert when_vi(datetime(2026, 10, 25, 7, 0).timestamp(), now) == "25/10 07:00"


def _touch(path, ts):
    path.write_text("x")
    os.utime(path, (ts, ts))


def test_recent_files_skips_old_locks_partials_and_other_types(tmp_path):
    now = time.time()
    dl = tmp_path / "Downloads"
    dl.mkdir()
    _touch(dl / "Giáo án (1).docx", now - 60)
    _touch(dl / "cũ.docx", now - 10 * 86400)
    _touch(dl / "~$Giáo án.docx", now - 30)
    _touch(dl / "bảng.xlsx.crdownload", now - 30)
    _touch(dl / "script.py", now - 30)
    _touch(dl / "ảnh.jpg", now - 3600)
    found = recent_files({"Downloads": str(dl)}, since=now - 72 * 3600)
    assert [f.name for f in found] == ["Giáo án (1).docx", "ảnh.jpg"]
    assert found[0].folder_label == "Downloads"


def test_recent_files_goes_one_level_down_only_where_asked(tmp_path):
    now = time.time()
    zalo = tmp_path / "Zalo Received Files"
    (zalo / "Truyền Anh").mkdir(parents=True)
    _touch(zalo / "Truyền Anh" / "bài.docx", now - 60)
    since = now - 3600
    assert recent_files({"Zalo Received Files": str(zalo)}, since) == []
    found = recent_files({"Zalo Received Files": str(zalo)}, since, depth={"Zalo Received Files": 1})
    assert found[0].folder_label == "Zalo Received Files\\Truyền Anh"


def test_format_vi_matches_the_t1_shape():
    snap = Snapshot(
        taken_at=datetime(2026, 10, 29, 10, 0).timestamp(),
        foreground=WindowInfo("Zalo - Nguyễn Lê Tuấn", "Zalo.exe", maximized=True),
        windows=[WindowInfo("Bảng kê khai thi đua - Tổ Nghệ Thuật - Google Sheets - Brave", "brave.exe"),
                 WindowInfo("Giáo án mẫu Âm nhạc 8.docx - Word", "WINWORD.EXE", minimized=True)],
        defaults={"link": "Brave", ".docx": "Word"},
        folders={"Downloads": r"C:\Users\Tuan\Downloads"},
        recent_files=[RecentFile("Giáo án mẫu Âm nhạc 8 (1).docx", "Downloads", "x",
                                 datetime(2026, 10, 28, 21, 5).timestamp())],
    )
    text = format_vi(snap)
    assert text.splitlines()[0] == ('- Cửa sổ đang ở trước mặt: Zalo (Zalo.exe), tiêu đề "Zalo - Nguyễn Lê Tuấn", '
                                    'đang phóng to.')
    assert '1) Brave (brave.exe), tiêu đề "Bảng kê khai thi đua' in text
    assert "2) Word (WINWORD.EXE)" in text and "đang thu nhỏ" in text
    assert "App mở mặc định: link: Brave; file .docx: Word." in text
    assert '"Giáo án mẫu Âm nhạc 8 (1).docx" trong Downloads, sửa hôm qua 21:05' in text


def test_format_vi_names_the_owner_chain_and_reports_errors():
    snap = Snapshot(foreground=WindowInfo("Save As", "WINWORD.EXE", owners=["Save As", "Giáo án.docx - Word"]),
                    folders={"Downloads": "D"}, errors={"app mặc định": "OSError: boom"})
    text = format_vi(snap)
    assert 'là hộp thoại của "Save As", nằm trên "Giáo án.docx - Word"' in text
    assert "Không có file tài liệu hay ảnh nào mới" in text
    assert "Không đọc được app mặc định: OSError: boom" in text


def test_desktop_in_front_is_not_reported_as_an_app():
    snap = Snapshot(foreground=WindowInfo("màn hình nền (Desktop)", "", kind="shell"))
    assert format_vi(snap) == "- Cửa sổ đang ở trước mặt: màn hình nền (Desktop), không phải cửa sổ app nào."


@pytest.mark.skipif(sys.platform == "win32", reason="checks the non-Windows guard")
def test_take_snapshot_refuses_off_windows():
    with pytest.raises(RuntimeError):
        take_snapshot()
