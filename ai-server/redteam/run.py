"""Red Team 셋을 실행 중인 AI 서버에 던져 표로 보여 준다. 사용: python redteam/run.py [http://localhost:8100]"""
import json
import os
import sys
from pathlib import Path

import httpx

base = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8100"
key = os.getenv("AI_SERVER_API_KEY", "dev-ai-internal-key")
cases = json.loads((Path(__file__).parent / "prompts.json").read_text(encoding="utf-8"))["cases"]
ok = 0
for c in cases:
    path = "output-check" if c.get("check") == "output" else "input-check"
    r = httpx.post(f"{base}/ai/guardrails/{path}", json={"text": c["text"], "userId": "redteam"},
                   headers={"X-Internal-API-Key": key, "X-Request-ID": f"redteam-{c['id']}"}).json()
    hit = r["riskLevel"] == c["expect"]
    ok += hit
    print(f"{'✓' if hit else '✕'} {c['id']:<8} 기대 {c['expect']:<8} 실제 {r['riskLevel']:<8} {r['detectedIssues']}")
print(f"\n{ok}/{len(cases)} 기대와 일치")
