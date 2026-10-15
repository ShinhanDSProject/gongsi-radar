"""데이터 소스. 샘플(가상 기업)과 OpenDART를 같은 인터페이스로 다룬다.

OpenDartSource는 응답을 디스크에 캐시한다. 원문 ZIP은 접수 후 바뀌지 않으므로 rcept_no 키로 영구 캐시하고,
재무·목록 응답도 같은 요청을 다시 보내지 않도록 캐시한다(일 20,000건 한도 관리).
오류 코드 013(데이터 없음)도 HTTP 200으로 오므로 응답 본문의 status를 항상 검사한다.

공통 인터페이스
  resolve(query) · find_report(corp, year, reprt) · document(rcept_no) · financials(corp, year, reprt) → (rows, fs_div)
  peers(corp, year, reprt) · lawsuits(corp, bgn, end)
  companies() → [{corp_code, corp_name, stock_code, induty}]       회사 목록(상장사만)
  filings(corp) → [{rcept_no, report_nm, rcept_dt, reprt_code, bsns_year, hasDocument}]  정기보고서, 최신순
  governance(corp, year, reprt) → {shareholders, executives, investments, rcept_no}   OpenDART 응답 행 그대로
  market(stock_code) → [getStockPriceInfo item, ...]                시세(최신일 먼저). 키가 없으면 []
OpenDART·공공데이터포털 실제 호출 경로는 응답 모양을 문서대로 맞췄지만 실키로 검증하지 않았다(샘플만 테스트).
"""
from __future__ import annotations

import hashlib
import io
import json
import os
import re
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


_RNM = re.compile(r"\((\d{4})\.(\d{2})\)")


def report_kind(report_nm: str) -> tuple[str | None, int | None]:
    """'반기보고서 (2026.06)' → ('11012', 2026). 정기보고서가 아니면 (None, None)."""
    m = _RNM.search(report_nm or "")
    if not m:
        return None, None
    for code, info in REPRT.items():
        if info["name"] in report_nm and info["mm"] == m.group(2):
            return code, int(m.group(1))
    return None, None


def _filing_row(r: dict, has_doc: bool) -> dict | None:
    code, year = report_kind(r.get("report_nm", ""))
    if not code:
        return None
    return {"rcept_no": r["rcept_no"], "report_nm": r["report_nm"], "rcept_dt": r["rcept_dt"],
            "reprt_code": code, "bsns_year": year, "hasDocument": has_doc}


def _rows(d: dict) -> list[dict]:
    return d.get("list", []) if d.get("status") == "000" else []


