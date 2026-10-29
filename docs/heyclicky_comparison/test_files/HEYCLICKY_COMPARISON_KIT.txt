# Bộ so sánh HeyClicky trên các tình huống của mẹ (v0)

Ngày soạn: 27/10/2026.

**Trạng thái:** Claude soạn, chưa chạy. Bộ này chỉ dùng cho **một lượt thử ngắn** trên máy của founder. Đây chưa phải kiểm chứng lớn, và chưa đại diện cho máy của mẹ.

**File giả:** `HEYCLICKY_TEST_FILES/Giáo án mẫu Âm nhạc 8.docx`. Đây là template có bảng. Trong file có dòng đánh dấu **"BẢN MẪU TỔ TRƯỞNG GỬI — CHƯA ĐIỀN"** để phân biệt bản gốc với bản đã sửa.

**Liên quan:** log thảo luận, mục "Cập nhật cạnh tranh: HeyClicky chính thức đã có bản Windows"; các tình huống 6, 8, 9, 12, 16 trong 16 tình huống.

---

## 0. Nguyên tắc chạy

1. **Chỉ dùng file giả và người nhận giả.** "Tổ trưởng" trong lượt thử là mục chat tự gửi cho chính mình trên Zalo; cần kiểm tra tên mục này trên Zalo PC của bạn, có thể là "Cloud của tôi". Không bao giờ gửi cho người thật.
2. **Quyền riêng tư:**
   - Theo lời hãng, ảnh chụp màn hình được gửi lên cloud, không lưu ảnh gốc, nhưng **có lưu phần phân tích và câu hỏi**.
   - Trước khi chạy, đóng các cửa sổ có thông tin cá nhân.
   - Danh sách chat bên trái của Zalo vẫn hiện tên người thật. Bạn tự quyết có chấp nhận điều này không, hoặc thu hẹp cửa sổ Zalo lại.
3. **Bạn đóng vai mẹ:**
   - Chỉ làm đúng điều tutor nói. Không dùng hiểu biết của mình để tự tìm giúp.
   - Khi chỉ dẫn mơ hồ (ví dụ "ở góc trên bên trái"), hỏi lại **một lần** như mẹ sẽ hỏi: "Ở đâu?". Nếu vẫn mơ hồ, làm theo cách mẹ đoán, rồi ghi lại lần đó vào C5.
   - Trả lời các câu tutor hỏi **theo kịch bản trả lời dựng sẵn** ở từng tác vụ. Nhờ vậy, sau này bản thử của bạn nhận đúng cùng thông tin.
4. **Ghi đáp án trước** khi bắt đầu từng tác vụ (ô "Đáp án ghi trước").
5. **Mỗi tác vụ chạy một lần**, tối đa **6 lượt nói hoặc 10 phút**, cái nào đến trước thì dừng.
   - Gói Free có 25 lượt talk và 25 lượt agent mỗi tháng (theo trang của hãng). Ba tác vụ, mỗi tác vụ tối đa 6 lượt, là 18 lượt talk.
   - Tác vụ T1b dùng lượt agent.
6. **Nói câu yêu cầu bằng giọng**, đúng nguyên văn trong kịch bản. Nếu HeyClicky có ô gõ chữ, chỉ dùng khi giọng nói thất bại hai lần, và ghi lại.

---

## 1. Ghi môi trường (điền trước khi chạy)

| Mục | Giá trị |
|---|---|
| Ngày, giờ |  |
| Phiên bản HeyClicky (Windows) |  |
| Đã đăng nhập gói | Free / Pro |
| Ngôn ngữ cài đặt trong HeyClicky (nếu có) |  |
| Windows 11 build |  |
| Ngôn ngữ giao diện Windows | Tiếng Việt / Tiếng Anh |
| Tỉ lệ hiển thị | 100% / 125% / 150% |
| Phiên bản Zalo PC |  |
| Thư mục Zalo tự lưu file (xem trong cài đặt Zalo) |  |
| Bản Word (Microsoft 365 / Office …) và ngôn ngữ của Word |  |
| Trình duyệt mặc định và phiên bản |  |
| Micro dùng |  |

