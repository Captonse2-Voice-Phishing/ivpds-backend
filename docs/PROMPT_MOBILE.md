# PROMPT — THIẾT KẾ VÀ XÂY DỰNG IVPDS MOBILE APP

Bạn là Senior React Native Engineer kiêm UI Designer. Hãy thiết kế và xây dựng **ứng dụng mobile cho người dùng cuối** của IVPDS trong thư mục hiện tại.

IVPDS (Intelligent Voice Phishing Detection System) phân tích ghi âm cuộc gọi tiếng Việt để phát hiện lừa đảo qua điện thoại: audio → transcript → các dấu hiệu lừa đảo → điểm rủi ro 0–100 và mức LOW / MEDIUM / HIGH. Người dùng ghi âm hoặc chọn một file ghi âm cuộc gọi, gửi lên, và nhận kết quả.

Backend đã viết xong, đã kiểm thử và đang chạy thật. Prompt này chứa đủ mọi API bạn cần. Bạn không sửa backend.

Mục tiêu không phải viết thật nhiều code nhanh. Mục tiêu là một ứng dụng **chạy thật, gọi API thật, không dữ liệu giả, không báo cáo sai sự thật**.

---

## PHẦN A — NGUYÊN TẮC

### A1. Công nghệ bắt buộc (theo README của dự án)

- React Native + TypeScript (strict) + **Expo**
- React Navigation
- Zustand (trạng thái phía ứng dụng: phiên đăng nhập, cài đặt)
- TanStack Query (mọi dữ liệu từ server)
- Axios
- Expo SecureStore (lưu token)
- Expo Audio (ghi âm, nghe lại)
- Expo Document Picker (chọn file ghi âm)
- Expo Image Picker (có trong README; backend hiện **không có API ảnh đại diện**, nên chưa dùng tới — không tự dựng chức năng ảnh)

Được thêm vì backend đã có API tương ứng: `expo-notifications` và `expo-device` (thông báo đẩy), `expo-haptics` (rung khi có cảnh báo).

Không thêm thư viện lớn khác (Redux, thư viện UI nặng, NativeWind...) nếu chưa hỏi tôi. Thư viện nhỏ cho một việc cụ thể thì nêu lý do rồi dùng.

### A2. Code thật

Cấm:

- dữ liệu giả, màn hình dựng bằng số liệu hard-code;
- kết quả phân tích giả, điểm rủi ro ngẫu nhiên, transcript viết sẵn;
- tự tính mức rủi ro ở ứng dụng (mức rủi ro luôn lấy từ backend);
- `TODO` nhưng báo đã xong;
- nói "đã chạy được" khi chưa chạy.

Phần chưa làm: **NOT IMPLEMENTED**. Chưa kiểm tra với backend thật hoặc trên thiết bị: **NOT VERIFIED**. Bị chặn: **BLOCKED** kèm thứ cần từ tôi. Lỗi đã biết: **KNOWN BUG**.

### A3. Phạm vi

**Trong phạm vi (README + API đã có):**

1. Đăng ký, đăng nhập, đăng xuất.
2. Quên mật khẩu, đổi mật khẩu.
3. Hồ sơ cá nhân: xem, sửa.
4. Ghi âm trong ứng dụng hoặc chọn file ghi âm, gửi lên.
5. Theo dõi quá trình phân tích, yêu cầu phân tích lại.
6. Xem điểm rủi ro, mức rủi ro, transcript, các dấu hiệu.
7. Lịch sử phân tích, có lọc; nghe lại ghi âm; xóa cuộc gọi.
8. Tra cứu số điện thoại trong danh sách đen.
9. Bật/tắt cảnh báo danh sách đen.
10. Báo cáo số lừa đảo, xem báo cáo của mình.
11. Thông báo trong ứng dụng và thông báo đẩy.

**Ngoài phạm vi, không làm nếu tôi chưa yêu cầu:**

- Ứng dụng **không** ghi âm được cuộc gọi của hệ thống điện thoại (Android và iOS đều chặn). "Ghi âm" ở đây là ghi bằng micro của máy (ví dụ bật loa ngoài) hoặc chọn file có sẵn. Ghi rõ điều này trên giao diện, không hứa điều ứng dụng không làm được.
- **Phân tích cuộc gọi trực tiếp (VoIP)**: backend đã có API (Phụ lục), nhưng ứng dụng cần tự thực hiện cuộc gọi VoIP và thu PCM theo thời gian thực — việc này cần module native, không chạy trong Expo Go, và không nằm trong README. Chỉ làm ở giai đoạn riêng khi tôi nói rõ.
- Mọi chức năng quản trị (`/api/v1/admin/**`).

---

## PHẦN B — THIẾT KẾ GIAO DIỆN

### B1. Phong cách

- Người dùng là người bình thường, có thể lớn tuổi, đang lo lắng vì một cuộc gọi lạ. Giao diện phải **rõ, ít chữ, chữ to, kết luận nằm ngay đầu màn hình**.
- Toàn bộ chữ bằng **tiếng Việt**, giọng bình tĩnh, không dọa dẫm.
- Màu chính: xanh dương đậm `#1F4E79`. Nền `#F5F7FA`, thẻ trắng bo góc 16, đổ bóng nhẹ.
- Cỡ chữ gốc 16; tiêu đề 20–24; số điểm rủi ro 48 trở lên. Vùng bấm tối thiểu 48×48.
- Hỗ trợ chế độ sáng; tôn trọng cỡ chữ hệ thống (không khóa `allowFontScaling`); có `accessibilityLabel` cho nút chỉ có biểu tượng.
- Tự viết các component nền (`Button`, `Card`, `Tag`, `TextField`, `Screen`, `EmptyState`, `ErrorState`) trong `src/components/`, dùng chung một file theme (`src/theme/`).

**Màu và lời cho mức rủi ro — dùng nhất quán ở mọi nơi:**

| Mức | Nhãn | Màu | Lời khuyên hiển thị |
|---|---|---|---|
| `HIGH` | Nguy cơ cao | đỏ `#D4380D` | "Cuộc gọi này có nhiều dấu hiệu lừa đảo. Không đọc mã OTP, mật khẩu và không chuyển tiền theo yêu cầu của người gọi." |
| `MEDIUM` | Đáng ngờ | cam `#D48806` | "Cuộc gọi có dấu hiệu đáng ngờ. Hãy kiểm tra lại qua kênh chính thức trước khi làm theo yêu cầu." |
| `LOW` | Chưa thấy dấu hiệu | xanh lá `#389E0D` | "Chưa phát hiện dấu hiệu lừa đảo rõ ràng. Kết quả do máy đánh giá, bạn vẫn nên cẩn thận." |

Không chỉ dựa vào màu: luôn có chữ và biểu tượng. Không viết "An toàn tuyệt đối": hệ thống có thể sai.

### B2. Điều hướng

```
Chưa đăng nhập:  Đăng nhập ─ Đăng ký ─ Quên mật khẩu (2 bước)

Đã đăng nhập:    Thanh tab dưới
  ┌──────────┬──────────┬────────────┬──────────┬──────────┐
  │ Trang chủ│ Lịch sử  │ ( Phân tích )│ Tra cứu  │ Tài khoản│
  └──────────┴──────────┴────────────┴──────────┴──────────┘
                           nút tròn nổi, màu chính

Màn hình mở chồng lên: Kết quả cuộc gọi · Thông báo · Báo cáo số ·
                       Báo cáo của tôi · Sửa hồ sơ · Đổi mật khẩu
```

