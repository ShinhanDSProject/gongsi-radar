"""용어집 정의 초안(#14). Spring `/api/glossary/{id}/ai-draft`가 부른다.

LLM은 초안만 쓴다. 게시는 사람이 검토·승인해야 하고(Spring 쪽 흐름), 여기서는 두 번 거른다.
  ① 입력 필터 — 표제어·별칭·맥락에 PII나 주입 문구가 있으면 LLM에 닿기 전에 막는다
  ② 출력 필터 — 만든 정의에 투자 권유·가치판단이 섞이면 돌려주지 않는다

LLM_PROVIDER=mock이면 정의를 지어내지 않는다. 직접 쓰라는 안내와 mock=true를 돌려준다.

  422 GUARDRAIL_BLOCKED · 503 KILL_SWITCH_ACTIVE · 502 LLM_PROVIDER_ERROR
"""
import json
import logging
import re
from typing import List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field

from ..agents import prompts
from ..config import settings
from ..deps import verify_internal_key
from ..llm.call_log import LLMCallLogger
from ..llm.factory import active_model_name, get_llm_client
from ..safety import kill_switch
from ..safety.audit import record_guardrail
from ..safety.context import set_request_uid
from ..safety.input_filter import check_input
from ..safety.output_filter import check_output

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/ai/glossary", tags=["glossary"])

MOCK_NOTE = "LLM_PROVIDER=mock 상태라 정의를 만들지 않았습니다. 직접 작성해 주세요."


class GlossaryDraftRequest(BaseModel):
    term: str = Field(min_length=1, max_length=100)
    aliases: List[str] = Field(default_factory=list)
    context: Optional[str] = Field(default=None, max_length=500)   # 이미 적어 둔 정의·쓰임새(있으면 다듬는다)
    userId: str = "api"


class GlossaryDraft(BaseModel):
    definition: str
    usageNote: Optional[str] = None
    mock: bool = False
    model: str


def _parse(text: str) -> tuple[str, Optional[str]]:
    """모델이 JSON을 지키면 그대로, 아니면 본문 전체를 정의로 쓴다."""
    m = re.search(r"\{.*\}", text, re.S)
    if m:
        try:
            obj = json.loads(m.group(0))
            d = str(obj.get("definition") or "").strip()
            if d:
                u = str(obj.get("usageNote") or "").strip() or None
                return d, u
        except (ValueError, AttributeError):
            pass
    return text.strip(), None


@router.post("/draft", response_model=GlossaryDraft, dependencies=[Depends(verify_internal_key)])
async def draft(req: GlossaryDraftRequest, x_request_id: str = Header(default="")) -> GlossaryDraft:
    set_request_uid(x_request_id or None)
    active, reason = kill_switch.status()
    if active:
        raise HTTPException(status_code=503, detail={"error": "KILL_SWITCH_ACTIVE", "reason": reason})

    text = " ".join([req.term, *req.aliases, req.context or ""]).strip()
    guard = check_input(text)
    record_guardrail("INPUT", guard, text, user_id=req.userId)
    if guard.shouldBlock:
        raise HTTPException(status_code=422, detail={"error": "GUARDRAIL_BLOCKED", "detectedIssues": guard.detectedIssues})

    provider = settings.llm_provider.lower()
    if provider == "mock":
        return GlossaryDraft(definition=f"[mock] {MOCK_NOTE}", mock=True, model=active_model_name())

    user = (f"표제어: {req.term}\n같은 말: {', '.join(req.aliases) or '없음'}\n"
            f"지금 적힌 내용: {check_input(req.context).filteredText if req.context else '없음'}")
    try:
        out = await get_llm_client().chat(
            [{"role": "system", "content": prompts.GLOSSARY_SYSTEM}, {"role": "user", "content": user}],
            config={"callbacks": [LLMCallLogger(provider=provider, model=active_model_name(), agent_id="glossary")]})
    except Exception as e:
        logger.warning("용어 정의 초안 실패: %s", e)
        raise HTTPException(status_code=502, detail={"error": "LLM_PROVIDER_ERROR", "message": str(e)[:200]})

    definition, usage = _parse(out)
    checked = check_output(" ".join(x for x in (definition, usage) if x))
    record_guardrail("OUTPUT", checked, definition, user_id=req.userId)
    if checked.shouldBlock:
        raise HTTPException(status_code=422, detail={"error": "GUARDRAIL_BLOCKED", "detectedIssues": checked.detectedIssues})
    return GlossaryDraft(definition=definition[:2000], usageNote=(usage or None) and usage[:500],
                         model=active_model_name())