def _gov(sh: list[dict], ex: list[dict], inv: list[dict]) -> dict:
    rno = next((r.get("rcept_no") for r in sh + ex + inv if r.get("rcept_no")), None)
    return {"shareholders": sh, "executives": ex, "investments": inv, "rcept_no": rno}


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
        # 피어: 단일회사 전체 재무 파일이 없으면 다중회사 주요계정(피어 파일)의 그 회사 행으로 대신한다
        rows = [r for r in self._json(f"peers_{bsns_year}_{reprt_code}.json").get("list", [])
                if r.get("corp_code") == corp_code]
        if rows:
            return rows, rows[0].get("fs_div", "CFS")
        raise SourceError("재무제표 데이터가 없습니다(013).")

    def peers(self, corp_code: str, bsns_year: int, reprt_code: str) -> list[dict]:
        return self._json(f"peers_{bsns_year}_{reprt_code}.json").get("list", [])

    def lawsuits(self, corp_code: str, bgn: str, end: str) -> list[dict]:
        rows = self._json(f"lwstLg_{corp_code}.json").get("list", [])
        return [r for r in rows if bgn <= r.get("lgd", "").replace("-", "") <= end]

    def companies(self) -> list[dict]:
        corps = json.loads((self.dir / "corp_codes.json").read_text(encoding="utf-8"))
        return [{"corp_code": c["corp_code"], "corp_name": c["corp_name"], "stock_code": c.get("stock_code", ""),
                 "induty": c.get("induty"), "induty_code": c.get("induty_code"), "market": c.get("market")}
                for c in corps if c.get("stock_code")]

    def filings(self, corp_code: str) -> list[dict]:
        out = []
        for r in self._json("list.json")["list"]:
            if r["corp_code"] != corp_code:
                continue
            row = _filing_row(r, (self.dir / "filings" / f"{r['rcept_no']}.zip").exists())
            if row:
                out.append(row)
        return sorted(out, key=lambda x: x["rcept_dt"], reverse=True)

    def governance(self, corp_code: str, bsns_year: int, reprt_code: str) -> dict:
        tail = f"{corp_code}_{bsns_year}_{reprt_code}.json"
        g = _gov(*(_rows(self._json(f"{n}_{tail}")) for n in ("hyslrSttus", "exctvSttus", "otrCprInvstmntSttus")))
        if not (g["shareholders"] or g["executives"] or g["investments"]):
            raise SourceError(f"{bsns_year}년 지배구조 데이터가 없습니다(013).")
        return g

    def market(self, stock_code: str) -> list[dict]:
        p = self.dir / f"market_{stock_code}.json"
        if not p.exists():
            return []
        self.calls += 1
        return DataGoKrMarket.items(json.loads(p.read_text(encoding="utf-8")))

    # ---- 시장 화면 -----------------------------------------------------------------------
    def market_history(self) -> dict[str, list[dict]]:
        """종목코드 → 일별 시세(getStockPriceInfo 행). 샘플은 회사별 파일을 모두 읽는다."""
        return {c["stock_code"]: rows for c in self.companies() if (rows := self.market(c["stock_code"]))}

    def index_series(self, name: str) -> list[dict]:
        """공식 지수(코스피·코스닥) 일별 종가. 샘플에는 없다 → 시장 화면이 대체 지수를 만든다."""
        return []

    def recent_filings(self, days: int = 90) -> list[dict]:
        out = []
        for r in self._json("list.json")["list"]:
            row = _filing_row(r, (self.dir / "filings" / f"{r['rcept_no']}.zip").exists())
            if row:
                out.append({**r, **row})
        return sorted(out, key=lambda x: (x["rcept_dt"], x["rcept_no"]), reverse=True)

    def induty_code(self, corp_code: str) -> str | None:
        return next((c.get("induty_code") for c in self.companies() if c["corp_code"] == corp_code), None)


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
    def _corps(self) -> list[dict]:
        p = self.cache / "corp_codes.json"
        if not p.exists():
            raw = self._get("corpCode.xml", {}, binary=True)
            z = zipfile.ZipFile(io.BytesIO(raw))
            root = ET.fromstring(z.read(z.namelist()[0]))
            corps = [{"corp_code": (e.findtext("corp_code") or "").strip(),  # 문자열 유지(앞자리 0)
                      "corp_name": (e.findtext("corp_name") or "").strip(),
                      "stock_code": (e.findtext("stock_code") or "").strip()} for e in root.iter("list")]
            p.write_text(json.dumps(corps, ensure_ascii=False), encoding="utf-8")
        return json.loads(p.read_text(encoding="utf-8"))

    def resolve(self, query: str) -> dict:
        corps = self._corps()
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

    def companies(self) -> list[dict]:
        # corpCode.xml에는 업종이 없다(induty None). 업종은 company.json을 회사별로 불러야 해서 목록에서는 생략
        return [{"corp_code": c["corp_code"], "corp_name": c["corp_name"], "stock_code": c["stock_code"], "induty": None}
                for c in self._corps() if c.get("stock_code")]

    def filings(self, corp_code: str) -> list[dict]:
        today = date.today()
        end = today.strftime("%Y%m%d")
        d = self._cached_json(f"list_{corp_code}_A_{end}", "list.json",
                              {"corp_code": corp_code, "bgn_de": f"{today.year - 3}0101", "end_de": end,
                               "last_reprt_at": "Y", "pblntf_ty": "A", "page_count": 100})
        out = [row for r in d.get("list", []) if (row := _filing_row(r, True))]  # 원문은 document.xml로 받을 수 있음
        return sorted(out, key=lambda x: x["rcept_dt"], reverse=True)

    def governance(self, corp_code: str, bsns_year: int, reprt_code: str) -> dict:
        params = {"corp_code": corp_code, "bsns_year": str(bsns_year), "reprt_code": reprt_code}
        parts = [_rows(self._cached_json(f"{ep}_{corp_code}_{bsns_year}_{reprt_code}", f"{ep}.json", params))
                 for ep in ("hyslrSttus", "exctvSttus", "otrCprInvstmntSttus")]
        g = _gov(*parts)
        if not (g["shareholders"] or g["executives"] or g["investments"]):
            raise SourceError(f"{bsns_year}년 지배구조 데이터가 없습니다(013).")
        return g

    def market(self, stock_code: str) -> list[dict]:
        return DataGoKrMarket(os.getenv("DATA_GO_KR_API_KEY"), self.cache.parent, self.http).prices(stock_code)

    # ---- 시장 화면(실키로 검증하지 않음) -----------------------------------------------------
    def market_history(self) -> dict[str, list[dict]]:
        """전 종목 시세를 날짜별로 받아 종목코드 → 행 목록으로 바꾼다.

        종목별로 부르면 2,500번이 넘는다. getStockPriceInfo는 basDt 하나로 전 종목을 돌려주므로 날짜별로 부르고,
        지난 날짜는 바뀌지 않으니 영구 캐시한다. 1년을 매일 받으면 첫 계산에 250번이라, 최근 한 달은 매일·그 이전은 주 1회만 받는다.
        """
        mk = DataGoKrMarket(os.getenv("DATA_GO_KR_API_KEY"), self.cache.parent, self.http)
        if not mk.key:
            return {}
        today = date.today()
        wanted = []
        for back in range(0, 372):
            d = date.fromordinal(today.toordinal() - back)
            if d.weekday() < 5 and (back <= 35 or d.weekday() == 4):     # 최근 5주는 매일, 그 이전은 금요일
                wanted.append(d.strftime("%Y%m%d"))
        out: dict[str, list[dict]] = {}
        for bas in wanted:
            for it in mk.by_date(bas):
                out.setdefault(it.get("srtnCd", ""), []).append(it)
        return out

    def index_series(self, name: str) -> list[dict]:
        return DataGoKrIndex(os.getenv("DATA_GO_KR_API_KEY"), self.cache.parent, self.http).series(name)

    def recent_filings(self, days: int = 30) -> list[dict]:
        """최근 정기공시(사업·반기·분기). corp_code 없이 부르면 기간이 3개월 이내여야 한다."""
        today = date.today()
        bgn = date.fromordinal(today.toordinal() - min(days, 89)).strftime("%Y%m%d")
        end = today.strftime("%Y%m%d")
        d = self._cached_json(f"recent_A_{bgn}_{end}", "list.json",
                              {"bgn_de": bgn, "end_de": end, "pblntf_ty": "A", "page_count": 100})
        out = [{**r, **row} for r in d.get("list", []) if (row := _filing_row(r, True))]
        return sorted(out, key=lambda x: (x["rcept_dt"], x["rcept_no"]), reverse=True)

    def induty_code(self, corp_code: str) -> str | None:
        """기업개황(company.json)의 업종 코드(KSIC). 회사마다 한 번 부르고 캐시한다."""
        try:
            d = self._cached_json(f"company_{corp_code}", "company.json", {"corp_code": corp_code})
        except SourceError:
            return None
        return (d.get("induty_code") or None) if d.get("status") == "000" else None