Biểu tượng chuông ở góc phải trên của Trang chủ, có huy hiệu số thông báo chưa đọc.

### B3. Đăng nhập, đăng ký, quên mật khẩu

- **Đăng nhập**: logo chữ "IVPDS" và dòng "Phát hiện lừa đảo qua cuộc gọi"; ô Email, ô Mật khẩu (có nút hiện/ẩn); nút "Đăng nhập"; liên kết "Quên mật khẩu?" và "Chưa có tài khoản? Đăng ký".
  - `INVALID_CREDENTIALS` → "Email hoặc mật khẩu không đúng". `ACCOUNT_LOCKED` → "Tài khoản đã bị khóa. Vui lòng liên hệ quản trị viên."
- **Đăng ký**: Họ tên, Email, Số điện thoại (không bắt buộc), Mật khẩu, Nhập lại mật khẩu. Dưới ô mật khẩu ghi "8–72 ký tự". Lỗi từ backend (`fieldErrors`) hiện đỏ dưới đúng ô. `EMAIL_ALREADY_REGISTERED` → hiện dưới ô email "Email này đã được đăng ký". Đăng ký xong vào thẳng ứng dụng.
  - Số điện thoại ở API đăng ký chỉ nhận chữ số, có thể có `+` ở đầu: bỏ khoảng trắng, dấu chấm, gạch ngang trước khi gửi.
- **Quên mật khẩu**: bước 1 nhập email → luôn hiện "Nếu email tồn tại, chúng tôi đã gửi mã 6 số. Mã có hiệu lực 15 phút." Bước 2: sáu ô nhập mã, mật khẩu mới, nhập lại. `INVALID_RESET_CODE` → "Mã không đúng hoặc đã hết hạn". Nút "Gửi lại mã" bị khóa 60 giây sau mỗi lần gửi, có đếm ngược. Xong thì về Đăng nhập kèm thông báo thành công.

### B4. Trang chủ

Từ trên xuống:

1. Lời chào "Xin chào, {tên}" và chuông thông báo.
2. **Thẻ hành động chính** (màu chính, chữ trắng): "Kiểm tra một cuộc gọi" với hai nút lớn cạnh nhau: **Ghi âm** và **Chọn file**.
3. **Ô tra cứu nhanh**: "Tra cứu số điện thoại" → chuyển sang tab Tra cứu với số đã nhập.
4. **"Gần đây"**: 3 cuộc gọi mới nhất (thành phần dòng cuộc gọi ở B7), liên kết "Xem tất cả" sang Lịch sử. Chưa có cuộc gọi: hình minh họa đơn giản và dòng "Bạn chưa kiểm tra cuộc gọi nào."
5. Thẻ mẹo an toàn (nội dung tĩnh, 3 dòng): không đọc OTP cho bất kỳ ai; cơ quan chức năng không làm việc qua điện thoại; gác máy và gọi lại số chính thức.

Kéo xuống để làm mới.

### B5. Phân tích: ghi âm hoặc chọn file

Mở từ nút giữa hoặc từ Trang chủ. Một màn hình, hai lựa chọn dạng `Segmented`: **Ghi âm** | **Chọn file**.

**Ghi âm**

- Lần đầu: giải thích trước khi xin quyền micro — "Ứng dụng cần micro để ghi âm. Hãy bật loa ngoài của cuộc gọi để ghi được cả hai bên." Từ chối quyền: hiện hướng dẫn và nút mở Cài đặt, không để màn hình trống.
- Nút ghi tròn lớn ở giữa; khi đang ghi: đồng hồ đếm giây, thanh mức âm lượng chuyển động theo tín hiệu thật từ micro, nút dừng. Có tạm dừng / tiếp tục.
- Dừng xong: trình nghe lại (phát/dừng, thanh tiến độ, thời lượng), nút "Ghi lại" và "Dùng bản ghi này".
- Ghi bằng định dạng `.m4a` (AAC). Dòng chữ nhỏ: "Ứng dụng không thể tự ghi âm cuộc gọi của điện thoại."

**Chọn file**

- Nút "Chọn file ghi âm" mở Document Picker, lọc `audio/*`.
- Kiểm tra trước khi gửi: đuôi file thuộc `mp3, wav, m4a, aac, ogg, webm, 3gp, amr, flac`; dung lượng ≤ 50 MB. Sai thì báo ngay, không gửi.
- Sau khi chọn: thẻ hiện tên file, dung lượng, nút nghe thử, nút bỏ chọn.

**Thông tin thêm** (chung cho cả hai, không bắt buộc): ô "Số điện thoại người gọi" (bàn phím số) và "Thời điểm cuộc gọi" (chọn ngày giờ).

**Gửi**: nút "Gửi phân tích". Trong lúc tải lên có thanh tiến độ phần trăm thật (từ `onUploadProgress`) và nút hủy. Gửi xong chuyển thẳng sang màn hình Kết quả của cuộc gọi vừa tạo.

Lỗi tải lên hiện bằng tiếng Việt theo `code` (bảng C9), giữ nguyên file đã chọn để thử lại.

### B6. Kết quả cuộc gọi

Màn hình quan trọng nhất. Nhận `callId`, tự hỏi kết quả định kỳ.

**Đang phân tích** (`PENDING` / `PROCESSING`):

- Hình động nhẹ, dòng "Đang phân tích cuộc gọi…", dòng phụ đổi theo trạng thái: "Đang chờ tới lượt" (`PENDING`) / "Đang nghe và đánh giá nội dung" (`PROCESSING`).
- Dòng "Bạn có thể rời màn hình này, chúng tôi sẽ thông báo khi có kết quả." Không hiện phần trăm giả.

**Hoàn tất** (`COMPLETED`), từ trên xuống:

1. **Thẻ kết luận** nền màu theo mức: biểu tượng, nhãn mức cỡ lớn, vòng điểm `riskScore`/100, và lời khuyên ở B1.
2. Nếu số người gọi nằm trong danh sách đen (`callerBlacklisted`): dải đỏ "Số này nằm trong danh sách đen".
3. **Dấu hiệu phát hiện được**: mỗi dấu hiệu một dòng có biểu tượng, tên tiếng Việt và câu giải thích (bảng C7). Không có dấu hiệu: "Không phát hiện dấu hiệu cụ thể nào."
4. **Nội dung cuộc gọi**: transcript trong thẻ, mặc định thu gọn 6 dòng, nút "Xem toàn bộ"; nút sao chép.
5. **Thông tin**: số người gọi, thời điểm, thời lượng, nguồn (Ghi âm trong ứng dụng / Tải file lên / Cuộc gọi trực tiếp).
6. **Nghe lại ghi âm**: trình phát.
7. Mục thu gọn "Chi tiết kỹ thuật": độ chắc chắn của kết luận (`confidence`, dạng %), xác suất do model tính (`modelProbability`, dạng %), các phiên bản. Kèm dòng: "Xác suất của model chỉ là một thành phần của điểm rủi ro."
8. Hàng nút: **Báo cáo số này** (ẩn nếu không có số người gọi hoặc số đã bị chặn), **Phân tích lại**, **Xóa** (đỏ, có xác nhận).