Máy mẹ dùng giao diện tiếng Việt. Nếu máy bạn để tiếng Anh, đó là **một giới hạn** của lượt thử, nhớ ghi lại.

---

## 2. Chuẩn bị chung (làm một lần)

1. Trên Windows, gửi file `Giáo án mẫu Âm nhạc 8.docx` vào mục chat tự gửi trên Zalo. File đã nằm sẵn trong thư mục OneDrive này.
2. Tạo một Google Sheet trống tên **"Bảng kê khai thi đua – GIẢ"** trong tài khoản của bạn, rồi gửi link vào cùng mục chat Zalo.
3. Cài HeyClicky bản mới nhất cho Windows, đăng nhập, kiểm tra micro, xem trong cài đặt có chọn ngôn ngữ không, và ghi vào mục 1.
4. Dọn trạng thái: trong các thư mục Downloads, Desktop, Documents và thư mục của Zalo, **không được có sẵn bản nào** của file giáo án giả.

---

## 3. Tác vụ T1: "Bản trắng" (tình huống 6/12)

**Vì sao dàn cảnh theo đường E:** đây là đường bạn đã xác nhận từng xảy ra với mẹ. Mẹ mở file "gần đây nhất" trong Explorer, sửa và lưu bằng Ctrl+S, nhưng Zalo vẫn trỏ về bản gốc. Đường này dùng đúng thói quen Ctrl+S của mẹ.

**Dàn cảnh**
1. Trong chat Zalo, bấm vào **thân tin nhắn** chứa file giáo án. Zalo tự tải về và mở bằng Word. Đóng Word, không sửa gì.
2. Bấm **icon tải** trên tin nhắn đó. Trong hộp lưu, giữ nguyên thư mục và tên được gợi ý (bản có đuôi (1)). Ghi lại hộp thoại hiện gì.
3. Mở Explorer tới thư mục vừa lưu, **nhấp đúp file ở trên cùng** (bản mới nhất, tức bản (1)). Trong Word, sửa như sau:
   - Thay dòng "BẢN MẪU TỔ TRƯỞNG GỬI — CHƯA ĐIỀN" bằng **"BẢN ĐÃ SỬA — GV TRẦN THỊ MẪU — 27/10"**.
   - Ô "Họ và tên giáo viên": **Trần Thị Mẫu**. Ô "Lớp dạy": **8A**.
   - Hàng "1. Khởi động", cột "Hoạt động của giáo viên": **Cho học sinh nghe bài hát mẫu**.
   - Lưu bằng **Ctrl+S**, rồi đóng Word.
4. Trong Zalo, bấm **icon thư mục** trên tin nhắn. Explorer sẽ tô sáng bản gốc, không có số. Nhấp đúp bản đó, Word hiện **bản trắng**.

**Trạng thái bắt đầu:** Word đang ở trước mặt, hiện bản trắng; Explorer mở phía sau; Zalo mở.

**Đáp án ghi trước**

| Mục | Ghi |
|---|---|
| Bản đúng (tên đầy đủ) | `Giáo án mẫu Âm nhạc 8 (1).docx` (sửa lại nếu tên thật khác) |
| Thư mục chứa bản đúng |  |
| Bản mồi nhử | `Giáo án mẫu Âm nhạc 8.docx` (bản gốc, đang mở) |
| Dấu hiệu nhận ra bản đúng | Dòng "BẢN ĐÃ SỬA — GV TRẦN THỊ MẪU — 27/10" |

**Câu nói đầu tiên (nói bằng giọng):**
> "Mẹ mở lại cái giáo án hôm qua mà nó vẫn vậy, mẹ làm rồi mà giờ không thấy đâu."

**Kịch bản trả lời dựng sẵn**

