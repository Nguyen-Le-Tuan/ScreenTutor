"""A made-up Zalo screen for the big-task tests (T12, plan section 7.2). Every name and word is invented.

The founder's two examples of a big task (02/11): a long message with numbered steps that
needs scrolling, and a principal's message with files and links. The window is drawn on a
tall canvas and cut at a scroll position, so the same message can be seen part by part,
with the true box of each message known exactly.

  .venv/bin/python -m tutor_eval.fake_zalo out_dir     # writes the pictures, for checking by eye
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

W, H = 1920, 1080
TASKBAR_H = 48
BAR_W, LIST_W = 64, 344
CHAT_X = BAR_W + LIST_W
HEADER_H, INPUT_H = 68, 110
BLUE, LIST_BG, CHAT_BG = (0, 104, 255), (255, 255, 255), (226, 233, 241)
INK, SOFT, LINE = (8, 27, 58), (112, 124, 145), (225, 229, 235)
FONT_DIR = "/usr/share/fonts/truetype/noto/"
FONT = FONT_DIR + "NotoSans-Regular.ttf"
BOLD = FONT_DIR + "NotoSans-Bold.ttf"


def font(px: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(BOLD if bold else FONT, px)


BODY = font(18)
SMALL = font(14)
LINE_H = 28
BUBBLE_W = 520


def wrap(text: str, width: int, f=BODY) -> list[str]:
    lines = []
    for para in text.split("\n"):
        line = ""
        for word in para.split():
            trial = f"{line} {word}".strip()
            if f.getlength(trial) > width and line:
                lines.append(line)
                line = word
            else:
                line = trial
        lines.append(line)
    return lines


@dataclass
class Message:
    who: str
    text: str = ""
    file: str = ""        # a file bubble, or
    link: str = ""        # a link bubble
    mine: bool = False


@dataclass
class Chat:
    title: str
    messages: list[Message]
    canvas: Image.Image = None
    boxes: list[tuple[int, int, int, int]] = field(default_factory=list)   # on the canvas
    contacts: list[str] = field(default_factory=list)                      # the chat list, when it is not the usual one


def draw_chat(chat: Chat) -> Chat:
    """All the messages on one tall strip; boxes are the bubbles."""
    width = W - CHAT_X
    canvas = Image.new("RGB", (width, 3200), CHAT_BG)
    d = ImageDraw.Draw(canvas)
    y = 24
    for m in chat.messages:
        d_x = width - BUBBLE_W - 40 if m.mine else 76
        if not m.mine:
            d.ellipse((24, y, 64, y + 40), fill=(150, 170, 200))
            d.text((44, y + 20), m.who[:1], font=font(18, True), fill="white", anchor="mm")
        if m.file:
            h = 92
            d.rounded_rectangle((d_x, y, d_x + 460, y + h), 10, fill="white")
            ext = m.file.rsplit(".", 1)[-1].upper()
            d.rounded_rectangle((d_x + 16, y + 16, d_x + 76, y + 76), 8, fill=(39, 110, 241) if ext == "DOCX" else (31, 163, 90))
            d.text((d_x + 46, y + 46), ext[:4], font=font(14, True), fill="white", anchor="mm")
            d.text((d_x + 92, y + 22), m.file, font=font(17, True), fill=INK)
            d.text((d_x + 92, y + 52), "1,2 MB", font=SMALL, fill=SOFT)
            box = (d_x, y, d_x + 460, y + h)
        elif m.link:
            lines = wrap(m.text, BUBBLE_W - 32) if m.text else []
            h = 24 + 26 + LINE_H * len(lines) + 12
            d.rounded_rectangle((d_x, y, d_x + BUBBLE_W, y + h), 10, fill="white")
            yy = y + 12
            d.text((d_x + 16, yy), m.link, font=BODY, fill=BLUE)
            yy += 32
            for ln in lines:
                d.text((d_x + 16, yy), ln, font=BODY, fill=INK)
                yy += LINE_H
            box = (d_x, y, d_x + BUBBLE_W, y + h)
        else:
            lines = wrap(m.text, BUBBLE_W - 32)
            head = 0 if m.mine else 26
            h = 12 + head + LINE_H * len(lines) + 30
            d.rounded_rectangle((d_x, y, d_x + BUBBLE_W, y + h), 10, fill=(229, 239, 255) if m.mine else "white")
            yy = y + 12
            if not m.mine:
                d.text((d_x + 16, yy), m.who, font=font(15, True), fill=SOFT)
                yy += head
            for ln in lines:
                d.text((d_x + 16, yy), ln, font=BODY, fill=INK)
                yy += LINE_H
            d.text((d_x + 16, yy + 4), "08:15", font=font(12), fill=SOFT)
            box = (d_x, y, d_x + BUBBLE_W, y + h)
        chat.boxes.append(box)
        y += h + 14
    chat.canvas = canvas.crop((0, 0, width, y + 20))
    return chat


def chrome(chat: Chat) -> Image.Image:
    img = Image.new("RGB", (W, H), LIST_BG)
    d = ImageDraw.Draw(img)
    bottom = H - TASKBAR_H
    d.rectangle((0, 0, BAR_W, bottom), fill=BLUE)
    for i in range(5):
        d.rounded_rectangle((18, 80 + i * 66, 46, 108 + i * 66), 7, outline="white", width=2)
    d.rectangle((BAR_W, 0, CHAT_X, bottom), fill=LIST_BG)
    d.rounded_rectangle((BAR_W + 14, 18, CHAT_X - 14, 52), 8, fill=(234, 237, 240))
    d.text((BAR_W + 30, 26), "Tìm kiếm", font=SMALL, fill=SOFT)
    names = chat.contacts or [chat.title, "Cloud của tôi", "Tổ trưởng (tên giả)", "Ban giám hiệu (tên giả)",
                              "Phụ huynh lớp 7A (tên giả)", "Công đoàn trường (tên giả)", "Nhóm Thử Nghiệm"]
    for i, name in enumerate(names):
        y = 74 + i * 78
        if i == 0:
            d.rectangle((BAR_W, y, CHAT_X, y + 78), fill=(229, 239, 255))
        d.ellipse((BAR_W + 16, y + 14, BAR_W + 66, y + 64), fill=(170, 186, 210))
        d.text((BAR_W + 80, y + 16), name, font=font(16, True), fill=INK)
        d.text((BAR_W + 80, y + 44), "Tin nhắn thử nghiệm", font=SMALL, fill=SOFT)
    d.rectangle((CHAT_X, 0, W, HEADER_H), fill="white")
    d.line((CHAT_X, HEADER_H, W, HEADER_H), fill=LINE)
    d.ellipse((CHAT_X + 16, 12, CHAT_X + 60, 56), fill=(170, 186, 210))
    d.text((CHAT_X + 74, 12), chat.title, font=font(18, True), fill=INK)
    d.text((CHAT_X + 74, 40), "38 thành viên", font=SMALL, fill=SOFT)
    d.rectangle((CHAT_X, bottom - INPUT_H, W, bottom), fill="white")
    d.line((CHAT_X, bottom - INPUT_H, W, bottom - INPUT_H), fill=LINE)
    d.text((CHAT_X + 20, bottom - INPUT_H + 56), "Nhập tin nhắn tới " + chat.title, font=font(16), fill=SOFT)
    for i in range(5):
        d.rounded_rectangle((CHAT_X + 20 + i * 44, bottom - INPUT_H + 12, CHAT_X + 46 + i * 44, bottom - INPUT_H + 38), 5,
                            outline=SOFT, width=2)
    d.rectangle((0, bottom, W, H), fill=(240, 243, 248))
    for i in range(6):
        x = 760 + i * 52
        d.rounded_rectangle((x, bottom + 10, x + 30, bottom + 40), 6, fill=(0, 120, 212) if i == 0 else (120, 134, 156))
    d.text((W - 92, bottom + 6), "08:21", font=SMALL, fill=INK)
    return img


def view(chat: Chat, top: int) -> tuple[Image.Image, list[tuple[int, int, int, int]]]:
    """The screen with the chat scrolled top px down, and the true boxes of what shows, in screen px."""
    img = chrome(chat)
    y0, y1 = HEADER_H, H - TASKBAR_H - INPUT_H
    piece = chat.canvas.crop((0, top, W - CHAT_X, top + y1 - y0))
    img.paste(piece, (CHAT_X, y0))
    if piece.height and chat.canvas.height - top < y1 - y0:
        ImageDraw.Draw(img).rectangle((CHAT_X, y0 + chat.canvas.height - top, W, y1), fill=CHAT_BG)
    boxes = []
    for x1, by1, x2, by2 in chat.boxes:
        sy1, sy2 = by1 - top + y0, by2 - top + y0
        if sy2 > y0 and sy1 < y1:
            boxes.append((x1 + CHAT_X, max(sy1, y0), x2 + CHAT_X, min(sy2, y1)))
        else:
            boxes.append(None)
    return img, boxes


STUDY = draw_chat(Chat("Tổ Khoa Học (tên giả)", [
    Message("Cô Lan (tên giả)", "Chào cả tổ, cuối tuần này nhớ họp tổ nhé."),
    Message("Thầy Minh (tên giả)", "Vâng ạ, em đã nhận được thông báo."),
    Message("Cô Lan (tên giả)",
            "THÔNG BÁO BỒI DƯỠNG THƯỜNG XUYÊN (nội dung giả để thử nghiệm)\n"
            "Kính gửi quý thầy cô tổ Khoa Học. Theo kế hoạch của nhà trường, mỗi thầy cô cần hoàn thành khoá bồi dưỡng "
            "trực tuyến trước ngày 15 tháng 11. Các bước thực hiện như sau:\n"
            "Bước 1. Vào trang boiduong-thunghiem.example và đăng nhập bằng tài khoản giáo viên đã được cấp.\n"
            "Bước 2. Chọn mô đun số 3 có tên là Đánh giá học sinh theo năng lực.\n"
            "Bước 3. Xem hết video bài giảng của mô đun, tổng cộng khoảng 40 phút. Lưu ý không tua nhanh vì hệ thống sẽ "
            "không ghi nhận thời gian học.\n"
            "Bước 4. Làm bài kiểm tra cuối mô đun, gồm 20 câu trắc nghiệm, cần đạt từ 16 câu đúng trở lên. Thầy cô được "
            "làm lại tối đa 3 lần.\n"
            "Bước 5. Tải giấy chứng nhận hoàn thành về máy và lưu lại dưới dạng file PDF.\n"
            "Bước 6. Gửi file giấy chứng nhận vào nhóm Zalo của tổ để tổ trưởng tổng hợp.\n"
            "Thầy cô nào gặp khó khăn khi đăng nhập thì báo lại cho tổ trưởng trước ngày 10 tháng 11 để được cấp lại mật "
            "khẩu. Những thầy cô đã hoàn thành rồi thì không cần làm lại. Trân trọng cảm ơn quý thầy cô."),
]))
LONG_CHAT = draw_chat(Chat("Tổ Khoa Học (tên giả)", [
    Message("Cô Lan (tên giả)", "Chào cả tổ, cuối tuần này nhớ họp tổ nhé."),
    Message("Thầy Minh (tên giả)", "Vâng ạ, em đã nhận được thông báo."),
    Message("Cô Hà (tên giả)", "Tổ mình họp ở phòng nào vậy cô? Em sợ nhầm phòng như lần trước."),
    Message("Cô Lan (tên giả)", "Phòng 204 nhé cô, tầng hai dãy nhà mới."),
    Message("Thầy Minh (tên giả)", "Dạ, em sẽ có mặt sớm để chuẩn bị máy chiếu."),
    STUDY.messages[2],
]))
CONTACTS = ["Tổ Khoa Học (tên giả)", "Cloud của tôi", "Chị Mai (tên giả)", "Anh Phát (tên giả)", "Cô Hiền (tên giả)",
            "Chú Tâm (tên giả)", "Bạn Yến (tên giả)"]


def contact_row(i: int) -> tuple[int, int, int, int]:
    """The row of chat list entry i, in screen px."""
    return BAR_W, 74 + i * 78, CHAT_X, 152 + i * 78


STUDY_PARTS = ["đăng nhập trang bồi dưỡng", "chọn mô đun 3", "xem hết video", "làm bài kiểm tra",
               "tải giấy chứng nhận PDF", "gửi vào nhóm Zalo của tổ"]

PRINCIPAL = draw_chat(Chat("Giáo viên trường Thử Nghiệm (tên giả)", [
    Message("Thầy Hùng (tên giả)", "Sáng nay trường có họp giao ban lúc 7 giờ."),
    Message("Hiệu trưởng (tên giả)",
            "Các thầy cô đọc tin nhắn và các file sau để hoàn thành việc nhận xét và đóng góp ý kiến cho dự thảo quy "
            "chế chi tiêu nội bộ năm học mới (nội dung giả để thử nghiệm). Hạn chót là 17 giờ thứ Sáu tuần này.\n"
            "Cụ thể: thứ nhất, đọc file dự thảo quy chế. Thứ hai, ghi ý kiến vào phiếu góp ý theo mẫu đính kèm. "
            "Thứ ba, điền vào biểu mẫu trực tuyến ở đường link bên dưới. Thứ tư, nộp phiếu góp ý cho tổ trưởng."),
    Message("Hiệu trưởng (tên giả)", file="Du_thao_quy_che_GIA.docx"),
    Message("Hiệu trưởng (tên giả)", file="Phieu_gop_y_GIA.docx"),
    Message("Hiệu trưởng (tên giả)", file="Bang_tong_hop_GIA.xlsx"),
    Message("Hiệu trưởng (tên giả)", link="https://bieumau-thunghiem.example/gop-y",
            text="Biểu mẫu trực tuyến để điền ý kiến"),
    Message("Cô Hoa (tên giả)", "Em đã nhận được, cảm ơn thầy."),
]))
PRINCIPAL_PARTS = ["đọc file dự thảo", "ghi ý kiến vào phiếu góp ý", "điền biểu mẫu trực tuyến", "nộp phiếu cho tổ trưởng"]


def main(argv=None) -> None:
    out = Path((argv or sys.argv[1:])[0])
    out.mkdir(parents=True, exist_ok=True)
    for name, chat in (("study", STUDY), ("principal", PRINCIPAL)):
        for i, top in enumerate(range(0, max(chat.canvas.height - 300, 1), 420)):
            img, _ = view(chat, top)
            img.save(out / f"{name}_{i}.png")
    print(STUDY.canvas.height, PRINCIPAL.canvas.height, "->", out)


if __name__ == "__main__":
    main()