**Lỗi** (`FAILED`): biểu tượng cảnh báo xám, tiêu đề "Không phân tích được", câu tiếng Việt theo `errorCode` (bảng C8), nút "Thử lại" (gọi phân tích lại) khi lỗi thuộc loại thử lại được. **Không hiện điểm hay mức rủi ro nào.** Vẫn có phần thông tin, nghe lại và nút xóa.

**Chưa phân tích** (`ANALYSIS_NOT_FOUND`): nút "Phân tích ngay".

### B7. Lịch sử

- Hàng chip lọc cuộn ngang: **Tất cả · Nguy cơ cao · Đáng ngờ · Chưa thấy dấu hiệu · Lỗi** (bốn mục đầu đặt `riskLevel`, "Lỗi" đặt `status=FAILED`). Biểu tượng lọc mở bảng dưới: khoảng thời gian và số người gọi.
- Danh sách cuộn vô hạn (`useInfiniteQuery`, mỗi lần 20 dòng), kéo xuống để làm mới.
- **Dòng cuộc gọi**: vạch màu theo mức ở mép trái; dòng 1 là số người gọi (hoặc "Không rõ số") và Tag mức rủi ro bên phải; dòng 2 là ngày giờ và thời lượng; dòng 3 là tối đa hai dấu hiệu và "+N". Số bị chặn có biểu tượng cấm nhỏ. Đang phân tích: Tag "Đang phân tích" có vòng quay. Lỗi: Tag xám "Lỗi".
- Vuốt sang trái trên một dòng để xóa (có xác nhận). `ANALYSIS_IN_PROGRESS` → "Cuộc gọi đang được phân tích, hãy thử lại sau."
- Rỗng: "Chưa có cuộc gọi nào" và nút "Kiểm tra một cuộc gọi". Rỗng do lọc: "Không có cuộc gọi phù hợp" và nút "Xóa bộ lọc".

### B8. Tra cứu số điện thoại

- Ô nhập số lớn (bàn phím số), nút "Tra cứu".
- Kết quả là một thẻ:
  - Bị chặn: nền đỏ nhạt, "Số này nằm trong danh sách đen", lý do (`reason`) và "Từ ngày {since}".
  - Không bị chặn: nền xanh nhạt, "Chưa có trong danh sách đen", dòng nhỏ "Điều này không có nghĩa số này an toàn.", và nút **"Báo cáo số này"**.
- `INVALID_PHONE_NUMBER` → dưới ô nhập: "Số điện thoại không hợp lệ".
- Dưới cùng: liên kết "Báo cáo của tôi".

### B9. Báo cáo số lừa đảo

- **Form báo cáo** (mở từ Kết quả hoặc Tra cứu): số điện thoại (điền sẵn, chỉ đọc khi đi từ một cuộc gọi), ô "Lý do" nhiều dòng (không bắt buộc, tối đa 1000 ký tự, có đếm), dòng giải thích "Quản trị viên sẽ xem xét báo cáo trước khi chặn số." Nút "Gửi báo cáo".
  - Đi từ một cuộc gọi thì gửi `callId` (không cần gửi số).
  - `NUMBER_ALREADY_REPORTED` → "Bạn đã báo cáo số này rồi." `PHONE_NUMBER_ALREADY_BLACKLISTED` → "Số này đã nằm trong danh sách đen." `TOO_MANY_PENDING_REPORTS` → "Bạn đang có quá nhiều báo cáo chờ duyệt. Hãy thử lại sau."
- **Báo cáo của tôi**: danh sách số đã báo cáo, ngày, lý do, Tag trạng thái — "Chờ duyệt" (cam), "Đã chặn" (xanh lá, `APPROVED`), "Không được duyệt" (xám, `REJECTED`).

### B10. Thông báo

- Danh sách, mới nhất trước, cuộn vô hạn. Mỗi dòng: biểu tượng theo loại (đỏ cho `HIGH_RISK_CALL`, cam cho `SUSPICIOUS_CALL`, biểu tượng cấm cho `BLACKLISTED_CALLER`), tiêu đề in đậm, nội dung tối đa 3 dòng, thời gian dạng "5 phút trước". Chưa đọc có chấm xanh và nền nhạt.
- `title` và `message` do backend viết sẵn bằng tiếng Việt: hiển thị nguyên văn.
- Bấm một dòng: đánh dấu đã đọc và mở Kết quả của `callId`; nếu `callId` là `null` (cuộc gọi đã xóa) thì chỉ đánh dấu đã đọc và báo "Cuộc gọi này đã bị xóa".
- Nút "Đánh dấu đã đọc tất cả" ở góc phải trên.
- Huy hiệu chuông lấy từ `unread-count`; làm mới khi ứng dụng trở lại tiền cảnh và sau mỗi lần phân tích xong.

### B11. Tài khoản

- Đầu trang: hình tròn chữ cái đầu của tên, họ tên, email.
- Nhóm **Hồ sơ**: "Sửa hồ sơ" (họ tên, số điện thoại), "Đổi mật khẩu".
- Nhóm **Cảnh báo**: công tắc "Cảnh báo khi số gọi đến nằm trong danh sách đen" (`blacklistAlertEnabled`), cập nhật ngay khi gạt, hoàn lại nếu lỗi. Công tắc "Thông báo đẩy" phản ánh quyền thông báo của hệ điều hành.
- Nhóm **Khác**: "Báo cáo của tôi", "Giới thiệu" (tên ứng dụng, phiên bản, dòng "Kết quả do hệ thống tự động đánh giá và có thể sai").
- Nút "Đăng xuất" (có xác nhận).
- **Đổi mật khẩu**: mật khẩu hiện tại, mật khẩu mới, nhập lại. `INVALID_CURRENT_PASSWORD` → dưới ô đầu "Mật khẩu hiện tại không đúng". Thành công: báo "Đã đổi mật khẩu, vui lòng đăng nhập lại" và về Đăng nhập (backend đăng xuất mọi phiên).

### B12. Quy tắc chung

- Mỗi màn hình có đủ: đang tải (khung xương), lỗi (câu tiếng Việt và nút "Thử lại"), rỗng.
- Mất mạng: dải thông báo "Không có kết nối mạng" ở đầu màn hình; không hiện lỗi kỹ thuật.
- Nút đang gửi có trạng thái tải và không bấm lại được.
- Bàn phím không che ô nhập; bấm ra ngoài để đóng bàn phím.
- Thao tác không hoàn tác được (xóa, đăng xuất) có xác nhận.
- Thời gian hiển thị theo giờ của máy, dạng `10/10/2026 13:15`; thời lượng dạng `2 phút 30 giây`.
- Số điện thoại hiển thị đúng như backend trả (`+84…`).

---

## PHẦN C — API

### C1. Kết nối