| Nếu tutor hỏi | "Mẹ" trả lời |
|---|---|
| Tên file là gì? | "Mẹ không nhớ, mẹ cứ mở cái mới nhất thôi." |
| Mẹ lưu ở đâu? | "Mẹ không biết, mẹ bấm lưu thôi." |
| Mẹ đã sửa gì? | "Mẹ điền tên mẹ với lớp 8A." |
| Mẹ có dùng "Lưu thành" / "Save As" không? | "Mẹ không biết cái đó." |
| File này đúng chưa? | Trả lời theo nội dung thật trên màn hình: thấy dòng "BẢN ĐÃ SỬA…" thì nói "Đúng rồi", không thấy thì nói "Không phải". |
| Câu khác ngoài kịch bản | Trả lời như mẹ: ngắn gọn, không dùng thuật ngữ, rồi ghi câu hỏi đó lại. |

**Kết thúc khi:** bản đúng được mở và "mẹ" xác nhận; hoặc hết 6 lượt hay 10 phút; hoặc tutor nói không tìm được.

### T1b (tùy chọn, dùng lượt agent): agent trên Windows có làm hộ trong app desktop không

- **Dàn cảnh:** đóng bản đúng, mở lại bản trắng, quay về trạng thái bắt đầu của T1.
- **Câu nói:** "HeyClicky agent, tìm giúp mẹ bản giáo án mẹ đã sửa hôm qua rồi mở lên."
- **Ghi lại:**
  - Agent có chạy được trên Windows không.
  - Có điều khiển chuột và bàn phím trong Explorer/Word không, hay chỉ làm việc trong trình duyệt.
  - Có hỏi trước khi làm không.
  - Kết quả cuối cùng.
- Tác vụ này trả lời trực tiếp câu "**Làm hộ trên Windows: chưa rõ**" trong log.

---

## 4. Tác vụ T2: "Link mở ở đâu" (tình huống 9, có thêm phần nhiều tab của tình huống 3)

**Dàn cảnh**
1. Mở trình duyệt mặc định, rồi đưa Zalo lên trước, phóng to toàn màn hình.
2. Trong chat Zalo, bấm link "Bảng kê khai thi đua – GIẢ". Nếu trình duyệt nhảy lên trước, bấm lại vào Zalo để Zalo ở trước.
3. Lặp lại bước 2 thêm **2 lần**. Kết quả là 3 tab cùng một bảng tính, và Zalo đang ở trước.

**Trạng thái bắt đầu:** Zalo ở trước; trình duyệt ở phía sau, có 3 tab trùng nhau.

**Đáp án ghi trước**

| Mục | Ghi |
|---|---|
| Link đã mở trong trình duyệt nào |  |
| Số tab trùng | 3 |
| Bước tiếp theo đúng | Đưa trình duyệt lên trước (bấm biểu tượng trên taskbar hoặc Alt+Tab). Tab nào cũng được vì là **cùng một bảng tính**. Có thể đóng các tab thừa. |

**Câu nói đầu tiên:**
> "Mẹ bấm cái link cô tổ trưởng gửi rồi mà không thấy gì hết."

**Kịch bản trả lời dựng sẵn**

| Nếu tutor hỏi | "Mẹ" trả lời |
|---|---|
| Link nào? | "Cái link trong Zalo đó." |
| Mẹ bấm mấy lần? | "Mẹ bấm mấy lần rồi mà không thấy." |
| Mẹ dùng trình duyệt nào? | "Mẹ không biết, cái google đó." |

**Kết thúc khi:** bảng tính hiện ra trước mặt "mẹ"; hoặc hết giới hạn.

**Ghi thêm cho mục tiêu học (C6):** tutor có giải thích rằng các tab là cùng một bảng tính và không cần bấm nhiều lần không? Ghi nguyên văn.

---

## 5. Tác vụ T3: "Xuất PDF để gửi" (tình huống 8/16)

**Dàn cảnh**
1. Mở **bản đúng** của T1 (bản có dòng "BẢN ĐÃ SỬA…") trong Word và để Word ở trước.
2. Kiểm tra trong thư mục **chưa có** file PDF nào của giáo án.
3. Zalo mở phía sau, đang ở mục chat tự gửi.

**Đáp án ghi trước**

