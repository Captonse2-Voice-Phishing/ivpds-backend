"""Constants and helpers shared by the tests."""

import os

API_KEY = "test-api-key-0123456789"

# Must be set before app.main is imported: the app reads its settings at import time.
os.environ["AI_API_KEY"] = API_KEY

from app.config import Settings  # noqa: E402

# Spoken by a speech synthesiser to make test audio. Synthetic speech only shows that the pipeline
# runs end to end; it is not evidence of accuracy on real phone calls.
SPEECH_TEXT = "Tôi gọi từ ngân hàng. Tài khoản của anh đang có vấn đề. Anh đọc mã OTP tôi vừa gửi."


def make_settings(**overrides) -> Settings:
    return Settings(api_key=API_KEY, **overrides)


def expected_model_name() -> str:
    """Name the service reports for the model under test (set AI_WHISPER_MODEL to test another model)."""
    from app.stt import model_label

    settings = make_settings()
    return f"faster-whisper/{model_label(settings.whisper_model)} ({settings.whisper_compute_type}, cpu)"
