"""Xử lý lỗi: mọi lỗi của API đều được trả về theo cấu trúc ``ErrorResponse``."""

import logging
from datetime import UTC, datetime
from http import HTTPStatus

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.observability import REQUEST_ID_HEADER
from app.schemas import ErrorResponse, FieldViolation

log = logging.getLogger(__name__)

INTERNAL_ERROR_MESSAGE = "An unexpected error occurred."


class ApiError(Exception):
    """Lỗi có chủ đích của service (ví dụ: sai khóa API, audio không hợp lệ, model chưa sẵn sàng).

    ``message`` được trả nguyên văn cho bên gọi, nên không được chứa thông tin nội bộ.
    """

    def __init__(self, status_code: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message


def error_response(
    request: Request,
    status_code: int,
    code: str,
    message: str,
    field_errors: list[FieldViolation] | None = None,
) -> JSONResponse:
    """Tạo phản hồi lỗi theo cấu trúc chung, kèm đường dẫn và mã request."""
    request_id = getattr(request.state, "request_id", None)
    body = ErrorResponse(
        timestamp=datetime.now(UTC),
        status=status_code,
        code=code,
        message=message,
        path=request.url.path,
        request_id=request_id,
        field_errors=field_errors or None,
    )
    headers = {REQUEST_ID_HEADER: request_id} if request_id else None
    return JSONResponse(
        status_code=status_code,
        content=body.model_dump(mode="json", by_alias=True, exclude_none=True),
        headers=headers,
    )


async def _handle_api_error(request: Request, exc: ApiError) -> JSONResponse:
    """Lỗi có chủ đích: giữ nguyên mã HTTP, mã lỗi và thông báo."""
    return error_response(request, exc.status_code, exc.code, exc.message)


async def _handle_http_exception(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    """Lỗi HTTP của framework (404, 405...): mã lỗi lấy theo tên mã HTTP, ví dụ NOT_FOUND."""
    try:
        status = HTTPStatus(exc.status_code)
        code, message = status.name, status.phrase
    except ValueError:
        code, message = f"HTTP_{exc.status_code}", "Request failed."
    return error_response(request, exc.status_code, code, message)


async def _handle_validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Dữ liệu đầu vào không hợp lệ: trả 422 kèm lỗi của từng trường."""
    violations = [
        # Bỏ phần tử đầu ("body", "query"...) để chỉ còn tên trường.
        # Lỗi của cả body (ví dụ thiếu cả hai trường thay thế nhau) không có tên trường, ghi là "body".
        FieldViolation(field=".".join(str(part) for part in error["loc"][1:]) or "body", message=error["msg"])
        for error in exc.errors()
    ]
    return error_response(
        request, HTTPStatus.UNPROCESSABLE_ENTITY, "VALIDATION_FAILED", "Request validation failed.", violations
    )


async def _handle_unexpected(request: Request, exc: Exception) -> JSONResponse:
    """Mọi lỗi không lường trước: ghi log đầy đủ, chỉ trả thông báo chung, không lộ chi tiết nội bộ."""
    log.error("Unhandled exception", exc_info=exc)
    return error_response(request, HTTPStatus.INTERNAL_SERVER_ERROR, "INTERNAL_ERROR", INTERNAL_ERROR_MESSAGE)


def install_error_handlers(app: FastAPI) -> None:
    """Đăng ký các hàm xử lý lỗi cho ứng dụng."""
    app.add_exception_handler(ApiError, _handle_api_error)
    app.add_exception_handler(StarletteHTTPException, _handle_http_exception)
    app.add_exception_handler(RequestValidationError, _handle_validation_error)
    app.add_exception_handler(Exception, _handle_unexpected)
