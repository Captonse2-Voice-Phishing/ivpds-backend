"""Cấu hình của AI service, đọc từ biến môi trường có tiền tố ``AI_``."""

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Toàn bộ cấu hình của service. Thiếu hoặc sai giá trị bắt buộc thì service không khởi động."""

    model_config = SettingsConfigDict(env_prefix="AI_", extra="ignore")

    # Khóa bí mật dùng chung với backend Spring Boot; mọi API nghiệp vụ đều yêu cầu khóa này.
    api_key: str = Field(min_length=16)
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    service_name: str = "ivpds-ai"

    # --- Xử lý audio (FFmpeg) ---
    # Kích thước tối đa của file audio gửi lên (mặc định 50 MB, bằng giới hạn của backend).
    max_audio_bytes: int = Field(default=50 * 1024 * 1024, gt=0)
    # Thời lượng tối đa của audio. Nhận dạng trên CPU mất thời gian xấp xỉ thời lượng audio,
    # nên audio quá dài sẽ làm request chờ rất lâu.
    max_audio_seconds: int = Field(default=600, gt=0)
    # Thời gian tối đa cho một lệnh ffmpeg/ffprobe.
    audio_processing_timeout_seconds: int = Field(default=120, gt=0)

    # --- Speech-to-text (Whisper) ---
    # Model speech-to-text. Mặc định là PhoWhisper-medium của VinAI (Whisper huấn luyện thêm cho
    # tiếng Việt), đã được chuyển sang CTranslate2 và đóng sẵn vào image khi build (xem Dockerfile),
    # nên máy nào cũng dùng cùng một model mà không cần tải hay cài thêm gì.
    # Đo trên 19 đoạn giọng đọc tiếng Việt thật (bộ FOSD, 258 từ): Whisper small đúng 75.6% số từ,
    # medium 81.0%, large-v3-turbo 85.3%, PhoWhisper-small 94.6%, PhoWhisper-medium 99.6%.
    # Có thể đổi sang thư mục model CTranslate2 khác, hoặc tên một model Whisper gốc
    # (small, medium, large-v3-turbo...; khi đó model được tải từ Hugging Face lúc khởi động).
    whisper_model: str = "/opt/models/phowhisper-medium-int8"
    # Kiểu số khi tính toán; int8 nhanh và ít tốn RAM nhất trên CPU.
    whisper_compute_type: str = "int8"
    # Ngôn ngữ của audio. Đặt cố định là tiếng Việt thay vì để model tự đoán.
    whisper_language: str = "vi"
    whisper_beam_size: int = Field(default=5, ge=1, le=10)
    # Số luồng CPU cho model; 0 nghĩa là để thư viện tự chọn.
    whisper_cpu_threads: int = Field(default=0, ge=0)
    # Số request được nhận dạng cùng lúc. Nhận dạng dùng hết CPU nên mặc định xử lý lần lượt.
    max_concurrent_transcriptions: int = Field(default=1, ge=1)

    # --- NLP Model ---
    # Thư mục chứa artifact đã fine-tune (trọng số, tokenizer, nlp_config.json). Artifact không nằm trong image
    # hay trong git vì nặng; docker-compose gắn thư mục artifact của máy vào đường dẫn này.
    # Không có artifact thì service vẫn chạy, /v1/info báo NLP Model là UNAVAILABLE và API phân loại trả 503.
    nlp_model_dir: str = "/opt/models/nlp"
    nlp_device: Literal["cpu", "cuda"] = "cpu"

    # --- Phân tích cuộc gọi trực tiếp (WebSocket /v1/live-sessions) ---
    # Số cuộc gọi được phân tích cùng lúc. Mỗi cuộc cần nhận dạng liên tục nên trên CPU chỉ nên để nhỏ.
    live_max_sessions: int = Field(default=2, ge=1)
    # Thời lượng tối đa của một cuộc gọi trực tiếp; tới giới hạn thì phiên được chốt kết quả và đóng.
    live_max_session_seconds: int = Field(default=1800, gt=0)
    # Không nhận được gì trong khoảng này thì coi như cuộc gọi đã kết thúc.
    live_idle_timeout_seconds: float = Field(default=30, gt=0)
    # Lượng âm thanh tối đa được phép chờ nhận dạng; vượt quá nghĩa là máy không theo kịp tốc độ nói.
    live_max_pending_seconds: float = Field(default=60, gt=0)
    # Ngưỡng độ lớn (RMS trên thang 16 bit, tối đa 32768) để coi một khung 20 ms là có tiếng nói.
    live_speech_threshold: float = Field(default=300, gt=0)
    # Im lặng bao lâu thì coi là hết một câu.
    live_end_silence_ms: int = Field(default=700, ge=100)
    # Một câu nói liên tục dài tới mức này thì bị cắt để nhận dạng, không chờ người nói nghỉ.
    live_max_utterance_seconds: float = Field(default=15, gt=1)


@lru_cache
def get_settings() -> Settings:
    """Trả về cấu hình (chỉ đọc biến môi trường một lần rồi dùng lại)."""
    return Settings()