- Backend chạy trên máy tính của tôi ở cổng 8080, và **chỉ nghe trên `127.0.0.1` của máy đó**. Địa chỉ gốc lấy từ biến môi trường `EXPO_PUBLIC_API_URL` (có `.env.example`), không ghi cứng trong code:
  - Android Emulator: `http://10.0.2.2:8080`
  - Điện thoại Android thật cắm USB: chạy `adb reverse tcp:8080 tcp:8080` rồi dùng `http://127.0.0.1:8080`
  - Điện thoại thật qua Wi-Fi: **không kết nối được** với cấu hình hiện tại của backend. Nếu cần, báo **BLOCKED** và nói với tôi; không tự sửa backend.
- Android chặn HTTP không mã hóa theo mặc định: bật `usesCleartextTraffic` cho bản phát triển.
- Chạy bằng Expo web sẽ bị chặn vì backend chưa bật CORS; ứng dụng này nhắm tới Android/iOS.
- Mọi đường dẫn bắt đầu bằng `/api/v1`. JSON; thời gian ISO 8601 UTC; id là UUID; trường không có giá trị là `null` (không bị bỏ đi).

### C2. Token

Mọi API trừ nhóm công khai ở C4 cần `Authorization: Bearer <accessToken>`.

- `accessToken` sống 15 phút. `refreshToken` sống 7 ngày và **chỉ dùng được một lần**: mỗi lần làm mới trả về cặp token mới, token cũ vô hiệu.
- Lưu `refreshToken` trong **Expo SecureStore**; `accessToken` giữ trong bộ nhớ (Zustand). Không dùng AsyncStorage cho token. Không in token ra log.
- Mở ứng dụng: có `refreshToken` thì làm mới trước khi hiện giao diện (màn hình chờ); thất bại thì về Đăng nhập.
- Axios interceptor: khi một API trả `401`, gọi `refresh` rồi gửi lại request. Nhiều request cùng `401` thì **chỉ gọi refresh một lần**, các request khác chờ kết quả đó. Refresh thất bại (`INVALID_REFRESH_TOKEN`): xóa token, xóa cache của TanStack Query, về Đăng nhập.
- Tài khoản bị quản trị viên khóa: access token bị từ chối ngay (`401`) và refresh thất bại → về Đăng nhập.

### C3. Phân trang và lỗi

Danh sách nhận `page` (bắt đầu từ 0) và `size` (mặc định 20, tối đa 100), trả:

```json
{ "items": [], "page": 0, "size": 20, "totalItems": 57, "totalPages": 3 }
```

Mọi lỗi có dạng:

```json
{
  "timestamp": "2026-10-10T06:15:30.123Z", "status": 400, "code": "VALIDATION_FAILED",
  "message": "Request validation failed.", "path": "/api/v1/auth/register", "requestId": "3f2c9a1e-...",
  "fieldErrors": [ { "field": "password", "message": "size must be between 8 and 72" } ]
}
```

Xử lý theo `code`. `fieldErrors` chỉ có khi `code` là `VALIDATION_FAILED`: gắn vào đúng ô. `message` là tiếng Anh, không hiện thẳng cho người dùng.

### C4. Xác thực

| API | Body | Trả về |
|---|---|---|
| `POST /api/v1/auth/register` (công khai) | `{email, password, fullName, phoneNumber?}` | `201` AuthResponse · `400 VALIDATION_FAILED` · `409 EMAIL_ALREADY_REGISTERED` |
| `POST /api/v1/auth/login` (công khai) | `{email, password}` | `200` AuthResponse · `401 INVALID_CREDENTIALS` · `403 ACCOUNT_LOCKED` |
| `POST /api/v1/auth/refresh` (công khai) | `{refreshToken}` | `200` AuthResponse · `401 INVALID_REFRESH_TOKEN` |
| `POST /api/v1/auth/logout` (công khai) | `{refreshToken}` | `204` |
| `POST /api/v1/auth/forgot-password` (công khai) | `{email}` | luôn `204`; gửi lại trong 60 giây không gửi thêm mail |
| `POST /api/v1/auth/reset-password` (công khai) | `{email, code, newPassword}` — `code` 6 chữ số, hiệu lực 15 phút, sai quá 5 lần phải xin mã mới | `204` · `400 INVALID_RESET_CODE` |
| `POST /api/v1/auth/change-password` | `{currentPassword, newPassword}` | `204` (đăng xuất mọi phiên) · `400 INVALID_CURRENT_PASSWORD` |

Quy tắc: `email` hợp lệ, tối đa 255; `password` 8–72 ký tự; `fullName` bắt buộc, tối đa 100; `phoneNumber` khi đăng ký khớp `^\+?[0-9]{6,15}$`.

```json
{
  "accessToken": "eyJ...", "refreshToken": "b7Jk2...", "tokenType": "Bearer", "expiresIn": 900,
  "user": { "id": "0b9f...", "email": "an@example.com", "fullName": "Nguyễn Văn An", "roles": ["USER"] }
}
```

**Đăng xuất đúng thứ tự:** (1) `DELETE /api/v1/notifications/devices?token=…` khi còn access token, (2) `POST /api/v1/auth/logout`, (3) xóa token và cache.

### C5. Hồ sơ

- `GET /api/v1/users/me`
- `PATCH /api/v1/users/me` — chỉ gửi trường muốn đổi: `fullName` (1–100 ký tự), `phoneNumber` (mọi dạng: `0901234567`, `090 123 4567`, `+84901234567`), `blacklistAlertEnabled` (`true`/`false`). Lỗi: `400 VALIDATION_FAILED`, `400 INVALID_PHONE_NUMBER`. Email không đổi được.

```json
{ "id": "0b9f...", "email": "an@example.com", "fullName": "Nguyễn Văn An", "phoneNumber": "+84901234567",
  "status": "ACTIVE", "blacklistAlertEnabled": true, "roles": ["USER"], "createdAt": "2026-10-01T03:00:00Z" }
```

Backend chuẩn hóa số điện thoại: số nội địa thành `+84…`.

### C6. Cuộc gọi, phân tích, lịch sử

**Gửi cuộc gọi** — `POST /api/v1/calls`, `multipart/form-data`:

| Phần | Bắt buộc | Mô tả |
|---|---|---|
| `audio` | Có | File. Đuôi `mp3, wav, m4a, aac, ogg, webm, 3gp, amr, flac`; tối đa 50 MB; backend kiểm tra cả nội dung file |
| `callerNumber` | Không | Số người gọi, mọi dạng |
| `calledAt` | Không | ISO 8601 |
| `source` | Không | `RECORDED` (ghi âm trong ứng dụng) hoặc `UPLOADED` (chọn file, mặc định) |

Với React Native, phần file trong `FormData` là `{ uri, name, type }`; `name` phải có đuôi đúng.

Trả `201`:

```json
{
  "id": "5d0c...", "callerNumber": "+84901234567", "calledAt": null, "source": "RECORDED",
  "createdAt": "2026-10-10T06:15:30Z",
  "audio": { "id": "a41e...", "originalFilename": "cuoc-goi.m4a", "contentType": "audio/mp4",
             "sizeBytes": 1245678, "durationSeconds": null, "checksumSha256": "9f2b..." }
}
```

