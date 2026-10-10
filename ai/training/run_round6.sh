#!/bin/sh
# Đợt huấn luyện 6: giữ toàn bộ dữ liệu đợt 5d và thêm (a) các cuộc gọi viết tay từng cuộc, (b) các kịch bản bổ sung
# trong tools/dataset_synthesize_vi_more.py (hãng bay, tòa án, đặt bàn, từ thiện, máy lọc nước...).
set -e
python -m training.baseline baseline-tfidf-logreg-r6
python -m training.finetune --model vinai/phobert-base-v2 --revision 86cd7fd4c1 --name phobert-base-r6 --batch-size 8 --word-segmentation
python -m training.evaluate --name phobert-base-r6
for f in handwritten_holdout user_gendata short_requests context_pairs translated_calls everyday_calls short_sentences real_calls vlsp_ordinary_speech; do python -m training.evaluate_extra data/extra_tests/$f.jsonl -r6; done
