"""기업 목록·상세. 데이터 조회도 Tool Gateway를 지나게 해 Scope 검사와 호출 기록이 같은 길로 남게 한다.
시장 지표는 MARKET_DATA_READ가 있을 때만 따로 붙인다(공시 조회 권한만으로는 시세를 볼 수 없다).
"""
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, Header, HTTPException

from ..deps import parse_scopes, verify_internal_key
from ..safety import rate_limit
from ..safety.context import set_request_uid
from ..tools.gateway import KillSwitchActive, gateway

router = APIRouter(prefix="/ai/companies", tags=["companies"])


def _call(name: str, params: Dict[str, Any], user_id: str, scopes: List[str]):
    try:
        return gateway.invoke(name, params, agent_id="api", user_id=user_id, scope=scopes)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except KillSwitchActive as e:
        raise HTTPException(status_code=503, detail={"error": "KILL_SWITCH_ACTIVE", "reason": str(e)})
    except rate_limit.RateLimitExceeded as e:
        raise HTTPException(status_code=429, detail={"error": "RATE_LIMIT_EXCEEDED", "message": str(e)})


@router.get("", dependencies=[Depends(verify_internal_key)])
def list_companies(q: str = "", limit: int = 50, x_user_id: str = Header(default="api"),
                   x_user_scopes: str = Header(default=""), x_request_id: str = Header(default="")):
    set_request_uid(x_request_id or None)
    return _call("search_companies", {"query": q, "limit": limit}, x_user_id, parse_scopes(x_user_scopes))


@router.get("/{corp_code}", dependencies=[Depends(verify_internal_key)])
def company(corp_code: str, x_user_id: str = Header(default="api"), x_user_scopes: str = Header(default=""),
            x_request_id: str = Header(default="")):
    set_request_uid(x_request_id or None)
    scopes = parse_scopes(x_user_scopes)
    try:
        prof = _call("get_company_profile", {"corp_code": corp_code}, x_user_id, scopes)
    except HTTPException:
        raise
    except Exception as e:               # 없는 회사 등 소스 오류
        raise HTTPException(status_code=404, detail=f"{type(e).__name__}: {e}")
    if "MARKET_DATA_READ" in scopes:
        try:
            prof["valuation"] = _call("get_valuation", {"company": corp_code}, x_user_id, scopes)
        except HTTPException:
            raise
        except Exception as e:
            prof["valuation"], prof["valuationNote"] = None, f"시장 지표를 계산하지 못했습니다: {e}"
    else:
        prof["valuation"], prof["valuationNote"] = None, "MARKET_DATA_READ 권한이 없어 시장 지표를 표시하지 않습니다."
    return prof
