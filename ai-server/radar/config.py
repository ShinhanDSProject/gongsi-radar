"""설정값. 임계값은 dev셋으로만 조정한다(평가 계획 참고)."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PIPELINE_VERSION = "0.1.0-prototype"

# 임베더별 문단 정렬 임계값
#   match: 이 값 이상이어야 같은 문단으로 짝지음 / split_gain: 분할·병합으로 볼 최소 유사도 상승폭
#   part: 분할 조각이 원 문단과 가져야 할 최소 유사도 / move: 순서가 바뀐 문단을 다시 짝지을 때 기준
#   slot: 앞뒤 짝 사이 '같은 자리'에 남은 문단끼리 짝지을 최소 유사도
ALIGN_THRESHOLDS = {
    "tfidf": {"match": 0.35, "split_gain": 0.12, "part": 0.25, "move": 0.55, "slot": 0.18},
    "kure": {"match": 0.80, "split_gain": 0.12, "part": 0.50, "move": 0.90, "slot": 0.55},
    "qwen3": {"match": 0.78, "split_gain": 0.12, "part": 0.50, "move": 0.90, "slot": 0.55},
}

# 관련 서술 검색 대상 섹션(섹션 키 접두사)
RELATE_SECTIONS = ("II", "III-3", "IV", "X", "XI")

# 핵심 손익 계정(Must): 항상 관련 서술 연결
KEY_ACCOUNTS = {
    "ifrs-full_Revenue": "매출액",
    "dart_OperatingIncomeLoss": "영업이익",
    "ifrs-full_ProfitLoss": "당기순이익",
}
# 중요성 플래그에서 뺄 계정: 소계·합계, 세전이익에 연동되는 법인세
# 지배주주 귀속분은 당기순이익·자본총계의 일부라 따로 플래그하지 않는다(시장 지표 계산에만 씀)
FLAG_EXCLUDE = {"매출총이익", "법인세비용차감전순이익", "법인세비용", "자산총계", "부채총계", "자본총계",
                "지배기업의 소유주에게 귀속되는 당기순이익", "지배기업의 소유주에게 귀속되는 자본"}
MATERIALITY_REV_SHARE = 0.01   # 변동액이 매출액의 1% 이상
MATERIALITY_YOY = 0.30         # 그리고 증감률 30% 이상
ROBUST_Z = 3.0
MAX_VERIFY_RETRIES = 2


@dataclass
class Settings:
    source: str = field(default_factory=lambda: os.getenv("RADAR_SOURCE", "sample"))  # sample | opendart
    dart_api_key: str | None = field(default_factory=lambda: os.getenv("OPENDART_API_KEY"))
    sample_dir: Path = field(default_factory=lambda: Path(os.getenv("RADAR_SAMPLE_DIR", ROOT / "samples" / "data")))
    cache_dir: Path = field(default_factory=lambda: Path(os.getenv("RADAR_CACHE_DIR", ROOT / ".cache")))
    out_dir: Path = field(default_factory=lambda: Path(os.getenv("RADAR_OUT_DIR", ROOT / "out")))
    embedder: str = field(default_factory=lambda: os.getenv("RADAR_EMBEDDER", "tfidf"))
    llm_base_url: str | None = field(default_factory=lambda: os.getenv("RADAR_LLM_BASE_URL", "https://api.openai.com/v1"))
    llm_api_key: str | None = field(default_factory=lambda: os.getenv("OPENAI_API_KEY"))
    llm_model_small: str = field(default_factory=lambda: os.getenv("RADAR_LLM_SMALL", "gpt-4o-mini"))
    llm_model_large: str = field(default_factory=lambda: os.getenv("RADAR_LLM_LARGE", "gpt-4o"))
    peers_file: Path | None = field(default_factory=lambda: Path(p) if (p := os.getenv("RADAR_PEERS_FILE")) else None)
    # #3 적재 DB(읽기). 비어 있으면 원천만 쓴다. 쓰기(수집)는 RADAR_INGEST_WRITE_DB(수집 전용 계정)
    ingest_db: str | None = field(default_factory=lambda: os.getenv("RADAR_INGEST_DB") or None)
    demo_fault_injection: bool = False  # 시연용: 첫 시도에서 수치 오류를 주입해 반려 루프를 보여 줌

    @property
    def use_llm(self) -> bool:
        return bool(self.llm_api_key) or os.getenv("RADAR_LLM", "") == "on"
