"""Core Service 설정. Quant-X mock-core-service와 같은 방식(pydantic-settings)을 쓴다."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # 인증 — Read와 Write를 다른 키로 나눈다. 이 분리가 Core Zone의 핵심이다
    core_api_key: str = "dev-core-read-key"          # Tool Gateway(AI 서버) → Read
    core_system_key: str = "dev-core-system-key"     # Spring Boot(승인 후) → Write

    # 시뮬레이션 — 기본은 꺼 둔다. 테스트가 결정적이어야 하므로
    core_latency_ms_min: int = 0
    core_latency_ms_max: int = 0
    core_fail_rate: float = 0.0

    # 비즈니스 룰
    publication_daily_limit: int = 20                 # 요청자 1인 하루 발행 요청 20건
    publication_decision_timeout_sec: int = 86400     # 승인 대기 만료 24시간

    # DB
    core_db_path: str = "./data/core.db"

    service_name: str = "gongsi-core-service"
    version: str = "0.1.0"


settings = Settings()


def check_keys() -> None:
    """[보안] 두 키가 같으면 조회 키만 가진 AI 서버가 발행을 넣을 수 있다.
    그 상태로는 아예 뜨지 않게 한다. 비어 있는 키도 같은 이유로 막는다.
    """
    if not settings.core_api_key or not settings.core_system_key:
        raise RuntimeError("CORE_API_KEY와 CORE_SYSTEM_KEY는 비워 둘 수 없다")
    if settings.core_api_key == settings.core_system_key:
        raise RuntimeError("CORE_API_KEY와 CORE_SYSTEM_KEY가 같다. 서로 다른 값으로 둬야 한다")
