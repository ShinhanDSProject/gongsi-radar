"""Agent 정의. 같은 클래스에 프롬프트와 Tool 세트만 다르다. Report Writer는 Tool이 없어 그래프가 직접 부른다."""
from __future__ import annotations

from typing import Dict, Optional

from . import prompts
from .base import SingleAgent

DISCLOSURE_ANALYST = SingleAgent(
    agent_id="disclosure_analyst", system_prompt=prompts.DISCLOSURE_ANALYST_SYSTEM,
    tool_names=["compare_filings", "search_disclosures"],
    description="전년 대비 정기보고서 본문 변경을 정리한다")

FINANCIAL_ANALYST = SingleAgent(
    agent_id="financial_analyst", system_prompt=prompts.FINANCIAL_ANALYST_SYSTEM,
    tool_names=["get_financial_changes", "get_business_metrics", "get_valuation", "get_stock_price"],
    description="계정 증감·회사 서술·사업 지표·시장 지표를 정리한다")

RISK_REVIEWER = SingleAgent(
    agent_id="risk_reviewer",
    # ChatPromptTemplate이 {}를 치환 자리로 읽지 않도록 이중 이스케이프한다
    system_prompt=prompts.RISK_REVIEWER_SYSTEM.replace("{", "{{").replace("}", "}}"),
    tool_names=["get_governance", "get_lawsuits"],
    description="코드 검증 결과와 초안을 검토하고 지배구조·소송 누락을 확인한다")

AGENTS: Dict[str, SingleAgent] = {a.agent_id: a for a in (DISCLOSURE_ANALYST, FINANCIAL_ANALYST, RISK_REVIEWER)}


def get_agent(agent_id: str) -> Optional[SingleAgent]:
    return AGENTS.get(agent_id)
