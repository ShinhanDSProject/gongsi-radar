"""노드와 엣지를 StateGraph로 묶는다. 그래프 모양이 곧 실행 흐름이다.

  plan → disclosure → financial → review ─(통과/상한)→ write → END
                          ↑            │
                          └──(반려)────┘
"""
from __future__ import annotations

from functools import lru_cache

from langgraph.graph import END, StateGraph

from .nodes import disclosure_node, financial_node, plan_node, review_node, route_after_review, write_node
from .state import AnalysisState


@lru_cache(maxsize=1)
def get_analysis_graph():
    g = StateGraph(AnalysisState)
    g.add_node("plan", plan_node)
    g.add_node("disclosure", disclosure_node)
    g.add_node("financial", financial_node)
    g.add_node("review", review_node)
    g.add_node("write", write_node)
    g.set_entry_point("plan")
    g.add_edge("plan", "disclosure")
    g.add_edge("disclosure", "financial")
    g.add_edge("financial", "review")
    # [통제] 반려되면 financial로 되돌아간다. 상한은 review_node가 이미 봤다
    g.add_conditional_edges("review", route_after_review, {"financial": "financial", "write": "write"})
    g.add_edge("write", END)
    return g.compile()
