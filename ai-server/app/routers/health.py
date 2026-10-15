from fastapi import APIRouter

from ..config import settings
from ..safety import kill_switch
from ..safety.moderation import is_moderation_active

router = APIRouter(tags=["health"])


@router.get("/ai/health")
def health() -> dict:
    # 헬스 체크는 캐시를 거치지 않고 DB를 직접 본다 — "지금 켜져 있나"를 묻는 곳이 3초 전 값을 주면 곤란하다
    active, reason = kill_switch.status(force_refresh=True)
    return {
        "status": "healthy", "service": settings.service_name, "version": settings.version,
        "llmProvider": settings.llm_provider, "embeddingProvider": settings.embedding_provider,
        "killSwitchActive": active, "killSwitchReason": reason,
        # 설정값이 아니라 유효 상태 — ENABLE_MODERATION=true여도 폐쇄망이면 꺼진다
        "moderationEnabled": is_moderation_active(),
    }