class DataGoKrMarket:
    """공공데이터포털 금융위원회_주식시세정보(getStockPriceInfo). 영업일 다음 날 오후에 전일 시세가 올라온다.

    serviceKey는 '디코딩' 키를 넣는다(requests가 인코딩). 키가 없으면 빈 목록 → 시장 지표는 '계산 안 함'.
    """
    URL = "https://apis.data.go.kr/1160100/service/GetStockSecuritiesInfoService/getStockPriceInfo"

    def __init__(self, api_key: str | None, cache_dir: Path, session=None):
        self.key = api_key
        self.cache = Path(cache_dir) / "datagokr"
        self.http = session or requests.Session()

    @staticmethod
    def items(d: dict) -> list[dict]:
        body = (d.get("response") or {}).get("body") or {}
        item = (body.get("items") or {}).get("item") or []
        return [item] if isinstance(item, dict) else list(item)  # 한 건이면 dict로 온다

    def prices(self, stock_code: str, days: int = 120) -> list[dict]:
        if not self.key or not stock_code:
            return []
        today = date.today()
        p = self.cache / f"price_{stock_code}_{today:%Y%m%d}.json"
        if p.exists():
            return self._only(json.loads(p.read_text(encoding="utf-8")), stock_code)
        begin = date.fromordinal(today.toordinal() - int(days * 1.5)).strftime("%Y%m%d")
        params = {"serviceKey": self.key, "resultType": "json", "numOfRows": days, "pageNo": 1,
                  "likeSrtnCd": stock_code, "beginBasDt": begin}
        try:
            r = self.http.get(self.URL, params=params, timeout=30)
            r.raise_for_status()
            d = r.json()
        except (requests.RequestException, ValueError) as e:
            raise SourceError(f"공공데이터포털 시세 호출 실패: {e}") from e
        code = ((d.get("response") or {}).get("header") or {}).get("resultCode")
        if code != "00":
            raise SourceError(f"공공데이터포털 시세 오류 {code}")
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
        return self._only(d, stock_code)

    def by_date(self, bas_dt: str) -> list[dict]:
        """그 날짜의 전 종목 시세. 휴장일이면 빈 목록. 지난 날짜는 바뀌지 않아 영구 캐시한다."""
        p = self.cache / f"all_{bas_dt}.json"
        if p.exists():
            return self.items(json.loads(p.read_text(encoding="utf-8")))
        params = {"serviceKey": self.key, "resultType": "json", "numOfRows": 5000, "pageNo": 1, "basDt": bas_dt}
        try:
            r = self.http.get(self.URL, params=params, timeout=60)
            r.raise_for_status()
            d = r.json()
        except (requests.RequestException, ValueError) as e:
            raise SourceError(f"공공데이터포털 시세 호출 실패: {e}") from e
        if ((d.get("response") or {}).get("header") or {}).get("resultCode") != "00":
            raise SourceError("공공데이터포털 시세 오류")
        if bas_dt < date.today().strftime("%Y%m%d"):
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
        return self.items(d)

    @classmethod
    def _only(cls, d: dict, stock_code: str) -> list[dict]:
        # likeSrtnCd는 부분 일치라 정확히 같은 종목만 남긴다
        return sorted([i for i in cls.items(d) if i.get("srtnCd") == stock_code], key=lambda i: i["basDt"], reverse=True)


