"""시장 화면(docs/CONTRACT.md §9). 조회도 Tool Gateway를 지나 Scope 검사·호출 기록이 같은 길로 남는다."""
from fastapi import APIRouter, Depends, Header, HTTPException

from ..deps import parse_scopes, verify_internal_key
from ..safety.context import set_request_uid
from .companies import _call

router = APIRouter(prefix="/ai/market", tags=["market"])


@router.get("", dependencies=[Depends(verify_internal_key)])
def market(market: str = "ALL", x_user_id: str = Header(default="api"), x_user_scopes: str = Header(default=""),
           x_request_id: str = Header(default="")):
    set_request_uid(x_request_id or None)
    if market.upper() not in ("ALL", "KOSPI", "KOSDAQ", "KONEX"):
        raise HTTPException(status_code=400, detail="market은 ALL·KOSPI·KOSDAQ·KONEX 중 하나")
    return _call("get_market_overview", {"market": market.upper()}, x_user_id, parse_scopes(x_user_scopes))
