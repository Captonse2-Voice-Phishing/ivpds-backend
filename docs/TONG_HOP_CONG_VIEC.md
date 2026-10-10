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

## 9. Phase 10 — Risk Engine (09/10/2026)

Risk Engine ghép kết quả của Rule Engine và NLP Model thành điểm rủi ro 0–100 và mức LOW / MEDIUM / HIGH.

- Mã nguồn: `ai/app/risk.py` (công thức), `ai/app/api/v1/risk_assessments.py` (API), test ở `ai/tests/test_risk.py`.
- API: `POST /v1/risk-assessments`, gửi `text` hoặc `turns`, trả `riskScore`, `riskLevel`, `confidence`, `indicators` theo contract trong README, kèm `components` để giải thích điểm. Thiếu NLP Model thì trả 503, không tính điểm chỉ từ luật.
- Công thức (bản 2026.10.1): `điểm = min(100, 70 × xác suất model + Rule Score + Indicator Severity)`.
  - Rule Score: mỗi dấu hiệu LOW 3, MEDIUM 8, HIGH 15 điểm; tổ hợp "giả danh + đòi hỏi" cộng 25; trần 35.
  - Indicator Severity: theo dấu hiệu nặng nhất, LOW 3, MEDIUM 8, HIGH 20.
  - Ngưỡng theo README: 0–29 LOW, 30–59 MEDIUM, 60–100 HIGH.
- Hệ quả của công thức: model rất chắc chắn thì tự lên HIGH; Rule Engine một mình tối đa 55 điểm (MEDIUM); một dấu hiệu yếu đứng riêng vẫn là LOW.
- Công cụ đo: `ai/tools/risk_signals_dump.py` (ghi tín hiệu), `ai/tools/risk_evaluate.py` (chấm, ghi `ai/training/reports/risk-engine.json`).

Kết quả trên 199 cuộc gọi tiếng Việt (80 lừa đảo, 119 bình thường), "phát hiện" nghĩa là từ MEDIUM trở lên:

| Cách làm | Lừa đảo bị sót | Bình thường bị báo |
|---|---|---|
| Chỉ Rule Engine | 20/80 | 6/119 |
| Chỉ NLP Model (5d) | 3/80 | 11/119 |
| Risk Engine | 1/80 | 14/119 (11 HIGH, 3 MEDIUM) |

Trọng số được chọn trên tập validation; bảng trên là các bộ test. Các bộ test này đã được xem nhiều lần trong ngày nên con số có thể lạc quan.

### Kiểm thử lớn sau Phase 10: 2.136 cuộc gọi mới (10/10/2026)

Hai bộ test mới, không dùng để train và không dùng để chọn trọng số:

- `ai/data/extra_tests/generated_test_calls.jsonl`: 1.336 cuộc tự viết (680 lừa đảo, 656 bình thường) từ 34 kịch bản có chủ đề không nằm trong dữ liệu train; sinh bằng `ai/tools/testset_generate_vi.py`.
- `ai/data/extra_tests/translated_calls_rest.jsonl`: 800 cuộc (400 + 400) là phần còn lại của bộ công khai `shakeleoatmeal/phone-scam-detection-synthetic`, dịch máy sang tiếng Việt bằng `ai/tools/translated_calls_fetch.py rest`.

Kết quả của Risk Engine ("phát hiện" = từ MEDIUM trở lên):

| Bộ | Số cuộc | Đúng | Lừa đảo bị sót | Bình thường bị báo |
|---|---|---|---|---|
| Tự viết, tiếng Việt | 1.336 | 99,1% | 1/680 (0,1%) | 11/656 (1,7%) |
| Dịch máy từ tiếng Anh | 800 | 62,5% | 19/400 (4,8%) | 281/400 (70,2%) |
| Cả hai bộ mới | 2.136 | 85,4% | 20/1.080 (1,9%) | 292/1.056 (27,7%) |
| Tất cả bộ test (cũ + mới) | 3.981 | 81,6% | 36/2.000 (1,8%) | 695/1.981 (35,1%) |

Giới hạn: bộ tự viết gồm 40 biến thể cho mỗi kịch bản nên chỉ có 34 kịch bản độc lập, và do cùng người viết với dữ liệu train; bộ dịch máy là kịch bản kiểu Mỹ do máy sinh, bản dịch sai nghĩa nhiều chỗ. Số liệu chi tiết ở `ai/training/reports/risk-engine.json`.

### Đợt huấn luyện 6 (10/10/2026): thêm cuộc gọi viết tay và kịch bản bổ sung

Theo yêu cầu, dữ liệu cũ được giữ nguyên và thêm 427 cuộc gọi viết tay cùng 2.056 hội thoại từ 52 kịch bản mới; tổng 12.255 dòng train. Model `phobert-base-r6` đang chạy trong AI service. So với 5d trên các bộ cuộc gọi tiếng Việt còn độc lập: bắt lừa đảo 172/174 (5d: 169/174), báo nhầm 12/169 (5d: 14/169). Trên bộ dịch máy báo nhầm tăng từ 364 lên 444 trên 500. Chi tiết ở `ai/training/README.md`, mục "Đợt 6"; số liệu Risk Engine với model mới ở `ai/training/reports/risk-engine.json`.

