"""#3 일일 수집 파이프라인. 원천(OpenDART·공공데이터포털)을 적재 DB에 쌓고, 화면은 그 DB를 읽는다.

  python -m radar ingest daily  [--budget 15000]          최근 공시·시세·재무 증분
  python -m radar ingest backfill --years 3                회사별 지난 정기공시·재무
  python -m radar ingest status                            최근 실행 기록

쓰는 DB: RADAR_INGEST_WRITE_DB(수집 계정 gongsi_ingest) · 읽는 DB: RADAR_INGEST_DB(앱 계정 gongsi_app)
"""
from .dbsource import IngestedSource, wrap
from .jobs import STEPS, Ingestor, RunReport
from .store import IngestStore

__all__ = ["IngestedSource", "Ingestor", "IngestStore", "RunReport", "STEPS", "wrap"]
