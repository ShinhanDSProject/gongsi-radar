"""헬스 체크. 인증도 시뮬레이션도 걸지 않는다 — 살아 있는지만 보는 창구다."""
from typing import Any, Dict

from fastapi import APIRouter

from ..config import settings

router = APIRouter(prefix="/core", tags=["health"])


@router.get("/health")
def health() -> Dict[str, Any]:
    return {
        "status": "healthy",
        "service": settings.service_name,
        "version": settings.version,
        "latency_ms_range": [settings.core_latency_ms_min,
                             settings.core_latency_ms_max],
        "fail_rate": settings.core_fail_rate,
    }
