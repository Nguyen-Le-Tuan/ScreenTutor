# ScreenTutor

Trợ lý trên màn hình Windows giúp người mới dùng máy tính vừa làm xong việc, vừa dần hiểu và tự làm được. Dự án thi Meta Global AI Developer Hackathon (hạn nộp 4/11/2026).

Repo được xây theo từng thành phần. Mỗi thành phần được thử riêng trước khi ráp vào nhau. Hiện mới có một thành phần.

## Thành phần 1: phép thử grounding với model Meta (`grounding_test/`)

Phép thử này trả lời: model Meta có chỉ đúng chỗ cần bấm trên giao diện Windows không, theo quy ước toạ độ nào, và mất bao lâu, tốn bao nhiêu cho mỗi lần hỏi?

Script **chỉ gọi API và chấm điểm**. Nó không bấm chuột hay gõ phím trên máy nào.

| File | Vai trò |
|---|---|
| `config.py` | Endpoint, model, bảng giá, ngưỡng quyết định |
| `meta_api.py` | Hai cách hỏi. **M1:** computer use (Responses API, tool `computer`), chỉ đọc hành động đầu tiên. **M2:** image understanding, trả về JSON toạ độ |
| `scoring.py` | Chấm trúng / sát / trượt. Mỗi câu trả lời được chấm theo **cả hai quy ước**, pixel và thang 0–1000, vì docs Meta mâu thuẫn ở điểm này |
| `datasets.py` | Đọc ảnh hiệu chuẩn và 12 ca thật, chuẩn bị ảnh để gửi |
| `report.py` | Tổng hợp `calls.jsonl` thành `summary.md` |
| `run.py` | Dòng lệnh `check` / `plan` / `run` |
| `calibration/` | 2 ảnh tổng hợp có đáp án biết trước. Tạo lại bằng `tools/make_calibration.py` |
| `cases/cases.json` | Mô tả 12 ca thật và khung đúng. Ảnh `.png` của các ca **không commit**, vì repo công khai |

### Cài đặt

```bash
uv venv .venv && uv pip install --python .venv/bin/python -r requirements.txt
cp .env.example .env   # rồi điền MODEL_API_KEY
```

### Chạy

```bash
.venv/bin/python -m pytest -q                                         # kiểm tra logic chấm điểm, không gọi API
.venv/bin/python -m grounding_test.run check                          # key có hợp lệ không, model nào dùng được (không tốn tiền)
.venv/bin/python -m grounding_test.run plan --stage calibration       # xem trước sẽ gọi gì, ước tính chi phí
.venv/bin/python -m grounding_test.run run --stage calibration --yes  # bước 0: hiệu chuẩn
.venv/bin/python -m grounding_test.run run --stage cases --yes        # bước 1: 12 ca thật
.venv/bin/python -m grounding_test.run run --stage cases --models spark --methods m1 --resize 1366x768 --yes
.venv/bin/python -m grounding_test.run run --stage cases --only case_01,case_06,case_09,case_11 --lang en --yes
```

Kết quả nằm ở `grounding_test/results/<thời điểm>-<giai đoạn>/`, gồm `summary.md`, `calls.jsonl` và `raw/`. Thư mục này không được commit.

### Quyền riêng tư

- Chỉ dùng model **Standard**. Không dùng bản Contributor, vì Meta được phép dùng nội dung gửi tới bản đó để huấn luyện.
- Ảnh chụp màn hình thật và phản hồi gốc của API chỉ lưu trên máy.
- Key nằm trong `.env`. File này đã được gitignore.

### Tài liệu gốc

Kế hoạch giấy, các ngưỡng quyết định và nhật ký thảo luận nằm trong ghi chú Obsidian của founder (`GROUNDING_TEST_PLAN.md`), không nằm trong repo này.
