#!/bin/sh
# Đợt huấn luyện 7: giữ toàn bộ dữ liệu đợt 6 và thêm các đoạn ngắn một người nói sinh bởi
# tools/dataset_synthesize_vi_short.py (lời nhờ thanh toán, nhắc phí, mượn tiền đời thường, và lời lừa đảo cùng chủ đề).
# Lý do: model đợt 6 báo mức cao cho đoạn ghi âm ngắn chỉ có lời người gọi nhờ đặt cọc hay đóng phí.
# Kết quả (12/10/2026): KHÔNG triển khai. Bản 7 (30/24 đoạn mỗi kịch bản) sót 4/16 cuộc gọi lừa đảo thật; bản 7b
# (10/10 đoạn, tên phobert-base-r7b) sót 1/16. Model đang dùng vẫn là phobert-base-r6; xem training/README.md.
# Để chạy lại bản 7b: python -m tools.dataset_synthesize_vi_short && python -m tools.dataset_prepare, rồi script này
# với tên phobert-base-r7b.
set -e
python -m training.baseline baseline-tfidf-logreg-r7
python -m training.finetune --model vinai/phobert-base-v2 --revision 86cd7fd4c1 --name phobert-base-r7 --batch-size 8 --word-segmentation
python -m training.evaluate --name phobert-base-r7
for f in short_monologues handwritten_holdout user_gendata short_requests context_pairs translated_calls everyday_calls short_sentences real_calls vlsp_ordinary_speech; do python -m training.evaluate_extra data/extra_tests/$f.jsonl -r7; done
