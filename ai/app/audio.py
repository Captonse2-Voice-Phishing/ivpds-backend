"""Tầng xử lý audio bằng FFmpeg: kiểm tra file và chuẩn hóa về định dạng mà Whisper cần."""

import json
import logging
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from app.errors import ApiError

log = logging.getLogger(__name__)

# Chỉ cho phép FFmpeg đọc các định dạng audio thật. Nếu không giới hạn, một file "playlist"
# (m3u8, ffconcat) đội lốt audio có thể khiến FFmpeg mở file khác trên máy chủ hoặc gọi ra mạng.
# "mov" bao gồm m4a/mp4/3gp; "matroska" bao gồm webm.
ALLOWED_FORMATS = "mp3,wav,mov,aac,ogg,matroska,amr,flac"

# Định dạng đầu ra cho Whisper: 16 kHz, mono, PCM 16-bit.
TARGET_SAMPLE_RATE = 16_000


@dataclass(frozen=True)
class AudioInfo:
    """Thông tin kỹ thuật của một file audio."""

    container: str
    codec: str
    sample_rate: int
    channels: int
    duration_seconds: float


def _invalid_audio() -> ApiError:
    return ApiError(422, "INVALID_AUDIO", "The file is not a supported audio file.")


class AudioProcessor:
    """Gọi ffprobe/ffmpeg để kiểm tra và chuẩn hóa audio."""

    def __init__(self, timeout_seconds: int, max_seconds: int) -> None:
        self._timeout = timeout_seconds
        self._max_seconds = max_seconds

    @staticmethod
    def available() -> bool:
        """Máy có đủ hai chương trình ffmpeg và ffprobe hay không."""
        return shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None

    def probe(self, path: Path) -> AudioInfo:
        """Đọc thông tin của file audio (định dạng, codec, sample rate, số kênh, thời lượng).

        Ném lỗi 422 INVALID_AUDIO nếu file không phải audio thuộc các định dạng cho phép.
        """
        output = self._run(
            [
                "ffprobe", "-v", "error",
                "-format_whitelist", ALLOWED_FORMATS,
                "-select_streams", "a:0",
                "-show_entries", "format=format_name,duration:stream=codec_name,sample_rate,channels",
                "-of", "json",
                str(path),
            ]
        )
        try:
            data = json.loads(output)
            stream = data["streams"][0]
            return AudioInfo(
                container=data["format"]["format_name"],
                codec=stream["codec_name"],
                sample_rate=int(stream["sample_rate"]),
                channels=int(stream["channels"]),
                duration_seconds=_to_float(data["format"].get("duration")),
            )
        except (ValueError, KeyError, IndexError, TypeError):
            # ffprobe chạy được nhưng file không có luồng audio nào đọc được.
            raise _invalid_audio() from None

    def normalize(self, source: Path, target: Path) -> AudioInfo:
        """Chuyển audio về WAV 16 kHz, mono, PCM 16-bit và trả về thông tin của file kết quả.

        Chỉ lấy luồng audio đầu tiên; hình ảnh, phụ đề và dữ liệu khác bị bỏ. Ném lỗi 422
        AUDIO_TOO_LONG nếu audio dài hơn giới hạn, INVALID_AUDIO nếu không giải mã được.
        """
        self._run(
            [
                "ffmpeg", "-nostdin", "-hide_banner", "-v", "error", "-y",
                "-format_whitelist", ALLOWED_FORMATS,
                "-i", str(source),
                "-map", "a:0", "-vn", "-sn", "-dn",
                "-ac", "1",
                "-ar", str(TARGET_SAMPLE_RATE),
                "-c:a", "pcm_s16le",
                # Dừng ngay sau giới hạn một giây: đủ để biết audio quá dài mà không phải giải mã hết.
                "-t", str(self._max_seconds + 1),
                "-f", "wav",
                str(target),
            ]
        )
        info = self.probe(target)
        if info.duration_seconds > self._max_seconds:
            raise ApiError(422, "AUDIO_TOO_LONG", f"Audio is longer than the {self._max_seconds} second limit.")
        if info.duration_seconds <= 0:
            raise _invalid_audio()
        return info

    def _run(self, command: list[str]) -> str:
        """Chạy một lệnh ffmpeg/ffprobe và trả về stdout; chuyển các kiểu thất bại thành ApiError."""
        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=self._timeout, check=False)
        except FileNotFoundError:
            log.error("%s is not installed", command[0])
            raise ApiError(503, "AUDIO_PROCESSING_UNAVAILABLE", "Audio processing is not available.") from None
        except subprocess.TimeoutExpired:
            log.error("%s timed out after %s seconds", command[0], self._timeout)
            raise ApiError(503, "AUDIO_PROCESSING_TIMEOUT", "Audio processing took too long.") from None
        if result.returncode != 0:
            # Lỗi của ffmpeg chỉ ghi vào log; không trả cho client vì có thể chứa đường dẫn nội bộ.
            log.info("%s rejected the input: %s", command[0], result.stderr.strip()[:300])
            raise _invalid_audio()
        return result.stdout


def _to_float(value: object) -> float:
    """Chuyển giá trị thời lượng của ffprobe thành số; trả 0 nếu không có (ví dụ "N/A")."""
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0.0