Lỗi: `400 EMPTY_AUDIO` · `400 INVALID_PHONE_NUMBER` · `413 PAYLOAD_TOO_LARGE` · `415 UNSUPPORTED_AUDIO_FORMAT` · `415 INVALID_AUDIO_CONTENT` · `503 STORAGE_UNAVAILABLE`.

**Sau khi gửi, phân tích tự bắt đầu.** Không cần gọi API yêu cầu phân tích.

**Kết quả** — `GET /api/v1/calls/{callId}/analyses/latest`

Hỏi lại mỗi 3 giây (`refetchInterval`) khi `status` là `PENDING` hoặc `PROCESSING`; dừng hỏi khi `COMPLETED` hoặc `FAILED`, và khi rời màn hình.

```json
{
  "id": "c7a2...", "callId": "5d0c...", "status": "COMPLETED",
  "errorCode": null, "errorMessage": null,
  "createdAt": "2026-10-10T06:15:30Z", "startedAt": "2026-10-10T06:15:31Z", "completedAt": "2026-10-10T06:16:02Z",
  "transcript": "a lô mình là bên bộ công an ạ ...", "language": "vi",
  "riskScore": 97, "riskLevel": "HIGH", "confidence": 0.98,
  "indicators": ["LEGAL_THREAT", "SECRECY_DEMAND", "URGENCY"],
  "details": { "sttModel": "faster-whisper/phowhisper-medium-int8 (int8, cpu)", "modelProbability": 0.999912,
               "nlpModelVersion": "2026.10.09-phobert-base-r6", "rulesetVersion": "2026.10.5", "riskEngineVersion": "2026.10.1" }
}
```

- `riskLevel`: `LOW` 0–29, `MEDIUM` 30–59, `HIGH` 60–100 — do backend tính, ứng dụng không tự suy ra từ điểm.
- `confidence` (0–1) là độ chắc chắn của kết luận, **không phải** xác suất lừa đảo. `modelProbability` là xác suất do NLP Model tính, **không phải** điểm rủi ro. Ba con số khác nhau; màn hình chính chỉ nhấn `riskLevel` và `riskScore`.
- Khi `FAILED`: `errorCode`, `errorMessage` có giá trị; `riskScore`, `riskLevel`, `confidence`, `indicators` là `null`; `transcript` có thể vẫn có.
- Lỗi HTTP: `404 CALL_NOT_FOUND` · `404 ANALYSIS_NOT_FOUND` (chưa phân tích lần nào).
- Thời gian phân tích đo được trên máy chủ phát triển (CPU): 6–12 giây cho cuộc gọi 16 giây; cuộc gọi dài vài phút mất lâu hơn nhiều.

**Phân tích lại** — `POST /api/v1/calls/{callId}/analyses` (không body) → `202`. Lỗi: `409 ANALYSIS_IN_PROGRESS` · `409 CALL_HAS_NO_AUDIO` · `503 ANALYSIS_QUEUE_FULL`.

**Các API khác của cuộc gọi**

| API | Dùng để |
|---|---|
| `GET /api/v1/calls/{id}` | Một cuộc gọi (dạng như kết quả gửi). `durationSeconds` có sau lần phân tích đầu |
| `GET /api/v1/calls/{id}/audio` | Tải file ghi âm (nhị phân, cần Bearer token). Để phát: tải về thư mục cache bằng `expo-file-system` kèm header rồi phát file cục bộ. `404 AUDIO_OBJECT_MISSING` |
| `DELETE /api/v1/calls/{id}` | Xóa cuộc gọi cùng audio và kết quả → `204`. `409 ANALYSIS_IN_PROGRESS` |

**Lịch sử** — `GET /api/v1/history`

Tham số: `riskLevel` (`LOW`/`MEDIUM`/`HIGH`), `status` (`PENDING`/`PROCESSING`/`COMPLETED`/`FAILED`), `from`, `to` (ISO 8601, theo thời điểm gửi lên), `callerNumber` (một phần chữ số; khoảng trắng và số 0 đầu được bỏ qua), `page`, `size`. Mới nhất trước.

```json
{
  "callId": "5d0c...", "callerNumber": "+84901234567", "callerBlacklisted": true, "calledAt": null,
  "source": "UPLOADED", "createdAt": "2026-10-10T06:15:30Z", "durationSeconds": 150.2,
  "analysis": { "id": "c7a2...", "status": "COMPLETED", "errorCode": null, "errorMessage": null,
                "completedAt": "2026-10-10T06:16:02Z", "riskScore": 97, "riskLevel": "HIGH", "confidence": 0.98,
                "indicators": ["LEGAL_THREAT", "SECRECY_DEMAND"], "transcript": null, "details": null },
  "owner": null
}
```

- Trong danh sách, `analysis.transcript` và `analysis.details` luôn `null`. `analysis` là `null` nếu chưa phân tích. `owner` luôn `null` ở ứng dụng.
- `GET /api/v1/history/{callId}`: cùng dạng, có đủ `transcript` và `details`. `404 CALL_NOT_FOUND`.
- Màn hình Kết quả dùng `GET /api/v1/history/{callId}` cho thông tin cuộc gọi (số, thời lượng, `callerBlacklisted`) và `analyses/latest` để theo dõi trạng thái.

### C7. Dấu hiệu: mã, tên và câu giải thích

| Mã | Tên hiển thị | Giải thích cho người dùng |
|---|---|---|
| `OTP_REQUEST` | Đòi mã OTP | Người gọi yêu cầu bạn đọc mã OTP. Ngân hàng không bao giờ hỏi mã này. |
| `MONEY_TRANSFER` | Yêu cầu chuyển tiền | Người gọi yêu cầu bạn chuyển tiền. |
| `BANK_IMPERSONATION` | Tự xưng ngân hàng | Người gọi nói mình là nhân viên ngân hàng. |
| `URGENCY` | Thúc giục | Người gọi ép bạn làm ngay, không cho thời gian suy nghĩ. |
| `ACCOUNT_LOCK_THREAT` | Dọa khóa tài khoản | Người gọi dọa tài khoản của bạn sẽ bị khóa. |
| `SENSITIVE_INFORMATION` | Hỏi thông tin nhạy cảm | Người gọi hỏi số thẻ, mật khẩu hoặc giấy tờ tùy thân. |
| `AUTHORITY_IMPERSONATION` | Tự xưng cơ quan chức năng | Người gọi nói mình là công an, viện kiểm sát hoặc tòa án. |
| `LEGAL_THREAT` | Đe dọa pháp lý | Người gọi dọa bắt giữ, khởi tố hoặc nói bạn liên quan vụ án. |
| `HARM_THREAT` | Đe dọa gây hại | Người gọi đe dọa bạn hoặc người thân. |
| `SECRECY_DEMAND` | Yêu cầu giữ bí mật | Người gọi yêu cầu bạn không nói với ai. |
| `REMOTE_ACCESS_REQUEST` | Yêu cầu điều khiển máy | Người gọi yêu cầu cài ứng dụng hoặc chia sẻ màn hình. |
| `FINANCIAL_BAIT` | Dụ dỗ bằng tiền | Người gọi hứa trúng thưởng, hoàn tiền hoặc lãi cao. |
| `UNUSUAL_PAYMENT` | Thanh toán bất thường | Người gọi yêu cầu trả tiền theo cách khác thường. |
| `CALL_HANDOFF` | Chuyển máy | Người gọi chuyển máy cho một "cán bộ" khác. |
| `COORDINATED_CALLERS` | Nhiều người phối hợp | Có nhiều người ở đầu dây bên kia cùng tham gia. |

