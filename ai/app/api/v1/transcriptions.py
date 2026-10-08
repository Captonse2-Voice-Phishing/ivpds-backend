"""API chuyển audio thành văn bản (hai tầng đầu của pipeline: FFmpeg và Whisper)."""

from typing import Annotated

from fastapi import APIRouter, File, Request, UploadFile

from app.schemas import TranscriptionResponse

router = APIRouter(tags=["Transcriptions"])


@router.post("/transcriptions")
def transcribe(
    request: Request,
    audio: Annotated[UploadFile, File(description="Call audio: mp3, wav, m4a, aac, ogg, webm, 3gp, amr or flac")],
) -> TranscriptionResponse:
    """Nhận một file audio cuộc gọi, chuẩn hóa bằng FFmpeg rồi nhận dạng tiếng Việt bằng Whisper.

    Hàm khai báo đồng bộ (``def``) để FastAPI chạy nó trong luồng riêng: nhận dạng tốn nhiều CPU
    và mất nhiều giây, không được chặn vòng lặp sự kiện đang phục vụ các request khác.
    """
    return request.app.state.transcription.transcribe(audio.file)
