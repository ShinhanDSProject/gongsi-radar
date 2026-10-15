"""ServiceSource(Spring 내부 데이터 API, docs/CONTRACT.md §11.2)와 원문 파생 정보(/ai/insights) 테스트.

Spring을 띄우지 않는다. httpx.MockTransport로 만든 가짜 Spring이 샘플 소스(SampleSource)를 §11.2 모양으로 내준다 —
경로·쿼리 이름·응답 모양이 계약과 다르면 여기서 깨진다.
"""
import json
from pathlib import Path

import httpx
import pytest

from radar.config import ROOT, Settings
from radar.pipeline.graph import finalize, initial_state, prepare_context, run_graph
from radar.insights.document import document_insights
from radar.sources.service import ServiceSource, SourceNotFound, SourceUnavailable, set_header_provider
from radar.sources.base import SourceError
from radar.sources.sample import SampleSource

BASE = "http://spring.test/internal/data"
KEY = "test-data-key"
GOLDEN = ROOT.parent / "backend" / "src" / "test" / "resources" / "golden"


def _origin(handler, origin="sample"):
    """가짜 Spring 응답마다 X-Data-Origin을 붙인다(§11.2)."""
    def wrapped(request):
        r = handler(request)
        r.headers["X-Data-Origin"] = origin
        return r
    return wrapped


def _sample() -> SampleSource:
    return SampleSource(Settings().sample_dir)


class FakeSpring:
    """§11.2 경로를 샘플 소스로 답한다. 받은 요청을 기록한다."""

    def __init__(self, src: SampleSource):
        self.src = src
        self.requests: list[httpx.Request] = []
        self.fail_next: list = []  # 앞에서부터 꺼내 쓰는 고장(예외 또는 상태 코드)

    def __call__(self, req: httpx.Request) -> httpx.Response:
        self.requests.append(req)
        if self.fail_next:
            f = self.fail_next.pop(0)
            if isinstance(f, Exception):
                raise f
            return httpx.Response(f, json={"detail": f"고장 {f}"})
        if req.headers.get("X-Internal-API-Key") != KEY:
            return httpx.Response(401, json={"detail": "bad key"})
        path = req.url.path.removeprefix("/internal/data")
        q = req.url.params
        s = self.src
        try:
            if path == "/companies/resolve":
                return httpx.Response(200, json=s.resolve(q["q"]))
            if path == "/companies":
                return httpx.Response(200, json=s.companies())
            if path == "/filings":
                return httpx.Response(200, json=s.filings(q["corpCode"]))
            if path == "/report":
                return httpx.Response(200, json=s.find_report(q["corpCode"], int(q["bsnsYear"]), q["reprtCode"]))
            if path.startswith("/documents/"):
                return httpx.Response(200, content=s.document(path.rsplit("/", 1)[1]),
                                      headers={"Content-Type": "application/zip"})
            if path == "/financials":
                rows, fs = s.financials(q["corpCode"], int(q["bsnsYear"]), q["reprtCode"])
                return httpx.Response(200, json={"fs_div": fs, "list": rows})
            if path == "/peers":
                rows = s.peers(q["corpCode"], int(q["bsnsYear"]), q["reprtCode"])
                return httpx.Response(200, json={"list": rows}) if rows else httpx.Response(404, json={"detail": "피어 없음"})
            if path == "/lawsuits":
                return httpx.Response(200, json={"list": s.lawsuits(q["corpCode"], q["bgn"], q["end"])})
            if path == "/governance":
                return httpx.Response(200, json=s.governance(q["corpCode"], int(q["bsnsYear"]), q["reprtCode"]))
            if path.startswith("/market/"):
                items = s.market(path.rsplit("/", 1)[1])
                return httpx.Response(200, json={"items": items}) if items else httpx.Response(404, json={"detail": "시세 없음"})
        except SourceError as e:
            return httpx.Response(404, json={"detail": str(e)})
        return httpx.Response(404, json={"detail": f"no route {path}"})


@pytest.fixture
def spring():
    return FakeSpring(_sample())


def make(spring, **kw) -> ServiceSource:
    return ServiceSource(BASE, KEY, client=httpx.Client(transport=httpx.MockTransport(_origin(spring))), **kw)


def test_interface_matches_sample_source(spring):
    svc, smp = make(spring), _sample()
    assert svc.name == "service"
    assert svc.resolve("999001") == smp.resolve("999001")
    assert svc.companies() == smp.companies()
    assert svc.filings("00999001") == smp.filings("00999001")
    assert svc.find_report("00999001", 2025, "11011") == smp.find_report("00999001", 2025, "11011")
    assert svc.document("20260317000388") == smp.document("20260317000388")
    assert svc.financials("00999001", 2025, "11011") == smp.financials("00999001", 2025, "11011")
    assert svc.governance("00999001", 2025, "11011") == smp.governance("00999001", 2025, "11011")
    assert svc.lawsuits("00999001", "20250101", "20260317") == smp.lawsuits("00999001", "20250101", "20260317")
    assert svc.market("999001") == smp.market("999001")
    assert svc.calls == 9
    # 쿼리 이름은 §11.2 그대로(camelCase)
    fin = next(r for r in spring.requests if r.url.path.endswith("/financials"))
    assert dict(fin.url.params) == {"corpCode": "00999001", "bsnsYear": "2025", "reprtCode": "11011"}
    assert all(r.headers["X-Internal-API-Key"] == KEY for r in spring.requests)


