#!/bin/sh
# Đợt huấn luyện 4: thêm 4 cuộc gọi lừa đảo thật, 5 kịch bản lừa đảo và 11 kịch bản bình thường thường ngày
# (học phí, bố mẹ hỏi con, bạn bè tâm sự, vay trả tiền, tiền nhà, nhắc nợ thật, cuộc gọi tự động...).
set -e
python -m training.baseline baseline-tfidf-logreg-r4
python -m training.finetune --model vinai/phobert-base-v2 --revision 86cd7fd4c1 --name phobert-base-r4 --batch-size 8 --word-segmentation
python -m training.evaluate --name phobert-base-r4
python -m training.finetune --model intfloat/multilingual-e5-small --revision 614241f622 --name e5-small-r4 --batch-size 16
python -m training.evaluate --name e5-small-r4
for f in everyday_calls short_sentences real_calls vlsp_ordinary_speech sms_vi; do python -m training.evaluate_extra data/extra_tests/$f.jsonl -r4; done
