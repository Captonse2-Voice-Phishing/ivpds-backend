# Quy trình huấn luyện NLP Model

Tài liệu này mô tả từng bước để tạo ra model phân loại cuộc gọi (bình thường / lừa đảo), và ở mỗi bước
dùng những file nào. Mọi lệnh chạy từ thư mục `ai/`.

Hình dung như dạy một học sinh: chuẩn bị sách bài tập, cho học, kiểm tra thử để chọn học sinh giỏi nhất,
thi thật, rồi đưa đi làm việc.

```text
Bước 1  Chuẩn bị dữ liệu
Bước 2  Dựng môi trường huấn luyện
Bước 3  Baseline (model đơn giản làm mốc)
Bước 4  Fine-tune (dạy thêm cho model có sẵn) và chọn model
Bước 5  Đánh giá và phân tích lỗi
Bước 6  Đưa model vào AI service
```

---

## Bước 1: Chuẩn bị dữ liệu

Tải dữ liệu đã được duyệt, sinh thêm hội thoại bối cảnh Việt Nam, cắt cuộc gọi thật từ YouTube, rồi làm sạch
và chia thành các tập. Model chỉ học từ tập train; tập validation dùng để chọn model; tập test chỉ dùng để chấm.

| File | Vai trò |
|---|---|
| `tools/dataset_download.py` | Tải bộ hội thoại công khai về `data/raw/`, ghi nguồn gốc và mã SHA-256 |
| `tools/dataset_synthesize_vi.py` | Sinh 1.524 hội thoại theo kịch bản lừa đảo ở Việt Nam |
| `tools/youtube_calls_collect.py` | Tải âm thanh video YouTube đã chọn, chuyển thành chữ bằng PhoWhisper |
| `tools/youtube_calls_build.py` | Cắt đúng đoạn cuộc gọi, sửa lỗi nghe nhầm |
| `tools/dataset_prepare.py` | Kiểm tra, bỏ trùng, kiểm tra rò rỉ, chia tập |
| `data/youtube_calls_selection.json` | Video nào được chọn, lấy từ giây nào đến giây nào |
| `data/youtube_calls_corrections.json` | Danh sách chỗ sửa lỗi nghe nhầm |
| `data/rule_tuning_rows.json` | Các dòng đã dùng khi chỉnh Rule Engine (để không đưa vào tập test) |

Kết quả nằm trong `data/processed/`:

| File | Số mẫu | Dùng ở bước |
|---|---|---|
| `train.jsonl` | 3.975 | 3, 4 (để học) |
| `validation.jsonl` | 816 | 4 (kiểm tra thử; dữ liệu tổng hợp, dễ) |
| `validation_vi_context.jsonl` | 100 | 3, 4 (chọn model; hội thoại Việt Nam viết tay, khó hơn) |
| `test.jsonl` | 576 | 5 |
| `test_vi_context.jsonl` | 50 | 5 |
| `test_real_calls.jsonl` | 7 | 5 (cuộc gọi thật) |
| `AUDIT.json` | – | Báo cáo kiểm tra dữ liệu |

Lệnh:

```powershell
docker run --rm -v "D:/Capstone2/ai:/work" -w /work --user root ivpds/ai:test python -m tools.dataset_download
docker run --rm --network none -v "D:/Capstone2/ai:/work" -w /work --user root ivpds/ai:test python -m tools.dataset_synthesize_vi
docker run --rm --network none -v "D:/Capstone2/ai:/work" -w /work --user root ivpds/ai:test python -m tools.youtube_calls_build
docker run --rm --network none -v "D:/Capstone2/ai:/work" -w /work --user root ivpds/ai:test python -m tools.dataset_prepare
```

`youtube_calls_build` cần các transcript trong `data/raw/youtube_calls/transcripts/`. Thư mục này không có trong
git (bản quyền thuộc kênh đăng); muốn có phải chạy `tools.youtube_calls_collect` trước.

---

## Bước 2: Dựng môi trường huấn luyện

