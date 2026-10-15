"""FastAPI가 설치되지 않은 환경용 대체 서버(Starlette). api.py와 같은 경로·같은 응답을 제공한다.

python -m radar serve 는 FastAPI가 있으면 api.py를, 없으면 이 모듈을 띄운다.
"""
from __future__ import annotations

import json
import os

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse
from starlette.routing import Route

from .service import ReviewError, Service
from .webui import index_html

svc = Service()


def _json(data, status: int = 200) -> JSONResponse:
    return JSONResponse(data, status_code=status)


def _guard(fn):
    async def wrapped(request: Request):
        want = os.getenv("RADAR_INTERNAL_KEY")
        if want and request.headers.get("x-internal-key") != want:
            return _json({"detail": "내부 API Key가 필요합니다."}, 401)
        try:
            return await fn(request)
        except ReviewError as e:
            return _json({"detail": str(e)}, e.code)
        except KeyError as e:
            return _json({"detail": f"없는 분석: {e}"}, 404)
        except (ValueError, json.JSONDecodeError) as e:
            return _json({"detail": str(e)}, 422)
    return wrapped


@_guard
async def analyses(request: Request):
    if request.method == "GET":
        return _json(svc.store.list())
    body = await request.json()
    req = {"company": str(body.get("company", "999001")), "bsns_year": int(body.get("bsns_year", 2025)),
           "reprt_code": str(body.get("reprt_code", "11011")),
           "demo_fault_injection": bool(body.get("demo_fault_injection", False))}
    if req["reprt_code"] not in ("11011", "11012", "11013", "11014"):
        raise ValueError("reprt_code는 11011·11012·11013·11014 중 하나")
    return _json(svc.start(req, request.headers.get("x-request-uid")), 202)


@_guard
async def analysis(request: Request):
    return _json(svc.status(request.path_params["aid"]))


@_guard
async def report(request: Request):
    return _json(svc.store.load(request.path_params["aid"]))


@_guard
async def audit(request: Request):
    return _json(svc.store.audit_for(request.path_params["aid"]))


@_guard
async def review(request: Request):
    body = await request.json()
    if not isinstance(body.get("edits", []), list):
        raise ValueError("edits는 목록이어야 합니다")
    return _json(svc.review(request.path_params["aid"], body))


@_guard
async def kill(request: Request):
    if request.method == "GET":
        return _json({"on": svc.store.killed()})
    body = await request.json()
    return _json({"on": svc.store.set_kill(bool(body.get("on")), body.get("actor", "admin"))})


async def index(request: Request):
    return HTMLResponse(index_html(None))


app = Starlette(routes=[
    Route("/", index),
    Route("/api/analyses", analyses, methods=["GET", "POST"]),
    Route("/api/analyses/{aid}", analysis),
    Route("/api/analyses/{aid}/report", report),
    Route("/api/analyses/{aid}/audit", audit),
    Route("/api/analyses/{aid}/review", review, methods=["POST"]),
    Route("/api/admin/kill-switch", kill, methods=["GET", "POST"]),
])