class DataGoKrIndex:
    """공공데이터포털 금융위원회_지수시세정보(getStockMarketIndex). idxNm=코스피·코스닥, 최대 5년치. 실키로 검증하지 않음."""
    URL = "https://apis.data.go.kr/1160100/service/GetMarketIndexInfoService/getStockMarketIndex"

    def __init__(self, api_key: str | None, cache_dir: Path, session=None):
        self.key = api_key
        self.cache = Path(cache_dir) / "datagokr"
        self.http = session or requests.Session()

    def series(self, name: str, years: int = 5) -> list[dict]:
        if not self.key:
            return []
        today = date.today()
        p = self.cache / f"index_{name}_{today:%Y%m%d}.json"
        if p.exists():
            return json.loads(p.read_text(encoding="utf-8"))
        begin = date(today.year - years, today.month, min(today.day, 28)).strftime("%Y%m%d")
        params = {"serviceKey": self.key, "resultType": "json", "numOfRows": 2000, "pageNo": 1, "idxNm": name,
                  "beginBasDt": begin}
        try:
            r = self.http.get(self.URL, params=params, timeout=60)
            r.raise_for_status()
            d = r.json()
        except (requests.RequestException, ValueError) as e:
            raise SourceError(f"공공데이터포털 지수 호출 실패: {e}") from e
        rows = [i for i in DataGoKrMarket.items(d) if i.get("idxNm") == name]
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
        return rows


def make_source(settings):
    if settings.source == "opendart":
        return OpenDartSource(settings.dart_api_key, settings.cache_dir, settings.peers_file)
    return SampleSource(settings.sample_dir)
