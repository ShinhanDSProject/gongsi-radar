"""데이터 소스. 샘플(가상 기업)과 OpenDART를 같은 인터페이스로 다룬다.

OpenDartSource는 응답을 디스크에 캐시한다. 원문 ZIP은 접수 후 바뀌지 않으므로 rcept_no 키로 영구 캐시하고,
재무·목록 응답도 같은 요청을 다시 보내지 않도록 캐시한다(일 20,000건 한도 관리).
오류 코드 013(데이터 없음)도 HTTP 200으로 오므로 응답 본문의 status를 항상 검사한다.
"""
from __future__ import annotations

import hashlib
import io
import json
import time
import xml.etree.ElementTree as ET
import zipfile
from datetime import date
from pathlib import Path

import requests

REPRT = {
    "11011": {"name": "사업보고서", "detail": "A001", "mm": "12"},
    "11012": {"name": "반기보고서", "detail": "A002", "mm": "06"},
    "11013": {"name": "1분기보고서", "detail": "A003", "mm": "03"},
    "11014": {"name": "3분기보고서", "detail": "A003", "mm": "09"},
}


class SourceError(RuntimeError):
    pass


def dart_url(rcept_no: str) -> str:
    return f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={rcept_no}"


class SampleSource:
    name = "sample"

    def __init__(self, data_dir: Path):
        self.dir = Path(data_dir)
        if not (self.dir / "list.json").exists():
            raise SourceError(f"샘플 데이터가 없습니다: {self.dir} (python samples/build_samples.py 실행)")
        self.calls = 0

    def _json(self, name: str) -> dict:
        self.calls += 1
        p = self.dir / name
        if not p.exists():
            return {"status": "013", "message": "조회된 데이타가 없습니다.", "list": []}
        return json.loads(p.read_text(encoding="utf-8"))

    def resolve(self, query: str) -> dict:
        corps = json.loads((self.dir / "corp_codes.json").read_text(encoding="utf-8"))
        for c in corps:
            if query in (c["corp_code"], c["stock_code"], c["corp_name"]):
                return c
        raise SourceError(f"샘플에 없는 회사입니다: {query} (가능: {[c['stock_code'] for c in corps]})")

    def find_report(self, corp_code: str, bsns_year: int, reprt_code: str) -> dict:
        tag = f"({bsns_year}.{REPRT[reprt_code]['mm']})"
        for r in self._json("list.json")["list"]:
            if r["corp_code"] == corp_code and tag in r["report_nm"] and REPRT[reprt_code]["name"] in r["report_nm"]:
                return {**r, "bsns_year": bsns_year, "reprt_code": reprt_code, "url": dart_url(r["rcept_no"])}
        raise SourceError(f"{bsns_year}년 {REPRT[reprt_code]['name']}를 찾지 못했습니다.")

    def document(self, rcept_no: str) -> bytes:
        self.calls += 1
        p = self.dir / "filings" / f"{rcept_no}.zip"
        if not p.exists():
            raise SourceError(f"원문 ZIP 없음: {p}")
        return p.read_bytes()

    def financials(self, corp_code: str, bsns_year: int, reprt_code: str) -> tuple[list[dict], str]:
        for fs in ("CFS", "OFS"):
            d = self._json(f"fnltt_{corp_code}_{bsns_year}_{reprt_code}_{fs}.json")
            if d.get("status") == "000" and d.get("list"):
                return d["list"], fs
        raise SourceError("재무제표 데이터가 없습니다(013).")

    def peers(self, corp_code: str, bsns_year: int, reprt_code: str) -> list[dict]:
        return self._json(f"peers_{bsns_year}_{reprt_code}.json").get("list", [])

    def lawsuits(self, corp_code: str, bgn: str, end: str) -> list[dict]:
        rows = self._json(f"lwstLg_{corp_code}.json").get("list", [])
        return [r for r in rows if bgn <= r.get("lgd", "").replace("-", "") <= end]


