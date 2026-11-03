"""T14, the part that costs nothing: does her knowledge base find the right task, and keep secrets out?

  .venv/bin/python -m tutor_eval.memory_eval

Rule, fixed before the first run (02/11, plan section 7.2b). Every word below is made up. The
filter's samples and the questions were written before this ever ran, and MIN_COVER stays as it
is in memory.py. If a rule fails it is reported as failed; the data is not changed to pass it.
- R1: for the 10 questions that have a related task, it is in the top 3 for at least 9.
- R2: for the 5 questions with no related task, nothing is found for at least 4.
- R3: the filter stops all 20 samples with a password, a phone number or a name.
- R3b, added before the run: none of the 12 ordinary sentences is harmed.
- R4: a search over 500 tasks takes under 50 ms.
"""

from __future__ import annotations

import statistics
import time

from screentutor.memory import Index, is_clean

NOW = 1_800_000_000.0
DAY = 86400.0

# Made-up tasks of a made-up teacher, written the way the notes come out: name, apps, steps, keywords.
TASKS = {
    "pdf_in": "Xuất giáo án ra PDF gửi tiệm in. Word Zalo. Bấm File, chọn Export, tạo PDF, gửi vào chat tiệm in",
    "doi_co": "Đổi cỡ chữ giáo án cho to hơn. Word. Bôi đen chữ, chọn cỡ chữ 14. cỡ chữ font to",
    "le_trang": "Căn lề trang giáo án theo mẫu của trường. Word. Layout, Margins, Custom Margins. lề trang căn lề",
    "dau_trang": "Thêm số trang vào cuối giáo án. Word. Insert, Page Number, Bottom of Page. đánh số trang",
    "bang_word": "Chèn bảng phân phối chương trình vào Word. Word. Insert, Table, chọn số cột. bảng biểu",
    "ke_khai": "Mở bảng kê khai thi đua trong Zalo. Zalo Brave. Bấm link Google Sheet, điền tên vào bảng. thi đua",
    "diem_sheet": "Nhập điểm giữa kỳ lớp 7A vào Google Sheet. Brave. Mở sheet điểm, chọn tab 7A, gõ điểm. bảng điểm",
    "sheet_mau": "Tô màu dòng tiêu đề trong bảng tính. Excel. Bôi đen dòng, chọn màu nền. fill color",
    "excel_tong": "Tính tổng điểm bằng hàm SUM trong Excel. Excel. Chọn ô, gõ SUM, kéo xuống. công thức",
    "excel_in": "In bảng điểm Excel vừa một trang. Excel. Page Layout, Fit to Page, In. máy in",
    "zalo_tai": "Tải file từ Zalo về thư mục Tài liệu. Zalo. Bấm chuột phải vào file, Lưu về máy. tải về",
    "zalo_tam": "Sửa file nhưng không lưu được vì bản tạm Zalo. Word Zalo. Quay lại Zalo, tải về, mở bản thật. read-only",
    "zalo_nhom": "Gửi file ảnh vào nhóm Zalo của tổ. Zalo. Mở nhóm tổ, bấm kẹp giấy, chọn ảnh. đính kèm",
    "zalo_cloud": "Lưu tài liệu vào Cloud của tôi trong Zalo. Zalo. Mở Cloud của tôi, gửi file. lưu trữ",
    "zalo_tim": "Tìm lại tin nhắn cũ của tổ trưởng trong Zalo. Zalo. Bấm ô tìm kiếm, gõ tên. tìm tin nhắn",
    "boi_duong": "Đăng nhập trang bồi dưỡng thường xuyên. Brave. Mở trang, gõ tài khoản, chọn mô đun. khoá học",
    "video_bg": "Xem video bài giảng mô đun 3 tới hết. Brave. Bấm phát, chờ hết video. bồi dưỡng",
    "bai_ktra": "Làm bài kiểm tra cuối mô đun bồi dưỡng. Brave. Chọn đáp án, nộp bài. trắc nghiệm",
    "chung_nhan": "Tải giấy chứng nhận bồi dưỡng về máy. Brave. Bấm Tải về, lưu PDF. chứng chỉ",
    "mail_gui": "Gửi email báo cáo cho phòng giáo dục. Gmail. Soạn thư, đính kèm file, gửi. thư điện tử",
    "mail_doc": "Mở thư của nhà trường trong Gmail. Gmail. Bấm vào thư, tải file đính kèm. hộp thư",
    "drive_mo": "Mở tài liệu dùng chung trên Google Drive. Brave. Vào Drive, Shared with me, mở file. chia sẻ",
    "drive_up": "Tải bài giảng lên Google Drive của tổ. Brave. Bấm New, File upload, chọn file. upload",
    "pp_tao": "Làm bài trình chiếu PowerPoint cho tiết dạy. PowerPoint. New Slide, chèn chữ, chèn hình. slide",
    "pp_chieu": "Trình chiếu bài giảng trên máy chiếu. PowerPoint. Bấm Slide Show, From Beginning. tivi lớp",
    "pp_hinh": "Chèn hình ảnh vào slide bài giảng. PowerPoint. Insert, Pictures, chọn ảnh. tranh minh hoạ",
    "wifi": "Kết nối wifi của trường trên laptop. Windows. Bấm biểu tượng wifi, chọn mạng, gõ mật khẩu mạng. mạng",
    "loa": "Bật lại tiếng loa máy tính bị tắt. Windows. Bấm biểu tượng loa, kéo âm lượng. âm thanh",
    "tai_may": "Tìm file vừa tải về trong thư mục Downloads. File Explorer. Mở Downloads, xếp theo ngày. file mới",
    "doi_ten": "Đổi tên file giáo án cho đúng mẫu tổ. File Explorer. Bấm chuột phải, Rename. tên file",
    "thu_muc": "Tạo thư mục mới cho năm học 2026. File Explorer. Bấm chuột phải, New Folder. sắp xếp",
    "usb": "Chép file vào USB để mang lên trường. File Explorer. Cắm USB, kéo file sang. ổ đĩa",
    "pdf_doc": "Mở file PDF thông tư bằng trình đọc. Foxit. Bấm đúp file, phóng to chữ. đọc pdf",
    "pdf_word": "Chép chữ từ file PDF sang Word. Foxit Word. Bôi đen chữ, Copy, Paste. sao chép",
    "anh_chup": "Chụp màn hình gửi cho tổ trưởng. Windows Zalo. Bấm Print Screen, dán vào Zalo. ảnh màn hình",
    "lich": "Xem lịch họp hội đồng trên trang của trường. Brave. Mở trang trường, bấm Thông báo. lịch công tác",
    "ky_so": "Đóng dấu chữ ký vào file báo cáo. Word. Insert, Pictures, chọn ảnh chữ ký. ký tên",
    "dich": "Dịch đoạn tiếng Anh trong tài liệu. Brave. Mở Google Dịch, dán chữ. phiên dịch",
    "phong_chu": "Sửa lỗi phông chữ tiếng Việt khi mở file cũ. Word. Chọn Times New Roman. lỗi font",
    "cap_nhat": "Tắt thông báo cập nhật Windows đang hiện. Windows. Bấm Remind me later. update",
}

