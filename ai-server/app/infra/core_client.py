"""Core Zone(리포트 발행 원장) 조회 클라이언트.

**조회 메서드만 둔다.** 발행 요청·승인 메서드는 아예 만들지 않고, 시스템 키도 이 서버에 없다.
있으면 언젠가 불린다 — AI는 발행 원장에 쓸 수 없다는 것을 코드와 자격 증명 두 겹으로 보장한다.
"""
from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

import httpx

from ..config import settings
from ..safety.context import get_caller_user_id, get_request_uid

logger = logging.getLogger(__name__)


class CoreReadClient:
    def __init__(self, base_url: str, api_key: str, max_retries: int = 1, timeout: float = 5.0) -> None:
        self.max_retries = max_retries
        self._client = httpx.Client(base_url=base_url.rstrip("/"), timeout=timeout,
                                    headers={"X-Internal-API-Key": api_key, "X-Caller": "ai-server"})

    def list_publications(self, corp_code: str, status: Optional[str] = None) -> List[Dict[str, Any]]:
        """회사의 발행 이력. 이전에 발행된 리포트가 있는지(정정 발행 여부) 확인하는 데 쓴다."""
        params: Dict[str, Any] = {"corp_code": corp_code}
        if status:
            params["status"] = status
        return self._get("/core/publications", params=params).get("items", [])

    def _trace_headers(self) -> Dict[str, str]:
        h: Dict[str, str] = {}
        if uid := get_request_uid():
            h["X-Request-ID"] = uid
        if caller := get_caller_user_id():
            h["X-User-Id"] = caller
        return h

    def _get(self, path: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        last: Optional[Exception] = None
        for attempt in range(self.max_retries + 1):
            try:
                resp = self._client.get(path, params=params, headers=self._trace_headers())
                if resp.status_code == 503 and attempt < self.max_retries:   # 시뮬레이션 실패는 한 번 더
                    time.sleep(0.5 * (2 ** attempt))
                    continue
                resp.raise_for_status()
                return resp.json()
            except httpx.HTTPStatusError as e:      # 403·404는 다시 불러도 같다
                raise RuntimeError(f"Core Zone 호출 실패 {e.response.status_code}: {e.response.text[:200]}") from e
            except httpx.RequestError as e:
                last = e
                if attempt < self.max_retries:
                    time.sleep(0.5 * (2 ** attempt))
        raise RuntimeError(f"Core Zone에 닿지 못했다: {last}")


core_client = CoreReadClient(settings.core_base_url, settings.core_api_key)
