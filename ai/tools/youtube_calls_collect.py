"""Tải âm thanh các video YouTube đã chọn, chuyển thành transcript bằng PhoWhisper, rồi xóa âm thanh.

Cách dùng (cần mạng và một image có thêm ``yt-dlp``; chạy từ thư mục ``ai``):

    docker build -t ivpds/collect:tmp - <<< "FROM ivpds/ai:test
    USER root
    RUN pip install --no-cache-dir yt-dlp"
    docker run --rm -v "D:/Capstone2/ai:/work" -w /work ivpds/collect:tmp python -m tools.youtube_calls_collect

Đọc danh sách mã video ở ``data/raw/youtube_calls/selected.txt`` (mỗi dòng một mã, phần sau dấu ``#`` là ghi
chú). Với mỗi video, ghi ``data/raw/youtube_calls/transcripts/<mã>.json`` gồm đường dẫn, kênh, tiêu đề, thời
lượng và các đoạn transcript kèm mốc thời gian. File âm thanh chỉ tồn tại trong thư mục tạm và bị xóa ngay
sau khi nhận dạng xong. Video đã có transcript thì bỏ qua, nên có thể chạy lại khi bị ngắt giữa chừng.

Nguồn này đã được chủ dự án phê duyệt ngày 2026-10-08 ("Dataset 3"). Bản quyền video thuộc kênh đăng và trong
ghi âm có giọng người thật, nên transcript chỉ dùng nội bộ cho nghiên cứu và không được đưa lên git.
"""

import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from app.audio import AudioProcessor
from app.config import get_settings
from app.errors import ApiError
from app.stt import WhisperTranscriber

FOLDER = Path("data/raw/youtube_calls")
MAX_SECONDS = 20 * 60  # video dài hơn mức này không được chọn


def _metadata(video_id: str) -> dict:
    """Tiêu đề, kênh, thời lượng, ngày đăng của video (không tải nội dung)."""
    output = subprocess.run(
        ["yt-dlp", "--no-warnings", "--skip-download", "--dump-json", f"https://www.youtube.com/watch?v={video_id}"],
        capture_output=True, text=True, check=True, timeout=120,
    ).stdout
    data = json.loads(output)
    return {"title": data.get("title"), "channel": data.get("channel"), "duration_seconds": data.get("duration"),
            "upload_date": data.get("upload_date")}


def _download_audio(video_id: str, folder: Path) -> Path:
    """Tải riêng luồng âm thanh vào thư mục tạm và trả về đường dẫn file."""
    subprocess.run(
        ["yt-dlp", "--no-warnings", "-f", "bestaudio/best", "-o", str(folder / "audio.%(ext)s"),
         f"https://www.youtube.com/watch?v={video_id}"],
        capture_output=True, text=True, check=True, timeout=900,
    )
    return next(folder.glob("audio.*"))


def main() -> int:
    """Xử lý lần lượt các video trong danh sách; in một dòng kết quả cho mỗi video."""
    settings = get_settings()
    ids = [line.split("#")[0].strip() for line in (FOLDER / "selected.txt").read_text(encoding="utf-8").splitlines()]
    ids = [video_id for video_id in ids if video_id]
    out = FOLDER / "transcripts"
    out.mkdir(parents=True, exist_ok=True)

    audio = AudioProcessor(settings.audio_processing_timeout_seconds, MAX_SECONDS)
    transcriber = WhisperTranscriber(
        model=settings.whisper_model, compute_type=settings.whisper_compute_type, language=settings.whisper_language,
        beam_size=settings.whisper_beam_size, cpu_threads=settings.whisper_cpu_threads,
    )
    failed = 0
    for video_id in ids:
        target = out / f"{video_id}.json"
        if target.exists():
            print(f"{video_id}: already done")
            continue
        try:
            record = {"id": video_id, "url": f"https://www.youtube.com/watch?v={video_id}", **_metadata(video_id)}
            with tempfile.TemporaryDirectory() as workdir:
                source = _download_audio(video_id, Path(workdir))
                normalized = Path(workdir) / "normalized.wav"
                audio.normalize(source, normalized)
                started = time.perf_counter()
                transcript = transcriber.transcribe(normalized)
            record |= {
                "stt_model": transcriber.name, "processing_seconds": round(time.perf_counter() - started, 1),
                "transcript": transcript.text,
                "segments": [{"start": round(s.start, 1), "end": round(s.end, 1), "text": s.text}
                             for s in transcript.segments],
            }
            target.write_text(json.dumps(record, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
            print(f"{video_id}: {record['duration_seconds']}s audio, {len(transcript.text.split())} words, "
                  f"{record['processing_seconds']}s", flush=True)
        except (ApiError, subprocess.SubprocessError, StopIteration, json.JSONDecodeError) as error:
            failed += 1
            detail = getattr(error, "stderr", None) or getattr(error, "message", None) or str(error)
            print(f"{video_id}: FAILED {str(detail).strip()[:200]}", flush=True)
    print(f"done: {len(ids) - failed}/{len(ids)} videos have a transcript")
    return 0


if __name__ == "__main__":
    sys.exit(main())
