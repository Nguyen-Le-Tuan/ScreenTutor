BỘ NHÃN GROUNDING — 29/10/2026
===============================
Đã đo và rà ảnh cho 12 ca, toàn bộ ảnh 1920 × 1080 PNG.
Ảnh gốc và bản sao trong gói giữ nguyên từng byte. Không chỉnh nội dung hoặc đổi kích thước.

ĐÃ HOÀN THÀNH NHÃN 12 CA, CHỜ RÀ SOÁT TRƯỚC KHI CHỐT
1. case_07 đã thay bằng ảnh mới đúng Details, có đủ hai bản giáo án, 1920 × 1080.
   Khung đã đo lại từ icon tới hết tên bản có (1): [304,337,548,360), 244 × 23 px,
   cỡ nhỏ. Không sử dụng lại khung của bố cục biểu tượng lớn trước đó.
   Metadata ảnh mới nhất khoảng 120 DPI, khớp 11 ảnh còn lại và kích thước giao diện
   nhất quán với Scale 125% đã ghi trong checklist. Không còn chênh lệch DPI của lần
   chụp trước. Bản cũ được lưu riêng trong history/ của workspace để giữ lịch sử.
   Không sửa DPI metadata hoặc resize ảnh; đây là ảnh chụp lại mới do người dùng cung cấp.
2. case_03 có ba dòng URL (đã đo riêng từng dòng). Người dùng xác nhận trực tiếp
   ngày 29/10/2026: "Đã kiểm tra, bấm tiêu đề mở đúng bảng tính". Khung thứ tư
   đã được đưa vào accepted, khoanh sát tiêu đề: [921,737,1244,765), cỡ nhỏ.
   Không suy rộng xác nhận này sang tên miền, khoảng trống hay toàn khung tin nhắn.
3. Đây là nhãn do AI lập từ ảnh. Ngoài xác nhận thao tác của case_03, chưa có kiểm
   thử bấm trực tiếp hoặc người rà các mép khung. review.html cho phép xem ảnh gốc,
   bật/tắt khung, zoom và đọc tọa độ con trỏ
   để rà nhãn trước khi cố định bộ đánh giá. Trạng thái visually_reviewed không có nghĩa
   là đã chứng minh toàn bộ hitbox của ứng dụng bằng tương tác thực.

CÁC PHÁT HIỆN KHÁC
- case_01/case_02 và case_03/case_04 trùng byte. Có 12 nhiệm vụ trên 10 ảnh độc lập.
  Có thể dùng một ảnh cho hai mục tiêu khác nhau; nếu chia train/test, hãy nhóm theo
  SHA-256 để không tách bản sao sang hai tập.
- case_05: tab khác đang chọn là trang hackathon, không phải ví dụ google.com.
  Ba tab Sheet vẫn ở nền, mục tiêu vẫn đủ. Theo checklist khung bao toàn ô tab;
  điểm bấm thử nên ở icon/tên, tránh nút đóng có thể hiện lên khi hover.
- case_06: chỉ phần chính ô tab Cô Mẫu, loại mũi tên menu bên phải.
- case_09: đúng dòng ổ D, đường dẫn Raw_srouces (giữ nguyên cách viết trong ảnh).
  Có thêm bản (1) ở đầu Recent; không ảnh hưởng việc phân biệt ba bản tên gốc.
- case_12: nguyên văn hai dòng là:
  Giáo án "Âm nhạc 8"?.docx
  The file name is not valid.
- Không suy ra Scale 125%, trạng thái chuột lúc chụp, hoặc trang phía sau cửa sổ
  chỉ bằng các ảnh tĩnh. Các thiết lập A đã được đánh dấu từ checklist người dùng.
- Ảnh có các tên/tệp bên ngoài mục tiêu chưa được che; mục A7 có hướng dẫn xử lý
  trước khi gửi ra ngoài. Gói này chưa gửi đi bất cứ dịch vụ hoặc người nhận nào.

QUY ƯỚC ĐO
- Pixel ảnh gốc, gốc trên trái (0,0). x tăng sang phải, y tăng xuống dưới.
- [x1,y1,x2,y2), tức x1 <= x < x2, y1 <= y < y2.
- Chiều rộng=x2-x1, chiều cao=y2-y1; cỡ theo min(rộng,cao):
  nhỏ <32; vừa từ 32 tới 80 kể cả hai đầu; lớn >80.
- Không nhân/chia 1.25 do Windows Scale 125%.
- Khung có mép nút rõ: bám mép nút. Icon/chữ trần: ôm vùng nhìn thấy với lề nhỏ.
- Khung của nhãn hiện tại là vùng bấm mục tiêu được nhận diện từ ảnh, không phải
  khẳng định mọi pixel có thể bấm của control đã được đo bằng UI automation.

CÁC FILE
- CAPTURE_CHECKLIST_WINDOWS_FILLED.txt: checklist gốc đã điền mục C, có ghi rõ ngoại lệ.
- labels.json: nhãn, câu hỏi nguyên văn, bbox, cỡ, trạng thái, SHA-256, mô tả quy ước.
- boxes.csv: mỗi khung một dòng, không làm mất liên kết cỡ với từng khung.
- image_manifest.json: hash và kích thước 12 ảnh.
- review.html: bản xem kiểm tra độc lập, nhúng ảnh gốc; khung SVG nằm trên ảnh,
  không được trộn vào ảnh đầu vào dùng cho Meta. Khung cam nét đứt là chưa xác minh.
- case_01.png … case_12.png: bản sao byte-for-byte của ảnh gốc.

CHUYỂN SANG UBUNTU
Giải nén gói và đặt 12 ảnh cùng checklist đã điền vào thư mục cases của dự án.
labels.json là định dạng trung gian được mô tả rõ, CHƯA tuyên bố khớp schema cases.json
của script Ubuntu vì chưa có source/schema script đó trong tác vụ này. Đối chiếu script
trước khi chuyển trường; không tự bỏ các khung phụ hoặc khung candidate vào accepted.
Chưa chạy model Meta, chưa có kết quả accuracy. Phải cố định nhãn trước khi xem đầu ra
model để tránh chỉnh ground truth theo kết quả. Không dùng review.html hay diagnostic
crop làm ảnh đầu vào: chúng chỉ phục vụ kiểm tra nhãn.
