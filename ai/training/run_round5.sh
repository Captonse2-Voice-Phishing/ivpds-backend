#!/bin/sh
# Đợt huấn luyện 5 (bản 5d): thêm các cặp kịch bản cùng chủ đề (bản hợp pháp và bản lừa đảo dùng chung từ ngữ, chỉ khác
# hành vi) và các cuộc bình thường có chứa từ ngữ lừa đảo, để model dựa vào ngữ cảnh thay vì từ khóa.
set -e
python -m training.baseline baseline-tfidf-logreg-r5d
python -m training.finetune --model vinai/phobert-base-v2 --revision 86cd7fd4c1 --name phobert-base-r5d --batch-size 8 --word-segmentation
python -m training.evaluate --name phobert-base-r5d
for f in short_requests context_pairs translated_calls everyday_calls short_sentences real_calls vlsp_ordinary_speech; do python -m training.evaluate_extra data/extra_tests/$f.jsonl -r5d; done
