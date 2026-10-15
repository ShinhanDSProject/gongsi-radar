"""Spring 내부 데이터 API 소스(RADAR_SOURCE=service, docs/CONTRACT.md §11.2).

AI 서버는 OpenDART·공공데이터포털 키를 갖지 않는다. 원천 데이터는 모두 Spring(backend)의 `/internal/data/**`로 받는다.
응답 모양은 원천 그대로(OpenDART·공공데이터포털 필드)라 radar 파이프라인 코드는 소스가 바뀐 것을 모른다.

  인증   X-Internal-API-Key: RADAR_SERVICE_KEY (AI 서버 키와 다른 값, 기본 dev-data-internal-key)
  추적   X-Request-ID·X-User-Id — radar는 app/을 모르므로 호출자가 header_provider(콜백)를 넣어 준다
  오류   404 → SourceNotFound(detail). 연결 실패·타임아웃·5xx는 한 번 더 부르고 그래도 안 되면 SourceUnavailable
         (둘 다 SourceError 하위 — 기존 radar 코드는 그대로 잡는다. 401·403·400은 다시 부르지 않는다)
         피어·소송·시세의 404는 '데이터 없음'으로 보고 빈 목록(샘플 소스와 같은 동작 — 분석을 멈추지 않는다)
캐시하지 않는다(캐시·호출 한도 관리는 Spring 몫). 같은 분석 안의 재사용은 radar 세션이 한다.
"""
from __future__ import annotations

import threading
import time
from typing import Callable, Optional

import httpx

from radar.sources.base import SourceError

HeaderProvider = Callable[[], dict]


class SourceNotFound(SourceError):
    """데이터 서비스가 404로 답했다(회사·보고서·데이터 없음). SourceError를 잡는 기존 코드가 그대로 받는다."""


class SourceUnavailable(SourceError):
    """데이터 서비스에 닿지 못했거나(연결·타임아웃·5xx) 거절당했다(401·403·400). '데이터 없음'과 구분한다."""


# 앱(app/)이 시작할 때 심는 기본 추적 헤더 콜백. radar는 app의 contextvars를 직접 import하지 않는다
_default_header_provider: Optional[HeaderProvider] = None

_clients: dict[tuple, httpx.Client] = {}
_clients_lock = threading.Lock()


def _shared_client(timeout: float, connect_timeout: float) -> httpx.Client:
    """연결 풀을 프로세스에서 나눠 쓴다(소스는 Tool 호출·분석마다 새로 만든다). httpx.Client는 스레드 안전하다."""
    key = (timeout, connect_timeout)
    with _clients_lock:
        if key not in _clients:
            _clients[key] = httpx.Client(timeout=httpx.Timeout(timeout, connect=connect_timeout))
        return _clients[key]


def set_header_provider(fn: Optional[HeaderProvider]) -> None:
    """X-Request-ID·X-User-Id 등을 돌려주는 콜백을 등록한다. None이면 추적 헤더 없이 부른다."""
    global _default_header_provider
    _default_header_provider = fn