# Asked the way she talks, some without accents as speech-to-text can give them, some with other words.
RELATED = [
    ("Mẹ muốn xuất giáo án ra pdf để gửi tiệm in", {"pdf_in"}),
    ("lam sao doi co chu to hon", {"doi_co"}),
    ("Bảng kê khai thi đua mở ở đâu", {"ke_khai"}),
    ("Tải cái file trong Zalo về máy thế nào", {"zalo_tai", "zalo_tam"}),
    ("Nhập điểm lớp 7A vào sheet", {"diem_sheet"}),
    ("xem video bai giang boi duong", {"video_bg", "boi_duong"}),
    ("Lấy giấy chứng nhận bồi dưỡng", {"chung_nhan"}),
    ("Mẹ sửa file mà không lưu được", {"zalo_tam"}),
    ("Chèn hình vào bài giảng PowerPoint", {"pp_hinh", "pp_tao"}),
    ("Đổi tên file giáo án", {"doi_ten"}),
]
UNRELATED = [
    "Đặt báo thức ngày mai lúc năm giờ",
    "Thời tiết Hà Nội hôm nay thế nào",
    "Mua vé tàu đi Đà Nẵng",
    "Nấu canh chua cá lóc ra sao",
    "Xem bóng đá trực tiếp ở đâu",
]