Bộ test `generated_test_calls` (1.336 cuộc) đã chuyển sang huấn luyện nên con số 99,1% báo trước đó không còn dùng để đánh giá model mới.

## 10. Phase 11 — Spring Boot ↔ FastAPI (10/10/2026)

Backend gọi AI service thật để phân tích cuộc gọi và lưu kết quả.

- Mã nguồn: module `backend/src/main/java/com/ivpds/analysis/` (`AiClient`, `AnalysisProcessor`, `AnalysisService`, `AnalysisController`, các entity và repository), migration `V6__analysis_details.sql`.
- Luồng xử lý: gửi cuộc gọi → backend tự tạo một lần phân tích (PENDING) → luồng nền lấy audio từ MinIO, gọi `POST /v1/transcriptions` rồi `POST /v1/risk-assessments` của AI service → lưu `transcripts`, `risk_results`, `risk_indicators` → COMPLETED. Client hỏi lại trạng thái.
- API mới (cần đăng nhập, chỉ với cuộc gọi của mình):
  - `POST /api/v1/calls/{callId}/analyses`: yêu cầu phân tích (hoặc phân tích lại), trả 202.
  - `GET /api/v1/calls/{callId}/analyses/latest`: trạng thái và kết quả mới nhất (`transcript`, `riskScore`, `riskLevel`, `confidence`, `indicators` theo README).
  - `GET /api/v1/calls/{callId}/analyses`: lịch sử các lần phân tích.
- Xử lý lỗi: mọi lỗi của AI service làm lần phân tích FAILED kèm mã (`AI_SERVICE_UNAVAILABLE`, `AI_SERVICE_TIMEOUT`, `AI_SERVICE_ERROR`, `AI_SERVICE_AUTH_FAILED`, `AI_INVALID_RESPONSE`, hoặc mã của chính AI service như `STT_UNAVAILABLE`, `NLP_MODEL_UNAVAILABLE`, `INVALID_AUDIO`), cùng `NO_SPEECH_DETECTED`, `AUDIO_OBJECT_MISSING`, `ANALYSIS_INTERRUPTED`. Lần phân tích FAILED không bao giờ có điểm hay mức rủi ro.
- Cấu hình: `AI_BASE_URL`, `AI_API_KEY`, `AI_TRANSCRIPTION_TIMEOUT`, `ANALYSIS_AUTO_START` (xem `.env.example`).
- Test: backend 136 test qua (thêm 27). Thử thật qua Docker Compose: cuộc gọi lừa đảo thật 267 giây cho HIGH 97 sau 81 giây; giọng đọc máy nội dung bình thường cho LOW 16; âm thanh không có tiếng nói cho `NO_SPEECH_DETECTED`; tắt AI service cho `AI_SERVICE_UNAVAILABLE` trong khi backend vẫn healthy.

## 11. Phase 11B — Phân tích cuộc gọi trực tiếp (10/10/2026, ngoài README)

Thêm theo yêu cầu của người dùng và mentor: ứng dụng VoIP gửi âm thanh của cuộc gọi đang diễn ra và nhận cảnh báo ngay trong lúc gọi. Giao thức đầy đủ cho mobile: `docs/LIVE_CALL_API.md`.

- AI service: WebSocket `/v1/live-sessions` (`ai/app/live.py`, `ai/app/api/v1/live_sessions.py`). Âm thanh PCM 16 kHz đi theo luồng, mỗi gói ghi rõ người nói; service cắt từng câu theo khoảng lặng, nhận dạng từng câu, chấm lại rủi ro của cả cuộc gọi sau mỗi câu bằng đúng Rule Engine, NLP Model và Risk Engine của phân tích file, và phát `alert` khi mức rủi ro tăng.
- Backend: `POST /api/v1/live-calls` (mở cuộc gọi, phát vé dùng một lần) và WebSocket `/api/v1/live-calls/stream` (`LiveCallController`, `LiveCallSocketHandler`, `LiveCallRecorder`, `LiveCallTickets`). Backend chuyển tiếp âm thanh và sự kiện, lưu ghi âm WAV hai kênh vào MinIO và kết quả vào các bảng sẵn có; migration `V7` thêm nguồn cuộc gọi `LIVE`.
- Công cụ thử khi chưa có ứng dụng: `ai/tools/live_call_demo.py`.
- Test: AI service 430 test qua, backend 145 test qua.
- Thử thật qua Docker Compose: phát 150 giây đầu của một cuộc gọi lừa đảo thật theo thời gian thực. Cảnh báo HIGH đến ở giây 37,5 (câu gây cảnh báo kết thúc ở giây 32,9 của cuộc gọi); độ trễ từ lúc nói xong tới lúc có chữ trung vị 4,6 giây, lớn nhất 7,3 giây; kết quả cuối HIGH 100, lưu COMPLETED kèm ghi âm 150 giây.
- Hai lỗi tìm thấy nhờ lần thử thật và đã sửa: máy chủ uvicorn thiếu thư viện WebSocket (thêm `websockets` vào `requirements.txt` và một test canh); Whisper lặp vô tận trên một câu ngắn làm mất 65 giây (chế độ trực tiếp nay giải mã một lần và chặn độ dài kết quả).
- Giới hạn: nhận dạng trên CPU chỉ phục vụ được khoảng 2 cuộc gọi cùng lúc; phần thiết lập cuộc gọi VoIP giữa hai máy chưa có (thuộc ứng dụng mobile); chưa thử với hai luồng tiếng thật tách riêng, mới thử ghi âm trộn một kênh.

