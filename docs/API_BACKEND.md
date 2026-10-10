# IVPDS — Tài liệu API Backend

Tài liệu này mô tả backend IVPDS hiện làm được gì và dùng API nào cho từng việc. Dành cho người viết ứng dụng mobile (React Native) và trang quản trị (React).

- Địa chỉ khi chạy bằng Docker Compose: `http://127.0.0.1:8080`
- Swagger (thử API trên trình duyệt): `http://127.0.0.1:8080/swagger-ui/index.html`
- Mô tả OpenAPI dạng JSON: `http://127.0.0.1:8080/v3/api-docs`
- Mọi đường dẫn nghiệp vụ bắt đầu bằng `/api/v1`.

Danh sách endpoint trong tài liệu này được đối chiếu với OpenAPI của backend đang chạy ngày 10/10/2026 (48 endpoint HTTP và 1 WebSocket).

## Mục lục

1. [Backend làm được gì](#1-backend-làm-được-gì)
2. [Quy ước chung](#2-quy-ước-chung)
3. [Xác thực và tài khoản](#3-xác-thực-và-tài-khoản)
4. [Hồ sơ người dùng](#4-hồ-sơ-người-dùng)
5. [Cuộc gọi và file audio](#5-cuộc-gọi-và-file-audio)
6. [Phân tích cuộc gọi](#6-phân-tích-cuộc-gọi)
7. [Phân tích cuộc gọi trực tiếp](#7-phân-tích-cuộc-gọi-trực-tiếp)
8. [Lịch sử](#8-lịch-sử)
9. [Danh sách đen và báo cáo số lừa đảo](#9-danh-sách-đen-và-báo-cáo-số-lừa-đảo)
10. [Thông báo và thông báo đẩy](#10-thông-báo-và-thông-báo-đẩy)
11. [API quản trị](#11-api-quản-trị)
12. [Bảng mã lỗi](#12-bảng-mã-lỗi)
13. [Luồng mẫu](#13-luồng-mẫu)
14. [Giới hạn và phần chưa kiểm chứng](#14-giới-hạn-và-phần-chưa-kiểm-chứng)

---

## 1. Backend làm được gì

| Việc | API chính | Ai dùng |
|---|---|---|
| Đăng ký, đăng nhập, làm mới token, đăng xuất | `/api/v1/auth/*` | Mọi người |
| Đổi mật khẩu, quên mật khẩu (mã 6 số qua email) | `/api/v1/auth/change-password`, `forgot-password`, `reset-password` | Người dùng |
| Xem và sửa hồ sơ, bật/tắt cảnh báo danh sách đen | `/api/v1/users/me` | Người dùng |
| Gửi file ghi âm cuộc gọi, xem, tải lại, xóa | `/api/v1/calls` | Người dùng |
| Phân tích cuộc gọi: audio → transcript → dấu hiệu → điểm và mức rủi ro | `/api/v1/calls/{callId}/analyses` | Người dùng |
| Phân tích cuộc gọi đang diễn ra, cảnh báo ngay trong cuộc gọi | `POST /api/v1/live-calls` + WebSocket | Người dùng |
| Lịch sử cuộc gọi kèm kết quả, có lọc | `/api/v1/history` | Người dùng |
| Tra một số có trong danh sách đen không | `/api/v1/blacklist/lookup` | Người dùng |
| Báo cáo một số lừa đảo để quản trị viên duyệt | `/api/v1/blacklist/reports` | Người dùng |
| Thông báo trong ứng dụng, đăng ký thiết bị nhận thông báo đẩy | `/api/v1/notifications` | Người dùng |
| Quản lý tài khoản, danh sách đen, báo cáo, mẫu lừa đảo; xem cuộc gọi của mọi người; thống kê | `/api/v1/admin/*` | Quản trị viên |

Một cuộc gọi được phân tích theo chuỗi: **audio → FFmpeg → Whisper (PhoWhisper) → transcript → Rule Engine + NLP Model → Risk Engine → điểm 0–100 và mức LOW / MEDIUM / HIGH**. Phần AI chạy ở một service riêng (FastAPI); ứng dụng chỉ gọi backend.

---

## 2. Quy ước chung

### 2.1 Xác thực

Trừ các API ghi "Công khai", mọi request phải có header:

```
Authorization: Bearer <accessToken>
```

- `accessToken` sống 15 phút. Hết hạn thì gọi `POST /api/v1/auth/refresh` để lấy cặp token mới.
- `refreshToken` sống 7 ngày và **chỉ dùng được một lần**: mỗi lần làm mới, token cũ bị vô hiệu và backend trả token mới.
- Thiếu token, token sai hoặc hết hạn: `401 UNAUTHORIZED`.
- Tài khoản bị khóa: access token bị từ chối ngay ở request kế tiếp (`401`), đăng nhập trả `403 ACCOUNT_LOCKED`.

### 2.2 Vai trò

| Vai trò | Quyền |
|---|---|
| `USER` | Mọi API ngoài `/api/v1/admin/**`. Chỉ thấy dữ liệu của chính mình. |
| `ADMIN` | Thêm toàn bộ `/api/v1/admin/**`. |

Người dùng thường gọi API quản trị nhận `403 FORBIDDEN`. Tài khoản đăng ký qua API luôn là `USER`; tài khoản `ADMIN` đầu tiên được tạo lúc backend khởi động từ `ADMIN_EMAIL` và `ADMIN_PASSWORD` trong `.env`.

Truy cập dữ liệu của người khác (cuộc gọi, thông báo...) trả `404`, không phải `403`, để không lộ việc dữ liệu đó có tồn tại.

### 2.3 Định dạng dữ liệu

- Body gửi và nhận là JSON (`Content-Type: application/json`), trừ upload audio (`multipart/form-data`) và tải audio (nhị phân).
- Thời gian theo ISO 8601, giờ UTC: `2026-10-10T06:15:30Z`.
- Id là UUID.
- Trường không có giá trị được trả là `null`, không bị bỏ đi.

### 2.4 Số điện thoại

Backend chuẩn hóa mọi số về một dạng để so sánh:

| Nhập | Lưu và trả về |
|---|---|
| `0901234567`, `090 123 4567`, `090.123.4567` | `+84901234567` |
| `84901234567`, `+84901234567` | `+84901234567` |
| `19001234` (tổng đài) | `19001234` |

Số phải có 6–15 chữ số, có thể bắt đầu bằng `+`. Sai dạng: `400 INVALID_PHONE_NUMBER`.

Khi **tìm kiếm** theo số (`callerNumber`, `query`), chỉ cần gõ một phần chữ số; khoảng trắng và số 0 đầu được bỏ qua, nên `0901 23` tìm ra `+84901234567`.

### 2.5 Phân trang

Các API danh sách nhận `page` (bắt đầu từ 0, mặc định 0) và `size` (mặc định 20, tối đa 100), và trả:

```json
{
  "items": [],
  "page": 0,
  "size": 20,
  "totalItems": 57,
  "totalPages": 3
}
```

### 2.6 Lỗi

Mọi lỗi có cùng một dạng:

```json
{
  "timestamp": "2026-10-10T06:15:30.123Z",
  "status": 400,
  "code": "VALIDATION_FAILED",
  "message": "Request validation failed.",
  "path": "/api/v1/auth/register",
  "requestId": "3f2c9a1e-...",
  "fieldErrors": [
    { "field": "password", "message": "size must be between 8 and 72" }
  ]
}
```

- Ứng dụng nên xử lý theo `code`, không theo `message`. `message` bằng tiếng Anh, dành cho người lập trình.
- `fieldErrors` chỉ có khi lỗi là `VALIDATION_FAILED`.
- Bảng đầy đủ các `code` ở [mục 12](#12-bảng-mã-lỗi).

### 2.7 Mã truy vết

Mỗi response có header `X-Request-Id`. Khi báo lỗi cho người làm backend, gửi kèm giá trị này để tra log. Ứng dụng có thể tự gửi `X-Request-Id` trong request; backend sẽ dùng lại.

### 2.8 API công khai (không cần token)

`/api/v1/auth/register`, `login`, `refresh`, `logout`, `forgot-password`, `reset-password`; `/actuator/health`; Swagger và `/v3/api-docs`.

---

## 3. Xác thực và tài khoản

### POST `/api/v1/auth/register` — Đăng ký (Công khai)

Tạo tài khoản `USER` và đăng nhập luôn.

| Trường | Bắt buộc | Quy tắc |
|---|---|---|
| `email` | Có | Email hợp lệ, tối đa 255 ký tự; không phân biệt hoa thường |
| `password` | Có | 8–72 ký tự |
| `fullName` | Có | Tối đa 100 ký tự |
| `phoneNumber` | Không | 6–15 chữ số, có thể bắt đầu bằng `+` (ở API này không chấp nhận khoảng trắng hay dấu chấm) |

```json
{ "email": "an@example.com", "password": "matkhau-an-toan-1", "fullName": "Nguyễn Văn An", "phoneNumber": "0901234567" }
```

Trả `201`:

```json
{
  "accessToken": "eyJhbGciOi...",
  "refreshToken": "b7Jk2...",
  "tokenType": "Bearer",
  "expiresIn": 900,
  "user": { "id": "0b9f...", "email": "an@example.com", "fullName": "Nguyễn Văn An", "roles": ["USER"] }
}
```

Lỗi: `400 VALIDATION_FAILED`, `409 EMAIL_ALREADY_REGISTERED`.

### POST `/api/v1/auth/login` — Đăng nhập (Công khai)

```json
{ "email": "an@example.com", "password": "matkhau-an-toan-1" }
```

Trả `200` cùng dạng với đăng ký. Lỗi: `401 INVALID_CREDENTIALS` (sai email hoặc mật khẩu, không nói rõ cái nào), `403 ACCOUNT_LOCKED`.

### POST `/api/v1/auth/refresh` — Làm mới token (Công khai)

```json
{ "refreshToken": "b7Jk2..." }
```

Trả `200` với cặp token mới. Refresh token cũ không dùng lại được. Lỗi: `401 INVALID_REFRESH_TOKEN` (sai, hết hạn, đã dùng hoặc đã bị thu hồi) — khi đó ứng dụng phải đưa người dùng về màn hình đăng nhập.

### POST `/api/v1/auth/logout` — Đăng xuất (Công khai)

```json
{ "refreshToken": "b7Jk2..." }
```

Trả `204`. Thu hồi refresh token đó. Access token hiện tại vẫn dùng được tới khi hết hạn (tối đa 15 phút), nên ứng dụng phải tự xóa nó. Nếu đã đăng ký thiết bị nhận thông báo đẩy, gọi `DELETE /api/v1/notifications/devices` **trước** khi đăng xuất.

### POST `/api/v1/auth/change-password` — Đổi mật khẩu

```json
{ "currentPassword": "matkhau-cu", "newPassword": "matkhau-moi-1" }
```

Trả `204`. **Mọi phiên đăng nhập bị đăng xuất** (mọi refresh token bị thu hồi); người dùng đăng nhập lại bằng mật khẩu mới. Lỗi: `400 INVALID_CURRENT_PASSWORD`, `400 VALIDATION_FAILED`.

### POST `/api/v1/auth/forgot-password` — Quên mật khẩu (Công khai)

```json
{ "email": "an@example.com" }
```

Luôn trả `204`, dù email có đăng ký hay không (để không lộ email nào có tài khoản). Nếu email có tài khoản, backend gửi một mã 6 chữ số, có hiệu lực 15 phút. Yêu cầu lại trong vòng 60 giây không gửi thêm mail.

Mail đi đâu tùy cấu hình `MAIL_HOST` trong `.env`: mặc định là Mailpit (hộp thư thử, xem ở `http://127.0.0.1:8025`); nếu đặt một máy chủ SMTP thật (ví dụ Gmail) thì mail được gửi thật tới địa chỉ đó.

### POST `/api/v1/auth/reset-password` — Đặt lại mật khẩu bằng mã (Công khai)

```json
{ "email": "an@example.com", "code": "482913", "newPassword": "matkhau-moi-1" }
```

Trả `204` và đăng xuất mọi phiên. Lỗi: `400 INVALID_RESET_CODE` (sai, hết hạn, hoặc đã nhập sai quá 5 lần — khi đó phải xin mã mới).

---

## 4. Hồ sơ người dùng

### GET `/api/v1/users/me` — Xem hồ sơ

```json
{
  "id": "0b9f...",
  "email": "an@example.com",
  "fullName": "Nguyễn Văn An",
  "phoneNumber": "+84901234567",
  "status": "ACTIVE",
  "blacklistAlertEnabled": true,
  "roles": ["USER"],
  "createdAt": "2026-10-01T03:00:00Z"
}
```

### PATCH `/api/v1/users/me` — Sửa hồ sơ

Chỉ gửi trường muốn đổi; trường không gửi giữ nguyên.

| Trường | Quy tắc |
|---|---|
| `fullName` | 1–100 ký tự, không toàn khoảng trắng |
| `phoneNumber` | Số điện thoại ở mọi dạng trong [mục 2.4](#24-số-điện-thoại) |
| `blacklistAlertEnabled` | `true` / `false`: có nhận cảnh báo khi số gọi đến nằm trong danh sách đen không |

```json
{ "blacklistAlertEnabled": false }
```

Trả `200` với hồ sơ mới. Email không đổi được.

---

## 5. Cuộc gọi và file audio

Một "cuộc gọi" là một bản ghi gồm: số người gọi (nếu biết), thời điểm, nguồn, và file audio. File audio nằm ở MinIO; database chỉ giữ thông tin mô tả.

### POST `/api/v1/calls` — Gửi một cuộc gọi

`multipart/form-data`:

| Phần | Bắt buộc | Mô tả |
|---|---|---|
| `audio` | Có | File ghi âm. Định dạng: `mp3`, `wav`, `m4a`, `aac`, `ogg`, `webm`, `3gp`, `amr`, `flac`. Tối đa 50 MB. Backend kiểm tra cả đuôi file lẫn nội dung |
| `callerNumber` | Không | Số người gọi |
| `calledAt` | Không | Thời điểm cuộc gọi diễn ra (ISO 8601) |
| `source` | Không | `UPLOADED` (mặc định: chọn file từ máy) hoặc `RECORDED` (ghi âm trong ứng dụng). `LIVE` không dùng được ở đây |

```bash
curl -X POST http://127.0.0.1:8080/api/v1/calls \
  -H "Authorization: Bearer $TOKEN" \
  -F "audio=@cuoc-goi.m4a" -F "callerNumber=0901234567" -F "source=RECORDED"
```

Trả `201`:

```json
{
  "id": "5d0c...",
  "callerNumber": "+84901234567",
  "calledAt": null,
  "source": "RECORDED",
  "createdAt": "2026-10-10T06:15:30Z",
  "audio": {
    "id": "a41e...",
    "originalFilename": "cuoc-goi.m4a",
    "contentType": "audio/mp4",
    "sizeBytes": 1245678,
    "durationSeconds": null,
    "checksumSha256": "9f2b..."
  }
}
```

Sau khi gửi:

- **Phân tích tự bắt đầu** (cấu hình `ANALYSIS_AUTO_START=true`, mặc định). Ứng dụng chỉ cần hỏi kết quả ở [mục 6](#6-phân-tích-cuộc-gọi).
- Nếu `callerNumber` nằm trong danh sách đen và người dùng chưa tắt cảnh báo, một thông báo `BLACKLISTED_CALLER` được tạo ngay.
- `durationSeconds` là `null` cho tới khi phân tích xong lần đầu (thời lượng do AI service đo).

Lỗi: `400 EMPTY_AUDIO`, `400 INVALID_PHONE_NUMBER`, `400 INVALID_CALL_SOURCE`, `413 PAYLOAD_TOO_LARGE`, `415 UNSUPPORTED_AUDIO_FORMAT`, `415 INVALID_AUDIO_CONTENT` (nội dung không khớp đuôi file), `503 STORAGE_UNAVAILABLE`.

### GET `/api/v1/calls` — Danh sách cuộc gọi của tôi

Phân trang, mới nhất trước. Mỗi mục có dạng như trên. Nếu cần cả kết quả phân tích, dùng `/api/v1/history`.

### GET `/api/v1/calls/{id}` — Một cuộc gọi

Lỗi: `404 CALL_NOT_FOUND`.

### GET `/api/v1/calls/{id}/audio` — Tải file audio

Trả nội dung file với `Content-Type` của file và `Content-Disposition: attachment`. Chỉ chủ cuộc gọi tải được; quản trị viên cũng không tải được ghi âm của người dùng. Lỗi: `404 CALL_NOT_FOUND`, `404 AUDIO_OBJECT_MISSING`, `503 STORAGE_UNAVAILABLE`.

### DELETE `/api/v1/calls/{id}` — Xóa cuộc gọi

Trả `204`. Xóa cả file audio, transcript và mọi kết quả phân tích. Thông báo liên quan được giữ lại nhưng không còn trỏ tới cuộc gọi (`callId` thành `null`). Lỗi: `404 CALL_NOT_FOUND`, `409 ANALYSIS_IN_PROGRESS` (đang phân tích; thử lại sau khi xong).

---

## 6. Phân tích cuộc gọi

Phân tích chạy nền. Một cuộc gọi có thể được phân tích nhiều lần; mỗi lần là một bản ghi riêng.

Trạng thái: `PENDING` (đang chờ) → `PROCESSING` (đang chạy) → `COMPLETED` hoặc `FAILED`.

### POST `/api/v1/calls/{callId}/analyses` — Yêu cầu phân tích (lại)

Không cần body. Trả `202` với lần phân tích vừa tạo (thường ở trạng thái `PENDING`).

Thường **không cần gọi API này** sau khi upload, vì phân tích đã tự bắt đầu. Dùng khi muốn phân tích lại: lần trước lỗi, hoặc sau một cuộc gọi trực tiếp bị lỗi giữa chừng.

Lỗi: `404 CALL_NOT_FOUND`, `409 ANALYSIS_IN_PROGRESS`, `409 CALL_HAS_NO_AUDIO`, `503 ANALYSIS_QUEUE_FULL`.

### GET `/api/v1/calls/{callId}/analyses/latest` — Kết quả mới nhất

Ứng dụng gọi lặp lại (ví dụ mỗi 2–3 giây) cho tới khi `status` là `COMPLETED` hoặc `FAILED`.

```json
{
  "id": "c7a2...",
  "callId": "5d0c...",
  "status": "COMPLETED",
  "errorCode": null,
  "errorMessage": null,
  "createdAt": "2026-10-10T06:15:30Z",
  "startedAt": "2026-10-10T06:15:31Z",
  "completedAt": "2026-10-10T06:16:02Z",
  "transcript": "a lô mình là bên bộ công an ạ ...",
  "language": "vi",
  "riskScore": 100,
  "riskLevel": "HIGH",
  "confidence": 1.0,
  "indicators": ["AUTHORITY_IMPERSONATION", "LEGAL_THREAT", "SECRECY_DEMAND"],
  "details": {
    "sttModel": "faster-whisper/phowhisper-medium-int8 (int8, cpu)",
    "modelProbability": 0.999912,
    "nlpModelVersion": "2026.10.09-phobert-base-r6",
    "rulesetVersion": "2026.10.5",
    "riskEngineVersion": "2026.10.1"
  }
}
```

| Trường | Ý nghĩa |
|---|---|
| `riskScore` | Điểm rủi ro cuối cùng, 0–100 |
| `riskLevel` | `LOW` (0–29), `MEDIUM` (30–59), `HIGH` (60–100) |
| `confidence` | Mức chắc chắn của kết luận, 0–1. **Không phải** xác suất lừa đảo |
| `indicators` | Các dấu hiệu Rule Engine tìm thấy |
| `details.modelProbability` | Xác suất lừa đảo do NLP Model tính. **Không phải** điểm rủi ro: điểm rủi ro còn tính cả các dấu hiệu |

Ba con số `riskScore`, `confidence`, `modelProbability` là ba thứ khác nhau; giao diện nên hiển thị `riskLevel` và `riskScore`.

Khi `status` là `FAILED`: `errorCode` và `errorMessage` có giá trị; `riskScore`, `riskLevel`, `confidence`, `indicators` đều là `null`. **Backend không bao giờ bịa ra một mức rủi ro khi phân tích lỗi.** `transcript` có thể vẫn có nếu lỗi xảy ra sau bước nhận dạng giọng nói. Các `errorCode` ở [mục 12.3](#123-mã-lỗi-của-một-lần-phân-tích-errorcode).

Lỗi HTTP: `404 CALL_NOT_FOUND`, `404 ANALYSIS_NOT_FOUND` (cuộc gọi chưa được phân tích lần nào).

### GET `/api/v1/calls/{callId}/analyses` — Mọi lần phân tích của một cuộc gọi

Trả một mảng (không phân trang), mới nhất trước, mỗi phần tử có dạng như trên.

### Các dấu hiệu (`indicators`)

| Mã | Nghĩa |
|---|---|
| `OTP_REQUEST` | Đòi đọc mã OTP |
| `MONEY_TRANSFER` | Yêu cầu chuyển tiền |
| `BANK_IMPERSONATION` | Tự xưng ngân hàng |
| `URGENCY` | Thúc giục làm ngay |
| `ACCOUNT_LOCK_THREAT` | Dọa khóa tài khoản |
| `SENSITIVE_INFORMATION` | Đòi thông tin nhạy cảm (số thẻ, mật khẩu, CCCD...) |
| `AUTHORITY_IMPERSONATION` | Tự xưng công an, viện kiểm sát, tòa án, cơ quan nhà nước |
| `LEGAL_THREAT` | Dọa bắt giữ, khởi tố, liên quan vụ án |
| `HARM_THREAT` | Đe dọa gây hại |
| `SECRECY_DEMAND` | Yêu cầu giữ bí mật, không nói với ai |
| `REMOTE_ACCESS_REQUEST` | Yêu cầu cài ứng dụng, chia sẻ màn hình, điều khiển từ xa |
| `FINANCIAL_BAIT` | Mồi tài chính (trúng thưởng, hoàn tiền, lãi cao) |
| `UNUSUAL_PAYMENT` | Hình thức thanh toán bất thường |
| `CALL_HANDOFF` | Chuyển máy cho "cán bộ" khác |
| `COORDINATED_CALLERS` | Nhiều người phía gọi đến phối hợp |

---

## 7. Phân tích cuộc gọi trực tiếp

Dành cho ứng dụng tự thực hiện cuộc gọi (VoIP): âm thanh được gửi lên trong lúc gọi, backend trả transcript và cảnh báo ngay khi rủi ro tăng. Giao thức đầy đủ, ví dụ TypeScript và cách thử nằm ở [LIVE_CALL_API.md](LIVE_CALL_API.md). Tóm tắt:

### POST `/api/v1/live-calls` — Mở cuộc gọi

```json
{ "callerNumber": "0901234567" }
```

`callerNumber` không bắt buộc. Trả `201`:

```json
{
  "callId": "5d0c...",
  "analysisId": "c7a2...",
  "streamPath": "/api/v1/live-calls/stream",
  "ticket": "Zk3v...",
  "ticketExpiresInSeconds": 60,
  "audioFormat": {
    "encoding": "pcm_s16le", "sampleRate": 16000, "channels": 1,
    "speakerPrefix": { "0": "CALLER", "1": "CALLEE" }
  }
}
```

Cuộc gọi được tạo ngay với `source` là `LIVE`; nếu số gọi đến nằm trong danh sách đen, cảnh báo `BLACKLISTED_CALLER` được tạo ngay lúc này.

### WebSocket `/api/v1/live-calls/stream?ticket=<ticket>`

- Mở trong vòng 60 giây; `ticket` chỉ dùng được một lần. Không dùng access token ở đây.
- **Gửi:** các gói nhị phân, byte đầu là người nói (`0` người gọi, `1` người dùng), phần còn lại là PCM 16 bit, 16 kHz, một kênh. Kết thúc bằng tin nhắn văn bản `{"type":"end"}`.
- **Nhận:** các sự kiện JSON `ready`, `transcript`, `risk`, `alert` (rủi ro vừa lên mức mới — hiện cảnh báo cho người dùng), `final` (kết quả cuối), `error`.

Sau cuộc gọi, kết quả và ghi âm (WAV hai kênh) được lưu như mọi cuộc gọi khác và xem được bằng các API ở mục 5, 6, 8.

---

## 8. Lịch sử

Giống danh sách cuộc gọi nhưng kèm kết quả phân tích mới nhất của từng cuộc gọi. Đây là API cho màn hình "Lịch sử".

### GET `/api/v1/history` — Lịch sử của tôi

| Tham số | Mô tả |
|---|---|
| `riskLevel` | `LOW` / `MEDIUM` / `HIGH` |
| `status` | `PENDING` / `PROCESSING` / `COMPLETED` / `FAILED` (trạng thái của lần phân tích mới nhất) |
| `from`, `to` | Khoảng thời điểm gửi cuộc gọi lên (ISO 8601) |
| `callerNumber` | Một phần chữ số của số người gọi |
| `page`, `size` | Phân trang |

Ví dụ: `GET /api/v1/history?riskLevel=HIGH&callerNumber=0901&size=10`

```json
{
  "items": [
    {
      "callId": "5d0c...",
      "callerNumber": "+84901234567",
      "callerBlacklisted": true,
      "calledAt": null,
      "source": "UPLOADED",
      "createdAt": "2026-10-10T06:15:30Z",
      "durationSeconds": 150.2,
      "analysis": {
        "id": "c7a2...",
        "status": "COMPLETED",
        "errorCode": null,
        "errorMessage": null,
        "completedAt": "2026-10-10T06:16:02Z",
        "riskScore": 100,
        "riskLevel": "HIGH",
        "confidence": 1.0,
        "indicators": ["AUTHORITY_IMPERSONATION", "LEGAL_THREAT"],
        "transcript": null,
        "details": null
      },
      "owner": null
    }
  ],
  "page": 0, "size": 10, "totalItems": 1, "totalPages": 1
}
```

- `analysis` là `null` nếu cuộc gọi chưa được phân tích lần nào.
- `callerBlacklisted`: số người gọi **hiện** có đang nằm trong danh sách đen không.
- Trong danh sách, `transcript` và `details` luôn là `null` (để danh sách nhẹ). Lấy chúng ở API chi tiết.
- `owner` chỉ có giá trị trong API quản trị.

Lỗi: `400 BAD_REQUEST` khi tham số lọc sai giá trị.

### GET `/api/v1/history/{callId}` — Chi tiết một cuộc gọi

Cùng dạng, nhưng `analysis.transcript` và `analysis.details` có đầy đủ. Lỗi: `404 CALL_NOT_FOUND`.

---

## 9. Danh sách đen và báo cáo số lừa đảo

### GET `/api/v1/blacklist/lookup?phoneNumber=` — Tra một số

Nhận số ở mọi dạng.

```json
{ "phoneNumber": "+84901234567", "blacklisted": true, "reason": "Giả danh công an", "since": "2026-10-09T02:00:00Z" }
```

Số không bị chặn: `blacklisted` là `false`, `reason` và `since` là `null`. Lỗi: `400 INVALID_PHONE_NUMBER`.

### POST `/api/v1/blacklist/reports` — Báo cáo một số lừa đảo

Người dùng không tự chặn được số; họ gửi báo cáo và quản trị viên duyệt.

| Trường | Mô tả |
|---|---|
| `phoneNumber` | Số bị báo cáo |
| `callId` | Một cuộc gọi của chính mình. Nếu không gửi `phoneNumber`, backend lấy số người gọi của cuộc gọi này |
| `reason` | Lý do, tối đa 1000 ký tự (không bắt buộc) |

Phải có ít nhất `phoneNumber` hoặc `callId`. Cách dùng thường gặp — nút "Báo cáo số này" ở màn hình chi tiết cuộc gọi:

```json
{ "callId": "5d0c...", "reason": "Tự xưng công an, đòi chuyển tiền" }
```

Trả `201`:

```json
{
  "id": "e19a...",
  "phoneNumber": "+84901234567",
  "callId": "5d0c...",
  "reason": "Tự xưng công an, đòi chuyển tiền",
  "status": "PENDING",
  "createdAt": "2026-10-10T06:20:00Z",
  "reviewedAt": null
}
```

Quy tắc:

- Mỗi người báo cáo một số **một lần**, kể cả khi báo cáo trước đã bị từ chối (`409 NUMBER_ALREADY_REPORTED`).
- Số đang bị chặn thì không cần báo cáo nữa (`409 PHONE_NUMBER_ALREADY_BLACKLISTED`).
- Mỗi tài khoản có tối đa 20 báo cáo đang chờ duyệt (`429 TOO_MANY_PENDING_REPORTS`).
- Gửi cả `callId` và `phoneNumber` mà số không trùng số người gọi của cuộc gọi đó: `400 PHONE_NUMBER_MISMATCH`.

Lỗi khác: `400 INVALID_PHONE_NUMBER` (thiếu số, sai dạng, hoặc cuộc gọi không có số người gọi), `404 CALL_NOT_FOUND`, `400 VALIDATION_FAILED` (lý do quá dài).

### GET `/api/v1/blacklist/reports` — Các báo cáo của tôi

Phân trang, mới nhất trước. `status` là `PENDING`, `APPROVED` (số đã bị chặn) hoặc `REJECTED`.

---

## 10. Thông báo và thông báo đẩy

Backend tự tạo thông báo khi:

| `type` | Khi nào |
|---|---|
| `HIGH_RISK_CALL` | Một cuộc gọi phân tích xong ở mức HIGH |
| `SUSPICIOUS_CALL` | Một cuộc gọi phân tích xong ở mức MEDIUM |
| `BLACKLISTED_CALLER` | Có cuộc gọi (gửi file hoặc trực tiếp) từ số trong danh sách đen, và người dùng chưa tắt `blacklistAlertEnabled` |

Mức LOW và phân tích lỗi không tạo thông báo. Tiêu đề và nội dung bằng tiếng Việt, hiển thị thẳng được.

### GET `/api/v1/notifications` — Danh sách thông báo

Tham số: `unreadOnly` (`true` để chỉ lấy chưa đọc), `page`, `size`.

```json
{
  "items": [
    {
      "id": "77b1...",
      "type": "HIGH_RISK_CALL",
      "title": "Cuộc gọi có nguy cơ lừa đảo cao",
      "message": "Cuộc gọi từ số +84901234567 được đánh giá mức nguy cơ cao với 100/100 điểm rủi ro. Không cung cấp mã OTP, mật khẩu hay chuyển tiền theo yêu cầu của người gọi.",
      "read": false,
      "readAt": null,
      "analysisId": "c7a2...",
      "callId": "5d0c...",
      "createdAt": "2026-10-10T06:16:02Z"
    }
  ],
  "page": 0, "size": 20, "totalItems": 1, "totalPages": 1
}
```

Dùng `callId` để mở màn hình chi tiết cuộc gọi khi người dùng bấm vào thông báo. `callId` có thể là `null` nếu cuộc gọi đã bị xóa.

### GET `/api/v1/notifications/unread-count` — Số chưa đọc

```json
{ "unreadCount": 3 }
```

### POST `/api/v1/notifications/{id}/read` — Đánh dấu đã đọc

Trả `200` với thông báo đã cập nhật. Lỗi: `404 NOTIFICATION_NOT_FOUND`.

### POST `/api/v1/notifications/read-all` — Đánh dấu đã đọc tất cả

```json
{ "marked": 3 }
```

### Thông báo đẩy (Expo)

Để người dùng nhận thông báo khi ứng dụng không mở, ứng dụng đăng ký Expo push token của thiết bị.

#### PUT `/api/v1/notifications/devices` — Đăng ký thiết bị

```json
{ "token": "ExponentPushToken[xxxxxxxxxxxxxxxxxxxxxx]", "platform": "ANDROID" }
```

`platform`: `ANDROID`, `IOS` hoặc `WEB`. Trả `200`:

```json
{ "id": "9c3d...", "token": "ExponentPushToken[xxxxxxxxxxxxxxxxxxxxxx]", "platform": "ANDROID",
  "createdAt": "2026-10-10T06:00:00Z", "lastSeenAt": "2026-10-10T06:00:00Z" }
```

- Gọi **sau mỗi lần đăng nhập** và khi token đổi; gọi lại với cùng token là an toàn.
- Một token thuộc về người đăng nhập sau cùng trên thiết bị đó.
- Mỗi người tối đa 10 thiết bị; đăng ký thêm thì thiết bị lâu không dùng nhất bị gỡ.

Lỗi: `400 VALIDATION_FAILED` (token không đúng dạng Expo, thiếu `platform`).

#### GET `/api/v1/notifications/devices` — Các thiết bị của tôi

Trả một mảng (không phân trang).

#### DELETE `/api/v1/notifications/devices?token=` — Gỡ thiết bị

Trả `204`. Gọi **khi đăng xuất**, trước khi gọi `logout`. Token phải được mã hóa URL (dấu `[` `]`). Token không tồn tại hoặc không phải của mình thì không làm gì và vẫn trả `204`.

#### Nội dung một thông báo đẩy

```json
{
  "to": "ExponentPushToken[...]",
  "title": "Cuộc gọi có nguy cơ lừa đảo cao",
  "body": "Cuộc gọi từ số +84901234567 ...",
  "sound": "default",
  "priority": "high",
  "data": { "notificationId": "77b1...", "type": "HIGH_RISK_CALL", "callId": "5d0c...", "analysisId": "c7a2..." }
}
```

Ứng dụng đọc `data` để mở đúng màn hình.

**Kênh đẩy mặc định tắt.** Muốn bật, đặt `PUSH_ENABLED=true` trong `.env` rồi khởi động lại backend. Khi bật, tiêu đề và nội dung thông báo (có số điện thoại người gọi) được gửi tới Expo rồi Apple/Google. `PUSH_ACCESS_TOKEN` chỉ cần khi dự án Expo bật enhanced push security. Khi kênh đẩy tắt, các API đăng ký thiết bị vẫn hoạt động và thông báo vẫn có trong `GET /api/v1/notifications`.

---

## 11. API quản trị

Tất cả nằm dưới `/api/v1/admin` và cần vai trò `ADMIN`.

### 11.1 Tài khoản người dùng

| API | Mô tả |
|---|---|
| `GET /api/v1/admin/users` | Tìm tài khoản, mới nhất trước. `query` tìm trong email và họ tên; `status` là `ACTIVE` / `LOCKED`; phân trang |
| `GET /api/v1/admin/users/{id}` | Một tài khoản. Lỗi: `404 USER_NOT_FOUND` |
| `PATCH /api/v1/admin/users/{id}/status` | Khóa hoặc mở khóa |

```json
{ "status": "LOCKED" }
```

Một tài khoản trong kết quả:

```json
{ "id": "0b9f...", "email": "an@example.com", "fullName": "Nguyễn Văn An", "phoneNumber": "+84901234567",
  "status": "ACTIVE", "roles": ["USER"], "blacklistAlertEnabled": true, "createdAt": "2026-10-01T03:00:00Z" }
```

Khóa một tài khoản: mọi phiên của tài khoản đó bị đăng xuất và access token bị từ chối ngay ở request kế tiếp. Quản trị viên không tự khóa được chính mình (`409 CANNOT_LOCK_OWN_ACCOUNT`).

### 11.2 Cuộc gọi của mọi người dùng

| API | Mô tả |
|---|---|
| `GET /api/v1/admin/calls` | Như `/api/v1/history` nhưng của mọi người dùng. Thêm tham số `userId`. Dùng `riskLevel=HIGH` để theo dõi cuộc gọi rủi ro cao |
| `GET /api/v1/admin/calls/{callId}` | Chi tiết kèm transcript |

Kết quả có dạng của mục 8, với `owner` có giá trị:

```json
"owner": { "id": "0b9f...", "email": "an@example.com", "fullName": "Nguyễn Văn An" }
```

Quản trị viên đọc được kết quả và transcript nhưng **không tải được ghi âm** của người dùng.

### 11.3 Danh sách đen

| API | Mô tả |
|---|---|
| `GET /api/v1/admin/blacklist` | Danh sách, mới nhất trước. `query` (một phần chữ số), `active` (`true`/`false`), phân trang |
| `POST /api/v1/admin/blacklist` | Thêm một số: `{"phoneNumber": "0901234567", "reason": "Giả danh ngân hàng"}`. Trả `201`. Lỗi: `409 PHONE_NUMBER_ALREADY_BLACKLISTED` (kể cả số đã tắt) |
| `PATCH /api/v1/admin/blacklist/{id}` | Sửa lý do hoặc bật/tắt: `{"reason": "...", "active": false}` |
| `DELETE /api/v1/admin/blacklist/{id}` | Xóa hẳn. Trả `204` |

Một dòng:

```json
{ "id": "f0a1...", "phoneNumber": "+84901234567", "reason": "Giả danh ngân hàng", "active": true,
  "createdBy": "ad11...", "createdAt": "2026-10-09T02:00:00Z", "updatedAt": "2026-10-09T02:00:00Z" }
```

`reason` là nội dung người dùng thấy khi tra cứu, tối đa 1000 ký tự. Số đã tắt (`active: false`) không còn bị cảnh báo nhưng vẫn được giữ lại.

### 11.4 Duyệt báo cáo số lừa đảo

| API | Mô tả |
|---|---|
| `GET /api/v1/admin/blacklist/reports` | Hàng chờ, mới nhất trước. `status` (`PENDING`/`APPROVED`/`REJECTED`), `query` (một phần chữ số), phân trang |
| `POST /api/v1/admin/blacklist/reports/{id}/approve` | Duyệt |
| `POST /api/v1/admin/blacklist/reports/{id}/reject` | Từ chối |

Một báo cáo trong hàng chờ:

```json
{
  "id": "e19a...",
  "phoneNumber": "+84901234567",
  "reporterId": "0b9f...",
  "callId": "5d0c...",
  "reason": "Tự xưng công an, đòi chuyển tiền",
  "status": "PENDING",
  "reviewedBy": null,
  "reviewedAt": null,
  "createdAt": "2026-10-10T06:20:00Z",
  "reportsForNumber": 3,
  "blacklisted": false
}
```

- `reportsForNumber`: số người dùng khác nhau đã báo cáo số này. Nhiều người báo cáo cùng một số là tín hiệu đáng tin hơn.
- Có `callId` thì xem cuộc gọi đó ở `GET /api/v1/admin/calls/{callId}` để quyết định.

**Duyệt:** body không bắt buộc. `{"reason": "Đã xác minh: giả danh công an"}` là lý do người dùng sẽ thấy khi tra cứu; bỏ trống thì dùng lý do của báo cáo. Khi duyệt, số được đưa vào danh sách đen (hoặc bật lại nếu đã từng bị gỡ), và **mọi báo cáo đang chờ về số đó đều được duyệt theo**.

**Từ chối:** chỉ báo cáo đó bị từ chối; các báo cáo khác về cùng số giữ nguyên.

Lỗi: `404 BLACKLIST_REPORT_NOT_FOUND`, `409 REPORT_ALREADY_REVIEWED`, `409 REPORT_REVIEW_CONFLICT` (hai quản trị viên thao tác cùng lúc; thử lại).

### 11.5 Mẫu lừa đảo

Quản trị viên thêm các cụm từ đặc trưng của kẻ lừa đảo. Rule Engine dùng các mẫu **đang bật** ở mọi lần phân tích kế tiếp (cả file lẫn cuộc gọi trực tiếp); không cần khởi động lại gì.

| API | Mô tả |
|---|---|
| `GET /api/v1/admin/phishing-patterns` | Danh sách, mới nhất trước. `query` (tìm trong tên và cụm từ), `indicatorCode`, `active`, phân trang |
| `GET /api/v1/admin/phishing-patterns/{id}` | Một mẫu |
| `POST /api/v1/admin/phishing-patterns` | Thêm. Trả `201` |
| `PATCH /api/v1/admin/phishing-patterns/{id}` | Sửa hoặc bật/tắt; trường không gửi giữ nguyên; `description` rỗng nghĩa là xóa mô tả |
| `DELETE /api/v1/admin/phishing-patterns/{id}` | Xóa. Trả `204` |

```json
{ "name": "Gói bảo hiểm giả", "indicatorCode": "FINANCIAL_BAIT", "pattern": "gói bảo an tâm phúc", "description": "Xuất hiện từ tháng 10/2026" }
```

| Trường | Quy tắc |
|---|---|
| `name` | Bắt buộc, tối đa 150 ký tự |
| `indicatorCode` | Bắt buộc. Một trong 14 mã ở [mục 6](#các-dấu-hiệu-indicators), trừ `COORDINATED_CALLERS` |
| `pattern` | Bắt buộc. Cụm từ **ít nhất hai từ**, tối đa 200 ký tự |
| `description` | Tối đa 2000 ký tự |

Cách một mẫu hoạt động:

- Khớp nguyên cụm, không phân biệt hoa thường và dấu câu, đúng ranh giới từ, không vượt qua dấu kết câu.
- Bỏ qua khi đứng sau từ phủ định ("đừng cài ứng dụng hỗ trợ").
- Mẫu chỉ khớp chữ, không hiểu ngữ cảnh như các luật có sẵn, nên mức nghiêm trọng bị giới hạn ở MEDIUM: **riêng các mẫu không thể đẩy một cuộc gọi lên mức HIGH**.
- Một cụm một từ bị từ chối vì nó khớp quá nhiều câu bình thường.

Lỗi: `400 VALIDATION_FAILED`, `400 UNKNOWN_INDICATOR_CODE`, `400 PATTERN_TOO_SHORT`, `404 PHISHING_PATTERN_NOT_FOUND`.

### 11.6 Thống kê

#### GET `/api/v1/admin/statistics`

| Tham số | Mô tả |
|---|---|
| `days` | Số ngày của báo cáo theo ngày; mặc định 30, từ 1 đến 365 |
| `timeZone` | Múi giờ để chia ngày, ví dụ `Asia/Ho_Chi_Minh` (mặc định). Lỗi: `400 INVALID_TIME_ZONE` |

```json
{
  "generatedAt": "2026-10-10T06:30:00Z",
  "periodDays": 7,
  "timeZone": "Asia/Ho_Chi_Minh",
  "users": { "total": 42, "active": 41, "locked": 1, "newInPeriod": 5 },
  "calls": { "total": 310, "newInPeriod": 28, "RECORDED": 12, "UPLOADED": 280, "LIVE": 18 },
  "analysesByStatus": { "PENDING": 0, "PROCESSING": 1, "COMPLETED": 300, "FAILED": 14 },
  "callsByRiskLevel": { "LOW": 190, "MEDIUM": 40, "HIGH": 70 },
  "topIndicators": [ { "indicator": "AUTHORITY_IMPERSONATION", "calls": 55 } ],
  "blacklist": { "total": 20, "active": 18 },
  "blacklistReports": { "PENDING": 4, "APPROVED": 9, "REJECTED": 2 },
  "phishingPatterns": { "total": 6, "active": 5 },
  "suspectedNumbers": [
    { "phoneNumber": "+84901234567", "highRiskCalls": 3, "users": 2, "lastCallAt": "2026-10-10T05:00:00Z" }
  ],
  "daily": [
    { "date": "2026-10-10", "calls": 6, "high": 2, "medium": 1, "low": 2, "unanalysed": 1 }
  ]
}
```

- Mọi con số được đếm từ database lúc gọi API (các số trong ví dụ trên chỉ để minh họa cấu trúc).
- `callsByRiskLevel` và `daily` tính theo lần phân tích hoàn tất mới nhất của mỗi cuộc gọi.
- `topIndicators`: tối đa 10 dấu hiệu xuất hiện nhiều nhất.
- `suspectedNumbers`: tối đa 10 số gọi đến có cuộc gọi mức HIGH mà chưa bị chặn. Đây là **gợi ý** để xem xét, không phải kết luận: model vẫn có thể báo nhầm.
- `daily`: một dòng mỗi ngày, cũ nhất trước, kết thúc ở hôm nay theo `timeZone`. `unanalysed` là cuộc gọi chưa có lần phân tích hoàn tất nào.

---

## 12. Bảng mã lỗi

### 12.1 Mã chung

| HTTP | `code` | Nghĩa |
|---|---|---|
| 400 | `VALIDATION_FAILED` | Dữ liệu gửi lên sai quy tắc; xem `fieldErrors` |
| 400 | `MALFORMED_REQUEST` | Body thiếu hoặc không phải JSON hợp lệ |
| 400 | `BAD_REQUEST` | Tham số sai kiểu hoặc sai giá trị (ví dụ `riskLevel=EXTREME`), thiếu tham số bắt buộc |
| 401 | `UNAUTHORIZED` | Thiếu token, token sai hoặc hết hạn, hoặc tài khoản đã bị khóa |
| 403 | `FORBIDDEN` | Không đủ quyền (người dùng thường gọi API quản trị) |
| 404 | `NOT_FOUND` | Đường dẫn không tồn tại |
| 405 | `METHOD_NOT_ALLOWED` | Sai phương thức HTTP |
| 413 | `PAYLOAD_TOO_LARGE` | File lớn hơn 50 MB |
| 500 | `INTERNAL_ERROR` | Lỗi không lường trước ở backend; gửi kèm `requestId` khi báo lỗi |

### 12.2 Mã theo nghiệp vụ

| HTTP | `code` | API |
|---|---|---|
| 401 | `INVALID_CREDENTIALS` | Đăng nhập |
| 401 | `INVALID_REFRESH_TOKEN` | Làm mới token |
| 403 | `ACCOUNT_LOCKED` | Đăng nhập |
| 409 | `EMAIL_ALREADY_REGISTERED` | Đăng ký |
| 400 | `INVALID_CURRENT_PASSWORD` | Đổi mật khẩu |
| 400 | `INVALID_RESET_CODE` | Đặt lại mật khẩu |
| 400 | `INVALID_PHONE_NUMBER` | Mọi API nhận số điện thoại |
| 400 | `EMPTY_AUDIO` | Upload |
| 400 | `INVALID_CALL_SOURCE` | Upload với `source=LIVE` |
| 415 | `UNSUPPORTED_AUDIO_FORMAT` | Upload: đuôi file không hỗ trợ |
| 415 | `INVALID_AUDIO_CONTENT` | Upload: nội dung không khớp đuôi file |
| 503 | `STORAGE_UNAVAILABLE` | Upload, tải audio: MinIO không phản hồi |
| 404 | `CALL_NOT_FOUND` | Cuộc gọi không tồn tại hoặc không phải của mình |
| 404 | `AUDIO_OBJECT_MISSING` | File audio không còn trong kho |
| 404 | `ANALYSIS_NOT_FOUND` | Cuộc gọi chưa được phân tích |
| 409 | `ANALYSIS_IN_PROGRESS` | Yêu cầu phân tích hoặc xóa khi đang phân tích |
| 409 | `CALL_HAS_NO_AUDIO` | Yêu cầu phân tích cuộc gọi không có audio |
| 503 | `ANALYSIS_QUEUE_FULL` | Quá nhiều cuộc gọi đang chờ phân tích |
| 404 | `NOTIFICATION_NOT_FOUND` | Đánh dấu đã đọc |
| 409 | `DEVICE_REGISTRATION_CONFLICT` | Đăng ký thiết bị: hai tài khoản đăng ký cùng token cùng lúc; thử lại |
| 409 | `NUMBER_ALREADY_REPORTED` | Báo cáo số |
| 409 | `PHONE_NUMBER_ALREADY_BLACKLISTED` | Báo cáo số; quản trị thêm số |
| 400 | `PHONE_NUMBER_MISMATCH` | Báo cáo số |
| 429 | `TOO_MANY_PENDING_REPORTS` | Báo cáo số |
| 404 | `USER_NOT_FOUND` | Quản trị tài khoản |
| 409 | `CANNOT_LOCK_OWN_ACCOUNT` | Quản trị tài khoản |
| 404 | `BLACKLIST_ENTRY_NOT_FOUND` | Quản trị danh sách đen |
| 404 | `BLACKLIST_REPORT_NOT_FOUND` | Duyệt báo cáo |
| 409 | `REPORT_ALREADY_REVIEWED` | Duyệt báo cáo |
| 409 | `REPORT_REVIEW_CONFLICT` | Duyệt báo cáo |
| 404 | `PHISHING_PATTERN_NOT_FOUND` | Quản trị mẫu |
| 400 | `UNKNOWN_INDICATOR_CODE` | Quản trị mẫu |
| 400 | `PATTERN_TOO_SHORT` | Quản trị mẫu |
| 400 | `INVALID_TIME_ZONE` | Thống kê |

### 12.3 Mã lỗi của một lần phân tích (`errorCode`)

Các mã này nằm trong trường `errorCode` của kết quả phân tích có `status: FAILED` (HTTP vẫn là 200), và trong sự kiện `error` của cuộc gọi trực tiếp.

| `errorCode` | Nghĩa | Người dùng nên làm gì |
|---|---|---|
| `NO_SPEECH_DETECTED` | Không nhận ra lời nói nào trong audio | Kiểm tra file |
| `INVALID_AUDIO`, `EMPTY_AUDIO` | Không đọc được file như audio | Gửi file khác |
| `AUDIO_TOO_LONG`, `AUDIO_TOO_LARGE`, `PAYLOAD_TOO_LARGE` | Audio vượt giới hạn của AI service | Gửi đoạn ngắn hơn |
| `CALL_HAS_NO_AUDIO`, `AUDIO_OBJECT_MISSING` | Cuộc gọi không có file hoặc file đã mất | Gửi lại |
| `STT_UNAVAILABLE`, `STT_FAILED` | Nhận dạng giọng nói lỗi | Thử lại sau |
| `NLP_MODEL_UNAVAILABLE` | NLP Model chưa sẵn sàng | Thử lại sau |
| `AUDIO_PROCESSING_UNAVAILABLE`, `AUDIO_PROCESSING_TIMEOUT` | FFmpeg lỗi hoặc quá lâu | Thử lại sau |
| `AI_SERVICE_UNAVAILABLE`, `AI_SERVICE_TIMEOUT`, `AI_SERVICE_ERROR` | AI service không phản hồi, quá lâu hoặc lỗi | Thử lại sau |
| `AI_SERVICE_AUTH_FAILED`, `AI_REQUEST_REJECTED`, `AI_INVALID_RESPONSE` | Lỗi cấu hình hoặc lỗi giữa backend và AI service | Báo người quản trị hệ thống |
| `STORAGE_UNAVAILABLE` | MinIO không phản hồi | Thử lại sau |
| `ANALYSIS_QUEUE_FULL` | Hàng chờ đầy | Thử lại sau |
| `ANALYSIS_INTERRUPTED` | Backend khởi động lại giữa chừng | Yêu cầu phân tích lại |
| `LIVE_CALL_NOT_STARTED` | Mở cuộc gọi trực tiếp nhưng không kết nối luồng trong 60 giây | — |
| `LIVE_SESSION_LIMIT`, `LIVE_SESSION_OVERLOADED`, `LIVE_SESSION_FAILED` | Cuộc gọi trực tiếp: quá tải hoặc lỗi | Phân tích lại ghi âm như một file |
| `INVALID_AUDIO_FRAME`, `INVALID_MESSAGE` | Cuộc gọi trực tiếp: ứng dụng gửi sai giao thức | Sửa ứng dụng |
| `INTERNAL_ERROR` | Lỗi không lường trước | Báo kèm `requestId` |

---

## 13. Luồng mẫu

### 13.1 Người dùng gửi một file ghi âm và xem kết quả

```
1. POST /api/v1/auth/login                         -> accessToken, refreshToken
2. PUT  /api/v1/notifications/devices              (đăng ký nhận thông báo đẩy)
3. POST /api/v1/calls  (multipart: audio, callerNumber)   -> id cuộc gọi; phân tích tự bắt đầu
4. GET  /api/v1/calls/{id}/analyses/latest         lặp lại mỗi 2–3 giây
      status PENDING / PROCESSING  -> chờ
      status COMPLETED             -> hiện riskLevel, riskScore, indicators, transcript
      status FAILED                -> hiện lỗi theo errorCode, cho phép thử lại (bước 5)
5. POST /api/v1/calls/{id}/analyses                (chỉ khi cần phân tích lại)
```

Nếu kết quả là MEDIUM hoặc HIGH, một thông báo được tạo (và đẩy tới thiết bị nếu kênh đẩy bật).

Thời gian phân tích đo trên máy phát triển (CPU): 6–12 giây cho một cuộc gọi 16 giây; cuộc gọi dài hơn mất lâu hơn tương ứng.

### 13.2 Màn hình chính của ứng dụng

```
GET /api/v1/history?size=20                 danh sách cuộc gọi kèm mức rủi ro
GET /api/v1/notifications/unread-count      huy hiệu trên biểu tượng thông báo
GET /api/v1/history/{callId}                khi bấm vào một cuộc gọi: có transcript
```

### 13.3 Báo cáo một số lừa đảo

```
Người dùng:  POST /api/v1/blacklist/reports   {"callId": "..."}            -> PENDING
Quản trị:    GET  /api/v1/admin/blacklist/reports?status=PENDING
             GET  /api/v1/admin/calls/{callId}                             (xem cuộc gọi)
             POST /api/v1/admin/blacklist/reports/{id}/approve
Từ đó:       GET  /api/v1/blacklist/lookup?phoneNumber=...                 -> blacklisted: true
             Mọi người dùng nhận cuộc gọi từ số đó được cảnh báo BLACKLISTED_CALLER
```

### 13.4 Hết hạn access token

```
Một API trả 401 UNAUTHORIZED
  -> POST /api/v1/auth/refresh {refreshToken}
       200: lưu cặp token mới, gọi lại API ban đầu
       401 INVALID_REFRESH_TOKEN: về màn hình đăng nhập
```

Nếu nhiều request cùng nhận 401, chỉ gọi `refresh` **một lần** rồi dùng chung kết quả: refresh token chỉ dùng được một lần, lần gọi thứ hai với token cũ sẽ thất bại.

### 13.5 Đăng xuất

```
1. DELETE /api/v1/notifications/devices?token=...   (còn access token mới gọi được)
2. POST   /api/v1/auth/logout {refreshToken}
3. Xóa token trong ứng dụng
```

---

## 14. Giới hạn và phần chưa kiểm chứng

- **Thông báo đẩy tới điện thoại thật: NOT VERIFIED.** Backend đã được kiểm thử với một máy chủ giả thay cho Expo (gửi đúng nội dung, đọc đúng câu trả lời), nhưng chưa có ứng dụng mobile và dự án Expo thật để xác nhận một điện thoại nhận được thông báo.
- **Kết quả AI có thể sai.** Mức rủi ro là đánh giá tự động; `suspectedNumbers` và các cảnh báo là gợi ý, không phải kết luận. Số liệu đánh giá model nằm ở [TONG_HOP_CONG_VIEC.md](TONG_HOP_CONG_VIEC.md).
- **Phân tích chạy trên CPU.** Mặc định 2 cuộc gọi được phân tích cùng lúc, 50 cuộc gọi chờ trong hàng; cuộc gọi trực tiếp tối đa 2 phiên cùng lúc, mỗi phiên tối đa 30 phút.
- **Không có giới hạn tần suất gọi API** (rate limit) ngoài giới hạn số báo cáo đang chờ và số thiết bị.
- **Quản trị viên không tải được ghi âm** của người dùng; đây là chủ ý.
- Ứng dụng mobile và trang quản trị chưa được viết (Phase 13, 14), nên các API này mới được kiểm thử bằng test tự động và script, chưa qua giao diện thật.
