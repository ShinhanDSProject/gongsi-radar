"""Output Filter — 리포트가 사용자에게 나가기 직전 마지막 한 지점.

규칙은 tools/compliance.py와 같다. 차이는 쓰이는 자리다.
  compliance: Risk Reviewer(Agent)가 초안 검토 중에 부른다 → 지적 목록·반려 여부
  Output Filter: 파이프라인이 무조건 부른다 → 차단·마스킹·재작성 판정
Agent가 검토를 건너뛰거나 지적을 무시해도 이쪽은 돈다. 프롬프트는 지시이지 보장이 아니다.

공시레이더 리포트는 서술 덩어리가 여러 개다(Report Writer 본문, 변경 문단 요약, 관련 서술 문장).
radar 파이프라인이 요약·문장을 이미 금지 표현 필터→재작성→재검증으로 통과시켰지만, 여기서 전부 다시 본다.
"""
from __future__ import annotations

import copy
import re
from typing import Any, Dict, List, Tuple

from ..schemas.guardrail import GuardrailResult
from ..tools.compliance import check_compliance_rules
from .moderation import get_moderation_checker

DISCLAIMER = ("이 리포트는 생성형 AI가 공시 원문을 비교해 만든 초안이며, 사람 검토를 거쳐 공유됩니다. "
              "투자 판단이나 매매 권유가 아닙니다. 출처: DART")

_ACTION = {"GUARANTEE": "BLOCK", "RECOMMEND": "BLOCK", "CERTAIN": "REWRITE", "NO_SOURCE": "WARN"}

# 내부 등급은 차단이 아니라 마스킹이다. 문장 전체를 버리면 나머지 분석까지 날아간다
_GRADE_RE = re.compile(r"(내부\s*등급|신용\s*등급|리스크\s*등급)\s*:?\s*[0-9A-Fa-f]{1,2}\s*등급?")
_GRADE_MASK = "[GRADE_MASKED]"
BLOCKED_BODY = "규정 검사에서 걸러진 내용이 있어 이 서술을 표시할 수 없습니다. 담당자에게 문의해 주세요."


def mask_internal_grade(text: str) -> Tuple[str, List[str]]:
    if not _GRADE_RE.search(text):
        return text, []
    return _GRADE_RE.sub(_GRADE_MASK, text), ["INTERNAL_GRADE"]


def check_output(text: str, citation_count: int = 0) -> GuardrailResult:
    """출력 한 건을 판정한다. BLOCK이 하나라도 있으면 통째로 막는다 — 문장만 지우면 맥락이 어긋난다."""
    masked, issues = mask_internal_grade(text or "")
    rule = check_compliance_rules(masked, citation_count=citation_count)
    codes = [i["code"] for i in rule["issues"]]
    issues.extend(codes)
    actions = {_ACTION.get(c, "WARN") for c in codes}
    should_block = "BLOCK" in actions
    risk = "BLOCKED" if should_block else ("WARNING" if issues else "SAFE")
    moderation = get_moderation_checker().check(masked)
    if moderation and moderation.get("flagged"):
        issues.append("MODERATION_FLAGGED")
        risk, should_block = "BLOCKED", True
    return GuardrailResult(isSafe=(risk == "SAFE"), riskLevel=risk, detectedIssues=issues, filteredText=masked,
                           shouldBlock=should_block, shouldRewrite="REWRITE" in actions, moderation=moderation)


def filter_report(report: Dict[str, Any]) -> Tuple[Dict[str, Any], GuardrailResult]:
    """리포트의 모든 서술을 걸러 (거른 리포트, 종합 판정)을 돌려준다.

    본문(body)은 인용 개수를 함께 보고, 항목 서술(요약·관련 서술)은 각자 인용이 붙어 있으므로 NO_SOURCE를 보지 않는다.
    차단된 서술은 안내 문구로 바꾸되 무엇이 걸렸는지는 화면에 상세히 쓰지 않는다 — 그 목록이 우회 힌트가 된다.
    """
    out = copy.deepcopy(report)
    citations = len(out.get("citations") or [])
    body_result = check_output(out.get("body") or "", citation_count=citations)
    issues = list(body_result.detectedIssues)
    blocked_items: List[str] = []
    out["body"] = BLOCKED_BODY if body_result.shouldBlock else body_result.filteredText

    for item in out.get("changes") or []:
        if "지시문 의심" in (item.get("flags") or []):   # 원문 지시문은 이미 요약하지 않았다
            continue
        r = check_output(item.get("summary") or "", citation_count=1)
        if r.shouldBlock:
            item["summary"] = BLOCKED_BODY
            blocked_items.append(item.get("id", ""))
            issues += r.detectedIssues
    for item in out.get("relations") or []:
        r = check_output(item.get("statement") or "", citation_count=1)
        if r.shouldBlock:
            item["statement"] = BLOCKED_BODY
            blocked_items.append(item.get("account_key", ""))
            issues += r.detectedIssues

    should_block = body_result.shouldBlock or bool(blocked_items)
    risk = "BLOCKED" if should_block else ("WARNING" if issues else "SAFE")
    out["blocked"] = should_block
    out["guardrail"] = {"riskLevel": risk, "detectedIssues": issues, "blockedItems": blocked_items,
                        "shouldRewrite": body_result.shouldRewrite}
    meta = out.setdefault("meta", {})
    if not meta.get("disclaimer"):           # 통제는 앞단이 해 줬을 거라고 믿지 않는다
        meta["disclaimer"] = DISCLAIMER
    total = GuardrailResult(isSafe=(risk == "SAFE"), riskLevel=risk, detectedIssues=issues,
                            filteredText=out["body"], shouldBlock=should_block,
                            shouldRewrite=body_result.shouldRewrite)
    return out, total