## 12. Phase 12 — History / Blacklist / Notification / Admin API (10/10/2026)

API cho ứng dụng (cần đăng nhập, chỉ thấy dữ liệu của mình):

| API | Dùng để |
|---|---|
| `GET /api/v1/history` | Lịch sử cuộc gọi kèm kết quả phân tích mới nhất; lọc theo `riskLevel`, `status`, `from`, `to`, `callerNumber`; phân trang |
| `GET /api/v1/history/{callId}` | Chi tiết một cuộc gọi kèm transcript |
| `DELETE /api/v1/calls/{id}` | Xóa cuộc gọi cùng audio và kết quả |
| `GET /api/v1/blacklist/lookup?phoneNumber=` | Tra một số có trong danh sách đen không |
| `GET /api/v1/notifications`, `/unread-count` | Danh sách thông báo, số chưa đọc |
| `POST /api/v1/notifications/{id}/read`, `/read-all` | Đánh dấu đã đọc |

Bật, tắt cảnh báo blacklist dùng `PATCH /api/v1/users/me` với `blacklistAlertEnabled` (có từ Phase 5).

API quản trị (`/api/v1/admin/**`, chỉ ADMIN):

| API | Dùng để |
|---|---|
| `GET /users`, `GET /users/{id}`, `PATCH /users/{id}/status` | Tìm, xem, khóa và mở khóa tài khoản |
| `GET /calls`, `GET /calls/{callId}` | Cuộc gọi của mọi người dùng kèm kết quả; `riskLevel=HIGH` để theo dõi cuộc gọi rủi ro cao |
| `GET/POST /blacklist`, `PATCH/DELETE /blacklist/{id}` | Quản lý danh sách đen |
| `GET/POST /phishing-patterns`, `GET/PATCH/DELETE /phishing-patterns/{id}` | Quản lý mẫu lừa đảo |
| `GET /statistics?days=30` | Số liệu dashboard và báo cáo theo ngày |

Thông báo được tạo tự động khi: cuộc gọi phân tích xong ở mức HIGH (`HIGH_RISK_CALL`) hoặc MEDIUM (`SUSPICIOUS_CALL`), và khi có cuộc gọi (gửi file hoặc trực tiếp) từ số trong danh sách đen (`BLACKLISTED_CALLER`, trừ khi người dùng đã tắt cảnh báo).

- Mã nguồn: các module `history/`, `blacklist/`, `notification/`, `phishingpattern/`, `admin/` trong `backend/src/main/java/com/ivpds/`; migration `V8`.
- Test: backend 159 test qua (thêm 14). Thử thật qua Docker Compose với ghi âm cuộc gọi lừa đảo thật gửi từ một số trong danh sách đen: hai thông báo được tạo, lịch sử và thống kê quản trị hiện đúng, xóa cuộc gọi trả 204.
- Giới hạn: thông báo chỉ lưu trong database, chưa có kênh đẩy tới thiết bị; mẫu lừa đảo chỉ là dữ liệu quản trị, Rule Engine của AI service chưa đọc bảng này.

Bổ sung sau Phase 12 (cùng ngày):

- Báo cáo theo ngày chia ngày theo múi giờ `Asia/Ho_Chi_Minh` (cấu hình `REPORT_TIME_ZONE`, hoặc tham số `timeZone` của `GET /api/v1/admin/statistics`); trước đó tính theo UTC nên cuộc gọi buổi sáng ở Việt Nam bị xếp vào ngày hôm trước.
- Tài khoản bị khóa bị chặn ngay ở request kế tiếp: access token chỉ được chấp nhận khi tài khoản còn hoạt động (một truy vấn nhỏ cho mỗi request có đăng nhập).
- Thống kê có thêm `suspectedNumbers`: các số gọi đến có cuộc gọi mức HIGH mà chưa nằm trong danh sách đen, để quản trị viên xem xét. Đây là gợi ý, không phải kết luận.
- Backend: 161 test qua.
