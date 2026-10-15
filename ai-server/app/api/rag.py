import logging

from fastapi import APIRouter, Depends, HTTPException, status

from ..deps import require_user_id, verify_internal_key
from ..rag.service import get_rag_service
from ..schemas.rag import RagSearchHit, RagSearchRequest, RagSearchResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/ai/rag", tags=["rag"])


@router.post("/search", response_model=RagSearchResponse, dependencies=[Depends(verify_internal_key)])
def search(req: RagSearchRequest, user_id: str = Depends(require_user_id)) -> RagSearchResponse:
    try:
        hits = get_rag_service().search(req.query, req.scope, top_k=req.topK, min_score=req.minScore,
                                        trust_levels=req.trustLevels, corp_code=req.corpCode, rcept_no=req.rceptNo)
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    logger.info("rag_search user=%s query_len=%d hits=%d", user_id, len(req.query), len(hits))
    items = [RagSearchHit(chunkId=h.chunk_id, docId=h.doc_id, title=h.title, source=h.source,
                          publishedAt=h.published_at, content=h.content, score=h.score, trustLevel=h.trust_level,
                          sectionPath=h.section_path) for h in hits]
    return RagSearchResponse(items=items, total=len(items))