class ServiceSource:
    name = "service"

    def __init__(self, base_url: str, api_key: str, *, timeout: float = 20.0, connect_timeout: float = 3.0,
                 retries: int = 1, header_provider: Optional[HeaderProvider] = None,
                 client: Optional[httpx.Client] = None):
        if not base_url:
            raise SourceError("RADAR_SERVICE_URL이 없습니다(Spring 내부 데이터 API 주소).")
        self.base_url = base_url.rstrip("/")
        self.retries = retries
        self.header_provider = header_provider
        self.http = client or _shared_client(timeout, connect_timeout)
        self.base_headers = {"X-Internal-API-Key": api_key or "", "X-Caller": "ai-server"}
        self.calls = 0
        # Spring이 알려 주는 데이터 출처(X-Data-Origin: sample|opendart). 첫 응답 전에는 모른다(None).
        # 리포트의 '가상 샘플' 표시가 여기서 나온다 — 가상 데이터가 실제 공시처럼 보이면 안 된다
        self.origin: str | None = None

    # -- 공통 --------------------------------------------------------------------
    def _trace_headers(self) -> dict:
        fn = self.header_provider or _default_header_provider
        if not fn:
            return {}
        try:
            return {k: v for k, v in (fn() or {}).items() if v}
        except Exception:  # 추적 헤더 실패가 데이터 조회를 막지 않게
            return {}

    def _get(self, path: str, params: dict | None = None) -> httpx.Response:
        self.calls += 1
        url = f"{self.base_url}{path}"
        params = {k: v for k, v in (params or {}).items() if v is not None}
        last: Exception | None = None
        for attempt in range(self.retries + 1):
            try:
                r = self.http.get(url, params=params, headers={**self.base_headers, **self._trace_headers()})
            except httpx.RequestError as e:  # 연결 거부·타임아웃 — 한 번 더
                last = e
                if attempt < self.retries:
                    time.sleep(0.3 * (attempt + 1))
                    continue
                raise SourceUnavailable(f"데이터 서비스에 닿지 못했습니다({path}): {type(e).__name__}: {e}") from e
            self.origin = r.headers.get("X-Data-Origin") or self.origin
            if r.status_code == 404:
                raise SourceNotFound(_detail(r) or f"데이터 없음: {path}")
            if r.status_code >= 500 and attempt < self.retries:
                last = None
                time.sleep(0.3 * (attempt + 1))
                continue
            if r.status_code >= 400:  # 401·403·400은 다시 불러도 같다. 5xx는 여기까지 오면 재시도도 실패
                raise SourceUnavailable(f"데이터 서비스 오류 {r.status_code}({path}): {_detail(r) or r.text[:200]}")
            return r
        raise SourceUnavailable(f"데이터 서비스에 닿지 못했습니다({path}): {last}")

    def _json(self, path: str, params: dict | None = None):
        r = self._get(path, params)
        try:
            return r.json()
        except ValueError as e:
            raise SourceUnavailable(f"데이터 서비스 응답이 JSON이 아닙니다({path})") from e

    def _list_or_empty(self, path: str, params: dict, key: str) -> list[dict]:
        """선택 데이터(피어·소송·시세): 404는 '없음'으로 본다."""
        try:
            d = self._json(path, params)
        except SourceNotFound:  # 연결 실패·권한 오류는 그대로 올린다
            return []
        return list((d or {}).get(key) or [])

    # -- 인터페이스(radar.sources 공통 인터페이스와 같은 모양) ------------------------------
    def resolve(self, query: str) -> dict:
        return self._json("/companies/resolve", {"q": str(query)})

    def companies(self) -> list[dict]:
        return list(self._json("/companies") or [])

    def filings(self, corp_code: str) -> list[dict]:
        return list(self._json("/filings", {"corpCode": corp_code}) or [])

    def find_report(self, corp_code: str, bsns_year: int, reprt_code: str) -> dict:
        return self._json("/report", {"corpCode": corp_code, "bsnsYear": bsns_year, "reprtCode": reprt_code})

    def document(self, rcept_no: str) -> bytes:
        data = self._get(f"/documents/{rcept_no}").content
        if not data.startswith(b"PK"):
            raise SourceError(f"원문 ZIP 대신 다른 응답: {data[:200].decode('utf-8', 'replace')}")
        return data

    def financials(self, corp_code: str, bsns_year: int, reprt_code: str) -> tuple[list[dict], str]:
        d = self._json("/financials", {"corpCode": corp_code, "bsnsYear": bsns_year, "reprtCode": reprt_code}) or {}
        rows = d.get("list") or []
        if not rows:
            raise SourceError("재무제표 데이터가 없습니다(013).")
        return rows, d.get("fs_div") or "CFS"

    def peers(self, corp_code: str, bsns_year: int, reprt_code: str) -> list[dict]:
        return self._list_or_empty("/peers", {"corpCode": corp_code, "bsnsYear": bsns_year, "reprtCode": reprt_code},
                                   "list")

    def lawsuits(self, corp_code: str, bgn: str, end: str) -> list[dict]:
        return self._list_or_empty("/lawsuits", {"corpCode": corp_code, "bgn": bgn, "end": end}, "list")

    def governance(self, corp_code: str, bsns_year: int, reprt_code: str) -> dict:
        d = self._json("/governance", {"corpCode": corp_code, "bsnsYear": bsns_year, "reprtCode": reprt_code}) or {}
        g = {"shareholders": d.get("shareholders") or [], "executives": d.get("executives") or [],
             "investments": d.get("investments") or [], "rcept_no": d.get("rcept_no")}
        if not (g["shareholders"] or g["executives"] or g["investments"]):
            raise SourceError(f"{bsns_year}년 지배구조 데이터가 없습니다(013).")
        return g

    def market(self, stock_code: str) -> list[dict]:
        if not stock_code:
            return []
        return self._list_or_empty(f"/market/{stock_code}", {}, "items")


def _detail(r: httpx.Response) -> str:
    try:
        d = r.json()
    except ValueError:
        return ""
    if isinstance(d, dict):
        v = d.get("detail") or d.get("message") or d.get("error")
        return v if isinstance(v, str) else (str(v) if v else "")
    return ""