| Mục | Ghi |
|---|---|
| Đường menu xuất PDF đúng trên Word của bạn (ghi theo đúng chữ hiện trên menu) |  |
| Thư mục PDF sẽ được lưu (mặc định) |  |
| Tên PDF mong đợi |  |
| Bước gửi trong Zalo | Đính kèm file → chọn đúng PDF → **xác nhận trước khi bấm Gửi** |

**Câu nói đầu tiên:**
> "Giờ mẹ muốn gửi bản PDF cái giáo án này cho cô tổ trưởng qua Zalo."

**Kịch bản trả lời dựng sẵn**

| Nếu tutor hỏi | "Mẹ" trả lời |
|---|---|
| Gửi cho ai, ở đâu? | "Cho cô tổ trưởng." Nếu tutor hỏi tiếp tên chat: "Cái 'Cloud của tôi' đó." (Đây là một chỗ lệch so với thực tế, ghi lại.) |
| Mẹ đã có bản PDF chưa? | "Mẹ chưa biết làm." |
| Lưu PDF ở đâu? | "Chỗ nào cũng được, miễn mẹ tìm lại được." |

**Kết thúc khi:** PDF đã được gửi vào mục chat tự gửi; hoặc hết giới hạn.

**Ghi riêng:** tutor có nhắc hoặc hỏi xác nhận **trước** khi "mẹ" bấm Gửi không.

---

## 6. Bảng chấm chi tiết

### 6.1 Thang điểm

**C1. Đúng đối tượng.** Ở T1 và T3 là đúng bản file; ở T2 là đúng chỗ link đã mở.
- **2**: chỉ ra hoặc mở đúng.
- **1**: chưa tìm ra, nhưng nói rõ là chưa chắc, hoặc hỏi đúng câu để thu hẹp.
- **0**: không trả lời được.
- **⚠ Sai im lặng**: khẳng định một bản sai, hoặc một chỗ sai, mà không báo là không chắc. Ghi cờ ⚠. **Đây là lỗi nặng nhất**, tính riêng, không bù được bằng điểm khác.

**C2. Tiếng Việt**
- **C2a. Hiểu câu nói tiếng Việt:** 2 = hiểu đúng ngay; 1 = hiểu sau khi nói lại; 0 = không hiểu hoặc hiểu sai.
- **C2b. Trả lời bằng tiếng Việt** (giọng hoặc chữ): 2 = tiếng Việt tự nhiên; 1 = tiếng Việt nhưng lẫn tiếng Anh hoặc khó nghe; 0 = trả lời bằng tiếng Anh.
- **C2c. Lời mẹ hiểu được:** 2 = câu ngắn, không có thuật ngữ, hoặc thuật ngữ có kèm giải thích bằng từ quen; 1 = có thuật ngữ không giải thích (Explorer, Downloads, tab…); 0 = mẹ không thể làm theo.

**C3. Bước tiếp theo**
- **C3a. Bước đúng:** 2 = đúng và cụ thể; 1 = đúng hướng nhưng thiếu hoặc mơ hồ; 0 = sai.
- **C3b. Chỉ đúng chỗ trên màn hình:** 2 = vẽ hoặc chỉ đúng phần tử cần bấm; 1 = đúng vùng nhưng mơ hồ (kiểu "góc trên bên trái"); 0 = chỉ sai hoặc không chỉ.
- **C3c. Không dẫn lòng vòng:** đếm số bước thừa so với đáp án.

**C4. An toàn**
- Có hỏi hoặc nhắc xác nhận trước khi gửi hoặc ghi đè không: Có / Không / Không phát sinh.
- Có thao tác nào ngoài ý muốn không: mô tả.

**C5. Công sức của "mẹ"**
- Số lượt nói.
- Thời gian tới khi xong (phút:giây).
- Số lần "mẹ" phải tự đoán vì chỉ dẫn mơ hồ.

**C6. Học (chỉ ghi chú, không chấm điểm):** tutor có giải thích *vì sao* đủ để lần sau mẹ tự làm được không? Ghi nguyên văn câu giải thích.

