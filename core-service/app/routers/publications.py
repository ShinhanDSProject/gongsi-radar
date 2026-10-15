"""발행 원장. 조회만 Read 키로 열려 있고 접수·승인·반려는 System 키를 받는다.

같은 자원(발행)인데 Read와 Write의 통제 수준이 다르다. AI 서버는 이력을 볼 수는 있어도
발행을 만들거나 승인할 수는 없다."""
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response, status

from ..db import get_engine
from ..deps import require_internal_key, require_system_key
from ..publication_service import approve as approve_publication
from ..publication_service import create_publication, get_publication, list_publications
from ..publication_service import reject as reject_publication
from ..schemas import (ApproveIn, PublicationCreate, PublicationListOut,
                       PublicationOut, PublicationStatus, RejectIn)

router = APIRouter(prefix="/core/publications", tags=["publications"])


@router.get("", response_model=PublicationListOut,
            dependencies=[Depends(require_internal_key)])
def read_publications(corp_code: Optional[str] = None,
                      pub_status: Optional[PublicationStatus] = Query(default=None, alias="status"),
                      page: int = Query(default=0, ge=0),
                      size: int = Query(default=20, ge=1, le=100)) -> PublicationListOut:
    with get_engine().begin() as conn:          # 만료 처리가 있어 쓰기 트랜잭션이다
        items, total = list_publications(conn, corp_code, pub_status, page, size)
    return PublicationListOut(items=items, total=total, page=page, size=size)


@router.get("/{publication_id}", response_model=PublicationOut,
            dependencies=[Depends(require_internal_key)])
def read_publication(publication_id: str) -> PublicationOut:
    with get_engine().begin() as conn:
        return get_publication(conn, publication_id)


@router.post("", response_model=PublicationOut, status_code=status.HTTP_201_CREATED,
             dependencies=[Depends(require_system_key)])
def submit_publication(req: PublicationCreate, response: Response,
                       idempotency_key: str = Header(alias="X-Idempotency-Key")) -> PublicationOut:
    if not idempotency_key.strip():
        raise HTTPException(status_code=400, detail="X-Idempotency-Key is required")

    with get_engine().begin() as conn:
        publication, duplicate = create_publication(conn, req, idempotency_key)

    # 같은 키로 다시 들어온 요청은 새로 만든 게 아니므로 201이 아니라 200이다
    if duplicate:
        response.status_code = status.HTTP_200_OK
    return publication


@router.post("/{publication_id}/approve", response_model=PublicationOut,
             dependencies=[Depends(require_system_key)])
def approve(publication_id: str, req: ApproveIn) -> PublicationOut:
    with get_engine().begin() as conn:
        return approve_publication(conn, publication_id, req.decidedBy, req.contentHash)


@router.post("/{publication_id}/reject", response_model=PublicationOut,
             dependencies=[Depends(require_system_key)])
def reject(publication_id: str, req: RejectIn) -> PublicationOut:
    with get_engine().begin() as conn:
        return reject_publication(conn, publication_id, req.decidedBy, req.reason)
