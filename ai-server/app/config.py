"""AI 서버 설정. 값은 환경변수(.env)로 덮어쓴다. 기본값은 로컬 개발용이다(docs/CONTRACT.md §1).

radar/ 라이브러리는 자기 설정(radar.config.Settings)을 따로 가진다. 여기서는 AI 계층 —
인증·LLM 전환·감사·Core Zone 조회 — 과 데이터 소스 기본값만 다룬다.

[역할 분리, docs/CONTRACT.md §11] 이 서버는 OpenDART·공공데이터포털 키를 갖지 않는다. 공시·재무·시세 원자료는
Spring 내부 데이터 API(RADAR_SERVICE_URL, 키 RADAR_SERVICE_KEY)로만 받는다. 기본 RADAR_SOURCE=service이고,
테스트(conftest)·CLI 단독 실행만 sample을 쓴다. radar는 환경변수를 읽으므로 아래 값을 환경변수 기본값으로 내려 준다.
"""
import os

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # 인증 — Spring Boot만 이 키를 안다
    ai_server_api_key: str = "dev-ai-internal-key"

    service_name: str = "gongsi-ai-server"
    version: str = "0.2.0"

    # LLM. 기본은 mock — 키 없이 전 구간이 돈다(결정적이라 테스트에도 쓴다)
    llm_provider: str = "mock"                      # openai | ollama | mock
    llm_model: str = "gpt-4o-mini"
    openai_api_key: str = ""
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5:7b"

    # 폐쇄망 — false면 외부 LLM·외부 임베딩을 모두 막는다
    allow_external_llm: bool = True

    # RAG
    embedding_provider: str = "hash"                # hash | ollama | openai
    embedding_model: str = ""                       # 비우면 provider 기본값(ollama: bge-m3)
    chroma_persist_dir: str = "./data/chroma"

    # MariaDB — 업무 테이블(앱 계정)과 감사 기록(감사 계정)을 다른 커넥션으로 쓴다
    mariadb_url: str = "mysql+pymysql://gongsi_app:app-pass@localhost:3307/gongsi?charset=utf8mb4"
    mariadb_audit_url: str = "mysql+pymysql://gongsi_audit:audit-only-pass@localhost:3307/gongsi?charset=utf8mb4"

    # Agent 실행 통제
    agent_max_iterations: int = 5
    agent_timeout_seconds: int = 90
    # 검증 반려 후 관련 서술 연결을 다시 돌리는 최대 횟수. radar의 MAX_VERIFY_RETRIES와 같은 값
    agent_max_revisions: int = 2

    # 데이터 소스 — Spring 내부 데이터 API(§11.2). AI 서버 키(ai_server_api_key)와 다른 값
    radar_source: str = "service"                   # service | sample(테스트·데모)
    radar_service_url: str = "http://localhost:8180/internal/data"
    radar_service_key: str = "dev-data-internal-key"

    # Core Zone(발행 원장) — 조회 키만. 시스템 키는 이 서버에 두지 않는다
    core_base_url: str = "http://localhost:9100"
    core_api_key: str = "dev-core-read-key"

    # 가드레일·거버넌스
    kill_switch_enabled: bool = False
    rate_limit_per_min: int = 120                   # 분석 1건이 Tool을 20번 안팎 부른다
    enable_moderation: bool = False


settings = Settings()

# radar.config.Settings는 os.environ만 본다. .env·기본값을 환경변수 기본값으로 내려 준다(이미 있는 값은 덮지 않는다)
for _k, _v in (("RADAR_SOURCE", settings.radar_source), ("RADAR_SERVICE_URL", settings.radar_service_url),
               ("RADAR_SERVICE_KEY", settings.radar_service_key)):
    os.environ.setdefault(_k, _v)