def test_not_found_is_source_error_with_detail(spring):
    svc = make(spring)
    with pytest.raises(SourceNotFound, match="샘플에 없는 회사"):
        svc.resolve("없는회사")
    with pytest.raises(SourceError, match="지배구조 데이터가 없습니다"):
        svc.governance("00999001", 2010, "11011")
    # 선택 데이터(피어·시세)의 404는 '없음'
    assert svc.peers("00999001", 2010, "11011") == []
    assert svc.market("000000") == []


def test_retries_once_on_network_error_then_gives_up(spring):
    svc = make(spring)
    spring.fail_next = [httpx.ConnectError("refused")]
    assert svc.resolve("999001")["corp_code"] == "00999001"          # 한 번 더 불러 성공
    spring.fail_next = [httpx.ConnectError("refused"), httpx.ReadTimeout("slow")]
    with pytest.raises(SourceUnavailable, match="닿지 못했습니다"):
        svc.resolve("999001")
    spring.fail_next = [503]
    assert svc.companies()                                            # 5xx도 한 번 더
    spring.fail_next = [503, 503]
    with pytest.raises(SourceUnavailable, match="503"):
        svc.companies()


def test_auth_error_is_not_retried_and_not_swallowed(spring):
    svc = ServiceSource(BASE, "wrong", client=httpx.Client(transport=httpx.MockTransport(_origin(spring))))
    with pytest.raises(SourceUnavailable, match="401"):
        svc.market("999001")                                          # 선택 데이터여도 권한 오류는 올린다
    assert len(spring.requests) == 1


def test_trace_headers_from_provider(spring):
    svc = make(spring, header_provider=lambda: {"X-Request-ID": "req-1", "X-User-Id": "analyst_001", "X-Empty": ""})
    svc.companies()
    h = spring.requests[-1].headers
    assert (h["X-Request-ID"], h["X-User-Id"]) == ("req-1", "analyst_001") and "X-Empty" not in h
    # 생성자 콜백이 없으면 모듈 기본값(앱이 심는 것)을 쓴다
    set_header_provider(lambda: {"X-Request-ID": "req-2"})
    try:
        make(spring).companies()
        assert spring.requests[-1].headers["X-Request-ID"] == "req-2"
    finally:
        set_header_provider(None)


def test_pipeline_runs_through_service_source(spring, tmp_path):
    """분석 파이프라인이 Spring 응답 모양만으로 끝까지 돈다(샘플 소스로 돌린 결과와 같은 숫자)."""
    s = Settings()
    s.source, s.out_dir, s.llm_api_key = "service", Path(tmp_path), None
    req = {"company": "999001", "bsns_year": 2025, "reprt_code": "11011"}
    rep = finalize(run_graph(initial_state(prepare_context(s, dict(req), source=make(spring)), dict(req))))
    s2 = Settings()
    s2.source, s2.out_dir, s2.llm_api_key = "sample", Path(tmp_path), None
    ref = finalize(run_graph(initial_state(prepare_context(s2, dict(req), source=_sample()), dict(req))))
    assert rep["meta"]["company"]["corp_code"] == "00999001"
    assert rep["meta"]["sample_data"] is True                        # X-Data-Origin: sample
    assert rep["valuation"] is None or rep["valuation"]["marketSource"] == "sample"
    assert [(a["account_nm"], a["current"], a["prior"]) for a in rep["accounts"]] == \
           [(a["account_nm"], a["current"], a["prior"]) for a in ref["accounts"]]
    assert rep["governance"] == ref["governance"] and rep["business"] == ref["business"]


@pytest.mark.parametrize("corp", ["00999001", "00888012", "00777001"])
def test_insights_equal_golden_profile(corp, spring):
    """/ai/insights 결과 = 분리 전 Python 기업 상세(golden)의 business·governance·관련 notes. 샘플·서비스 소스 둘 다."""
    golden = json.loads((GOLDEN / f"profile_{corp}.json").read_text(encoding="utf-8"))
    want_notes = [n for n in golden["notes"] if n.startswith(("사업 지표", "지배구조"))]
    for src in (_sample(), make(spring)):
        got = json.loads(json.dumps(document_insights(src, corp), ensure_ascii=False))
        assert got["business"] == golden["business"]
        assert got["governance"] == golden["governance"]
        assert got["notes"] == want_notes


def test_insights_raises_when_service_down(spring):
    spring.fail_next = [httpx.ConnectError("refused")] * 2
    with pytest.raises(SourceUnavailable):
        document_insights(make(spring), "00999001")


def test_data_origin_header_marks_sample_report(spring):
    """Spring이 샘플을 내주면 리포트도 '가상 샘플'로 표시된다 — 가상 데이터가 실제 공시처럼 보이면 안 된다."""
    from radar.sources.base import data_origin
    svc = make(spring)
    assert data_origin(svc) == "service"          # 응답 전에는 모른다
    svc.resolve("999001")
    assert svc.origin == "sample" and data_origin(svc) == "sample"
