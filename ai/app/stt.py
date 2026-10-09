"""Tầng speech-to-text: chuyển audio tiếng Việt thành văn bản bằng Whisper."""

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from faster_whisper import WhisperModel


@dataclass(frozen=True)
class Segment:
    """Một đoạn lời nói được nhận dạng, kèm thời điểm bắt đầu và kết thúc (giây)."""

    start: float
    end: float
    text: str


@dataclass(frozen=True)
class Transcript:
    """Kết quả nhận dạng của một file audio."""

    text: str
    language: str
    segments: list[Segment]


class Transcriber(Protocol):
    """Giao diện của bộ nhận dạng giọng nói, để phần còn lại không phụ thuộc vào thư viện cụ thể."""

    name: str

    def transcribe(self, wav_path: Path) -> Transcript:
        """Nhận dạng một file WAV đã chuẩn hóa (16 kHz, mono)."""
        ...


def model_label(model: str) -> str:
    """Tên ngắn của model để ghi vào kết quả: với đường dẫn thư mục thì chỉ lấy tên thư mục cuối."""
    return Path(model).name if "/" in model else model


class WhisperTranscriber:
    """Nhận dạng bằng model họ Whisper (bản gốc của OpenAI hoặc bản huấn luyện thêm cho tiếng Việt
    như PhoWhisper), chạy trên CPU qua thư viện faster-whisper."""

    def __init__(
        self,
        model: str,
        compute_type: str,
        language: str,
        beam_size: int,
        cpu_threads: int,
    ) -> None:
        """Nạp model vào bộ nhớ.

        ``model`` là đường dẫn tới thư mục chứa model ở định dạng CTranslate2 (mặc định là
        PhoWhisper-medium đóng sẵn trong image), hoặc tên một model Whisper gốc (``small``,
        ``medium``...; khi đó model được tải từ Hugging Face về thư mục ``HF_HOME``).
        """
        self._model = WhisperModel(model, device="cpu", compute_type=compute_type, cpu_threads=cpu_threads)
        self._language = language
        self._beam_size = beam_size
        self.name = f"faster-whisper/{model_label(model)} ({compute_type}, cpu)"

    def transcribe(self, wav_path: Path) -> Transcript:
        """Nhận dạng file audio và trả về văn bản cùng các đoạn có mốc thời gian.

        Audio không có tiếng nói cho kết quả rỗng.
        """
        segments, _info = self._model.transcribe(
            str(wav_path),
            language=self._language,
            beam_size=self._beam_size,
            # Bộ lọc tiếng nói (VAD) loại các đoạn im lặng trước khi nhận dạng. Bắt buộc phải bật:
            # nếu không, Whisper tự bịa ra câu từ audio im lặng (ví dụ "Hãy subscribe cho kênh...").
            vad_filter=True,
            # Không dùng đoạn trước làm ngữ cảnh cho đoạn sau, để một lỗi nhận dạng không lặp lại
            # và lan sang cả phần còn lại của audio.
            condition_on_previous_text=False,
        )
        cleaned = [
            Segment(start=round(s.start, 2), end=round(s.end, 2), text=s.text.strip())
            for s in segments
            if s.text.strip()
        ]
        return Transcript(text=" ".join(s.text for s in cleaned), language=self._language, segments=cleaned)
