"""API phiên bản 1. Mọi route trong đây đều yêu cầu khóa API."""

from fastapi import APIRouter, Depends

from app.api.v1 import classifications, indicators, info, transcriptions
from app.security import require_api_key

router = APIRouter(prefix="/v1", dependencies=[Depends(require_api_key)])
router.include_router(info.router)
router.include_router(indicators.router)
router.include_router(classifications.router)
router.include_router(transcriptions.router)
