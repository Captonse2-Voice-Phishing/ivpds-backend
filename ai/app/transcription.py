"""Ghép hai tầng đầu của pipeline: Audio -> FFmpeg -> Whisper -> Transcript."""

import logging
import tempfile
import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING, BinaryIO

from app.audio import AudioProcessor
from app.config import Settings
from app.errors import ApiError
from app.schemas import AudioMetadata, ProcessingTime, TranscriptionResponse, TranscriptSegment
from app.stt import Transcriber

if TYPE_CHECKING:
    import numpy as np

log = logging.getLogger(__name__)


class TranscriptionService:
    """Nhận một file audio tải lên và trả về transcript tiếng Việt."""

    def __init__(self, settings: Settings, transcriber: Transcriber | None) -> None:
        self._max_bytes = settings.max_audio_bytes
        self._audio = AudioProcessor(settings.audio_processing_timeout_seconds, settings.max_audio_seconds)
        # None nghĩa là model chưa nạp được; khi đó mọi yêu cầu nhận dạng bị từ chối với lỗi 503.
        self.transcriber = transcriber
        # Giới hạn số lượt nhận dạng chạy cùng lúc; các request khác xếp hàng chờ.
        self._slots = threading.Semaphore(settings.max_concurrent_transcriptions)

    def transcribe(self, upload: BinaryIO) -> TranscriptionResponse:
        """Chạy toàn bộ chuỗi xử lý cho một file audio.

        File được ghi vào một thư mục tạm riêng và bị xóa ngay khi xử lý xong, dù thành công hay lỗi.
        Mọi thất bại đều trả về lỗi rõ ràng; không bao giờ thay bằng một transcript giả.
        """
        if self.transcriber is None:
            raise ApiError(503, "STT_UNAVAILABLE", "The speech-to-text model is not available.")

        with tempfile.TemporaryDirectory(prefix="ivpds-audio-") as workdir:
            # Tên file do server đặt; tên file của bên gọi không được dùng ở bất kỳ đâu.
            source = Path(workdir) / "input"
            normalized = Path(workdir) / "normalized.wav"
            self._save(upload, source)

            started = time.perf_counter()
            source_info = self._audio.probe(source)
            normalized_info = self._audio.normalize(source, normalized)
            audio_ms = _elapsed_ms(started)

            with self._slots:
                started = time.perf_counter()
                try:
                    transcript = self.transcriber.transcribe(normalized)
                except Exception:
                    log.exception("Speech-to-text failed")
                    raise ApiError(500, "STT_FAILED", "Speech-to-text failed.") from None
                stt_ms = _elapsed_ms(started)

        return TranscriptionResponse(
            transcript=transcript.text,
            language=transcript.language,
            stt_model=self.transcriber.name,
            audio=AudioMetadata(
                container=source_info.container,
                codec=source_info.codec,
                sample_rate=source_info.sample_rate,
                channels=source_info.channels,
                # Thời lượng lấy từ file đã chuẩn hóa vì một số định dạng nguồn không ghi thời lượng.
                duration_seconds=round(normalized_info.duration_seconds, 3),
            ),
            segments=[TranscriptSegment(start=s.start, end=s.end, text=s.text) for s in transcript.segments],
            processing=ProcessingTime(audio_ms=audio_ms, speech_to_text_ms=stt_ms),
        )

    def transcribe_samples(self, samples: "np.ndarray") -> str:
        """Nhận dạng một câu nói của cuộc gọi trực tiếp và trả về văn bản (rỗng nếu không có lời nói).

        Dùng chung giới hạn số lượt nhận dạng với việc phân tích file, vì cả hai cùng dùng hết CPU.
        """
        if self.transcriber is None:
            raise ApiError(503, "STT_UNAVAILABLE", "The speech-to-text model is not available.")
        with self._slots:
            return self.transcriber.transcribe_samples(samples).text

    def _save(self, upload: BinaryIO, target: Path) -> None:
        """Ghi file tải lên ra đĩa, dừng ngay khi vượt giới hạn kích thước."""
        written = 0
        with target.open("wb") as out:
            while chunk := upload.read(1024 * 1024):
                written += len(chunk)
                if written > self._max_bytes:
                    raise ApiError(413, "AUDIO_TOO_LARGE", f"Audio is larger than the {self._max_bytes} byte limit.")
                out.write(chunk)
        if written == 0:
            raise ApiError(422, "EMPTY_AUDIO", "The audio file is empty.")


def _elapsed_ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)
