"""Chạy FFmpeg + Whisper trên các file audio thật và in ra bản ghi đánh giá cho từng file.

Cách dùng (chạy trong container của AI service):

    docker compose run --rm -v D:/duong-dan/toi/audio:/samples:ro ai python -m tools.evaluate_stt /samples

Với mỗi file audio, nếu có file văn bản cùng tên đuôi ``.txt`` (ví dụ ``cuoc-goi-1.m4a`` và
``cuoc-goi-1.txt``) chứa nội dung chuẩn do người nghe gõ lại, công cụ tính thêm tỉ lệ lỗi từ (WER).
Không có file ``.txt`` thì chỉ in transcript, không đưa ra con số chất lượng nào.
"""

import json
import sys
import tempfile
import time
from pathlib import Path

from app.audio import AudioProcessor
from app.config import get_settings
from app.errors import ApiError
from app.evaluation import word_error_rate
from app.stt import WhisperTranscriber

AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".aac", ".ogg", ".webm", ".3gp", ".amr", ".flac"}


def main(folder: str) -> int:
    """Đánh giá mọi file audio trong thư mục; in mỗi file một dòng JSON và một dòng tổng kết."""
    settings = get_settings()
    files = sorted(p for p in Path(folder).iterdir() if p.suffix.lower() in AUDIO_EXTENSIONS)
    if not files:
        print(f"No audio files found in {folder}", file=sys.stderr)
        return 1

    audio = AudioProcessor(settings.audio_processing_timeout_seconds, settings.max_audio_seconds)
    transcriber = WhisperTranscriber(
        model=settings.whisper_model,
        compute_type=settings.whisper_compute_type,
        language=settings.whisper_language,
        beam_size=settings.whisper_beam_size,
        cpu_threads=settings.whisper_cpu_threads,
    )

    error_rates: list[float] = []
    with tempfile.TemporaryDirectory() as workdir:
        normalized = Path(workdir) / "normalized.wav"
        for path in files:
            record: dict[str, object] = {"file": path.name, "whisperModel": transcriber.name}
            try:
                source = audio.probe(path)
                info = audio.normalize(path, normalized)
                started = time.perf_counter()
                transcript = transcriber.transcribe(normalized)
                record |= {
                    "audioFormat": f"{source.container} / {source.codec}",
                    "sampleRate": source.sample_rate,
                    "channels": source.channels,
                    "durationSeconds": round(info.duration_seconds, 2),
                    "language": transcript.language,
                    "processingSeconds": round(time.perf_counter() - started, 2),
                    "transcript": transcript.text,
                }
                reference_file = path.with_suffix(".txt")
                if reference_file.exists():
                    reference = reference_file.read_text(encoding="utf-8")
                    wer = word_error_rate(reference, transcript.text)
                    error_rates.append(wer)
                    record |= {"reference": reference.strip(), "wer": round(wer, 4)}
            except ApiError as error:
                record |= {"error": error.code, "message": error.message}
            print(json.dumps(record, ensure_ascii=False))

    summary: dict[str, object] = {"files": len(files), "filesWithReference": len(error_rates)}
    if error_rates:
        summary["meanWer"] = round(sum(error_rates) / len(error_rates), 4)
    print(json.dumps({"summary": summary}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python -m tools.evaluate_stt <folder with audio files>", file=sys.stderr)
        sys.exit(2)
    sys.exit(main(sys.argv[1]))
