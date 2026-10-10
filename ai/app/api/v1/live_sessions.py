"""API phân tích cuộc gọi trực tiếp qua WebSocket.

Giao thức (phiên bản 1). Bên gọi là backend; kết nối tới ``/v1/live-sessions`` kèm header ``X-API-Key``.

Bên gọi gửi:

* Gói nhị phân: byte đầu cho biết người nói (0 = người gọi đến, 1 = người dùng ứng dụng), phần còn lại là PCM
  16 bit có dấu, little-endian, một kênh, 16 kHz. Gói dài bao nhiêu cũng được (khuyến nghị 100-500 ms).
* Tin nhắn văn bản ``{"type": "start", "customPatterns": [...]}`` (tùy chọn, chỉ trước gói âm thanh đầu tiên): các
  mẫu lừa đảo do quản trị viên quản lý, cùng cấu trúc với ``customPatterns`` của ``POST /v1/risk-assessments``.
* Tin nhắn văn bản ``{"type": "end"}``: kết thúc cuộc gọi, yêu cầu kết quả cuối.

Service gửi (JSON, mỗi sự kiện có ``type`` và số thứ tự ``seq``):

* ``ready``: phiên đã mở, kèm định dạng âm thanh và phiên bản các thành phần.
* ``transcript``: một câu vừa nhận dạng xong (``speaker``, ``start``, ``end``, ``text``).
* ``risk``: điểm rủi ro cập nhật của cả cuộc gọi tính đến lúc này.
* ``alert``: mức rủi ro vừa tăng lên MEDIUM hoặc HIGH; mỗi mức chỉ báo một lần.
* ``final``: kết quả chốt sau khi kết thúc, rồi service đóng kết nối.
* ``error``: phiên không thể tiếp tục (``code``, ``message``), rồi service đóng kết nối.
"""

import asyncio
import contextlib
import json
import logging
import secrets
import uuid

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from app.live import (BYTES_PER_SAMPLE, LIVE_API_VERSION, SAMPLE_RATE, SPEAKER_BY_PREFIX, LiveSession, Speaker,
                      Utterance, UtteranceSegmenter)
from app.risk import RISK_ENGINE_VERSION
from app.schemas import CustomPattern
from app.security import API_KEY_HEADER

log = logging.getLogger(__name__)

# Router riêng, không nằm dưới router /v1 dùng chung, vì cách kiểm tra khóa API của router đó chỉ áp dụng cho HTTP.
router = APIRouter(prefix="/v1", tags=["Live sessions"])

_MAX_FRAME_BYTES = 1024 * 1024
_MAX_CUSTOM_PATTERNS = 500
# Mã đóng kết nối riêng của ứng dụng (khoảng 4000-4999 dành cho ứng dụng).
CLOSE_UNAUTHORIZED = 4401
CLOSE_UNAVAILABLE = 4503
CLOSE_PROTOCOL_ERROR = 4400


class _SessionError(Exception):
    """Lỗi làm phiên phải dừng; được báo cho bên gọi bằng sự kiện ``error`` rồi đóng kết nối."""

    def __init__(self, code: str, message: str, close_code: int = CLOSE_PROTOCOL_ERROR) -> None:
        super().__init__(message)
        self.code, self.message, self.close_code = code, message, close_code


