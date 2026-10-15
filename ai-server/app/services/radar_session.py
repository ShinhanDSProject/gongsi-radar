"""분석 1건의 radar 파이프라인 상태를 Worker들이 나눠 쓰게 하는 세션.

radar/ 라이브러리는 고정 DAG(수집·파싱 → 수치 분석 → 본문 비교 → 관련 서술 연결 → 검증 ⇄ → Report Writer)의
노드 함수를 그대로 내보낸다. 이 모듈은 그 노드들을 Worker 단위로 나눠 부른다.

  disclosure_analyst : ingest · numbers · diff      (공시 수집·비교)
  financial_analyst  : relate                       (관련 서술 연결 — 반려되면 다시)
  risk_reviewer      : verify                       (코드 검증 → 반려 목록)
  report_writer      : report                       (리포트 계약 JSON)

세션은 (job_id, 회사, 연도, 보고서) 키로 찾는다. Tool은 인자로 회사·연도만 받고 job_id는 contextvar에서 읽는다 —
LLM이 job_id를 지어낼 수 없게 하기 위함이다. 그래프 밖에서 Tool을 직접 부르면(job 없음) 임시 세션을 만든다.

[주의] 세션은 프로세스 메모리에 있다. AI 서버가 재기동하면 사라지고, 다 쓴 세션은 LRU로 밀어낸다.
"""
from __future__ import annotations

import logging
import threading
import time
from collections import OrderedDict
from typing import Any, Dict, Optional, Tuple

from radar.config import Settings as RadarSettings
from radar.embed import make_embedder
from radar.graph import Ctx, NODES, route_after_verify
from radar.sources import make_source

from ..llm.factory import get_radar_llm
from ..safety.context import get_job_id, get_request_uid

logger = logging.getLogger(__name__)

STAGE_AGENT = {"ingest": "disclosure_analyst", "numbers": "disclosure_analyst", "diff": "disclosure_analyst",
               "relate": "financial_analyst", "verify": "risk_reviewer", "report": "report_writer"}
_MAX_SESSIONS = 32


def normalize_target(company: Any, bsns_year: Any, reprt_code: Any) -> Tuple[str, int, str]:
    return str(company).strip(), int(bsns_year), str(reprt_code or "11011").strip()


class RadarSession:
    def __init__(self, job_id: str, company: str, bsns_year: int, reprt_code: str,
                 demo_fault_injection: bool = False, request_id: int = 0) -> None:
        self.job_id = job_id
        self.target = (company, bsns_year, reprt_code)
        self.lock = threading.RLock()         # Worker의 Tool이 스레드풀에서 돌 수 있다
        self.done: set[str] = set()
        s = RadarSettings()
        s.demo_fault_injection = demo_fault_injection
        ctx = Ctx(settings=s, source=make_source(s), embedder=make_embedder(s.embedder),
                  llm=get_radar_llm("disclosure_analyst"), analysis_id=job_id, request_uid=get_request_uid())
        self.state: Dict[str, Any] = {
            "ctx": ctx, "timeline": [], "round": 0,
            "request": {"company": company, "bsns_year": bsns_year, "reprt_code": reprt_code,
                        "demo_fault_injection": demo_fault_injection, "request_id": request_id},
        }
        self.touched = time.time()

    # ---- 단계 실행 -------------------------------------------------------------
    def _run(self, name: str) -> None:
        ctx: Ctx = self.state["ctx"]
        ctx.llm = get_radar_llm(STAGE_AGENT[name])   # 단계마다 '어느 Worker의 호출인가'가 기록에 남는다
        self.state = {**self.state, **NODES[name](self.state)}
        self.done.add(name)
        self.touched = time.time()

    def prepare(self) -> None:
        """수집·파싱 → 수치 분석 → 본문 비교. 한 번만 돈다."""
        with self.lock:
            for name in ("ingest", "numbers", "diff"):
                if name not in self.done:
                    self._run(name)

    def relate(self) -> None:
        """관련 서술 연결. 반려된 계정(pending)만 다시 연결한다(radar relate 노드가 pending을 본다)."""
        with self.lock:
            self.prepare()
            self._run("relate")

    def verify(self) -> list:
        """코드 검증. 반려된 계정 키 목록을 돌려준다(radar verify가 상한까지 판단한다)."""
        with self.lock:
            if "relate" not in self.done:
                self.relate()
            self._run("verify")
            return list(self.state.get("pending") or [])

    def needs_revision(self) -> bool:
        return route_after_verify(self.state) == "relate"

    def finalize(self) -> Dict[str, Any]:
        with self.lock:
            if "verify" not in self.done:
                self.verify()
            if "report" not in self.done:
                self._run("report")
            rep = self.state["report"]
            rep["timeline"] = self.state["timeline"]
            rep.setdefault("metrics", {})["elapsed_ms"] = self.state["timeline"][-1]["ended_ms"] if self.state["timeline"] else 0
            return rep


class _Registry:
    def __init__(self) -> None:
        self._sessions: "OrderedDict[tuple, RadarSession]" = OrderedDict()
        self._lock = threading.Lock()

    def open(self, job_id: str, company: str, bsns_year: int, reprt_code: str, *,
             demo_fault_injection: bool = False, request_id: int = 0) -> RadarSession:
        key = (job_id, *normalize_target(company, bsns_year, reprt_code))
        with self._lock:
            sess = self._sessions.get(key)
            if sess is None:
                sess = RadarSession(job_id, *key[1:], demo_fault_injection=demo_fault_injection, request_id=request_id)
                self._sessions[key] = sess
            self._sessions.move_to_end(key)
            while len(self._sessions) > _MAX_SESSIONS:
                self._sessions.popitem(last=False)
            return sess

    def for_tool(self, company: Any, bsns_year: Any, reprt_code: Any) -> RadarSession:
        """Tool이 부르는 자리. 진행 중인 분석(job)이 있으면 그 세션을, 없으면 임시 세션을 쓴다."""
        target = normalize_target(company, bsns_year, reprt_code)
        job = get_job_id()
        if job:
            key = (job, *target)
            with self._lock:
                if key in self._sessions:
                    return self._sessions[key]
            # 같은 job인데 회사 표기만 다르면(종목코드 vs 회사명) job의 세션을 그대로 쓴다
            with self._lock:
                for k, s in reversed(self._sessions.items()):
                    if k[0] == job and k[2:] == target[1:]:
                        return s
        return self.open(job or "adhoc", *target)

    def drop(self, job_id: str) -> None:
        with self._lock:
            for k in [k for k in self._sessions if k[0] == job_id]:
                self._sessions.pop(k, None)


sessions = _Registry()