Tạo một image Docker có PyTorch dùng được GPU. Image này chỉ để huấn luyện, không dùng để chạy service.

| File | Vai trò |
|---|---|
| `training/Dockerfile` | Công thức tạo image `ivpds/train:dev` |
| `training/requirements.txt` | Thư viện cần cài: torch, transformers, scikit-learn, pyvi |

Lệnh:

```powershell
docker build -t ivpds/train:dev ai/training
```

Yêu cầu: GPU NVIDIA và khoảng 10 GB trống trên ổ chứa dữ liệu Docker. **Kiểm tra dung lượng trước khi build**;
ổ đầy giữa chừng có thể làm hỏng đĩa dữ liệu của Docker.

---

## Bước 3: Baseline

Huấn luyện một model rất đơn giản (đếm từ, không hiểu ngữ cảnh) để làm mốc. Nếu model phức tạp không hơn được
mốc này thì không có lý do dùng nó.

| File | Vai trò |
|---|---|
| `training/baseline.py` | Huấn luyện TF-IDF + Logistic Regression, chấm trên mọi tập |
| `training/common.py` | Đọc dữ liệu, tính precision / recall / F1 |
| `app/nlp.py` | Hàm `normalize_for_model`: đưa chữ về dạng giống transcript của Whisper |
| Đọc: `data/processed/train.jsonl`, `validation_vi_context.jsonl`, các tập test | |
| Ghi: `models/baseline-tfidf-logreg/model.joblib` | Model baseline |
| Ghi: `training/reports/baseline-tfidf-logreg/metrics.json` | Kết quả |

Lệnh:

```powershell
docker run --rm -e PYTHONPATH=/work -v "D:/Capstone2/ai:/work" -w /work ivpds/train:dev python -m training.baseline
```

---

## Bước 4: Fine-tune và chọn model

Lấy một model đã biết tiếng Việt, dạy thêm cho nó việc phân loại cuộc gọi. Với mỗi model ứng viên:

1. Chuẩn hóa chữ, tách token, cắt mỗi cuộc gọi thành các đoạn 256 token gối nhau.
2. Cho model học trên tập train trong 3 vòng (epoch).
3. Sau mỗi vòng, chấm trên hai tập validation.
4. Giữ lại phiên bản có điểm cao nhất trên `validation_vi_context`.

| File | Vai trò |
|---|---|
| `training/finetune.py` | Toàn bộ các việc trên cho một model |
| `training/common.py` | Đọc dữ liệu, tính chỉ số |
| `app/nlp.py` | Chuẩn hóa chữ, cắt đoạn (`token_windows`), gộp điểm các đoạn (`aggregate`) |
| Đọc: `data/processed/train.jsonl`, `validation.jsonl`, `validation_vi_context.jsonl`, `AUDIT.json` | |
| Ghi: `models/<tên>/model.safetensors` | Trọng số model đã học |
| Ghi: `models/<tên>/tokenizer.json`, `config.json` | Bộ tách token và cấu hình model |
| Ghi: `models/<tên>/nlp_config.json` | Cách dùng model: độ dài đoạn, cách gộp, ngưỡng |
| Ghi: `models/<tên>/training_log.json` | Nhật ký: dữ liệu, tham số, phần cứng, điểm từng vòng |

Lệnh cho một model:

```powershell
docker run --rm --gpus all -e PYTHONPATH=/work -v "D:/Capstone2/ai:/work" -v ivpds_hf_cache:/hf-cache -w /work `
    ivpds/train:dev python -m training.finetune --model FacebookAI/xlm-roberta-base --name xlmr-base --batch-size 8
```

Chạy bước 3, 4 và 5 cho tất cả model ứng viên bằng một lệnh:

```powershell
docker run --rm --gpus all -e PYTHONPATH=/work -v "D:/Capstone2/ai:/work" -v ivpds_hf_cache:/hf-cache -w /work `
    ivpds/train:dev sh training/run_all.sh
```

| File | Vai trò |
|---|---|
| `training/run_all.sh` | Danh sách model ứng viên và thứ tự chạy |