@router.websocket("/live-sessions")
async def live_session(websocket: WebSocket) -> None:
    """Một kết nối là một cuộc gọi đang được phân tích."""
    app = websocket.app
    settings = app.state.settings
    provided = websocket.headers.get(API_KEY_HEADER)
    if provided is None or not secrets.compare_digest(provided.encode(), settings.api_key.encode()):
        # Từ chối trước khi chấp nhận kết nối: bên gọi nhận HTTP 403 và không tốn tài nguyên nào của service.
        await websocket.close(code=CLOSE_UNAUTHORIZED)
        return
    await websocket.accept()

    session_id = websocket.headers.get("x-request-id") or str(uuid.uuid4())
    transcription = app.state.transcription
    try:
        if transcription.transcriber is None:
            raise _SessionError("STT_UNAVAILABLE", "The speech-to-text model is not available.", CLOSE_UNAVAILABLE)
        if app.state.nlp is None:
            raise _SessionError("NLP_MODEL_UNAVAILABLE", "The NLP model is not available.", CLOSE_UNAVAILABLE)
        if app.state.live_sessions >= settings.live_max_sessions:
            raise _SessionError("LIVE_SESSION_LIMIT", "Too many calls are being analysed right now.",
                                CLOSE_UNAVAILABLE)
    except _SessionError as error:
        await _fail(websocket, error)
        return

    app.state.live_sessions += 1
    log.info("Live session %s started", session_id)
    try:
        await _run(websocket, session_id)
    except WebSocketDisconnect:
        log.info("Live session %s: caller disconnected", session_id)
    except _SessionError as error:
        log.warning("Live session %s stopped: %s", session_id, error.code)
        await _fail(websocket, error)
    except Exception:
        log.exception("Live session %s failed", session_id)
        await _fail(websocket, _SessionError("LIVE_SESSION_FAILED", "The live analysis failed.", 1011))
    finally:
        app.state.live_sessions -= 1


async def _run(websocket: WebSocket, session_id: str) -> None:
    """Vòng đời của một phiên: nhận âm thanh, xử lý từng câu theo thứ tự, gửi sự kiện, chốt kết quả."""
    app = websocket.app
    settings = app.state.settings
    session = LiveSession(session_id=session_id, transcriber=app.state.transcription, rules=app.state.rules,
                          classifier=app.state.nlp)
    segmenters = {
        speaker: UtteranceSegmenter(speaker, settings.live_speech_threshold, settings.live_end_silence_ms,
                                    settings.live_max_utterance_seconds)
        for speaker in Speaker
    }
    await websocket.send_json({
        "type": "ready", "seq": 0, "sessionId": session_id, "apiVersion": LIVE_API_VERSION,
        "audioFormat": {"encoding": "pcm_s16le", "sampleRate": SAMPLE_RATE, "channels": 1,
                        "speakerPrefix": {str(prefix): speaker.value for prefix, speaker in SPEAKER_BY_PREFIX.items()}},
        "modelVersion": app.state.nlp.config["version"], "rulesetVersion": app.state.rules.version,
        "riskEngineVersion": RISK_ENGINE_VERSION, "sttModel": app.state.transcription.transcriber.name,
    })

    # Các câu chờ nhận dạng. Một tác vụ duy nhất xử lý lần lượt, để sự kiện ra đúng thứ tự câu được nói.
    pending: asyncio.Queue[Utterance | None] = asyncio.Queue()
    pending_seconds = 0.0
    loop = asyncio.get_running_loop()

    async def worker() -> None:
        nonlocal pending_seconds
        while (utterance := await pending.get()) is not None:
            # Nhận dạng và chấm điểm tốn CPU: chạy ở luồng khác để vòng lặp sự kiện vẫn nhận được âm thanh.
            started = loop.time()
            events = await loop.run_in_executor(None, session.process, utterance)
            pending_seconds -= utterance.seconds
            log.info("Live session %s: %s %.1f-%.1fs processed in %.1fs, %.1fs of audio waiting", session_id,
                     utterance.speaker.value, utterance.start, utterance.end, loop.time() - started, pending_seconds)
            for event in events:
                await websocket.send_json(event)

    async def enqueue(utterances: list[Utterance]) -> None:
        nonlocal pending_seconds
        for utterance in utterances:
            pending_seconds += utterance.seconds
            await pending.put(utterance)
        if pending_seconds > settings.live_max_pending_seconds:
            # Máy không nhận dạng kịp tốc độ nói: dừng hẳn thay vì cảnh báo trễ cả phút mà bên gọi không biết.
            raise _SessionError("LIVE_SESSION_OVERLOADED", "The live analysis cannot keep up with the call.",
                                CLOSE_UNAVAILABLE)

    task = asyncio.create_task(worker())
    ended_by = "CLIENT"
    try:
        while True:
            if task.done():
                task.result()  # tác vụ xử lý chỉ kết thúc sớm khi lỗi: ném lỗi đó ra
            try:
                message = await asyncio.wait_for(websocket.receive(), settings.live_idle_timeout_seconds)
            except TimeoutError:
                ended_by = "IDLE_TIMEOUT"
                break
            if message["type"] == "websocket.disconnect":
                raise WebSocketDisconnect(message.get("code", 1005))
            if (data := message.get("bytes")) is not None:
                await enqueue(_feed(data, segmenters))
                if max(s.seconds_received for s in segmenters.values()) >= settings.live_max_session_seconds:
                    ended_by = "MAX_DURATION"
                    break
            elif _is_end(message.get("text"), session, audio_started=any(
                    segmenter.seconds_received > 0 for segmenter in segmenters.values())):
                break
        for segmenter in segmenters.values():
            await enqueue(segmenter.flush())
        await pending.put(None)
        await task
    finally:
        if not task.done():
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task

    duration = max(segmenter.seconds_received for segmenter in segmenters.values())
    await websocket.send_json(session.final_event(duration, ended_by))
    log.info("Live session %s finished: %s turns, %.1fs audio, %.1fs speech-to-text, risk %s", session_id,
             len(session.turns), duration, session.stt_seconds, session.risk_level.value)
    await websocket.close(code=1000)


