"""Generate synthetic calibration screenshots with known target boxes.

Usage: python -m grounding_test.tools.make_calibration grounding_test/calibration

Each image has the same layout expressed in fractions of the canvas, so the
ground-truth boxes are known exactly. Target B sits at x > 1000 px on the
1920-wide image, which separates a pixel answer from a 0-1000 normalized one.
"""
import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

REG = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

# (id, kind, label, x_frac, y_frac, w_px_at_1920, h_px_at_1920, question, size_class)
TARGETS = [
    ("A", "button", "Mở giáo án", 0.08, 0.14, 260, 64,
     "Bấm vào nút 'Mở giáo án'.", "lớn"),
    ("B", "button", "Gửi cho tổ trưởng", 0.80, 0.84, 300, 64,
     "Bấm vào nút 'Gửi cho tổ trưởng'.", "lớn"),
    ("C", "button", "Xuất PDF", 0.62, 0.46, 150, 44,
     "Bấm vào nút 'Xuất PDF'.", "vừa"),
    ("D", "folder", "", 0.30, 0.70, 26, 22,
     "Bấm vào biểu tượng thư mục màu vàng nhỏ ở phía dưới bên trái.", "nhỏ"),
    ("E", "close", "×", 0.982, 0.018, 22, 22,
     "Bấm vào nút X nhỏ ở góc trên bên phải để đóng.", "nhỏ"),
]

DISTRACTORS = [
    ("button", "Lưu", 0.08, 0.30, 150, 44),
    ("button", "Đóng", 0.80, 0.70, 150, 44),
    ("button", "Mở thư mục", 0.40, 0.46, 200, 44),
    ("button", "Gửi file", 0.62, 0.84, 170, 44),
    ("box", "", 0.55, 0.70, 60, 50),  # a bigger yellow block, not a folder icon
]


def draw_button(d, box, label, size, fill="#2F6FDB"):
    d.rounded_rectangle(box, radius=8, fill=fill, outline="#1B4FA8", width=2)
    font = ImageFont.truetype(BOLD, size)
    tw = d.textlength(label, font=font)
    x1, y1, x2, y2 = box
    d.text(((x1 + x2 - tw) / 2, (y1 + y2 - size) / 2 - 2), label, font=font, fill="white")


def draw_folder(d, box):
    x1, y1, x2, y2 = box
    tab_w = (x2 - x1) * 0.45
    d.rectangle([x1, y1, x1 + tab_w, y1 + 5], fill="#E0A800")
    d.rectangle([x1, y1 + 4, x2, y2], fill="#F5C518", outline="#B8860B")


def render(width, height, out_dir):
    s = width / 1920
    img = Image.new("RGB", (width, height), "#F3F4F6")
    d = ImageDraw.Draw(img)

    # Fake title bar and a side panel so the image looks like an app window.
    d.rectangle([0, 0, width, int(40 * s)], fill="#DADDE3")
    d.text((int(16 * s), int(10 * s)), "Ứng dụng thử nghiệm (ảnh hiệu chuẩn)",
           font=ImageFont.truetype(REG, max(12, int(18 * s))), fill="#333333")
    d.rectangle([0, int(40 * s), int(220 * s), height], fill="#E8EAEE")
    side_font = ImageFont.truetype(REG, max(11, int(16 * s)))
    for i, name in enumerate(["Tin nhắn", "Danh bạ", "Tệp", "Cài đặt"]):
        d.text((int(24 * s), int((80 + 50 * i) * s)), name, font=side_font, fill="#444444")

    def box_for(xf, yf, w, h):
        x1 = round(xf * width)
        y1 = round(yf * height)
        return [x1, y1, x1 + max(12, round(w * s)), y1 + max(12, round(h * s))]

    for kind, label, xf, yf, w, h in DISTRACTORS:
        b = box_for(xf, yf, w, h)
        if kind == "button":
            draw_button(d, b, label, max(12, int(20 * s)), fill="#5B6B7F")
        else:
            d.rectangle(b, fill="#F5C518", outline="#B8860B")

    truth = []
    for tid, kind, label, xf, yf, w, h, question, size_class in TARGETS:
        b = box_for(xf, yf, w, h)
        if kind == "button":
            draw_button(d, b, label, max(12, int(22 * s)))
        elif kind == "folder":
            draw_folder(d, b)
        else:
            d.rectangle(b, fill="#E5484D")
            f = ImageFont.truetype(BOLD, max(10, int(18 * s)))
            tw = d.textlength(label, font=f)
            d.text(((b[0] + b[2] - tw) / 2, b[1] - 1), label, font=f, fill="white")
        truth.append({
            "id": tid,
            "question_vi": question,
            "box_px": b,
            "center_px": [round((b[0] + b[2]) / 2), round((b[1] + b[3]) / 2)],
            "center_if_0_1000": [round((b[0] + b[2]) / 2 / width * 1000),
                                 round((b[1] + b[3]) / 2 / height * 1000)],
            "size_class": size_class,
        })

    name = f"cal_{width}x{height}"
    img.save(out_dir / f"{name}.png")
    (out_dir / f"{name}.truth.json").write_text(
        json.dumps({"image": f"{name}.png", "width": width, "height": height,
                    "targets": truth}, ensure_ascii=False, indent=2),
        encoding="utf-8")
    return name, truth


if __name__ == "__main__":
    out = Path(sys.argv[1])
    out.mkdir(parents=True, exist_ok=True)
    for w, h in [(1920, 1080), (1366, 768)]:
        name, truth = render(w, h, out)
        print(name, [(t["id"], t["box_px"]) for t in truth])
