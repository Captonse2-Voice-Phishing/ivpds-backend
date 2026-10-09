"""Giới hạn kích thước body của request."""

from fastapi import Request
from starlette.datastructures import Headers
from starlette.types import ASGIApp, Receive, Scope, Send

from app.errors import ApiError, error_response


class MaxBodySizeMiddleware:
    """Từ chối request có body vượt quá giới hạn, trước khi nội dung được đọc.

    FastAPI đọc và ghi toàn bộ file tải lên ra đĩa trước khi kiểm tra khóa API, nên nếu không chặn
    ở đây thì bên không có khóa vẫn có thể làm đầy ổ đĩa bằng cách gửi file rất lớn.
    """

    def __init__(self, app: ASGIApp, max_bytes: int) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        declared = Headers(scope=scope).get("content-length")
        if declared is not None and declared.isdigit() and int(declared) > self.max_bytes:
            response = error_response(Request(scope), 413, "PAYLOAD_TOO_LARGE", "Request body is too large.")
            await response(scope, receive, send)
            return

        received = 0

        async def limited_receive():
            """Đếm số byte thực nhận, để chặn cả request không khai báo Content-Length."""
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_bytes:
                    raise ApiError(413, "PAYLOAD_TOO_LARGE", "Request body is too large.")
            return message

        await self.app(scope, limited_receive, send)
