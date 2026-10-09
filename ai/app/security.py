"""Xác thực giữa các service bằng khóa API dùng chung."""

import secrets
from typing import Annotated

from fastapi import Depends
from fastapi.security import APIKeyHeader

from app.config import Settings, get_settings
from app.errors import ApiError

API_KEY_HEADER = "X-API-Key"

# auto_error=False để tự trả lỗi theo cấu trúc chung thay vì lỗi mặc định của FastAPI.
_api_key_header = APIKeyHeader(name=API_KEY_HEADER, auto_error=False)


def require_api_key(
    provided: Annotated[str | None, Depends(_api_key_header)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> None:
    """Chỉ cho phép request có header ``X-API-Key`` đúng với khóa đã cấu hình.

    AI service chỉ phục vụ backend Spring Boot, không phục vụ trực tiếp mobile hay admin web.
    So sánh bằng ``compare_digest`` để thời gian so sánh không tiết lộ khóa.
    """
    if provided is None or not secrets.compare_digest(provided.encode(), settings.api_key.encode()):
        raise ApiError(401, "UNAUTHORIZED", "A valid API key is required.")
