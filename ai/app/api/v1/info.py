"""Thông tin service và trạng thái thật của từng thành phần AI."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request

from app import __version__
from app.audio import AudioProcessor
from app.config import Settings, get_settings
from app.schemas import ComponentStatus, PipelineComponents, ServiceInfo

router = APIRouter(tags=["Info"])


@router.get("/info")
def info(request: Request, settings: Annotated[Settings, Depends(get_settings)]) -> ServiceInfo:
    """Cho backend biết thành phần nào của pipeline đã dùng được.

    Trạng thái ở đây phải phản ánh đúng thực tế: thành phần nào chưa được triển khai thì báo
    NOT_IMPLEMENTED, thành phần đã triển khai nhưng không dùng được (thiếu ffmpeg, nạp model lỗi)
    thì báo UNAVAILABLE. Không báo READY khi chưa có model hay engine thật.
    """
    transcriber = request.app.state.transcription.transcriber
    return ServiceInfo(
        service=settings.service_name,
        version=__version__,
        components=PipelineComponents(
            audio_processing=ComponentStatus.READY if AudioProcessor.available() else ComponentStatus.UNAVAILABLE,
            speech_to_text=ComponentStatus.READY if transcriber is not None else ComponentStatus.UNAVAILABLE,
            rule_engine=ComponentStatus.READY,
            nlp_model=ComponentStatus.NOT_IMPLEMENTED,
            risk_engine=ComponentStatus.NOT_IMPLEMENTED,
        ),
        stt_model=transcriber.name if transcriber is not None else None,
    )
