import type { AgentExecution } from "../api/types";
import { StatusBadge } from "./ui";

const AGENT_LABELS: Record<string, string> = {
  manager: "Manager (계획)",
  disclosure_analyst: "Disclosure Analyst (공시 비교)",
  financial_analyst: "Financial Analyst (재무·사업지표·시장)",
  risk_reviewer: "Risk Reviewer (검증·지배구조·소송)",
  report_writer: "Report Writer (리포트 작성)",
};

// agent_execution 테이블이 화면이 되는 자리.
// 진행 중에는 폴링으로 이 목록이 한 줄씩 늘어나는 것이 보인다
export function AgentTimeline({ executions }: { executions: (Omit<AgentExecution, "summary"> & { summary?: string | null })[] }) {
  if (executions.length === 0) {
    return <p className="hint">아직 실행 기록이 없습니다.</p>;
  }
  return (
    <ol className="flex flex-col gap-2">
      {executions.map((e, i) => (
        <li key={i} className="grid grid-cols-[24px_minmax(0,1fr)_auto] gap-x-3 gap-y-0.5 items-baseline text-[13.5px]">
          <span className="text-muted text-right num">{e.stepOrder ?? i + 1}</span>
          <span className="min-w-0">
            <b className="font-semibold">{AGENT_LABELS[e.agentId] ?? e.agentId}</b>
            {e.durationMs != null && <span className="hint num"> · {(e.durationMs / 1000).toFixed(1)}s</span>}
          </span>
          <StatusBadge status={e.status} />
          {(e.summary || e.errorMessage) && (
            <span className={`col-start-2 col-span-2 text-[12.5px] ${e.errorMessage ? "text-bad" : "text-muted"}`}>
              {e.errorMessage ?? e.summary}
            </span>
          )}
        </li>
      ))}
    </ol>
  );
}