class OpenDartSource:
    name = "opendart"
    BASE = "https://opendart.fss.or.kr/api"

    def __init__(self, api_key: str, cache_dir: Path, peers_file: Path | None = None, session=None):
        if not api_key:
            raise SourceError("OPENDART_API_KEY가 없습니다. 서버 환경변수로 설정하세요(키는 1개만, 제3자 공유 금지).")
        self.key = api_key
        self.cache = Path(cache_dir) / "opendart"
        self.cache.mkdir(parents=True, exist_ok=True)
        self.peers_file = peers_file
        self.http = session or requests.Session()
        self.calls = 0

    # -- 공통 --------------------------------------------------------------------
    def _get(self, endpoint: str, params: dict, binary: bool = False):
        self.calls += 1
        for attempt in range(3):
            try:
                r = self.http.get(f"{self.BASE}/{endpoint}", params={"crtfc_key": self.key, **params}, timeout=60)
                r.raise_for_status()
                return r.content if binary else r.json()
            except (requests.RequestException, ValueError) as e:  # 마감 시즌 지연·SSL 오류 대비
                if attempt == 2:
                    raise SourceError(f"OpenDART {endpoint} 호출 실패: {e}") from e
                time.sleep(2 * (attempt + 1))

    def _cached_json(self, name: str, endpoint: str, params: dict) -> dict:
        p = self.cache / f"{name}.json"
        if p.exists():
            return json.loads(p.read_text(encoding="utf-8"))
        d = self._get(endpoint, params)
        status = d.get("status")
        if status == "020":
            raise SourceError("OpenDART 일 호출 한도(오류 020)를 넘었습니다.")
        if status not in ("000", "013"):
            raise SourceError(f"OpenDART 오류 {status}: {d.get('message')}")
        if status == "000":  # 데이터 없음(013)은 캐시하지 않는다(나중에 생길 수 있음)
            p.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
        return d

    # -- 인터페이스 ----------------------------------------------------------------
    def resolve(self, query: str) -> dict:
        p = self.cache / "corp_codes.json"
        if not p.exists():
            raw = self._get("corpCode.xml", {}, binary=True)
            z = zipfile.ZipFile(io.BytesIO(raw))
            root = ET.fromstring(z.read(z.namelist()[0]))
            corps = [{"corp_code": (e.findtext("corp_code") or "").strip(),  # 문자열 유지(앞자리 0)
                      "corp_name": (e.findtext("corp_name") or "").strip(),
                      "stock_code": (e.findtext("stock_code") or "").strip()} for e in root.iter("list")]
            p.write_text(json.dumps(corps, ensure_ascii=False), encoding="utf-8")
        corps = json.loads(p.read_text(encoding="utf-8"))
        for c in corps:
            if query in (c["corp_code"], c["stock_code"]) and (c["stock_code"] or query == c["corp_code"]):
                return c
        named = [c for c in corps if c["corp_name"] == query and c["stock_code"]]
        if named:
            return named[0]
        raise SourceError(f"회사를 찾지 못했습니다: {query}")

    def find_report(self, corp_code: str, bsns_year: int, reprt_code: str) -> dict:
        info = REPRT[reprt_code]
        end = min(date.today(), date(bsns_year + 1, 12, 31)).strftime("%Y%m%d")
        params = {"corp_code": corp_code, "bgn_de": f"{bsns_year}0101", "end_de": end, "last_reprt_at": "Y",
                  "pblntf_ty": "A", "pblntf_detail_ty": info["detail"], "page_count": 100}
        d = self._cached_json(f"list_{corp_code}_{bsns_year}_{info['detail']}_{end}", "list.json", params)
        tag = f"({bsns_year}.{info['mm']})"
        hits = [r for r in d.get("list", []) if tag in r["report_nm"] and info["name"][-4:] in r["report_nm"]]
        if not hits:
            raise SourceError(f"{bsns_year}년 {info['name']}를 찾지 못했습니다(12월 결산 법인만 지원).")
        r = sorted(hits, key=lambda x: x["rcept_dt"])[-1]  # last_reprt_at=Y: 정정 반영된 최종본
        r = {**r, "bsns_year": bsns_year, "reprt_code": reprt_code, "url": dart_url(r["rcept_no"])}
        r["is_correction"] = "정" in (r.get("rm") or "") or "[기재정정]" in r["report_nm"]
        return r

    def document(self, rcept_no: str) -> bytes:
        p = self.cache / "documents" / f"{rcept_no}.zip"
        if p.exists():
            return p.read_bytes()
        data = self._get("document.xml", {"rcept_no": rcept_no}, binary=True)
        if not data.startswith(b"PK"):
            raise SourceError(f"원문 ZIP 대신 오류 응답: {data[:200].decode('utf-8', 'replace')}")
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
        return data

    def financials(self, corp_code: str, bsns_year: int, reprt_code: str) -> tuple[list[dict], str]:
        for fs in ("CFS", "OFS"):  # 연결이 없으면 별도로 폴백
            d = self._cached_json(f"fnltt_{corp_code}_{bsns_year}_{reprt_code}_{fs}", "fnlttSinglAcntAll.json",
                                  {"corp_code": corp_code, "bsns_year": str(bsns_year), "reprt_code": reprt_code,
                                   "fs_div": fs})
            if d.get("status") == "000" and d.get("list"):
                return d["list"], fs
        raise SourceError("재무제표 데이터가 없습니다(013). 2015년 이전 사업연도는 제공되지 않습니다.")

    def peers(self, corp_code: str, bsns_year: int, reprt_code: str) -> list[dict]:
        if not self.peers_file or not Path(self.peers_file).exists():
            return []
        codes = [c for c in json.loads(Path(self.peers_file).read_text(encoding="utf-8")) if c != corp_code]
        rows = []
        for k in range(0, len(codes), 100):  # 다중회사 주요계정: 한 번에 최대 100개사
            batch = codes[k:k + 100]
            digest = hashlib.sha1(",".join(batch).encode()).hexdigest()[:10]
            d = self._cached_json(f"multi_{bsns_year}_{reprt_code}_{digest}",
                                  "fnlttMultiAcnt.json",
                                  {"corp_code": ",".join(batch), "bsns_year": str(bsns_year), "reprt_code": reprt_code})
            rows += [r for r in d.get("list", []) if r.get("fs_div", "CFS") == "CFS"]
        return rows

    def lawsuits(self, corp_code: str, bgn: str, end: str) -> list[dict]:
        d = self._cached_json(f"lwstLg_{corp_code}_{bgn}_{end}", "lwstLg.json",
                              {"corp_code": corp_code, "bgn_de": bgn, "end_de": end})
        return d.get("list", [])


def make_source(settings):
    if settings.source == "opendart":
        return OpenDartSource(settings.dart_api_key, settings.cache_dir, settings.peers_file)
    return SampleSource(settings.sample_dir)
