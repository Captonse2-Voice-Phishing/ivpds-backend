"""Tầng speech-to-text: chuyển audio tiếng Việt thành văn bản bằng Whisper."""

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import numpy as np
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

    def transcribe_samples(self, samples: np.ndarray) -> Transcript:
        """Nhận dạng mẫu âm thanh trong bộ nhớ (float32, 16 kHz, mono)."""
        ...


_DOT_RUN = re.compile(r"(?:\s*\.){3,}")


def _tidy(text: str) -> str:
    """Bỏ khoảng trắng thừa và các chuỗi dấu chấm dài mà model đôi khi sinh ra khi bị lặp."""
    cleaned = _DOT_RUN.sub(".", text).strip()
    # Chỉ còn dấu chấm nghĩa là không nhận ra lời nào.
    return cleaned if cleaned.strip(". ") else ""


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
        return self._run(str(wav_path))

    def transcribe_samples(self, samples: np.ndarray) -> Transcript:
        """Nhận dạng âm thanh đã nằm trong bộ nhớ (float32, 16 kHz, một kênh, giá trị từ -1 đến 1).

        Dùng cho phân tích cuộc gọi trực tiếp, nơi mỗi câu nói được nhận dạng riêng mà không ghi ra file. Ở đây thời
        gian xử lý phải có giới hạn chắc chắn, nên bộ giải mã bị ràng buộc chặt hơn so với khi xử lý file:

        * Chỉ giải mã một lần (``temperature=0``). Mặc định Whisper thử lại tới sáu lần khi kết quả đáng ngờ; với
          một câu ngắn khiến model lặp vô tận, việc đó từng mất 65 giây cho 2 giây âm thanh.
        * Số token sinh ra bị chặn theo độ dài câu nói (tiếng Việt nói nhanh cần khoảng 10 token mỗi giây).
        * Tìm kiếm tham lam (``beam_size=1``): nhanh hơn khoảng 30%, đổi lại sai thêm vài từ.
        """
        seconds = len(samples) / 16_000
        return self._run(samples, beam_size=1, temperature=0.0, max_new_tokens=32 + int(seconds * 16),
                         without_timestamps=True)

    def _run(self, audio: str | np.ndarray, **overrides) -> Transcript:
        """Chạy model; ``overrides`` thay các tùy chọn giải mã mặc định (dùng cho chế độ trực tiếp)."""
        options = {
            "language": self._language,
            "beam_size": self._beam_size,
            # Bộ lọc tiếng nói (VAD) loại các đoạn im lặng trước khi nhận dạng. Bắt buộc phải bật:
            # nếu không, Whisper tự bịa ra câu từ audio im lặng (ví dụ "Hãy subscribe cho kênh...").
            "vad_filter": True,
            # Không dùng đoạn trước làm ngữ cảnh cho đoạn sau, để một lỗi nhận dạng không lặp lại
            # và lan sang cả phần còn lại của audio.
            "condition_on_previous_text": False,
        } | overrides
        segments, _info = self._model.transcribe(audio, **options)
        cleaned = [
            Segment(start=round(s.start, 2), end=round(s.end, 2), text=_tidy(s.text))
            for s in segments
            if _tidy(s.text)
        ]
        return Transcript(text=" ".join(s.text for s in cleaned), language=self._language, segments=cleaned)