def _feed(data: bytes, segmenters: dict[Speaker, UtteranceSegmenter]) -> list[Utterance]:
    """Đưa một gói nhị phân vào bộ cắt câu của đúng người nói."""
    if len(data) > _MAX_FRAME_BYTES:
        raise _SessionError("AUDIO_FRAME_TOO_LARGE", "An audio frame is larger than 1 MB.")
    if not data or data[0] not in SPEAKER_BY_PREFIX:
        raise _SessionError("INVALID_AUDIO_FRAME", "The first byte of an audio frame must be 0 (caller) or 1 (callee).")
    if (len(data) - 1) % BYTES_PER_SAMPLE:
        raise _SessionError("INVALID_AUDIO_FRAME", "An audio frame must hold whole 16-bit samples.")
    return segmenters[SPEAKER_BY_PREFIX[data[0]]].feed(data[1:])


def _is_end(text: str | None, session: LiveSession, audio_started: bool) -> bool:
    """Xử lý một tin nhắn văn bản: ``end`` kết thúc phiên (trả True), ``start`` nạp các mẫu bổ sung (trả False).

    Mọi văn bản khác, ``start`` gửi sau khi đã có âm thanh, hay mẫu không hợp lệ đều là lỗi giao thức.
    """
    try:
        message = json.loads(text or "")
    except ValueError:
        message = None
    kind = message.get("type") if isinstance(message, dict) else None
    if kind == "end":
        return True
    if kind == "start" and not audio_started:
        try:
            patterns = [CustomPattern.model_validate(item) for item in message.get("customPatterns") or []]
        except (ValidationError, TypeError):
            raise _SessionError("INVALID_CUSTOM_PATTERNS", "customPatterns is not valid.") from None
        if len(patterns) > _MAX_CUSTOM_PATTERNS:
            raise _SessionError("INVALID_CUSTOM_PATTERNS", "Too many custom patterns.")
        session.extra_rules = [pattern.to_rule() for pattern in patterns]
        return False
    raise _SessionError("INVALID_MESSAGE", 'Text messages must be {"type": "end"}, or {"type": "start"} before any audio.')


async def _fail(websocket: WebSocket, error: _SessionError) -> None:
    """Gửi sự kiện lỗi rồi đóng kết nối; bên gọi có thể đã ngắt nên mọi lỗi gửi đều bị bỏ qua."""
    with contextlib.suppress(Exception):
        await websocket.send_json({"type": "error", "code": error.code, "message": error.message})
        await websocket.close(code=error.close_code)
