"""Điểm khởi động của AI service."""

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI

from app import __version__
from app.api import health
from app.api import v1
from app.config import Settings, get_settings
from app.errors import install_error_handlers
from app.limits import MaxBodySizeMiddleware
from app.nlp import CONFIG_FILE, TextClassifier
from app.observability import RequestContextMiddleware, configure_logging
from app.rules import RuleEngine
from app.stt import Transcriber, WhisperTranscriber
from app.transcription import TranscriptionService

log = logging.getLogger(__name__)

# Phần dư cho các trường khác và phần bao của multipart quanh file audio.
_MULTIPART_OVERHEAD_BYTES = 1024 * 1024


def create_app(settings: Settings | None = None, transcriber: Transcriber | None = None,
               classifier: TextClassifier | None = None) -> FastAPI:
    """Tạo ứng dụng FastAPI: nạp cấu hình, cấu hình log, đăng ký middleware, xử lý lỗi và các router.

    Các tham số chỉ dùng trong test: ``settings`` để thay cấu hình, ``transcriber`` và ``classifier`` để dùng
    sẵn một bộ nhận dạng hoặc một bộ phân loại thay vì nạp model khi khởi động.
    """
    # Đọc cấu hình ngay khi khởi động để thiếu biến môi trường bắt buộc thì dừng luôn.
    resolved = settings or get_settings()
    configure_logging(resolved.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        """Nạp model Whisper khi service khởi động.

        Nạp lỗi (không tải được model, thiếu bộ nhớ...) không làm service dừng: service vẫn chạy,
        ``/v1/info`` báo speech-to-text là UNAVAILABLE và các yêu cầu nhận dạng nhận lỗi 503.
        """
        service: TranscriptionService = app.state.transcription
        if service.transcriber is None:
            try:
                log.info("Loading Whisper model %s", resolved.whisper_model)
                service.transcriber = WhisperTranscriber(
                    model=resolved.whisper_model,
                    compute_type=resolved.whisper_compute_type,
                    language=resolved.whisper_language,
                    beam_size=resolved.whisper_beam_size,
                    cpu_threads=resolved.whisper_cpu_threads,
                )
                log.info("Whisper model ready: %s", service.transcriber.name)
            except Exception:
                log.exception("Could not load the Whisper model; speech-to-text is unavailable")
        if app.state.nlp is None:
            # Artifact của NLP Model nằm ngoài image. Thiếu hoặc nạp lỗi thì API phân loại trả 503.
            if (Path(resolved.nlp_model_dir) / CONFIG_FILE).is_file():
                try:
                    log.info("Loading NLP model from %s", resolved.nlp_model_dir)
                    app.state.nlp = TextClassifier(resolved.nlp_model_dir, device=resolved.nlp_device)
                    log.info("NLP model ready: %s", app.state.nlp.name)
                except Exception:
                    log.exception("Could not load the NLP model; classification is unavailable")
            else:
                log.warning("No NLP model artifact in %s; classification is unavailable", resolved.nlp_model_dir)
        yield

    app = FastAPI(
        title="IVPDS AI Service",
        description="Voice phishing risk analysis for the IVPDS backend. Internal service: called only by the backend.",
        version=__version__,
        lifespan=lifespan,
    )
    app.state.transcription = TranscriptionService(resolved, transcriber)
    app.state.rules = RuleEngine()
    app.state.nlp = classifier
    if settings is not None:
        # Để các route lấy cấu hình qua Depends(get_settings) cũng dùng cấu hình được truyền vào.
        app.dependency_overrides[get_settings] = lambda: settings

    # Middleware thêm sau nằm ngoài cùng: RequestContext bọc ngoài để mọi phản hồi đều có mã request.
    app.add_middleware(MaxBodySizeMiddleware, max_bytes=resolved.max_audio_bytes + _MULTIPART_OVERHEAD_BYTES)
    app.add_middleware(RequestContextMiddleware)
    install_error_handlers(app)
    app.include_router(health.router)
    app.include_router(v1.router)
    return app


app = create_app()