**Chọn model:** so điểm macro F1 trên `validation_vi_context` giữa các model (xem `best_checkpoint` trong
`training_log.json` và `metrics.json` của baseline). Không dùng các tập test để chọn.

---

## Bước 5: Đánh giá và phân tích lỗi

Chấm model trên các tập test bằng đúng đoạn code mà API dùng khi chạy thật, rồi ghi lại các mẫu đoán sai.

| File | Vai trò |
|---|---|
| `training/evaluate.py` | Chấm trên mọi tập, ghi chỉ số và danh sách mẫu sai |
| `app/nlp.py` | Lớp `TextClassifier`: nạp artifact và phân loại, giống hệt lúc chạy thật |
| `training/common.py` | Tính chỉ số |
| Đọc: `models/<tên>/`, các tập `validation*.jsonl` và `test*.jsonl` | |
| Ghi: `training/reports/<tên>/metrics.json` | Precision, recall, F1, ma trận nhầm lẫn theo từng tập (vào git) |
| Ghi: `training/reports/<tên>/errors.jsonl` | Các mẫu đoán sai kèm trích đoạn (không vào git) |

Lệnh:

```powershell
docker run --rm --gpus all -e PYTHONPATH=/work -v "D:/Capstone2/ai:/work" -w /work ivpds/train:dev `
    python -m training.evaluate --name xlmr-base
