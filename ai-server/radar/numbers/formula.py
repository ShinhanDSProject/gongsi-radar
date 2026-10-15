"""계산식·출처(Formula·Source). 화면의 숫자마다 '계산식·출처 펼치기'에 쓰는 구조를 만든다.

원칙
  - 값이 없으면 0으로 바꾸지 않는다: result None + status "계산 안 함" + reason
  - 입력값마다 어디서 왔는지(재무 API 필드, 원문 표 pid, 시세 기준일)를 남긴다
  - 여기서 만드는 문구에도 판단 표현은 넣지 않는다(verify.banned_hits로 검사)
필드 이름은 docs/CONTRACT.md §6.2(camelCase)를 따른다.
"""
from __future__ import annotations

from radar.sources.base import dart_url

DONE, SKIP = "계산됨", "계산 안 함"


def src(kind: str, label: str, rcept_no: str | None = None, pid: str | None = None, field: str | None = None,
        url: str | None = None) -> dict:
    """Source. kind: 재무 API | 원문 표 | 원문 문단 | 시세 | 계산 | 업종 피어"""
    out = {"kind": kind, "label": label}
    if rcept_no:
        out["rceptNo"] = rcept_no
        out["url"] = url or dart_url(rcept_no)
    elif url:
        out["url"] = url
    if pid:
        out["pid"] = pid
    if field:
        out["field"] = field
    return out


FIELD_LABEL = {
    "thstrm_amount": "당기", "frmtrm_amount": "전기", "bfefrmtrm_amount": "전전기",
    "thstrm_add_amount": "당기 누적", "frmtrm_add_amount": "전기 누적", "frmtrm_q_amount": "전기 같은 분기",
}


def fin_source(row: dict | None, field: str, label: str | None = None, fs_div: str | None = None) -> dict | None:
    """재무 API 한 행·한 필드의 출처. row가 없으면 None."""
    if not row:
        return None
    nm = row.get("account_nm", "")
    period = FIELD_LABEL.get(field, field)
    year = row.get("bsns_year")
    head = f"{year}년 보고서 · {nm}" if year else nm
    lab = label or f"{head} {period}" + (f" ({fs_div})" if fs_div else "")
    return src("재무 API", lab, rcept_no=row.get("rcept_no") or None, field=field)


def inp(name: str, value: float | int | None, unit: str, source: dict | None = None, note: str | None = None) -> dict:
    """FormulaInput."""
    out = {"name": name, "value": value, "unit": unit}
    if source:
        out["source"] = source
    if note:
        out["note"] = note
    return out


def formula(fid: str, label: str, expr: str, inputs: list[dict], result: float | int | None, unit: str,
            reason: str | None = None, notes: list[str] | None = None, digits: int | None = None) -> dict:
    """Formula. result가 None이면 '계산 안 함'이고 reason이 반드시 붙는다."""
    if result is not None and digits is not None:
        result = round(result, digits)
    out = {"id": fid, "label": label, "expr": expr, "inputs": inputs, "result": result, "unit": unit,
           "status": DONE if result is not None else SKIP, "notes": list(notes or [])}
    if result is None:
        missing = [i["name"] for i in inputs if i.get("value") is None]
        out["reason"] = reason or (f"입력값 없음: {', '.join(missing)}" if missing else "계산 조건을 충족하지 않음")
    elif reason:
        out["reason"] = reason
    return out


def missing(inputs: list[dict]) -> list[str]:
    return [i["name"] for i in inputs if i.get("value") is None]


def ratio(a: float | None, b: float | None) -> float | None:
    """a ÷ b. 둘 중 하나라도 없거나 b가 0이면 None(0으로 바꾸지 않음)."""
    if a is None or b is None or b == 0:
        return None
    return a / b


def texts(obj) -> list[str]:
    """중첩 dict·list 안의 문자열을 모두 모은다(출력 필터 검사용)."""
    out = []
    if isinstance(obj, str):
        out.append(obj)
    elif isinstance(obj, dict):
        for v in obj.values():
            out += texts(v)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            out += texts(v)
    return out
