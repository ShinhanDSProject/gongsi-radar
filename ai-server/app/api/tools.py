"""개발/디버깅용 Tool 직접 호출 엔드포인트.
운영에서는 Agent를 통해서만 호출된다.
"""
from typing import Any, Dict, List
from fastapi import APIRouter, Depends, HTTPException, Header

from ..deps import verify_internal_key
from ..safety import rate_limit
from ..tools.gateway import KillSwitchActive, gateway
from ..safety.context import set_request_uid

router = APIRouter(prefix="/ai/tools", tags=["tools"])


@router.get("", dependencies=[Depends(verify_internal_key)])
def list_tools(x_user_scopes: str = Header(default="")) -> List[Dict[str, Any]]:
    scopes = [s.strip() for s in x_user_scopes.split(",") if s.strip()]
    return [
        {"name": t.name, "description": t.description, "scopes": t.required_scopes}
        for t in gateway.list_tools(scopes)
    ]


@router.post("/{tool_name}/invoke", dependencies=[Depends(verify_internal_key)])
def invoke_tool(
    tool_name: str,
    payload: Dict[str, Any],
    x_user_id: str = Header(...),
    x_user_scopes: str = Header(default=""),
    x_agent_id: str = Header(default="debug-agent"),
    x_request_id: str = Header(default=""),):
    set_request_uid(x_request_id or None)
    scopes = [s.strip() for s in x_user_scopes.split(",") if s.strip()]
    try:
        result = gateway.invoke(
            tool_name=tool_name, params=payload,
            agent_id=x_agent_id, user_id=x_user_id, scope=scopes,
        )
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Tool {tool_name} not found")
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except KillSwitchActive as e:
        raise HTTPException(status_code=503,
                            detail={"error": "KILL_SWITCH_ACTIVE", "reason": str(e)})
    except rate_limit.RateLimitExceeded as e:
        raise HTTPException(status_code=429,
                            detail={"error": "RATE_LIMIT_EXCEEDED", "message": str(e)})
    return {"result": result}


@router.get("/calls/recent", dependencies=[Depends(verify_internal_key)])
def recent_calls() -> List[Dict[str, Any]]:
    return [r.__dict__ for r in gateway.recent_calls()]