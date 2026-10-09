# IVPDS — Tổng hợp công việc đã làm (Phase 0 đến Phase 9C)

Cập nhật: 09/10/2026. Tài liệu này tóm tắt những gì đã được xây dựng, nằm ở đâu trong repo, chạy thế nào,
kết quả đo được và những giới hạn cần biết. Số liệu đều lấy từ các lần chạy thật.

## 1. Hệ thống hiện có gì

IVPDS nhận file ghi âm cuộc gọi, chuyển thành chữ, rồi tìm dấu hiệu lừa đảo. Hiện đã chạy được tới bước
phân loại bằng model; phần chấm điểm rủi ro, ứng dụng mobile và trang admin chưa làm.

```text
Mobile / Admin (chưa làm)
        │
        ▼
Backend Spring Boot ──► PostgreSQL (dữ liệu)   MinIO (file audio)   Mail (gửi mã đặt lại mật khẩu)
        │
        ▼  (chưa nối, Phase 11)
AI service FastAPI:  Audio ─► FFmpeg ─► PhoWhisper ─► Transcript ─┬─► Rule Engine ─┐
                                                                  └─► NLP Model  ──┴─► Risk Engine (chưa làm)
```

| Thành phần | Trạng thái |
|---|---|
| Hạ tầng Docker (PostgreSQL, MinIO, Mailpit) | Xong |
| Backend: đăng ký, đăng nhập, người dùng, cuộc gọi, lưu audio | Xong |
| AI: FFmpeg + PhoWhisper (audio thành chữ) | Xong |
| AI: Rule Engine (tìm dấu hiệu lừa đảo) | Xong |
| AI: Dataset và NLP Model | Xong, nhưng dữ liệu gần như toàn tổng hợp |
| AI: Risk Engine (điểm LOW / MEDIUM / HIGH) | Chưa làm (Phase 10) |
| Backend gọi AI service | Chưa làm (Phase 11) |
| History, blacklist, notification, admin API | Chưa làm (Phase 12) |
| Mobile, Admin web, kiểm thử toàn hệ thống | Chưa làm (Phase 13–15) |

## 2. Cấu trúc thư mục

| Thư mục / file | Nội dung |
|---|---|
| `docker-compose.yml` | Khai báo 5 service: `postgres`, `minio`, `mailpit`, `ai`, `backend` |
| `.env` | Mật khẩu và khóa bí mật. **Không đưa lên git.** Mẫu ở `.env.example` |
| `backend/` | Spring Boot 3, Java 21 |
| `ai/app/` | Code của AI service (FastAPI) |
| `ai/tests/` | Test tự động của AI service |
| `ai/tools/` | Công cụ dòng lệnh: chuẩn bị dữ liệu, đo chất lượng |
| `ai/training/` | Code huấn luyện NLP Model, có `README.md` riêng |
| `ai/data/` | Dữ liệu (phần lớn không vào git, tạo lại bằng lệnh) |
| `ai/models/` | Model đã huấn luyện (không vào git vì nặng) |
| `infra/minio/` | Dockerfile build MinIO từ mã nguồn |
| `CLAUDE.md`, `README.md` | Quy trình làm việc và yêu cầu chính thức của dự án |

## 3. Từng phase đã làm gì

### Phase 0 — Kiểm tra môi trường
Đọc README, kiểm tra Java 21, Node, Python, Docker. Chưa viết tính năng.

### Phase 1 — Hạ tầng Docker
- PostgreSQL 17, MinIO, Mailpit chạy bằng Docker Compose, có health check.
- MinIO không còn image chính thức nên được build từ mã nguồn (`infra/minio/Dockerfile`).
- Dữ liệu Docker đặt ở `D:\DockerData` vì ổ C hết chỗ.

### Phase 2–3 — Nền Spring Boot và database
- Kiến trúc modular monolith, package gốc `com.ivpds`, các module: `auth`, `user`, `call`, `audio`, `analysis`,
  `history`, `blacklist`, `notification`, `admin`, `phishingpattern`, `common`.
- Schema quản lý bằng Flyway: `backend/src/main/resources/db/migration/V1` đến `V5`, 14 bảng.

### Phase 4 — Đăng nhập và phân quyền
- JWT (15 phút) + refresh token (xoay vòng, phát hiện dùng lại), mật khẩu băm BCrypt.
- Đặt lại mật khẩu bằng mã 6 số gửi qua email.
- Tài khoản admin đầu tiên tạo từ biến môi trường.

### Phase 5 — Người dùng, cuộc gọi, audio
- Tải file ghi âm lên: file lưu ở MinIO, PostgreSQL chỉ lưu thông tin mô tả.
- Mọi class Java có chú thích tiếng Việt.

API của backend (`http://localhost:8080`, tài liệu tại `/swagger-ui/index.html`):

