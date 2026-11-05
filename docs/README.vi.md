<p align="center"><img src="assets/hero.png" alt="Hình minh hoạ: ScreenTutor. Mẹ hỏi bằng tiếng Việt. Tutor chỉ từng chỗ bấm. Mẹ tự bấm." width="100%"></p>

<p align="center">
<a href="https://youtu.be/jDSKgcugi4U"><b>Video demo</b></a> ·
<a href="https://x.com/thanath1839/status/2118137790831501663"><b>Bài trên X</b></a> ·
<a href="#tutor-làm-gì"><b>Tutor làm gì</b></a> ·
<a href="#cách-hoạt-động"><b>Cách hoạt động</b></a> ·
<a href="#chạy-thử"><b>Chạy thử</b></a> ·
<a href="../README.md"><b>English</b></a>
</p>

# ScreenTutor (tiếng Việt)

**Tác tử hướng dẫn bằng giọng nói trên Windows: nhìn màn hình, chỉ từng chỗ một và kiểm từng bước, để một cô giáo lớn tuổi mới dùng máy tính tự làm xong việc của mình. Nó không bao giờ bấm thay.**

Dự án thi Meta Global AI Developer Hackathon (26/10 – 4/11/2026), dùng hai model của Meta: **Muse Spark 1.3** và **Muse Voice Transcribe**.

<p align="center">
<a href="https://youtu.be/jDSKgcugi4U"><img alt="Xem video demo 3 phút trên YouTube" src="https://img.shields.io/badge/Xem%20video%20demo-3%20ph%C3%BAt-FF0000?logo=youtube&logoColor=white&style=for-the-badge"></a>
<a href="https://x.com/thanath1839/status/2118137790831501663"><img alt="Đọc bài trên X" src="https://img.shields.io/badge/%C4%90%E1%BB%8Dc%20b%C3%A0i-tr%C3%AAn%20X-000000?logo=x&logoColor=white&style=for-the-badge"></a>
</p>

<p align="center"><img src="assets/demo.gif" alt="Bản quay màn hình thật trong MuseScore: câu hỏi tiếng Việt hiện thành phụ đề; sau đoạn chờ model (tua nhanh 8 lần, có nhãn trên hình) tutor nói việc có 3 phần, chấm đỏ và phím Ctrl + A hiện ra, người dùng tự bấm, cả bản nhạc chuyển xanh, viền sáng cho thấy tutor đang kiểm bước tiếp" width="100%"></p>
<p align="center"><sub>Bản quay màn hình thật trên Windows 11, 04/11/2026, cắt từ video demo. Đoạn chờ model tua nhanh 8 lần (có ghi trên hình); giọng tutor và cú bấm chạy tốc độ thường.</sub></p>

## Tóm tắt