Mã lạ (backend thêm về sau): hiện nguyên mã, không làm ứng dụng lỗi.

### C8. `errorCode` của lần phân tích và câu hiển thị

| Mã | Câu hiển thị | Cho thử lại |
|---|---|---|
| `NO_SPEECH_DETECTED` | Không nghe được lời nói nào trong ghi âm. | Không |
| `INVALID_AUDIO`, `EMPTY_AUDIO` | File ghi âm không đọc được. Hãy thử file khác. | Không |
| `AUDIO_TOO_LONG`, `AUDIO_TOO_LARGE`, `PAYLOAD_TOO_LARGE` | Ghi âm quá dài hoặc quá lớn. | Không |
| `CALL_HAS_NO_AUDIO`, `AUDIO_OBJECT_MISSING` | Không còn file ghi âm của cuộc gọi này. | Không |
| `STT_UNAVAILABLE`, `STT_FAILED`, `NLP_MODEL_UNAVAILABLE`, `AUDIO_PROCESSING_UNAVAILABLE`, `AUDIO_PROCESSING_TIMEOUT`, `AI_SERVICE_UNAVAILABLE`, `AI_SERVICE_TIMEOUT`, `AI_SERVICE_ERROR`, `STORAGE_UNAVAILABLE` | Hệ thống phân tích đang bận hoặc tạm ngừng. Hãy thử lại sau ít phút. | Có |
| `ANALYSIS_QUEUE_FULL` | Đang có quá nhiều cuộc gọi chờ phân tích. Hãy thử lại sau. | Có |
| `ANALYSIS_INTERRUPTED` | Quá trình phân tích bị gián đoạn. Hãy thử lại. | Có |
| mã khác | Không phân tích được cuộc gọi này. | Có |

### C9. Danh sách đen, báo cáo, thông báo

**Tra cứu** — `GET /api/v1/blacklist/lookup?phoneNumber=` (mọi dạng số)

```json
{ "phoneNumber": "+84901234567", "blacklisted": true, "reason": "Giả danh công an", "since": "2026-10-09T02:00:00Z" }
```

Không bị chặn: `blacklisted` là `false`, `reason` và `since` là `null`. Lỗi: `400 INVALID_PHONE_NUMBER`.

**Báo cáo số** — `POST /api/v1/blacklist/reports`

Body: `phoneNumber` và/hoặc `callId` (một cuộc gọi của chính mình; khi không gửi số, backend lấy số người gọi của cuộc gọi đó), `reason` (không bắt buộc, tối đa 1000 ký tự). Trả `201`:

```json
{ "id": "e19a...", "phoneNumber": "+84901234567", "callId": "5d0c...", "reason": "Tự xưng công an",
  "status": "PENDING", "createdAt": "2026-10-10T06:20:00Z", "reviewedAt": null }
```

Lỗi: `400 INVALID_PHONE_NUMBER` (thiếu số, sai dạng, hoặc cuộc gọi không có số người gọi) · `400 PHONE_NUMBER_MISMATCH` · `404 CALL_NOT_FOUND` · `409 NUMBER_ALREADY_REPORTED` (mỗi người báo cáo một số một lần, kể cả sau khi bị từ chối) · `409 PHONE_NUMBER_ALREADY_BLACKLISTED` · `429 TOO_MANY_PENDING_REPORTS` (tối đa 20 báo cáo đang chờ).

`GET /api/v1/blacklist/reports` — báo cáo của tôi, phân trang; `status` là `PENDING` / `APPROVED` / `REJECTED`.

**Thông báo**

| API | Dùng để |
|---|---|
| `GET /api/v1/notifications?unreadOnly=&page=&size=` | Danh sách, mới nhất trước |
| `GET /api/v1/notifications/unread-count` | `{"unreadCount": 3}` |
| `POST /api/v1/notifications/{id}/read` | Đánh dấu đã đọc → thông báo đã cập nhật. `404 NOTIFICATION_NOT_FOUND` |
| `POST /api/v1/notifications/read-all` | `{"marked": 3}` |

```json
{ "id": "77b1...", "type": "HIGH_RISK_CALL", "title": "Cuộc gọi có nguy cơ lừa đảo cao",
  "message": "Cuộc gọi từ số +84901234567 được đánh giá mức nguy cơ cao với 97/100 điểm rủi ro. ...",
  "read": false, "readAt": null, "analysisId": "c7a2...", "callId": "5d0c...", "createdAt": "2026-10-10T06:16:02Z" }
```

`type`: `HIGH_RISK_CALL` (phân tích xong mức HIGH), `SUSPICIOUS_CALL` (mức MEDIUM), `BLACKLISTED_CALLER` (cuộc gọi từ số trong danh sách đen, khi người dùng chưa tắt cảnh báo). Mức LOW và phân tích lỗi không tạo thông báo.

**Thông báo đẩy**

| API | Dùng để |
|---|---|
| `PUT /api/v1/notifications/devices` | Đăng ký: `{"token": "ExponentPushToken[...]", "platform": "ANDROID"}` (`ANDROID`/`IOS`). Gọi sau mỗi lần đăng nhập và khi token đổi; gọi lại với cùng token là an toàn. `400 VALIDATION_FAILED` nếu token không đúng dạng Expo |
| `DELETE /api/v1/notifications/devices?token=` | Gỡ khi đăng xuất → `204`. Token phải mã hóa URL |

Dữ liệu kèm một thông báo đẩy:

```json
{ "notificationId": "77b1...", "type": "HIGH_RISK_CALL", "callId": "5d0c...", "analysisId": "c7a2..." }
```

- Bấm vào thông báo đẩy → mở Kết quả của `callId` và đánh dấu `notificationId` đã đọc. Nhận khi ứng dụng đang mở → hiện dải thông báo trong ứng dụng và làm mới số chưa đọc.
- Lấy Expo push token cần thiết bị thật, bản dựng riêng (development build) và `projectId` của EAS; **không lấy được trên Android Emulator không có Google Play hay trong Expo Go**. Không lấy được token thì ứng dụng vẫn phải chạy bình thường, chỉ thiếu thông báo đẩy.
- Phía backend, kênh đẩy **mặc định tắt** (`PUSH_ENABLED=false`) và **chưa từng được kiểm chứng với thiết bị thật**. Sau khi làm xong phần này, ghi trạng thái là **NOT VERIFIED** trừ khi bạn thật sự thấy một thông báo về máy; muốn thử thật thì báo tôi để bật ở backend.

### C10. Câu hiển thị cho các mã lỗi chung