| Method | Đường dẫn | Dùng để |
|---|---|---|
| POST | `/api/v1/auth/register`, `/login`, `/refresh`, `/logout` | Đăng ký, đăng nhập, làm mới token, đăng xuất |
| POST | `/api/v1/auth/change-password`, `/forgot-password`, `/reset-password` | Đổi và đặt lại mật khẩu |
| GET, PATCH | `/api/v1/users/me` | Xem, sửa hồ sơ |
| POST, GET | `/api/v1/calls` | Tải cuộc gọi lên, xem danh sách |
| GET | `/api/v1/calls/{id}`, `/api/v1/calls/{id}/audio` | Chi tiết cuộc gọi, tải lại audio |

### Phase 6–7 — AI service, FFmpeg, PhoWhisper
- FastAPI chạy ở `http://localhost:8000`, mọi API nghiệp vụ cần header `X-API-Key`.
- FFmpeg chuẩn hóa audio về 16 kHz mono (`ai/app/audio.py`).
- Chuyển giọng nói thành chữ bằng **PhoWhisper-medium** của VinAI, đóng sẵn trong image (`ai/app/stt.py`).
- Đo trên 19 đoạn giọng đọc tiếng Việt thật: PhoWhisper-medium đúng 99,6% số từ; Whisper small chỉ 75,6%.

### Phase 8 — Rule Engine
- File chính: `ai/app/rules.py`. Tìm 15 loại dấu hiệu lừa đảo kèm bằng chứng và mức nghiêm trọng.
  - 6 dấu hiệu theo README: đòi OTP, đòi chuyển tiền, giả ngân hàng, hối thúc, dọa khóa tài khoản, đòi thông tin nhạy cảm.
  - 9 dấu hiệu bổ sung: giả cơ quan nhà nước, dọa pháp lý, dọa làm hại, bắt giữ bí mật, đòi cài ứng dụng / điều khiển
    từ xa, mồi nhử tài chính, thanh toán bất thường, chuyển máy, nhiều kẻ gọi phối hợp.
- Xét ngữ cảnh, không chỉ dò từ khóa: "Tôi nhập OTP của chính tôi" không bị báo.
- Xử lý hội thoại 2 người và 3 người trở lên, gán dấu hiệu cho từng người nói.
- Công cụ đo: `ai/tools/evaluate_rules.py`.

### Phase 9A–9B — Dataset
Không tồn tại dataset công khai về cuộc gọi lừa đảo thật bằng tiếng Việt. Dataset hiện tại gồm ba nguồn:

| Nguồn | Số mẫu | Bản chất |
|---|---|---|
| `adamtc/scam_dialogues` (Hugging Face, Apache-2.0) | 3.837 | Hội thoại tổng hợp, kịch bản Mỹ dịch máy |
| Hội thoại Việt Nam sinh theo kịch bản (`ai/tools/dataset_synthesize_vi.py`) | 1.524 | Tổng hợp, 22 kịch bản lừa đảo + 18 kịch bản bình thường |
| Ghi âm lừa đảo trên YouTube, chuyển thành chữ | 13 | Cuộc gọi thật, chưa có người nghe kiểm tra |
| Hội thoại Việt Nam viết tay (`ai/tests/data/conversations_vi.jsonl`) | 150 | Tổng hợp, chỉ dùng để chọn model và test |

Dữ liệu đã chia nằm trong `ai/data/processed/`; báo cáo kiểm tra ở `ai/data/processed/AUDIT.json`.
99,8% dữ liệu là tổng hợp. Đã kiểm tra: không có mẫu trùng hay gần trùng nằm ở hai tập khác nhau.

### Phase 9C — NLP Model
- Huấn luyện 4 ứng viên trên GPU RTX 3050 Ti; chi tiết từng bước và từng file ở `ai/training/README.md`.
- Model đang chạy trong service: **multilingual-e5-small** (Transformer, license MIT), artifact ở `ai/models/e5-small/`.
- Code nạp model: `ai/app/nlp.py`. API mới: `POST /v1/classifications`.

API của AI service (`http://localhost:8000`, tài liệu tại `/docs`):

| Method | Đường dẫn | Dùng để |
|---|---|---|
| GET | `/health` | Kiểm tra service còn sống |
| GET | `/v1/info` | Trạng thái từng thành phần AI |
| POST | `/v1/transcriptions` | Audio thành chữ |
| POST | `/v1/indicators` | Tìm dấu hiệu lừa đảo trong văn bản (Rule Engine) |
| POST | `/v1/classifications` | Xác suất lừa đảo của văn bản (NLP Model) |

## 4. Kết quả đo được

### Rule Engine

