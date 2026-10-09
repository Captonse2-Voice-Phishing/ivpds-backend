#!/bin/sh
# Đợt huấn luyện 2: dữ liệu có thêm lời nói thường ngày thật (VLSP 2020) làm mẫu NORMAL.
# Kết quả ghi vào các thư mục có hậu tố -r2, để so sánh được với đợt 1.
set -e
python -m training.baseline baseline-tfidf-logreg-r2
python -m training.finetune --model intfloat/multilingual-e5-small --revision 614241f622 --name e5-small-r2 --batch-size 16
python -m training.evaluate --name e5-small-r2
python -m training.finetune --model vinai/phobert-base-v2 --revision 86cd7fd4c1 --name phobert-base-r2 --batch-size 8 --word-segmentation
python -m training.evaluate --name phobert-base-r2
python -m training.finetune --model FacebookAI/xlm-roberta-base --revision e73636d4f7 --name xlmr-base-r2 --batch-size 8 --freeze-embeddings
python -m training.evaluate --name xlmr-base-r2
for f in real_calls vlsp_ordinary_speech sms_vi; do python -m training.evaluate_extra data/extra_tests/$f.jsonl -r2; done