- **Dành cho ai.** Mẹ tôi, một cô giáo người Việt mới dùng máy tính. Công việc của mẹ giờ đi qua Zalo, Word, Google Sheets và trình duyệt, và những chuyện nhỏ làm mẹ bị kẹt: giáo án sửa hôm qua "mất rồi" vì mẹ mở nhầm bản tạm, hay bấm link "không thấy mở" vì trang hiện ra sau một cửa sổ khác.
- **Tutor làm gì.** Mẹ hỏi thành tiếng, bằng tiếng Việt. ScreenTutor nhìn màn hình, nói một bước và đặt một dấu chấm lên đúng chỗ cần bấm. **Mẹ tự bấm; tutor không bao giờ bấm hay gõ thay.** Khi màn hình đứng yên, tutor kiểm bước vừa làm có đúng không rồi chỉ bước tiếp, cho tới khi xong việc.
- **Vai trò hai model Meta.** **Muse Voice Transcribe** nghe câu hỏi theo thời gian thực. **Muse Spark 1.3** đọc ảnh màn hình cùng một bản tóm tắt trạng thái Windows, quyết định chỉ vào đâu và nói gì, lập kế hoạch cho việc nhiều phần, và sau mỗi cú bấm thì kiểm bước đó và cả việc đã xong chưa.
- **Chạy thử.** Windows 10/11, Python 3.10+, micro và key Meta Model API. Xem [Chạy thử](#chạy-thử).

## Vấn đề

Câu hỏi của mẹ cho thấy mẹ bị kẹt ở đâu. Tám câu đã được ghi âm bằng chính giọng mẹ:

- **"Giáo án hôm qua mình sửa mất rồi."** Một file có thể có nhiều bản, và bản mẹ mở chưa chắc có phần đã sửa. Một đường dẫn tới chuyện này, đã xác nhận trên máy cài giống máy mẹ: bấm thẳng vào file trong Zalo thì Word mở *bản tạm chỉ đọc* trong `AppData\Local\Temp\Zalo Temp\TempDownloads`, nên phần sửa không bao giờ vào file thật.
- **"Bấm link mà không thấy gì."** Google Sheet thật ra đã mở, trong một cửa sổ trình duyệt nằm sau Zalo.
- Mẹ cần gửi file PDF cho tiệm in, gặp tên file "không hợp lệ", hay phải thêm một dòng vào bảng.

Với người biết chỗ bấm, mỗi việc chỉ vài cú bấm; với mẹ thì là ngõ cụt. Làm thay thì giải quyết được hôm nay; chỉ từng bước thì mai mẹ tự làm được.

## Tutor làm gì

1. **Mẹ hỏi bằng lời của mình.** Bấm nút micro tròn, hoặc giữ **Ctrl+Alt**, rồi nói tiếng Việt. Mẹ có thể trỏ chuột vào một chỗ, hoặc khoanh một vùng, rồi nói "cái này".
2. **Tutor đọc màn hình và cả máy.** Cùng với ảnh màn hình, tutor nhận một **bản tóm tắt trạng thái Windows**: những gì ảnh không cho thấy, như cửa sổ nào nằm sau cửa sổ nào, app mặc định, thư mục thật và các file mới nhất.
3. **Chỉ từng bước một.** Một giọng tiếng Việt nhẹ nhàng nói cần làm gì và vì sao, và dấu chỉ di chuyển đúng lúc giọng bắt đầu:
   - **chấm đỏ** đứng chờ cạnh chuột khi tutor đang xem, rồi bay tới đúng chỗ cần bấm;
   - **chấm vàng** khi cú bấm sẽ gửi đi hoặc ghi đè một file;
   - **khung** quanh chỗ cần đọc, phần còn lại của màn hình tối đi;
   - **con chuột nhỏ có bánh xe quay** ở chỗ cần cuộn;
   - phím tắt hiện thành phím, ví dụ **[Ctrl] + [A]**.
4. **Mẹ làm, tutor kiểm.** Tutor chờ màn hình đứng yên, kiểm bước vừa làm, hiện **dấu tích xanh** ở chỗ mẹ bấm, rồi chỉ bước tiếp.
5. **Lập kế hoạch cho việc nhiều phần.** Kế hoạch hiện trên dynamic island ở đầu màn hình, và tutor tự đi từ phần này sang phần kia, không cần hỏi lại. Khi việc cần làm nằm trong một tin nhắn dài, tutor bảo mẹ cuộn tới cuối và lập kế hoạch từ chính tin nhắn đó.
6. **Theo kịp mẹ.** Ngay trước khi nói, tutor so một ảnh màn hình mới với ảnh nó vừa dựa vào để trả lời. Nếu mẹ đã tự bấm trước, hoặc có hộp thoại mới mở, tutor im và xem lại.
7. **Tự lên tiếng khi thấy bẫy quen.** Khi Word đang mở bản tạm của Zalo, tutor nói một lần, chỉ dựa vào tín hiệu trên máy, và dẫn mẹ tới file thật nếu mẹ muốn.
8. **Nhớ việc của mẹ.** Sau mỗi việc, một ghi chú ngắn vào kho kiến thức trên máy mẹ, tìm ngay trên máy, để câu "gửi cái này cho tiệm in như lần trước" có nghĩa.
9. **Dừng khi mẹ bảo.** Một câu ngắn như "dừng" hay "để sau", hoặc dấu × trên island, sẽ dừng việc ngay trên máy, không gọi model.

Mục tiêu là mẹ tự làm xong việc, và thuộc đường đi qua mỗi lần làm.

## Cách hoạt động

<p align="center"><img src="assets/how-it-works.png" alt="Hình minh hoạ. Cách hoạt động: 1 mẹ hỏi (Muse Voice Transcribe), 2 tutor đọc màn hình (Muse Spark 1.3), 3 chấm và giọng cùng lúc (trên máy mẹ), 4 mẹ bấm và tutor kiểm (Muse Spark 1.3)" width="100%"></p>
<p align="center"><sub>Hình minh hoạ theo màu của app. Ảnh đầu trang cũng là hình minh hoạ; GIF ở trên là bản quay thật.</sub></p>

### Hai model Meta được dùng thế nào

| Model | Vai trò trong ScreenTutor | Vì sao chọn |
|---|---|---|
| **Muse Spark 1.3**: hiểu ảnh, trả JSON trên lưới 0–1000, stream, `reasoning_effort: "minimal"` | Một lần gọi trả về chỗ cần chỉ, câu cần nói, loại bước, khung cần đọc, kế hoạch và ghi chú. Sau khi mẹ làm, một lần gọi tiếp quyết định bước và việc đã xong chưa, tiếp theo là gì. Lần gọi thứ ba, chỉ có chữ, biến mỗi việc đã xong thành một ghi chú cho kho kiến thức. | So với Muse Wonder trên ảnh chụp thật có đánh nhãn của các app mẹ dùng, Spark chỉ đúng hơn và trả lời nhanh hơn. |
| **Muse Voice Transcribe**: WebSocket thời gian thực | Nút tròn dùng ENDPOINTING, để model tự nghe khi mẹ ngừng nói. **Ctrl+Alt** dùng PUSH_TO_TALK. Cả hai có bias tiếng Việt cùng từ khoá tên app và người nhà, và các đoạn ngắt ngắn được ghép thành một lượt. | Các câu hỏi ghi âm của mẹ giữ đúng ý khi có bias, từ khoá và ghép lượt. |

**Stream câu trả lời có cấu trúc.** API viết khoá JSON theo thứ tự chữ cái bất kể schema, và chữ hoa đứng trước. Vì vậy các khoá định vị bước được đặt tên `Box, Caution, Goal_done, Step_done, Target, X, Y`, sau đó là `say` và các khoá khác, các trường `task_*` ở cuối. Vị trí có ngay khi `Y` xong, giọng có thể bắt đầu ngay khi `say` xong, trong lúc kế hoạch và ghi chú vẫn đang về. Chấm bay đúng lúc tiếng đầu tiên phát ra, nên mẹ nghe và thấy bước cùng lúc.

**Phần chạy trên máy mẹ.** Chỉ dùng model hạng Standard, không dùng bản Contributor. Meta API không có chuyển chữ thành giọng nói hay model embedding, nên giọng đọc là **VieNeu-TTS v3 Turbo** (Apache-2.0) chạy trên CPU (int8), và kho kiến thức được tìm bằng BM25 ngay trên máy.

## Quyền riêng tư và an toàn

- **Không bao giờ bấm hay gõ thay.** Mẹ luôn là người thao tác. Cú bấm chỉ được *quan sát*, bằng cách đọc trạng thái nút chuột; không cài hook toàn hệ thống.
- **Không gửi gì cho tới khi mẹ hỏi**, bằng nút tròn hoặc Ctrl+Alt. Lúc đó giọng mẹ được gửi tới Muse Voice Transcribe. Trong một việc mẹ đã bắt đầu, mỗi bước gửi Muse Spark một ảnh màn hình và bản tóm tắt trạng thái, trong đó có tiêu đề cửa sổ và tên file gần đây. Giọng tutor được tạo ngay trên máy.
- **Chỗ mẹ trỏ chuột** được tính trên máy và gửi đi dưới dạng một dòng toạ độ, không bao giờ là hình.
- **Phần canh bản tạm của Zalo** chỉ đọc cửa sổ đang ở trước và tên file trong một thư mục. Nó không chụp màn hình và không gửi gì.
- **Sau mỗi việc, phần chữ được gửi tới Muse Spark** để tóm tắt, không kèm hình, và một câu hỏi mới có thể mang theo ghi chú ngắn của các việc tương tự trước đó. Một bộ lọc trên máy bỏ mật khẩu, số điện thoại, email và họ tên đầy đủ trước. Bộ lọc không bắt được hết, và không đụng tới ảnh màn hình.
- **Những gì ở lại trên máy mẹ:** ảnh từng bước (`tutor_runs/`), các việc (`history/`) và kho kiến thức (`history/memory/`), đều được gitignore. Một nút trên island xoá lịch sử và kho kiến thức. Ngoài GIF MuseScore ngắn ở trên, repo không chứa ảnh màn hình thật, bản quay hay câu trả lời gốc của API.
- Model được dặn đánh dấu cú bấm **gửi đi hoặc ghi đè**, để chấm chuyển vàng và câu nói báo trước điều sẽ xảy ra.

## Chạy thử

Windows 10/11, Python 3.10+, micro, loa và key Meta Model API. Mở PowerShell ở thư mục repo:

```powershell
py -m pip install -r requirements.txt
Copy-Item .env.example .env
# Trong Notepad, dán key sau MODEL_API_KEY= rồi lưu
notepad .env
.\ScreenTutor.bat
```

`ScreenTutor.bat` chạy `py -m screentutor.app` trong một cửa sổ thu nhỏ (bấm đúp vào file cũng được; đóng cửa sổ đó là tắt ScreenTutor). Lần chạy đầu tải mô hình giọng nói khoảng 250 MB. Sau đó bấm nút micro tròn, hoặc giữ **Ctrl+Alt**, rồi hỏi.

Phát triển cũng chạy được trên Linux: mọi phần riêng của Windows nằm sau giao diện nhỏ, kiểm được.

```bash
python -m pytest -q    # hơn 300 test, không cần mạng
```

## Lộ trình

- Chặn Enter, Tab và Delete khi cả tài liệu đang được chọn, để việc sửa cả tài liệu an toàn.
- Quay lại việc lớn ngay từ nút "Làm tiếp" trên island sau một câu hỏi phụ.
- Thử cùng mẹ trên chính việc của mẹ, để xem mẹ có cần ít trợ giúp hơn qua mỗi lần không.
- Thêm app, cấu hình màn hình và ngôn ngữ.

## Làm trong thời gian hackathon

Mọi thứ trong repo được viết trong thời gian sự kiện: commit đầu tiên ngày 27/10/2026, công việc kéo dài từ 28/10 tới 4/11/2026. Lịch sử commit cho thấy từng bước. ScreenTutor không tồn tại trước hackathon.

Không phải của dự án, dùng nguyên trạng qua gói hoặc API công khai: Muse Spark 1.3 và Muse Voice Transcribe của Meta qua Meta Model API; VieNeu-TTS v3 Turbo (Apache-2.0) chạy trên máy; Qt for Python (PySide6, LGPL), Pillow, httpx, websockets và sounddevice. Video demo dùng MuseScore 4 như một app bình thường, với giai điệu dân gian *Frère Jacques*; ScreenTutor không có dòng code nào riêng cho MuseScore.

Giấy phép MIT, xem [LICENSE](../LICENSE).