| Tập | Bắt được lừa đảo | Báo nhầm cuộc thường |
|---|---|---|
| 2.106 hội thoại kịch bản Mỹ chưa từng xem (bản luật 2026.10.4) | 1.007/1.075 (93,7%) | 31/1.031 (3,0%) |
| 50 hội thoại Việt Nam viết tay giữ riêng | 31/32 | 1/18 |
| 7 cuộc gọi thật giữ riêng | 3/7 | không đo được |

### NLP Model (e5-small)

| Tập | Số mẫu | Precision | Recall | Báo nhầm | Bỏ sót |
|---|---|---|---|---|---|
| Test tổng hợp | 576 | 100% | 100% | 0 | 0 |
| Test Việt Nam viết tay | 50 | 96,9% | 96,9% | 1 | 1 |
| Test cuộc gọi thật | 7 | 100% | 100% | 0 | 0 |

So sánh 4 ứng viên trên tập dùng để chọn model (100 hội thoại Việt Nam viết tay, macro F1): baseline đếm từ 0,942;
PhoBERT 0,932; e5-small 0,920; XLM-RoBERTa 0,912. Chênh lệch nằm trong sai số.

### Test tự động

| Phần | Kết quả |
|---|---|
| Backend (JUnit, Testcontainers) | 109 đạt (lần chạy ở Phase 5) |
| AI service (pytest) | 370 đạt khi có model; 366 đạt + 4 bỏ qua khi không có model |

## 5. Cách chạy

Yêu cầu: Docker Desktop, file `.env` (chép từ `.env.example` rồi điền giá trị).

```powershell
docker compose up -d --build --wait      # bật cả 5 service
docker compose ps                        # xem trạng thái
docker compose logs -f ai                # xem log AI service
docker compose down                      # tắt (dữ liệu vẫn giữ)
```

Lần build đầu tải khoảng 3 GB cho PhoWhisper và mất 10–15 phút.

Chạy test:

```powershell
cd backend; .\mvnw.cmd test                                   # backend
docker build --target test -t ivpds/ai:test ai                # AI
docker run --rm --network none ivpds/ai:test
```

Thử API: mở Swagger của backend (`/swagger-ui/index.html`) hoặc của AI service (`/docs`). Với AI service, bấm
Authorize và dán giá trị `AI_API_KEY` trong `.env`.

**Về NLP Model trên máy thành viên khác:** thư mục `ai/models/` không có trong git. Cần chép `ai/models/e5-small/`
(466 MB) từ máy đã huấn luyện, hoặc huấn luyện lại theo `ai/training/README.md` (khoảng 5 phút, cần GPU NVIDIA).
Thiếu model thì service vẫn chạy, `/v1/info` báo `nlpModel: UNAVAILABLE` và `/v1/classifications` trả lỗi 503.

## 6. Giới hạn cần biết

1. **Chưa kiểm chứng trên cuộc gọi thật.** Chỉ có 13 cuộc gọi thật, toàn lừa đảo, transcript còn lỗi nghe nhầm và
   chưa có người nghe kiểm tra. Tỉ lệ báo nhầm trên cuộc gọi bình thường thật chưa đo được.
2. **Tập test tổng hợp quá dễ.** Một model đếm từ đơn giản cũng đạt 100%, nên con số 100% không chứng minh chất lượng.
3. **Rule Engine yếu trên cuộc gọi thật** (3/7), vì người thật nói vòng vo và transcript có lỗi.
4. **NLP Model báo nhầm các cuộc bình thường có nhắc tới tiền** (đóng quỹ lớp, chia tiền, viện phí), với xác suất
   rất cao. Xác suất của model chưa được hiệu chỉnh.
5. **Audio thật chưa tách được người nói.** Muốn có cần thêm speaker diarization, nằm ngoài README.
6. **Hai điểm lệch nhỏ so với README, chủ dự án đã chấp nhận:** chỉ số đánh giá được tính bằng công thức tự viết
   thay vì `sklearn.metrics`; model triển khai là e5-small thay vì PhoBERT mà README gợi ý.
7. **Dung lượng ổ đĩa.** Docker nằm ở ổ D. Ổ đầy từng làm hỏng đĩa dữ liệu của Docker hai lần; luôn kiểm tra còn
   ít nhất 20 GB trước khi build image lớn.

## 7. Việc tiếp theo

| Phase | Nội dung |
|---|---|
| 10 | Risk Engine: gộp dấu hiệu và xác suất thành điểm 0–100 và mức LOW / MEDIUM / HIGH |
| 11 | Backend gọi AI service, lưu kết quả phân tích |
| 12 | History, blacklist, notification, admin API |
| 13–14 | Ứng dụng mobile (React Native) và trang admin (React) |
| 15 | Kiểm thử toàn hệ thống |

Song song: thu thập thêm cuộc gọi thật, nhất là cuộc gọi bình thường, để đo được chất lượng thực tế.