SECRETS = [
    "mật khẩu là Thuy@1975", "Mật khẩu mới: hoa123456", "password: giaovien2026", "pass 123456abc", "mk là cogiao99",
    "mã OTP 482910", "Mã xác nhận là 773421", "Số điện thoại 0987 654 321", "gọi cô ấy 0987654321", "SĐT: 091.234.5678",
    "+84 912 345 678", "tài khoản ngân hàng 19034567890123", "CCCD 038175001234", "email thuyhoa75@example.com",
    "Nguyễn Văn Bình lớp 7A điểm kém", "học sinh Trần Thị Mai nghỉ học", "em Tuấn Anh chưa nộp bài", "Phạm Minh Đức 8B",
    "cháu Linh bị ốm", "Lê Hoàng Long học yếu",
]
ORDINARY = [
    "Xuất giáo án ra PDF gửi tiệm in", "Hay nhận giáo án qua Zalo nhóm tổ", "Lớp 7A có 38 học sinh", "Báo cáo tháng 11 năm 2026",
    "Mở Word trong thư mục Downloads", "Tải file từ Google Sheet", "Bấm nút Export ở góc trái", "Làm bài kiểm tra 20 câu",
    "Gửi vào nhóm Zalo của tổ", "Hay dùng Word để soạn giáo án", "Xem video 40 phút", "Đạt 16 câu đúng trở lên",
]


def main() -> None:
    idx = Index()
    for i, (doc, text) in enumerate(TASKS.items()):
        idx.add(doc, text, NOW - i * 3 * DAY, True)
    print(f"{len(TASKS)} việc giả, {len(RELATED)} câu có việc liên quan, {len(UNRELATED)} câu không có.")
    r1 = 0
    for q, want in RELATED:
        got = [d for d, _ in idx.search(q, 3, NOW)]
        r1 += bool(want & set(got))
        print(f"  {'đúng' if want & set(got) else 'SAI '} {q} -> {got}")
    r2 = 0
    for q in UNRELATED:
        got = [d for d, _ in idx.search(q, 3, NOW)]
        r2 += not got
        print(f"  {'đúng' if not got else 'SAI '} {q} -> {got}")
    leaks = [s for s in SECRETS if is_clean(s)]
    harmed = [s for s in ORDINARY if not is_clean(s)]
    big = Index()
    for i in range(500):
        big.add(str(i), TASKS[list(TASKS)[i % len(TASKS)]] + f" lần {i}", NOW - i * DAY, True)
    times = []
    for q, _ in RELATED * 3:
        t = time.perf_counter()
        big.search(q, 3, NOW)
        times.append((time.perf_counter() - t) * 1000)
    ok = {True: "đạt", False: "KHÔNG đạt"}
    print(f"R1 đúng việc trong top 3: {r1}/{len(RELATED)} (cần ≥ 9) {ok[r1 >= 9]}")
    print(f"R2 không lấy nhầm: {r2}/{len(UNRELATED)} (cần ≥ 4) {ok[r2 >= 4]}")
    print(f"R3 bộ lọc chặn: {len(SECRETS) - len(leaks)}/{len(SECRETS)} {ok[not leaks]} {leaks}")
    print(f"R3b câu thường không bị hại: {len(ORDINARY) - len(harmed)}/{len(ORDINARY)} {ok[not harmed]} {harmed}")
    print(f"R4 tìm trên 500 việc: trung vị {statistics.median(times):.1f} ms, lớn nhất {max(times):.1f} ms (cần < 50) "
          f"{ok[max(times) < 50]}")


if __name__ == "__main__":
    main()
