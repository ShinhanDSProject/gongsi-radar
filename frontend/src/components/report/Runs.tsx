// 실행 기록 탭. 파이프라인 타임라인(radar 그래프) + §6.1 Agent·Tool 호출 기록 + 실행 지표.
import type { RadarReport } from "../../api/types";
import { AgentTimeline } from "../AgentTimeline";
import { Empty } from "../ui";

function argsText(a: unknown): string {
  if (a == null) return "";
  if (typeof a === "string") return a;
  try {
    return JSON.stringify(a);
  } catch {
    return String(a);
  }
}

export function Runs({ rep }: { rep: RadarReport }) {
  const tl = rep.timeline ?? [];
  const maxMs = Math.max(1, ...tl.map((t) => t.ended_ms - t.started_ms));
  const m = rep.meta;
  const usage = rep.metrics.llm_usage || {};
  return (
    <div className="stack">
      {(rep.agents?.length ?? 0) > 0 && (
        <section className="panel">
          <header className="panel-h">
            <h2>Agent</h2>
            <span className="hint">Manager가 Worker 4종을 순서대로 부른 기록</span>
          </header>
          <AgentTimeline
            executions={rep.agents!.map((a) => ({ ...a, errorMessage: null }))}
          />
        </section>
      )}

      {(rep.toolCalls?.length ?? 0) > 0 && (
        <section className="panel">
          <header className="panel-h">
            <h2>Tool 호출</h2>
            <span className="hint">{rep.toolCalls!.length}회 · 조회 Tool만(발행·승인 Tool은 등록되지 않음)</span>
          </header>
          <div className="scroll-x">
            <table className="grid-table">
              <thead>
                <tr>
                  <th scope="col">Agent</th>
                  <th scope="col">Tool</th>
                  <th scope="col">인자</th>
                  <th scope="col">결과 요약</th>
                </tr>
              </thead>
              <tbody>
                {rep.toolCalls!.map((c, i) => (
                  <tr key={i}>
                    <td className="mono">{c.agentId}</td>
                    <td className="mono">{c.tool}</td>
                    <td className="mono text-xs break-all">{argsText(c.args)}</td>
                    <td>{c.resultSummary}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      <section className="panel">
        <header className="panel-h">
          <h2>파이프라인</h2>
          <span className="hint">고정 순서 · 검증 반려 시에만 되돌아감(최대 2회)</span>
        </header>
        {!tl.length && <Empty>타임라인 기록이 없습니다.</Empty>}
        <ol className="runs">
          {tl.map((t, i) => (
            <li key={i} className={`run run-${t.status}`}>
              <span className="run-name">
                {t.label}
                {t.round && (t.node === "relate" || t.node === "verify") ? ` · ${t.round + 1}차` : ""}
              </span>
              <span className="run-bar" aria-hidden="true">
                <span style={{ width: `${Math.max(2, ((t.ended_ms - t.started_ms) / maxMs) * 100)}%` }} />
              </span>
              <span className="run-ms num">{t.ended_ms - t.started_ms}ms</span>
              <span className="run-note">
                {t.status === "rejected" ? "반려 · " : t.status === "error" ? "오류 · " : ""}
                {t.note}
              </span>
            </li>
          ))}
        </ol>
      </section>
      <section className="panel">
        <header className="panel-h">
          <h2>실행 정보</h2>
        </header>
        <dl className="kv">
          <dt>분석 ID</dt>
          <dd className="mono">{m.analysis_id}</dd>
          <dt>요청 UID</dt>
          <dd className="mono">{m.request_uid || "—"}</dd>
          <dt>생성 시각</dt>
          <dd className="mono">{rep.generatedAt || m.created_at}</dd>
          <dt>데이터</dt>
          <dd>
            {m.sample_data ? "가상 기업 샘플" : "OpenDART"} · 재무 {m.fs_div === "CFS" ? "연결" : "별도"}
          </dd>
          <dt>임베딩</dt>
          <dd>{m.embedder}</dd>
          <dt>LLM</dt>
          <dd>{m.llm}</dd>
          <dt>그래프</dt>
          <dd>{m.graph_engine === "langgraph" ? "LangGraph StateGraph" : "내장 러너(LangGraph와 같은 토폴로지)"}</dd>
          <dt>버전</dt>
          <dd className="mono">{m.pipeline_version}</dd>
          <dt>소요 시간</dt>
          <dd className="num">{rep.metrics.elapsed_ms ?? "—"}ms</dd>
          <dt>데이터 호출</dt>
          <dd className="num">{rep.metrics.source_calls ?? 0}회</dd>
          <dt>LLM 호출</dt>
          <dd className="num">
            {usage.calls || 0}회 · 입력 {usage.input_tokens || 0} / 출력 {usage.output_tokens || 0} 토큰
          </dd>
          {rep.metrics.llm_cost_estimate_usd != null && (
            <>
              <dt>LLM 비용 추정</dt>
              <dd className="num">
                약 ${rep.metrics.llm_cost_estimate_usd} <span className="hint">{rep.metrics.llm_cost_note}</span>
              </dd>
            </>
          )}
        </dl>
      </section>
    </div>
  );
}