| Mã | Câu hiển thị |
|---|---|
| `UNAUTHORIZED` | Phiên đăng nhập đã hết hạn. Vui lòng đăng nhập lại. |
| `VALIDATION_FAILED` | (hiện từng lỗi dưới đúng ô) |
| `MALFORMED_REQUEST`, `BAD_REQUEST` | Yêu cầu không hợp lệ. |
| `INVALID_PHONE_NUMBER` | Số điện thoại không hợp lệ. |
| `EMPTY_AUDIO` | File ghi âm trống. |
| `UNSUPPORTED_AUDIO_FORMAT` | Định dạng file không được hỗ trợ. Hãy dùng mp3, wav, m4a, aac, ogg, webm, 3gp, amr hoặc flac. |
| `INVALID_AUDIO_CONTENT` | File không phải là file ghi âm hợp lệ. |
| `PAYLOAD_TOO_LARGE` | File lớn hơn 50 MB. |
| `STORAGE_UNAVAILABLE` | Hệ thống lưu trữ đang tạm ngừng. Hãy thử lại sau. |
| `ANALYSIS_IN_PROGRESS` | Cuộc gọi đang được phân tích. Hãy thử lại sau. |
| `CALL_NOT_FOUND` | Không tìm thấy cuộc gọi (có thể đã bị xóa). |
| `INTERNAL_ERROR`, lỗi không rõ | Hệ thống gặp lỗi. Hãy thử lại. Mã tra cứu: {requestId} |
| Không có mạng / hết thời gian chờ | Không kết nối được máy chủ. Hãy kiểm tra mạng. |

Mỗi response có header `X-Request-Id`; hiện nó trong thông báo lỗi `INTERNAL_ERROR` để tra log.

---

## PHẦN D — CÁCH LÀM VIỆC

### D0. Tự cấu hình môi trường (Giai đoạn 0)

Máy của tôi chạy **Windows 11**, dùng PowerShell. Bạn tự kiểm tra và tự cài những gì còn thiếu; tôi không cấu hình tay trước. Làm theo đúng thứ tự: **kiểm tra trước, chỉ cài thứ còn thiếu, kiểm tra lại sau khi cài.**

**Bước 1 — Kiểm tra hiện trạng.** Chạy và ghi lại kết quả thật của từng lệnh:

```powershell
node --version; npm --version; git --version
java -version
adb version
echo $env:ANDROID_HOME; echo $env:JAVA_HOME
winget --version
docker ps --format "{{.Names}} {{.Status}}"
```

**Bước 2 — Cài phần còn thiếu** (ưu tiên `winget`, thêm `--accept-source-agreements --accept-package-agreements`):

| Cần có | Kiểm tra | Cài khi thiếu |
|---|---|---|
| Node.js LTS (20 trở lên) | `node --version` | `winget install OpenJS.NodeJS.LTS` |
| Git | `git --version` | `winget install Git.Git` |
| JDK 17 (để dựng bản Android) | `java -version` | `winget install Microsoft.OpenJDK.17`, đặt `JAVA_HOME` |
| Android SDK, platform-tools, emulator | `adb version`, thư mục `%LOCALAPPDATA%\Android\Sdk` | `winget install Google.AndroidStudio`, rồi dùng `sdkmanager` cài `platform-tools`, `emulator`, một `platforms;android-XX` và một `system-images;android-XX;google_apis_playstore;x86_64` mà phiên bản Expo đang dùng yêu cầu |
| Biến môi trường | `$env:ANDROID_HOME` | Đặt `ANDROID_HOME` ở mức người dùng và thêm `platform-tools`, `emulator`, `cmdline-tools\latest\bin` vào `Path` (`[Environment]::SetEnvironmentVariable(..., "User")`) |
| Máy ảo Android | `emulator -list-avds` | `avdmanager create avd` với system image ở trên |

- Sau khi cài hoặc đổi biến môi trường, mở phiên PowerShell mới (hoặc nạp lại `Path`) rồi mới kiểm tra lại; phiên cũ không thấy thay đổi.
- Không cài Expo CLI toàn cục: dùng `npx expo`.
- Nếu máy đã có một bản khác của công cụ (ví dụ JDK 21 dùng cho backend), **không gỡ và không đổi mặc định của cả máy**; chỉ đặt `JAVA_HOME` cho việc dựng Android và nói rõ đã làm gì.

**Bước 3 — Tạo dự án.** Trong thư mục hiện tại: `npx create-expo-app@latest . --template blank-typescript` (nếu thư mục chỉ có `CLAUDE.md` thì tạo vào thư mục tạm rồi chuyển file vào, giữ nguyên `CLAUDE.md`). Dùng `npx expo install <gói>` để cài các gói của Expo, để phiên bản khớp với SDK. Tạo `.env.example` và `.env` với `EXPO_PUBLIC_API_URL`; thêm `.env` vào `.gitignore`. Chạy `git init` nếu chưa có.

**Bước 4 — Kiểm tra backend.** Backend nằm ở `D:\Capstone2` và chạy bằng Docker Compose.

- Kiểm tra: `curl http://127.0.0.1:8080/actuator/health` phải trả `{"status":"UP"}`.
- Nếu chưa chạy mà Docker Desktop đang mở: được phép chạy `docker compose up -d --wait` trong `D:\Capstone2`. Đó là thao tác duy nhất bạn được làm trong thư mục backend; **không sửa, không xóa file nào ở đó, không chạy `docker compose down -v`**.
- Docker Desktop chưa mở hoặc backend không lên được: báo **BLOCKED**.

**Bước 5 — Chạy thử.** Khởi động máy ảo, chạy `npx expo start --android`, và sửa màn hình mặc định để gọi `GET {EXPO_PUBLIC_API_URL}/actuator/health` rồi hiện kết quả. Giai đoạn 0 chỉ xong khi thấy `UP` trên màn hình máy ảo hoặc thiết bị. Với máy ảo, `EXPO_PUBLIC_API_URL` là `http://10.0.2.2:8080`.

**Những việc phải dừng lại hỏi tôi, không tự làm:**

- cần quyền quản trị (UAC) mà lệnh bị từ chối, hoặc cần khởi động lại máy;
- bật ảo hóa trong BIOS hay bật tính năng Windows (Hyper-V, Windows Hypervisor Platform) để máy ảo chạy được;
- chấp nhận giấy phép hoặc đăng nhập tài khoản thay tôi (tài khoản Expo/EAS, Google);
- một bước tải về lớn hơn khoảng 5 GB, hoặc ổ đĩa còn ít chỗ;
- gỡ, hạ cấp, hay thay phiên bản mặc định của phần mềm đang có trên máy.

Nếu không dựng được máy ảo (máy không hỗ trợ ảo hóa), phương án thay thế là điện thoại Android thật cắm USB, bật gỡ lỗi USB, dùng `adb reverse tcp:8080 tcp:8080`; nói với tôi để tôi cắm máy.

**Báo cáo Giai đoạn 0** phải có một bảng: từng công cụ — phiên bản tìm thấy ban đầu — đã cài gì — phiên bản sau cùng — lệnh kiểm tra và kết quả thật; danh sách biến môi trường đã đặt; và ảnh chụp hoặc mô tả đúng điều đã thấy trên máy ảo.

### D1. Cấu trúc

