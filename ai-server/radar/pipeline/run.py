"""분석 한 번 실행(동기). CLI·테스트가 쓰는 진입점이다.

서버에서는 app/agents/runner.py가 같은 그래프(radar.pipeline.graph)를 LangGraph 노드로 돌린다.
결재(HITL)·감사 로그·Kill Switch는 Spring(backend) 몫이다 — docs/CONTRACT.md §11.
"""
from __future__ import annotations

from radar.config import Settings
from radar.pipeline.graph import finalize, initial_state, prepare_context, run_graph


def run_analysis(request: dict, settings: Settings | None = None, on_event=None,
                 analysis_id: str | None = None, request_uid: str | None = None) -> dict:
    ctx = prepare_context(settings or Settings(), request, on_event, analysis_id, request_uid)
    return finalize(run_graph(initial_state(ctx, request)))