```

Cách đọc chỉ số:

- **Precision:** trong những cuộc model báo lừa đảo, bao nhiêu phần trăm đúng. Thấp nghĩa là báo nhầm nhiều.
- **Recall:** trong những cuộc lừa đảo thật, model bắt được bao nhiêu phần trăm. Thấp nghĩa là bỏ sót nhiều.
- **F1:** điểm tổng hợp của hai chỉ số trên.

---

## Bước 6: Đưa model vào AI service

AI service nạp artifact khi khởi động và phục vụ qua API. Artifact không nằm trong image hay trong git vì nặng;
service đọc nó từ thư mục `ai/models/` trên máy.

| File | Vai trò |
|---|---|
| `app/nlp.py` | Nạp artifact và phân loại transcript |
| `app/api/v1/classifications.py` | API `POST /v1/classifications`: nhận transcript, trả xác suất lừa đảo |
| `app/api/v1/info.py` | `GET /v1/info`: báo NLP Model đang `READY` hay `UNAVAILABLE` |
| `app/main.py` | Nạp model lúc service khởi động |
| `app/config.py` | Cấu hình `AI_NLP_MODEL_DIR` (thư mục artifact) |
| `app/schemas.py` | Cấu trúc dữ liệu vào/ra của API |
| `Dockerfile`, `requirements.txt` | Thêm PyTorch (bản CPU) và Transformers vào image service |
| `../docker-compose.yml` | Gắn `ai/models/` vào container; biến `AI_NLP_MODEL_NAME` chọn model |
| `tests/test_nlp.py` | Test: chuẩn hóa chữ, cắt đoạn, API, và test trên artifact thật |

Nếu máy chưa có artifact, service vẫn chạy: `/v1/info` báo `UNAVAILABLE` và API phân loại trả lỗi 503.
Service không bao giờ trả một kết quả thay thế.

Lệnh:

```powershell
docker compose up -d --build --wait
```

---

## Lưu ý về kết quả

- Dữ liệu huấn luyện gần như hoàn toàn là tổng hợp (99,8%). Chỉ có 13 cuộc gọi thật, 6 trong train và 7 trong test.
- Tập test tổng hợp rất dễ: baseline đã đạt 100% trên đó. Điểm trên tập này không nói lên nhiều về chất lượng.
- Tập cuộc gọi thật không có cuộc gọi bình thường, nên chưa đo được tỉ lệ báo nhầm trên dữ liệu thật.

---

## Cập nhật 09/10/2026: ba đợt huấn luyện

Phép thử trên dữ liệu thật cho thấy model đợt 1 báo nhầm rất nhiều, nên đã huấn luyện lại hai lần.

| Đợt | Thay đổi dữ liệu | Kết quả chính |
|---|---|---|
| 1 | Chỉ dữ liệu tổng hợp + 6 cuộc gọi thật | Báo nhầm 33,5% lời nói thường ngày, 82,3% tin nhắn hợp lệ |
| 2 | Thêm 1.870 mẫu lời nói thường ngày thật (VLSP 2020) làm lớp NORMAL | Báo nhầm giảm mạnh, nhưng model học lối tắt "ngắn là bình thường" và bỏ sót câu lừa đảo ngắn. **Không triển khai.** |
| 3 | Thêm đoạn ngắn cho cả hai lớp (lấy từ kịch bản Việt Nam) | Đã từng triển khai: `phobert-base-r3` (nay thay bằng `phobert-base-r5d`) |

File thêm ở các đợt sau:

| File | Vai trò |
|---|---|
| `tools/dataset_fetch_vlsp.py` | Lấy transcript lời nói thường ngày (chỉ chữ) cho train và validation |
| `training/evaluate_extra.py` | Chấm mọi model và Rule Engine trên một bộ test bổ sung |
| `training/run_round2.sh`, `run_round3.sh` | Lệnh của đợt 2 và đợt 3 |
| `training/reports/extra/*.json` | Kết quả trên 4 bộ test bổ sung (hậu tố `-r2`, `-r3` là đợt huấn luyện) |

Cách chọn model từ đợt 2: macro F1 trên tập gồm 100 hội thoại Việt Nam viết tay + lời nói thật của tập validation
+ (từ đợt 3) các đoạn ngắn của những kịch bản model chưa thấy khi học. Xem `load_selection` trong `training/common.py`.

Cách gộp điểm các đoạn: `top2` (trung bình hai đoạn đáng ngờ nhất). Bài học của đợt 2: khi thêm dữ liệu cho một
lớp, phải kiểm tra phân bố độ dài của hai lớp có lệch nhau không.

`phobert-base-v2` có license AGPL-3.0 và cần thư viện tách từ `pyvi` (đã thêm vào `requirements.txt` của service).

### Đợt 4 (`phobert-base-r4`, đã thay bằng `phobert-base-r5d`)

Thêm 4 cuộc gọi lừa đảo thật, 5 kịch bản lừa đảo (giả giáo viên thu học phí, giả con xin tiền học, học bổng giả,
giả chủ trọ, cuộc gọi tự động) và 11 kịch bản cuộc gọi thường ngày (hỏi nhau về học phí, bố mẹ hỏi con, bạn bè
tâm sự, vay trả tiền, tiền nhà, lương thưởng, nhắc nợ thật, tư vấn bán hàng thật...). Lệnh: `training/run_round4.sh`.

So với đợt 3: bắt cuộc gọi lừa đảo thật 16/16 (trước 12/16), sáu case bắt buộc A-F đều đúng, cuộc gọi thường
ngày báo nhầm 0/44. Điểm xấu đi: báo nhầm tin nhắn SMS hợp lệ tăng từ 21,5% lên 60,5% (SMS không phải cuộc gọi,
nhưng cho thấy model dễ báo động với văn bản lạ). Số liệu: `training/reports/extra/*-r4.json`.

### Đợt 5 và 5b (chưa triển khai, chờ quyết định)

Mục tiêu: model phân biệt theo ngữ cảnh và hành vi, không theo từ khóa. Thay đổi so với đợt 4:

- `tools/dataset_synthesize_vi.py`: thêm 10 cặp kịch bản cùng chủ đề (`PAIRS`). Mỗi cặp có phần mở đầu dùng chung, rồi một bản hợp pháp và một bản lừa đảo chỉ khác nhau ở hành vi. Thêm 3 kịch bản bình thường có nhắc từ ngữ lừa đảo (kể lại, dặn dò, ngân hàng cảnh báo).
- `tools/dataset_prepare.py`: không cắt mẫu ngắn từ 3 kịch bản "nhắc từ ngữ lừa đảo", và bỏ hai lượt mở đầu dùng chung khi cắt mẫu ngắn từ bản hợp pháp của cặp.
- `data/extra_tests/context_pairs.jsonl`: bộ test mới viết tay, 20 cặp cùng chủ đề + 6 cuộc bình thường nhắc từ ngữ lừa đảo (46 cuộc). Viết sau khi đã có kịch bản train và cùng một người viết, nên kết quả có thể lạc quan.
- Chạy: `sh training/run_round5.sh` (tạo `baseline-tfidf-logreg-r5b`, `phobert-base-r5b`).

Đợt 5 (bản đầu) bị loại và đã xóa: nó bỏ sót Case D vì mẫu ngắn cắt từ lời kể lại bị gắn nhãn bình thường.

| Bộ test | `phobert-base-r4` | `phobert-base-r5b` |
|---|---|---|
| `context_pairs` (46) | bắt 20/20, báo nhầm 6/26 | bắt 20/20, báo nhầm 1/26 |
| `everyday_calls` (56) | bắt 12/12, báo nhầm 0/44 | bắt 12/12, báo nhầm 0/44 |
| `short_sentences` (37) | bắt 14/14, báo nhầm 3/23 | bắt 12/14, báo nhầm 0/23 |
| `real_calls` (24) | bắt 16/16, báo nhầm 5/8 | bắt 15/16, báo nhầm 5/8 |
| `vlsp_ordinary_speech` (889) | báo nhầm 3 | báo nhầm 1 |
| `translated_calls` (1.020) | bắt 505/520, báo nhầm 390/500 | bắt 509/520, báo nhầm 394/500 |
| `test` (576) | sai 0 | sai 1 (báo nhầm) |
| `test_vi_context` (50) | sai 1 (báo nhầm) | sai 0 |
| Case A, B, D, E, F | đúng | đúng |
| Case C (model) | PHISHING 0,994 | NORMAL 0,000 (Rule Engine vẫn gắn `BANK_IMPERSONATION` + `SENSITIVE_INFORMATION`) |

Đổi tên người trong 508 cuộc của `test` không làm đổi nhãn cuộc nào ở cả hai model.

### Đợt 5c và 5d (cùng ngày)

Mục tiêu: lấy lại các ca lừa đảo 5b bỏ sót (câu ngắn chỉ xin thông tin) mà vẫn giữ phần ngữ cảnh.

- `tools/dataset_synthesize_vi.py`: thêm `SHORT_PAIRS`, 5 cặp cuộc gọi ngắn "xin thông tin qua điện thoại" (thẻ, giấy tờ vay, tài khoản, ví điện tử, thuê bao).
- `data/extra_tests/short_requests.jsonl`: bộ test mới, 18 câu xin thông tin kiểu lừa đảo + 18 câu bình thường dùng cùng từ ngữ.
- **5c** (dùng cả bản hợp pháp lẫn bản lừa đảo của cặp ngắn): bị loại và đã xóa. Cuộc gọi thật chỉ còn bắt 10/16, sót Case D, báo nhầm Case B.
- **5d** (chỉ dùng bản lừa đảo của cặp ngắn; đây là trạng thái hiện tại của mã nguồn): `phobert-base-r5d`, train 8.582 dòng.

Tổng trên 5 bộ cuộc gọi tiếng Việt (`short_requests`, `context_pairs`, `everyday_calls`, `short_sentences`, `real_calls`; 80 lừa đảo, 119 bình thường):

| Model | Bắt lừa đảo | Báo nhầm | Đúng tổng |
|---|---|---|---|
| `phobert-base-r4` | 79/80 | 19/119 | 179/199 = 89,9% |
| `phobert-base-r5b` | 72/80 | 7/119 | 184/199 = 92,5% |
| `phobert-base-r5d` | 77/80 | 11/119 | 185/199 = 93,0% |

Các bộ khác của 5d: `test` 576 sai 0; `test_vi_context` 50 sai 4 (3 báo nhầm, 1 sót); `vlsp_ordinary_speech` báo nhầm 5/889; `translated_calls` bắt 496/520, báo nhầm 364/500. Case A, B, D, E, F đúng; Case C model cho NORMAL 0,010 (Rule Engine vẫn gắn hai dấu hiệu).

Lưu ý: các bộ test trên đã được xem kết quả qua bốn lần train liên tiếp trong ngày, nên không còn là dữ liệu hoàn toàn chưa thấy.

### Triển khai (09/10/2026)

Model đang chạy trong AI service là `phobert-base-r5d` (`AI_NLP_MODEL_NAME` trong `docker-compose.yml` và `.env.example`). Đã kiểm tra sau khi đổi: `/v1/info` báo `2026.10.09-phobert-base-r5d`; sáu case bắt buộc qua API thật cho kết quả như bảng trên; `pytest` trong image test với model này: 370 passed. `phobert-base-r4` và `phobert-base-r5b` vẫn nằm trong `ai/models/` để đổi lại khi cần. Các ca model bỏ sót sẽ được bù bằng Rule Engine trong Risk Engine (Phase 10).

### Đợt 6 (model đang triển khai: `phobert-base-r6`, 10/10/2026)

Giữ toàn bộ dữ liệu của 5d và thêm hai nguồn theo yêu cầu của người dùng:

- `data/synthetic/handwritten/*.txt` → `tools/handwritten_calls_build.py`: 533 cuộc gọi viết tay từng cuộc (283 lừa đảo, 250 bình thường). 427 cuộc vào train (nguồn `ivpds_handwritten_vi`), 106 cuộc giữ lại làm test (`data/extra_tests/handwritten_holdout.jsonl`).
- `tools/dataset_synthesize_vi_more.py`: 52 kịch bản bổ sung, 2.056 hội thoại (`data/synthetic/vi_generated_more.jsonl`). 34 kịch bản trong số này từng là bộ test `generated_test_calls`; bộ test đó đã bị bỏ.
- Chạy: `sh training/run_round6.sh`. Train 12.255 dòng (6.062 lừa đảo, 6.193 bình thường), 24 phút.

| Bộ test | `phobert-base-r5d` | `phobert-base-r6` |
|---|---|---|
| `handwritten_holdout` (106) | bắt 55/56, báo nhầm 3/50 | bắt 56/56, báo nhầm 0/50 |
| `user_gendata` (38 cuộc lừa đảo của kho `hoangvt2501/data_scam`, chỉ để test) | bắt 37/38 | bắt 37/38 |
| `context_pairs` (46) | bắt 20/20, báo nhầm 2/26 | bắt 20/20, báo nhầm 0/26 |
| `short_requests` (36) | bắt 17/18, báo nhầm 4/18 | bắt 17/18, báo nhầm 4/18 |
| `short_sentences` (37) | bắt 13/14, báo nhầm 0/23 | bắt 14/14, báo nhầm 3/23 |
| `real_calls` (24) | bắt 15/16, báo nhầm 5/8 | bắt 16/16, báo nhầm 5/8 |
| `everyday_calls` (56) | bắt 12/12, báo nhầm 0/44 | bắt 12/12, báo nhầm 0/44 |
| `vlsp_ordinary_speech` (889) | báo nhầm 5 | báo nhầm 2 |
| `translated_calls` (1.020) | bắt 496/520, báo nhầm 364/500 | bắt 512/520, báo nhầm 444/500 |
| `test` (576) / `test_vi_context` (50) | sai 0 / sai 4 | sai 0 / sai 0 |

Sáu case bắt buộc qua API thật: A, B, F là LOW; C, D, E là HIGH (Case C nay model tự cho PHISHING). `pytest` với model này: 397 passed.

Điểm kém hơn 5d: báo nhầm trên bộ dịch máy tăng (364 → 444 trên 500) và có 3 câu ngắn bình thường bị báo nhầm. Kho `hoangvt2501/data_scam` không có giấy phép nên không đưa vào huấn luyện; chỉ dùng 38 hội thoại `gendata` để test.
