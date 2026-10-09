#!/bin/sh
# Đợt huấn luyện 3: như đợt 2, thêm các đoạn ngắn cho cả hai lớp để model không học lối tắt "ngắn là bình thường".
set -e
python -m training.baseline baseline-tfidf-logreg-r3
python -m training.finetune --model vinai/phobert-base-v2 --revision 86cd7fd4c1 --name phobert-base-r3 --batch-size 8 --word-segmentation
python -m training.evaluate --name phobert-base-r3
python -m training.finetune --model intfloat/multilingual-e5-small --revision 614241f622 --name e5-small-r3 --batch-size 16
python -m training.evaluate --name e5-small-r3
python -m training.finetune --model FacebookAI/xlm-roberta-base --revision e73636d4f7 --name xlmr-base-r3 --batch-size 8 --freeze-embeddings
python -m training.evaluate --name xlmr-base-r3
for f in short_sentences real_calls vlsp_ordinary_speech sms_vi; do python -m training.evaluate_extra data/extra_tests/$f.jsonl -r3; done
