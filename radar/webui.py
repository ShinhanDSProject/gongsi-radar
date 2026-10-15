"""빌드된 리뷰 화면(web/dist/index.html)에 리포트 JSON을 심어 단일 HTML로 만든다."""
from __future__ import annotations

import json

from .config import ROOT

DIST = ROOT / "web" / "dist" / "index.html"
PLACEHOLDER = '<script id="radar-report" type="application/json">null</script>'


def index_html(report: dict | None) -> str:
    if not DIST.exists():
        return ("<!doctype html><meta charset='utf-8'><p>리뷰 화면이 빌드되지 않았습니다. "
                "<code>node web/build.mjs</code>를 실행하세요.</p>")
    html = DIST.read_text(encoding="utf-8")
    if report is None:
        return html
    payload = json.dumps(report, ensure_ascii=False).replace("</", "<\\/")
    if PLACEHOLDER not in html:
        raise RuntimeError("web/dist/index.html에 리포트 자리표시자가 없습니다.")
    return html.replace(PLACEHOLDER, f'<script id="radar-report" type="application/json">{payload}</script>', 1)
