"""Mã request (request id) và access log, cùng cách hoạt động với backend Spring Boot.

Backend gửi kèm header ``X-Request-Id`` khi gọi sang AI service, nhờ đó một request của người dùng
tra được xuyên suốt log của cả hai service.
"""

import logging
import re
import time
import uuid
from contextvars import ContextVar

from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

REQUEST_ID_HEADER = "X-Request-Id"

# Mã do bên gọi gửi sẽ được ghi vào log, nên chỉ chấp nhận tập ký tự an toàn.
_SAFE_ID = re.compile(r"[A-Za-z0-9._-]{1,64}")

_request_id: ContextVar[str] = ContextVar("request_id", default="")

log = logging.getLogger("app.access")


def resolve_request_id(header_value: str | None) -> str:
    """Dùng lại mã của bên gọi nếu hợp lệ, ngược lại sinh mã UUID mới."""
    if header_value and _SAFE_ID.fullmatch(header_value):
        return header_value
    return str(uuid.uuid4())


class _RequestIdFilter(logging.Filter):
    """Gắn mã request hiện tại vào mọi dòng log."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = _request_id.get()
        return True


def configure_logging(level: str) -> None:
    """Cấu hình log ra stdout theo một định dạng duy nhất, có kèm mã request."""
    handler = logging.StreamHandler()
    handler.addFilter(_RequestIdFilter())
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)5s [%(request_id)s] %(name)s : %(message)s")
    )
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)


class RequestContextMiddleware:
    """Gắn mã request cho mỗi request, trả lại trong header và ghi một dòng access log."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = resolve_request_id(Headers(scope=scope).get(REQUEST_ID_HEADER))
        # Lưu vào scope để các hàm xử lý lỗi đọc được qua request.state.request_id.
        scope.setdefault("state", {})["request_id"] = request_id
        token = _request_id.set(request_id)
        started = time.perf_counter()
        # Nếu ứng dụng ném exception trước khi gửi phản hồi thì kết quả là lỗi 500.
        status = 500

        async def send_with_request_id(message: Message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
                MutableHeaders(scope=message)[REQUEST_ID_HEADER] = request_id
            await send(message)

        try:
            await self.app(scope, receive, send_with_request_id)
        finally:
            millis = int((time.perf_counter() - started) * 1000)
            # Health check gọi liên tục nên chỉ ghi ở mức DEBUG để không làm ngập log.
            level = logging.DEBUG if scope["path"] == "/health" else logging.INFO
            log.log(level, "%s %s -> %s (%s ms)", scope["method"], scope["path"], status, millis)
            _request_id.reset(token)
