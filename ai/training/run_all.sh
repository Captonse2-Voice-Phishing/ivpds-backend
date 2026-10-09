#!/bin/sh
# Huấn luyện và đánh giá lần lượt các model ứng viên. Chạy trong image ivpds/train:dev, từ thư mục ai:
#   docker run --rm --gpus all -e PYTHONPATH=/work -v "D:/Capstone2/ai:/work" -v ivpds_hf_cache:/hf-cache -w /work \
#       ivpds/train:dev sh training/run_all.sh
set -e
python -m training.baseline
python -m training.finetune --model intfloat/multilingual-e5-small --revision 614241f622 --name e5-small --batch-size 16
python -m training.evaluate --name e5-small
python -m training.finetune --model FacebookAI/xlm-roberta-base --revision e73636d4f7 --name xlmr-base --batch-size 8 --freeze-embeddings
python -m training.evaluate --name xlmr-base
python -m training.finetune --model vinai/phobert-base-v2 --revision 86cd7fd4c1 --name phobert-base-v2 --batch-size 8 --word-segmentation
python -m training.evaluate --name phobert-base-v2
