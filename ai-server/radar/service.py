"""분석 실행·작업 관리·검토(HITL)·감사 로그. API 프레임워크와 무관한 서비스 계층.

실제 아키텍처에서는 인증·HITL·감사 로그를 Spring Boot가 맡는다. 이 프로토타입은 AI Layer 단독으로
끝까지 시연할 수 있도록 같은 기능을 최소한으로 넣었다(감사 로그는 append-only JSONL).
"""
from __future__ import annotations

import json
import threading
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

from .config import Settings
from .graph import finalize, initial_state, new_id, prepare_context, run_graph
from .schemas import Report
from .verify import banned_hits


class ReviewError(ValueError):
    def __init__(self, msg: str, code: int = 400):
        super().__init__(msg)
        self.code = code


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Store:
    """작업 상태(메모리)와 리포트·감사 로그(디스크)."""

    def __init__(self, settings: Settings):
        self.s = settings
        self.dir = Path(settings.out_dir) / "analyses"
        self.dir.mkdir(parents=True, exist_ok=True)
        self.audit_path = Path(settings.out_dir) / "audit.jsonl"
        self.jobs: dict[str, dict] = {}
        self.lock = threading.Lock()

    # -- 감사 로그(append-only) -------------------------------------------------------
    def audit(self, analysis_id: str, actor: str, action: str, **detail) -> dict:
        rec = {"at": now(), "analysis_id": analysis_id, "actor": actor, "action": action, **detail}
        with self.lock, self.audit_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        return rec

    def audit_for(self, analysis_id: str) -> list[dict]:
        if not self.audit_path.exists():
            return []
        out = []
        for line in self.audit_path.read_text(encoding="utf-8").splitlines():
            r = json.loads(line)
            if r.get("analysis_id") == analysis_id:
                out.append(r)
        return out

    # -- Kill Switch ---------------------------------------------------------------
    @property
    def kill_path(self) -> Path:
        return Path(self.s.out_dir) / "KILL_SWITCH"

    def killed(self) -> bool:
        return self.kill_path.exists()

    def set_kill(self, on: bool, actor: str) -> bool:
        if on:
            self.kill_path.write_text(now(), encoding="utf-8")
        elif self.kill_path.exists():
            self.kill_path.unlink()
        self.audit("-", actor, "kill_switch_on" if on else "kill_switch_off")
        return on

    # -- 리포트 ----------------------------------------------------------------------
    def save(self, report: dict) -> Path:
        p = self.dir / report["meta"]["analysis_id"] / "report.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
        return p

    def load(self, analysis_id: str) -> dict:
        p = self.dir / analysis_id / "report.json"
        if not p.exists():
            raise KeyError(analysis_id)
        return json.loads(p.read_text(encoding="utf-8"))

    def list(self) -> list[dict]:
        out = []
        for p in sorted(self.dir.glob("*/report.json"), reverse=True):
            m = json.loads(p.read_text(encoding="utf-8"))
            out.append({"analysis_id": m["meta"]["analysis_id"], "company": m["meta"]["company"]["corp_name"],
                        "current": m["meta"]["current"]["report_nm"], "prior": m["meta"]["prior"]["report_nm"],
                        "created_at": m["meta"]["created_at"], "review": m["review"]["status"]})
        return out


def run_analysis(request: dict, settings: Settings | None = None, on_event=None,
                 analysis_id: str | None = None, request_uid: str | None = None) -> dict:
    ctx = prepare_context(settings or Settings(), request, on_event, analysis_id, request_uid)
    return finalize(run_graph(initial_state(ctx, request)))