**Kết quả cuối:** Đạt mục tiêu / Đạt nhờ "mẹ" tự đoán / Không đạt.

### 6.2 Phiếu điểm

| Tiêu chí | T1 | T1b | T2 | T3 |
|---|---|---|---|---|
| C1 Đúng đối tượng (2/1/0) |  |  |  |  |
| ⚠ Sai im lặng (có/không) |  |  |  |  |
| C2a Hiểu tiếng Việt (0–2) |  |  |  |  |
| C2b Trả lời tiếng Việt (0–2) |  |  |  |  |
| C2c Lời mẹ hiểu được (0–2) |  |  |  |  |
| C3a Bước đúng (0–2) |  |  |  |  |
| C3b Chỉ đúng chỗ (0–2) |  |  |  |  |
| C3c Số bước thừa |  |  |  |  |
| C4 Xác nhận trước gửi/ghi đè |  |  |  |  |
| C4 Thao tác ngoài ý muốn |  |  |  |  |
| C5 Số lượt nói |  |  |  |  |
| C5 Thời gian (mm:ss) |  |  |  |  |
| C5 Số lần phải tự đoán |  |  |  |  |
| Kết quả cuối |  |  |  |  |

---

## 7. Ghi nguyên văn từng lượt

Mỗi tác vụ dùng một bảng như sau:

| Lượt | "Mẹ" nói | HeyClicky nói / vẽ gì | "Mẹ" làm gì | Màn hình sau đó |
|---|---|---|---|---|
| 1 |  |  |  |  |
| 2 |  |  |  |  |

Có thể chụp màn hình để làm bằng chứng, vì dữ liệu trong lượt thử là giả. Che danh sách chat Zalo trước khi lưu ảnh.

---

## 8. Ghi kết quả theo ba cột

Cột "Hãng công bố" chép từ trang của hãng, đối chiếu ngày 27/10/2026. Cột "Tự thử" chỉ điền sau khi đã chạy.

| Điểm cần biết | Hãng công bố | Tự thử | Chưa biết |
|---|---|---|---|
| Chỉ dẫn trên màn hình trên Windows | "draw answers in 2D and 3D" (changelog v1.1.1 Windows) |  |  |
| Agent làm hộ trong app desktop trên Windows | "HeyClicky drive" chỉ được mô tả "in a Mac app"; Windows có "agents that run in the background" |  |  |
| Hỏi trước khi làm | "asks, and with your yes…" (Mac) |  |  |
| Hiểu và trả lời tiếng Việt | Không nhắc trong các trang đã đọc |  |  |
| Tìm đúng bản file khi có nhiều bản | Không công bố |  |  |
| Biết link mở ở đâu, giải thích tab trùng | Không công bố |  |  |
| Xác nhận trước khi gửi | Không công bố riêng |  |  |
| Nhớ giữa các ngày | "remembers your conversations from day to day" | Không thử trong lượt này (cần ngày thứ hai) |  |
| Giới hạn gói Free | 25 lượt talk và 25 lượt agent mỗi tháng |  |  |

---

## 9. Sau khi chạy

- **Dọn dẹp:** các file tạo ra trong lượt thử là bản gốc tải từ Zalo, bản (1), file PDF, và có thể cả bản do agent tạo. Bạn tự xóa bằng tay sau khi đã ghi kết quả.
- **Chạy lại đúng bộ này** trên bản thử của bạn, cùng dàn cảnh, cùng câu nói và cùng kịch bản trả lời, để so trong cùng điều kiện.
- **Cách đọc kết quả, không kết luận quá mức:**
  - Nếu HeyClicky đạt cao ở cả ba tác vụ, kể cả phần tiếng Việt, thì phải xem lại hướng khác biệt **trước khi xây tiếp**.
  - Nếu HeyClicky trượt ở chỗ nào (ví dụ ⚠ ở T1, hoặc không hiểu tiếng Việt), đó là **ứng viên** chỗ hở, ghi là "một lượt thử trên máy founder". Đó chưa phải lợi thế, cho tới khi bản thử của bạn làm tốt hơn trong cùng điều kiện.
