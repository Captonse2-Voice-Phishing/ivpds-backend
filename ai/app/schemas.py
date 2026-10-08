"""Các cấu trúc dữ liệu dùng chung của API."""

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic.alias_generators import to_camel


class ApiModel(BaseModel):
    """Lớp cơ sở cho mọi dữ liệu vào/ra của API.

    Tên trường trong JSON dùng camelCase (``riskScore``) để khớp với API contract trong README
    và với DTO của backend Spring Boot, còn trong code Python vẫn dùng snake_case.
    """

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class FieldViolation(ApiModel):
    """Lỗi của một trường dữ liệu đầu vào."""

    field: str
    message: str


class ErrorResponse(ApiModel):
    """Cấu trúc lỗi chung, giống hệt cấu trúc lỗi của backend để hai service xử lý thống nhất."""

    timestamp: datetime
    status: int
    code: str
    message: str
    path: str
    request_id: str | None
    field_errors: list[FieldViolation] | None = None


class HealthResponse(ApiModel):
    """Kết quả health check."""

    status: str


class ComponentStatus(StrEnum):
    """Trạng thái của một thành phần trong pipeline AI."""

    NOT_IMPLEMENTED = "NOT_IMPLEMENTED"  # Chưa được triển khai.
    READY = "READY"  # Đã nạp và sẵn sàng xử lý.
    UNAVAILABLE = "UNAVAILABLE"  # Đã triển khai nhưng hiện không dùng được (ví dụ nạp model lỗi).


class PipelineComponents(ApiModel):
    """Trạng thái từng tầng của pipeline: Audio -> FFmpeg -> Whisper -> Rule Engine + NLP -> Risk Engine."""

    audio_processing: ComponentStatus
    speech_to_text: ComponentStatus
    rule_engine: ComponentStatus
    nlp_model: ComponentStatus
    risk_engine: ComponentStatus


class ServiceInfo(ApiModel):
    """Thông tin về service và trạng thái thật của từng thành phần AI."""

    service: str
    version: str
    components: PipelineComponents
    # Tên model speech-to-text đang nạp; None nếu chưa nạp được.
    stt_model: str | None = None


class ConversationTurn(ApiModel):
    """Một lượt lời: ai nói và nói gì."""

    # Tên hoặc nhãn bất kỳ của người nói ("A", "Người gọi 1"); cùng một người phải dùng cùng một nhãn.
    speaker: str = Field(min_length=1, max_length=50)
    text: str = Field(max_length=20_000)


_MAX_TEXT_LENGTH = 100_000


class IndicatorRequest(ApiModel):
    """Nội dung cần tìm dấu hiệu lừa đảo. Gửi đúng một trong hai trường ``text`` hoặc ``turns``.

    ``text`` là transcript liền (như Whisper trả về); nếu trong đó có nhãn người nói ("A: ... B: ...")
    thì nó vẫn được tách thành lượt lời. ``turns`` là hội thoại đã tách sẵn, từ hai người nói trở lên.
    """

    text: str | None = Field(default=None, max_length=_MAX_TEXT_LENGTH)
    turns: list[ConversationTurn] | None = Field(default=None, min_length=1, max_length=2_000)

    @model_validator(mode="after")
    def _exactly_one_input(self) -> "IndicatorRequest":
        """Phải có đúng một trong ``text`` và ``turns``, và tổng độ dài các lượt lời không vượt giới hạn."""
        if (self.text is None) == (self.turns is None):
            raise ValueError("exactly one of 'text' or 'turns' is required")
        if self.turns is not None and sum(len(turn.text) for turn in self.turns) > _MAX_TEXT_LENGTH:
            raise ValueError(f"turns must not contain more than {_MAX_TEXT_LENGTH} characters in total")
        return self


class IndicatorResult(ApiModel):
    """Một dấu hiệu lừa đảo tìm thấy trong văn bản."""

    # Mã dấu hiệu. Sáu mã theo README: OTP_REQUEST, MONEY_TRANSFER, BANK_IMPERSONATION, URGENCY,
    # ACCOUNT_LOCK_THREAT, SENSITIVE_INFORMATION. Các mã mở rộng: AUTHORITY_IMPERSONATION, LEGAL_THREAT,
    # HARM_THREAT, SECRECY_DEMAND, REMOTE_ACCESS_REQUEST, FINANCIAL_BAIT, UNUSUAL_PAYMENT, CALL_HANDOFF, COORDINATED_CALLERS.
    code: str
    # Mức nghiêm trọng khi dấu hiệu đứng riêng: LOW, MEDIUM hoặc HIGH.
    severity: str
    # Các đoạn văn bản (đã chuẩn hóa về chữ thường) khiến dấu hiệu được báo.
    evidence: list[str]
    # Mã các luật đã khớp.
    rule_ids: list[str]


class SpeakerResult(ApiModel):
    """Các dấu hiệu do một người nói gây ra."""

    speaker: str
    # Số lượt lời của người này.
    turns: int
    # Mã các dấu hiệu xuất hiện trong lời của người này; rỗng nếu không có.
    indicators: list[str]


class IndicatorResponse(ApiModel):
    """Kết quả của Rule Engine. Đây chỉ là các dấu hiệu, chưa phải điểm hay mức rủi ro."""

    indicators: list[IndicatorResult]
    ruleset_version: str
    # Theo thứ tự xuất hiện; rỗng khi không biết ai nói câu nào (transcript liền không có nhãn người nói).
    speakers: list[SpeakerResult]
    speaker_count: int


class AudioMetadata(ApiModel):
    """Thông tin kỹ thuật của file audio nhận được (trước khi chuẩn hóa)."""

    container: str
    codec: str
    sample_rate: int
    channels: int
    duration_seconds: float


class TranscriptSegment(ApiModel):
    """Một đoạn lời nói kèm mốc thời gian (giây) trong audio."""

    start: float
    end: float
    text: str


class ProcessingTime(ApiModel):
    """Thời gian xử lý của từng tầng, tính bằng mili giây."""

    audio_ms: int
    speech_to_text_ms: int


class TranscriptionResponse(ApiModel):
    """Kết quả chuyển audio thành văn bản."""

    # Văn bản nhận dạng được; rỗng nếu audio không có tiếng nói.
    transcript: str
    language: str
    stt_model: str
    audio: AudioMetadata
    segments: list[TranscriptSegment]
    processing: ProcessingTime