class Service:
    def __init__(self, settings: Settings | None = None):
        self.s = settings or Settings()
        self.store = Store(self.s)

    def start(self, request: dict, request_uid: str | None = None, actor: str = "api") -> dict:
        if self.store.killed():
            raise ReviewError("Kill Switch가 켜져 있어 새 분석을 시작할 수 없습니다.", 423)
        aid = new_id()
        job = {"analysis_id": aid, "status": "running", "request": request, "created_at": now(),
               "events": [], "error": None}
        with self.store.lock:
            self.store.jobs[aid] = job
        self.store.audit(aid, actor, "analysis_requested", request=request, request_uid=request_uid)

        def on_event(e):
            job["events"].append({**e, "t": round(time.time(), 3)})

        def work():
            try:
                rep = run_analysis(request, Settings(**{**self.s.__dict__}), on_event, aid, request_uid)
                self.store.save(rep)
                self.store.audit(aid, "system", "analysis_completed", model=rep["meta"]["llm"],
                                 embedder=rep["meta"]["embedder"], pipeline=rep["meta"]["pipeline_version"],
                                 rcept_no=[rep["meta"]["prior"]["rcept_no"], rep["meta"]["current"]["rcept_no"]])
                job["status"] = "done"
            except Exception as e:  # noqa: BLE001 — 실패 사유를 그대로 돌려준다
                job["status"], job["error"] = "error", f"{type(e).__name__}: {e}"
                job["trace"] = traceback.format_exc(limit=5)
                self.store.audit(aid, "system", "analysis_failed", error=job["error"])

        threading.Thread(target=work, daemon=True).start()
        return {"analysis_id": aid, "status": "running"}

    def status(self, aid: str) -> dict:
        job = self.store.jobs.get(aid)
        if job:
            return {k: v for k, v in job.items() if k != "trace"}
        self.store.load(aid)  # 디스크에만 있는 지난 분석
        return {"analysis_id": aid, "status": "done", "events": [], "error": None}

    def review(self, aid: str, body: dict) -> dict:
        rep = self.store.load(aid)
        reviewer = (body.get("reviewer") or "").strip()
        action = body.get("action")
        if not reviewer:
            raise ReviewError("검토자 이름이 필요합니다.")
        if rep["review"]["status"] == "승인됨":
            raise ReviewError("이미 승인된 리포트는 수정할 수 없습니다(정정은 새 분석으로).", 409)
        items = {c["id"]: ("changes", c) for c in rep["changes"]}
        items.update({r["account_key"]: ("relations", r) for r in rep["relations"]})
        for e in body.get("edits", []):
            kind, it = items.get(e.get("item_id"), (None, None))
            if it is None:
                raise ReviewError(f"없는 항목: {e.get('item_id')}")
            field = "summary" if kind == "changes" else "statement"
            hits = banned_hits(e.get("value", ""))
            if hits:
                raise ReviewError(f"수정 문구에 금지 표현이 있습니다: {', '.join(hits)}")
            before = it[field]
            it[field] = e["value"]
            it.setdefault("flags", [])
            if kind == "changes" and "검토자 수정" not in it["flags"]:
                it["flags"].append("검토자 수정")
            ev = {"at": now(), "actor": reviewer, "action": "수정", "item_id": e["item_id"],
                  "detail": f"{before} → {e['value']}"}
            rep["review"]["events"].append(ev)
            self.store.audit(aid, reviewer, "edit", item_id=e["item_id"], before=before, after=e["value"])
        if action == "approve":
            if self.store.killed():
                raise ReviewError("Kill Switch가 켜져 있어 공유 승인을 할 수 없습니다.", 423)
            rep["review"].update(status="승인됨", reviewer=reviewer, decided_at=now(), comment=body.get("comment"))
            rep["review"]["events"].append({"at": now(), "actor": reviewer, "action": "승인·공유",
                                            "detail": body.get("comment") or ""})
            self.store.audit(aid, reviewer, "approve", comment=body.get("comment"))
        elif action == "request_changes":
            rep["review"].update(status="수정 요청", reviewer=reviewer, decided_at=now(), comment=body.get("comment"))
            rep["review"]["events"].append({"at": now(), "actor": reviewer, "action": "수정 요청",
                                            "detail": body.get("comment") or ""})
            self.store.audit(aid, reviewer, "request_changes", comment=body.get("comment"))
        Report.model_validate(rep)
        self.store.save(rep)
        return rep
