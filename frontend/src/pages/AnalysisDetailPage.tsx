import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import { api } from "../api/client";
import type { AnalysisRequestDto, JobStatus } from "../api/types";
import { AgentTimeline } from "../components/AgentTimeline";
import { ReportScreen } from "../components/report/ReportScreen";
import { ReportView } from "../components/report/ReportView";
import { ErrorText, StatusBadge } from "../components/ui";
import { fmtTime, REPRT_LABEL } from "../lib/format";

const POLL_MS = 1500;

const STEPS: [string, string][] = [
  ["PLANNING", "계획"],
  ["DISCLOSURE", "공시 비교"],
  ["FINANCIAL", "재무·사업지표·시장"],
  ["REVIEW", "검증"],
  ["WRITING", "리포트 작성"],
  ["DONE", "완료"],
];

export default function AnalysisDetailPage() {
  const { id } = useParams();
  const queryClient = useQueryClient();

  // RUNNING 동안만 1.5초 간격으로 다시 묻고, 끝나면 폴링도 멈춘다(refetchInterval이 false면 중단).
  // /status를 부르면 Spring이 FastAPI Job을 확인해 COMPLETED면 리포트를 저장하고 reportId를 채운다
  const status = useQuery({
    queryKey: ["analysis-request", id],
    queryFn: () => api.get<AnalysisRequestDto>(`/api/analysis-requests/${id}/status`),
    refetchInterval: (q) => (q.state.data?.status === "RUNNING" ? POLL_MS : false),
  });

  const request = status.data;
  const job = useQuery({
    queryKey: ["analysis-job", id],
    queryFn: () => api.get<JobStatus>(`/api/analysis-requests/${id}/job`),
    enabled: !!request?.jobId, // 실행 전에는 Job이 없다
    refetchInterval: (q) => (q.state.data?.status === "RUNNING" || request?.status === "RUNNING" ? POLL_MS : false),
    retry: false,
  });

  const execute = useMutation({
    mutationFn: () => api.post(`/api/analysis-requests/${id}/execute`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["analysis-request", id] });
      queryClient.invalidateQueries({ queryKey: ["analysis-job", id] });
      queryClient.invalidateQueries({ queryKey: ["analysis-requests"] });
    },
  });

  if (status.isLoading) return <p className="hint">불러오는 중…</p>;
  if (!request) return <ErrorText error={status.error ?? new Error("요청을 찾을 수 없습니다.")} />;

  const j = job.data;
  const running = request.status === "RUNNING" || j?.status === "RUNNING";
  const progress = Math.round((j?.progress ?? (request.status === "COMPLETED" ? 1 : 0)) * 100);
  const stepIdx = STEPS.findIndex(([k]) => k === j?.currentStep);
  // 저장된 리포트가 아직 없으면(Spring 저장 전) Job 결과를 읽기 전용으로 보여 준다
  const jobReport = j?.result?.report;

  return (
    <div className="stack">
      <section className="panel" aria-labelledby="req-title">
        <header className="panel-h">
          <h1 id="req-title" className="font-display text-[19px] font-extrabold">
            #{request.id} {request.corpName ?? request.company}{" "}
            <span className="hint font-body font-normal">
              {request.bsnsYear} {REPRT_LABEL[request.reprtCode] ?? request.reprtCode}
            </span>
          </h1>
          <StatusBadge status={request.status} />
        </header>
        <dl className="kv">
          <dt>관심 질문</dt>
          <dd>{request.query ?? "—"}</dd>
          <dt>요청자</dt>
          <dd className="mono">{request.userId}</dd>
          <dt>권한 범위</dt>
          <dd className="flex flex-wrap gap-1">
            {request.scope.map((s) => (
              <code key={s} className="bg-sunken rounded px-1">{s}</code>
            ))}
          </dd>
          <dt>시각</dt>
          <dd className="num">
            생성 {fmtTime(request.createdAt)}
            {request.startedAt && ` · 시작 ${fmtTime(request.startedAt)}`}
            {request.finishedAt && ` · 종료 ${fmtTime(request.finishedAt)}`}
          </dd>
          {request.demoFaultInjection && (
            <>
              <dt>시연</dt>
              <dd>오류 주입 켬(검증 반려 루프)</dd>
            </>
          )}
        </dl>

        {(request.status === "CREATED" || request.status === "FAILED") && (
          <div className="row">
            <button onClick={() => execute.mutate()} disabled={execute.isPending} className="btn">
              {execute.isPending ? "시작 중…" : request.status === "FAILED" ? "다시 실행" : "분석 실행"}
            </button>
          </div>
        )}
        <ErrorText error={execute.error} fallback="실행하지 못했습니다." />
        {request.status === "BLOCKED" && (
          <p className="err-box">입력 가드레일이 이 요청을 차단했습니다. 관심 질문을 고쳐 새 분석을 만드세요.</p>
        )}

        {request.jobId && (
          <div className="flex flex-col gap-2" aria-live="polite">
            <div
              className="progress-track"
              role="progressbar"
              aria-label="분석 진행률"
              aria-valuemin={0}
              aria-valuemax={100}
              aria-valuenow={progress}
            >
              <div className="progress-fill" style={{ width: `${progress}%` }} />
            </div>
            <ol className="steps" aria-label="진행 단계">
              {STEPS.map(([k, label], i) => (
                <li
                  key={k}
                  className={j?.status === "COMPLETED" || (stepIdx >= 0 && i < stepIdx) ? "done" : i === stepIdx ? "now" : ""}
                  aria-current={i === stepIdx ? "step" : undefined}
                >
                  {label}
                </li>
              ))}
            </ol>
            <p className="hint num">
              {progress}%{j?.currentStep ? ` · 현재 단계 ${j.currentStep}` : ""}
              {running ? " · 진행 중…" : ""}
            </p>
          </div>
        )}
      </section>

      {request.jobId && (
        <section className="panel">
          <header className="panel-h">
            <h2>Agent 실행 기록</h2>
            <span className="hint mono">{request.jobId}</span>
          </header>
          {/* Job은 AI 서버 메모리에 산다. AI 서버가 재기동됐으면 여기만 비고,
              요청·리포트·감사 기록처럼 DB에 남긴 것은 그대로다 */}
          {job.error ? (
            <p className="hint">실행 기록을 가져올 수 없습니다(AI 서버가 재기동됐을 수 있습니다).</p>
          ) : (
            <AgentTimeline executions={j?.agentExecutions ?? []} />
          )}
          {j?.status === "FAILED" && <p className="err-box">분석 실패: {j.result?.error ?? "원인 미상"}</p>}
        </section>
      )}

      {request.reportId != null ? (
        <ReportScreen reportId={request.reportId} />
      ) : (
        jobReport && (
          <div className="stack">
            <p className="note">리포트를 저장하는 중입니다. 저장이 끝나면 수정·발행 요청을 할 수 있습니다.</p>
            <ReportView rep={jobReport} editable={false} onEdit={async () => undefined} />
          </div>
        )
      )}
      <p>
        <Link to="/analyses" className="link">← 분석 목록</Link>
      </p>
    </div>
  );
}