## 8. Cập nhật 09/10/2026 (sau khi viết tài liệu này): kiểm thử thêm và huấn luyện lại NLP Model

Các mục 3 (Phase 9C), 4 và 6 ở trên mô tả model đợt 1 (`e5-small`). Model đang chạy hiện là **`phobert-base-r3`**.

Kiểm thử trên 3.493 mẫu mới (24 cuộc gọi thật, 889 câu nói thường ngày, 2.543 tin nhắn SMS, 37 câu ngắn) cho thấy
model đợt 1 báo nhầm rất nhiều trên tiếng Việt thật. Đã thêm lời nói thường ngày thật vào dữ liệu và huấn luyện lại.

| Bộ test | Model đợt 1 (e5-small) | Model hiện tại (phobert-base-r3) |
|---|---|---|
| Lời nói thường ngày (889): báo nhầm | 298 (33,5%) | 0 |
| SMS hợp lệ (1.855): báo nhầm | 1.526 (82,3%) | 398 (21,5%) |
| Cuộc gọi thật: bắt lừa đảo (16) | 14 | 12 |
| Cuộc gọi thật: báo nhầm (8) | 5 | 4 |
| Câu ngắn: bắt lừa đảo (14) | 10 | 11 |
| Câu ngắn: báo nhầm (23) | 5 | 3 |

Giới hạn còn lại: model một mình vẫn gán nhãn lừa đảo cho hai câu bình thường trong các case bắt buộc ("Cho tôi số
tài khoản để tôi chuyển tiền", "Tôi đăng nhập ngân hàng và nhập OTP của chính tôi"); Risk Engine (Phase 10) phải kết
hợp với Rule Engine để không báo HIGH cho các câu này. Chi tiết ba đợt huấn luyện ở `ai/training/README.md`.

### Cập nhật tiếp (cùng ngày): đợt huấn luyện 4 (`phobert-base-r4`, sau đó thay bằng `phobert-base-r5d`)

| Bộ test | Đợt 3 | Đợt 4 (đang chạy) |
|---|---|---|
| Cuộc gọi thật: bắt lừa đảo (16) | 12 | 16 |
| Cuộc gọi thật: báo nhầm (8) | 4 | 5 |
| Cuộc gọi thường ngày tự viết: báo nhầm (44) | 1 | 0 |
| Lừa đảo cùng chủ đề thường ngày (12) | 12 | 12 |
| Câu ngắn: bắt lừa đảo (14) / báo nhầm (23) | 11 / 3 | 14 / 3 |
| Lời nói thường ngày (889): báo nhầm | 0 | 3 |
| SMS hợp lệ (1.855): báo nhầm | 398 | 1.123 |

Sáu case bắt buộc A-F đều được model phân loại đúng. Dữ liệu huấn luyện: 7.259 mẫu, trong đó 1.555 mẫu là lời nói
thường ngày VLSP (không phải cuộc gọi) và 10 cuộc gọi lừa đảo thật.

### Cập nhật tiếp (cùng ngày): đợt huấn luyện 5 và 5b

Yêu cầu: model phải phân biệt cuộc gọi lừa đảo và cuộc gọi thường theo ngữ cảnh, không theo từ khóa có trong bộ train. Đã thêm 10 cặp kịch bản cùng chủ đề (bản hợp pháp và bản lừa đảo dùng chung từ ngữ, chỉ khác hành vi), 3 kịch bản bình thường có nhắc từ ngữ lừa đảo, và bộ test `context_pairs.jsonl` (46 cuộc viết tay). Model `phobert-base-r5b` đã train xong nhưng CHƯA triển khai; model đang chạy vẫn là `phobert-base-r4`. Bảng so sánh và chi tiết ở `ai/training/README.md`, mục "Đợt 5 và 5b".

Tóm tắt: 5b giảm báo nhầm trên cuộc gọi tiếng Việt (14/101 xuống 6/101) nhưng sót thêm 3 ca lừa đảo (62/62 xuống 59/62) và không còn tự gắn nhãn lừa đảo cho Case C.

Bổ sung: đã train thêm 5c (loại, đã xóa) và 5d (`phobert-base-r5d`). Trên 199 cuộc gọi tiếng Việt: đợt 4 bắt 79/80 lừa đảo và báo nhầm 19/119; 5b bắt 72/80 và báo nhầm 7/119; 5d bắt 77/80 và báo nhầm 11/119. Chưa có bản nào vừa bắt đủ như đợt 4 vừa ít báo nhầm như 5b. Model đang chạy vẫn là `phobert-base-r4`.

Quyết định: dùng `phobert-base-r5d`. AI service đã chuyển sang model này (370 test qua, sáu case bắt buộc đã thử qua API thật). Các ca model sót sẽ do Risk Engine ở Phase 10 bù bằng điểm của Rule Engine.
