"""Health check, không cần khóa API (dùng cho Docker và các công cụ giám sát)."""

from fastapi import APIRouter

from app.schemas import HealthResponse

router = APIRouter(tags=["Health"])


@router.get("/health")
def health() -> HealthResponse:
    """Service đang chạy và nhận được request. Không phản ánh trạng thái của các model AI."""
    return HealthResponse(status="UP")
