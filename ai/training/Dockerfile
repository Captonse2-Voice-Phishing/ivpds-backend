# Môi trường huấn luyện NLP Model (cần GPU NVIDIA và NVIDIA Container Toolkit). Không dùng để chạy service.
#
#   docker build -t ivpds/train:dev ai/training
#   docker run --rm --gpus all -v "D:/Capstone2/ai:/work" -v ivpds_hf_cache:/hf-cache -w /work ivpds/train:dev \
#       python -m training.baseline
#
# Dùng cùng phiên bản torch và transformers với image chạy service, để artifact lưu ở đây nạp được ở đó.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1 \
    HF_HOME=/hf-cache HF_HUB_DISABLE_TELEMETRY=1
COPY requirements.txt /tmp/requirements.txt
# Bản torch mặc định trên PyPI cho Linux đã kèm thư viện CUDA.
RUN pip install -r /tmp/requirements.txt
WORKDIR /work