```
src/
  api/          axios, interceptor, kiểu dữ liệu, hàm gọi API theo nhóm
  auth/         store phiên đăng nhập (Zustand), SecureStore, luồng khởi động
  navigation/   các navigator, kiểu tham số màn hình
  features/     auth/ home/ analyze/ result/ history/ lookup/ reports/ notifications/ profile/
  components/   component dùng chung
  theme/        màu, cỡ chữ, khoảng cách
  constants/    tên dấu hiệu, câu lỗi, nhãn mức rủi ro — một chỗ duy nhất
  utils/        định dạng thời gian, thời lượng, số điện thoại
```

- Kiểu TypeScript cho mọi request và response theo Phần C; không dùng `any`.
- Dữ liệu server chỉ nằm trong TanStack Query; không chép sang Zustand.
- Sau thao tác thay đổi dữ liệu, làm mới đúng các truy vấn liên quan (gửi cuộc gọi → lịch sử; phân tích xong → lịch sử, số thông báo chưa đọc; xóa → lịch sử; báo cáo → báo cáo của tôi).
- Chú thích code bằng tiếng Việt, ngắn, chỉ ở chỗ cần giải thích lý do.
- Không đưa `.env`, token, mật khẩu vào git.

### D2. Kiểm thử

- Test (Jest) cho phần logic dễ sai: interceptor làm mới token khi nhiều request cùng 401; ánh xạ mã lỗi và dấu hiệu, kể cả mã lạ; kiểm tra đuôi và dung lượng file; chuẩn hóa số điện thoại trước khi đăng ký; định dạng thời lượng.
- `tsc --noEmit` và ESLint không lỗi.
- Mỗi màn hình phải được chạy thật với backend thật trước khi báo xong.

### D3. Các giai đoạn

Làm từng giai đoạn. Sau mỗi giai đoạn, báo cáo rồi **DỪNG**, chờ tôi nói `Tiếp tục giai đoạn N`.

| Giai đoạn | Nội dung |
|---|---|
| 0 | **Tự cấu hình môi trường** theo mục D0, tới khi một ứng dụng Expo trống chạy được trên emulator hoặc thiết bị và gọi được `GET /actuator/health` của backend. Đối chiếu `{API_URL}/v3/api-docs` với Phần C. Không viết tính năng. |
| 1 | **Khung.** Dự án Expo + TypeScript, theme, component nền, điều hướng, axios, TanStack Query, biến môi trường. |
| 2 | **Xác thực.** Đăng nhập, đăng ký, quên mật khẩu, lưu token, làm mới token, đăng xuất, màn hình khởi động. |
| 3 | **Gửi cuộc gọi.** Ghi âm, chọn file, kiểm tra file, tải lên có tiến độ. |
| 4 | **Kết quả.** Theo dõi phân tích, màn hình kết quả đủ bốn trạng thái, nghe lại, phân tích lại, xóa. |
| 5 | **Trang chủ và Lịch sử.** |
| 6 | **Tra cứu, báo cáo số, báo cáo của tôi.** |
| 7 | **Thông báo và thông báo đẩy.** |
| 8 | **Tài khoản.** Hồ sơ, đổi mật khẩu, công tắc cảnh báo. |
| 9 | **Rà soát.** Lint, kiểm tra kiểu, test; đi qua toàn bộ luồng với backend thật; liệt kê mọi thứ còn NOT VERIFIED. |

### D4. Báo cáo sau mỗi giai đoạn

```
Giai đoạn N — tên
Đã hoàn thành:   việc thật sự đã làm
File:            file đã tạo hoặc sửa
Lệnh đã chạy:    lệnh thật và kết quả thật (tổng / qua / lỗi)
Đã thử với backend thật:  màn hình nào, trên emulator hay thiết bị nào, kết quả
Vấn đề:          vấn đề thật gặp phải
Chưa xác minh:   NOT VERIFIED / BLOCKED / KNOWN BUG
Tiếp theo:       giai đoạn kế
```

Không viết "mọi thứ hoạt động" nếu chưa chạy. Không sửa kỳ vọng của test để test qua.

### D5. Khi có điều không khớp

- Backend thật trả khác Phần C: backend thật là đúng. Báo cho tôi chỗ khác nhau, không tự đoán và không sửa backend.
- Cần tài khoản để thử: tự đăng ký một tài khoản thường qua API đăng ký (email `@example.com`). Không cần tài khoản quản trị.
- Luồng quên mật khẩu: backend của tôi đang gửi mail thật; chỉ thử với địa chỉ email tôi cung cấp. Chưa có thì ghi **NOT VERIFIED**.
- Muốn thêm thư viện lớn, đổi cấu trúc, hay làm phần ngoài phạm vi: đề xuất, giải thích lý do và tác động, chờ tôi duyệt.

### D6. Bắt đầu

Chỉ làm **Giai đoạn 0** (tự cấu hình môi trường theo D0), báo cáo, rồi dừng.

---

## PHỤ LỤC — Cuộc gọi trực tiếp (chỉ dùng khi tôi yêu cầu giai đoạn VoIP)

Không làm phần này trong các giai đoạn 0–9.

1. `POST /api/v1/live-calls` (Bearer token), body tùy chọn `{"callerNumber": "0901234567"}` → `201`:

```json
{ "callId": "…", "analysisId": "…", "streamPath": "/api/v1/live-calls/stream", "ticket": "…",
  "ticketExpiresInSeconds": 60,
  "audioFormat": { "encoding": "pcm_s16le", "sampleRate": 16000, "channels": 1,
                   "speakerPrefix": { "0": "CALLER", "1": "CALLEE" } } }
```

2. Mở WebSocket `ws://<backend>/api/v1/live-calls/stream?ticket=<ticket>` trong 60 giây. Vé dùng một lần; không dùng Bearer token ở đây.
3. Chờ sự kiện `ready`, rồi gửi các gói **nhị phân**: byte đầu là người nói (`0` người gọi đến, `1` người dùng), phần còn lại là PCM 16 bit little-endian, một kênh, 16 kHz. Gói 100–500 ms. **Gửi cả hai luồng liên tục, kể cả khi im lặng.**
4. Nhận các sự kiện JSON:
   - `transcript`: `{speaker, start, end, text}` — một câu vừa nhận dạng.
   - `risk`: `{riskScore, riskLevel, confidence, indicators, newIndicators, modelProbability}` — rủi ro của cả cuộc gọi tới lúc này.
   - `alert`: mức rủi ro vừa tăng lên `MEDIUM` hoặc `HIGH`; có `atSeconds` và `triggeredBy: {speaker, text}`. Mỗi mức báo một lần. Đây là lúc rung và hiện cảnh báo.
   - `final`: kết quả chốt, có `endedBy`, `durationSeconds`, `transcript`, `turns`. Không nhận ra câu nào thì `riskScore`, `riskLevel` là `null`.
   - `error`: `{code, message}`, sau đó server đóng kết nối.
5. Kết thúc: gửi văn bản `{"type":"end"}`, chờ `final`.
6. Sau cuộc gọi, kết quả và ghi âm xem được qua các API ở C6 (`source` là `LIVE`).

Giới hạn hiện tại của backend: 2 cuộc gọi trực tiếp cùng lúc, mỗi cuộc tối đa 30 phút, tự đóng sau 30 giây im lặng trên kết nối; độ trễ từ lúc nói xong tới lúc có chữ đo được trung vị 4,6 giây.
