"""가드레일 검사 엔드포인트.

파이프라인이 알아서 부르는데 왜 API로도 여는가. 두 가지 때문이다.
① Spring Boot가 Agent를 태우기 전에 미리 걸러 볼 수 있다 (요청 접수 화면에서 즉시 안내)
② Red Team 프롬프트 셋을 한 번에 던져 볼 창구가 필요하다
"""
from fastapi import APIRouter, Depends, Header

from ..deps import verify_internal_key
from ..safety.audit import record_guardrail
from ..safety.context import set_request_uid
from ..safety.input_filter import check_input
from ..safety.output_filter import check_output
from ..schemas.guardrail import GuardrailCheckRequest, GuardrailResult

router = APIRouter(prefix="/ai/guardrails", tags=["guardrails"])


@router.post("/input-check", response_model=GuardrailResult,
             dependencies=[Depends(verify_internal_key)])
def input_check(req: GuardrailCheckRequest,
                x_request_id: str = Header(default="")) -> GuardrailResult:
    set_request_uid(x_request_id or None)
    result = check_input(req.text)
    record_guardrail("INPUT", result, req.text, user_id=req.userId)
    return result


@router.post("/output-check", response_model=GuardrailResult,
             dependencies=[Depends(verify_internal_key)])
def output_check(req: GuardrailCheckRequest,
                 x_request_id: str = Header(default="")) -> GuardrailResult:
    set_request_uid(x_request_id or None)
    result = check_output(req.text)
    record_guardrail("OUTPUT", result, req.text, user_id=req.userId)
    return result
