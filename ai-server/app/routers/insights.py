"""기업 상세의 원문 파생 정보(docs/CONTRACT.md §11.1). Spring `/api/companies/{corpCode}`가 business·governance 칸을 채우려고 부른다.

조회도 Tool Gateway(`get_document_insights`, DISCLOSURE_READ)를 지나 Scope 검사·호출 기록이 분석 Tool과 같은 길로 남는다.
기업 목록·재무 표·시장 지표·공시 목록은 Spring이 Java로 계산한다 — 이 서버에는 그 API가 없다.

  404 — 회사를 찾지 못함(데이터 서비스 404 포함)
  502 — 데이터 서비스(Spring 내부 데이터 API)에 닿지 못함. '데이터 없음'과 구분해 부른 쪽이 캐시하지 않게 한다
"""
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, Header, HTTPException

from radar.service_source import SourceUnavailable
from radar.sources import SourceError

from ..deps import parse_scopes, verify_internal_key
from ..safety import rate_limit
from ..safety.context import set_request_uid
from ..tools.gateway import KillSwitchActive, gateway

router = APIRouter(prefix="/ai/insights", tags=["insights"])


def _call(name: str, params: Dict[str, Any], user_id: str, scopes: List[str]):
    try:
        return gateway.invoke(name, params, agent_id="api", user_id=user_id, scope=scopes)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except KillSwitchActive as e:
        raise HTTPException(status_code=503, detail={"error": "KILL_SWITCH_ACTIVE", "reason": str(e)})
    except rate_limit.RateLimitExceeded as e:
        raise HTTPException(status_code=429, detail={"error": "RATE_LIMIT_EXCEEDED", "message": str(e)})
    except SourceUnavailable as e:
        raise HTTPException(status_code=502, detail=f"데이터 서비스 오류: {e}")
    except SourceError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/{corp_code}", dependencies=[Depends(verify_internal_key)])
def insights(corp_code: str, x_user_id: str = Header(default="api"), x_user_scopes: str = Header(default=""),
             x_request_id: str = Header(default="")) -> Dict[str, Any]:
    """{business: Business|null, governance: Governance|null, notes: string[]}"""
    set_request_uid(x_request_id or None)
    return _call("get_document_insights", {"corp_code": corp_code}, x_user_id, parse_scopes(x_user_scopes))
