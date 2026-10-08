# Python 3.12: the ML libraries used in later phases (PyTorch, Transformers) support it.

# ---------------------------------------------------------------------------------------------------
# Speech-to-text model: PhoWhisper-medium by VinAI (Whisper fine-tuned for Vietnamese, BSD-3-Clause),
# converted here to the CTranslate2 format that faster-whisper loads. On 19 real Vietnamese clips it got
# 99.6% of the words right, against 75.6% for stock Whisper "small" and 85.3% for "large-v3-turbo".
#
# The model is built into the image so every machine gets the same one with a plain
# "docker compose up --build": no manual step, and no download when the service starts.
# PyTorch and Transformers are needed only for this conversion and do not end up in the final image.
# The first build downloads about 3 GB and takes several minutes; later builds reuse the cached layer.
FROM python:3.12-slim AS model
ARG PHOWHISPER_REPO=vinai/PhoWhisper-medium
# Exact commit of the model repository, so the image does not change if the repository does.
ARG PHOWHISPER_REVISION=55a7e3eb6c906de891f8f06a107754427dd3be79
ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    HF_HOME=/tmp/hf \
    HF_HUB_DISABLE_TELEMETRY=1
RUN pip install torch==2.14.1 --index-url https://download.pytorch.org/whl/cpu \
    && pip install transformers==4.57.6 ctranslate2==4.8.2
# The downloaded PyTorch checkpoint is removed in the same layer; only the converted model is kept.
RUN ct2-transformers-converter --model "${PHOWHISPER_REPO}" --revision "${PHOWHISPER_REVISION}" \
        --output_dir /model --quantization int8 --copy_files tokenizer.json preprocessor_config.json \
    && rm -rf /tmp/hf \
    && test -s /model/model.bin

# ---------------------------------------------------------------------------------------------------
FROM python:3.12-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    # Only used if AI_WHISPER_MODEL is set to a stock Whisper name, which is then downloaded here.
    HF_HOME=/tmp/hf \
    HF_HUB_DISABLE_TELEMETRY=1
# FFmpeg validates and normalises uploaded audio before speech-to-text.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /srv
COPY requirements.txt .
RUN pip install -r requirements.txt
RUN useradd --system --no-create-home ivpds
COPY --from=model /model /opt/models/phowhisper-medium-int8
COPY app app
COPY tools tools

# Test image (the model is inside the image, so no volume or network is needed):
#   docker build --target test -t ivpds/ai:test ai
#   docker run --rm ivpds/ai:test
FROM base AS test
# espeak-ng synthesises Vietnamese speech so the pipeline can be exercised without recordings.
# Synthetic speech only proves the pipeline works; it says nothing about accuracy on real calls.
RUN apt-get update \
    && apt-get install -y --no-install-recommends espeak-ng \
    && rm -rf /var/lib/apt/lists/*
COPY requirements-dev.txt .
RUN pip install -r requirements-dev.txt
COPY pytest.ini .
COPY tests tests
USER ivpds
CMD ["pytest", "-v"]

FROM base AS runtime
USER ivpds
EXPOSE 8000
# The app writes its own access log line per request (with the request id).
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
