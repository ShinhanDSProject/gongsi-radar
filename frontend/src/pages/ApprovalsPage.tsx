import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";
import { api, ApiError, asList, describeError } from "../api/client";
import type { PublicationDto } from "../api/types";
import { useAuth } from "../auth";
import { ErrorText, StatusBadge } from "../components/ui";
import { fmtTime } from "../lib/format";

// HITL이 화면이 되는 자리. 발행 승인·반려는 Senior Manager만 —
// AI Agent는 이 화면에 대응하는 API를 부를 자격 증명 자체가 없다(발행·승인 Tool은 등록하지 않는다)
export default function ApprovalsPage() {
  const queryClient = useQueryClient();
  const pending = useQuery({
    queryKey: ["publications-pending"],
    queryFn: async () => asList(await api.get<PublicationDto[] | { items: PublicationDto[] }>("/api/publications/pending")),
    refetchInterval: 15000,
  });

  const refresh = () => {
    queryClient.invalidateQueries({ queryKey: ["publications-pending"] });
    queryClient.invalidateQueries({ queryKey: ["publications"] });
  };

  return (
    <div className="stack">
      <div className="page-h">
        <h1>결재함</h1>
        <span className="hint">승인하면 Core 발행 원장에 PUBLISHED로 기록되고 리포트가 잠깁니다. 자기가 요청한 건은 승인할 수 없습니다.</span>
      </div>
      {pending.isLoading && <p className="hint">불러오는 중…</p>}
      <ErrorText error={pending.error} fallback="결재 대기 목록을 가져올 수 없습니다." />
      {pending.data?.length === 0 && <p className="empty">결재 대기 중인 발행 요청이 없습니다.</p>}
      <ul className="flex flex-col gap-3">
        {pending.data?.map((p) => (
          <li key={p.publicationId}>
            <PendingCard p={p} onDone={refresh} />
          </li>
        ))}
      </ul>
    </div>
  );
}

function PendingCard({ p, onDone }: { p: PublicationDto; onDone: () => void }) {
  const { user } = useAuth();
  const [mode, setMode] = useState<"idle" | "approve" | "reject">("idle");
  const [comment, setComment] = useState("");
  const [reason, setReason] = useState("");
  const [error, setError] = useState<unknown>(null);
  const mine = user?.userId === p.submittedBy;

  const approve = useMutation({
    mutationFn: () =>
      api.post<PublicationDto>(`/api/publications/${encodeURIComponent(p.publicationId)}/approve`, comment.trim() ? { comment: comment.trim() } : {}),
    onSuccess: () => {
      setError(null);
      onDone();
    },
    onError: setError,
  });
  const reject = useMutation({
    mutationFn: () => api.post<PublicationDto>(`/api/publications/${encodeURIComponent(p.publicationId)}/reject`, { reason: reason.trim() }),
    onSuccess: () => {
      setError(null);
      onDone();
    },
    onError: setError,
  });
  const busy = approve.isPending || reject.isPending;
  const selfApproval = error instanceof ApiError && error.code === "SELF_APPROVAL_FORBIDDEN";

  return (
    <article className="panel" aria-labelledby={`pub-${p.publicationId}`}>
      <header className="panel-h">
        <div className="min-w-0">
          <h3 id={`pub-${p.publicationId}`} className="text-[15.5px] font-semibold">{p.title}</h3>
          <p className="hint">
            {p.corpName} · {p.periodLabel} · v{p.version}
            {p.supersedesId && <> · 정정 대상 <span className="mono">{p.supersedesId}</span></>}
          </p>
        </div>
        <StatusBadge status={p.status} />
      </header>
      <dl className="kv">
        <dt>요청자</dt>
        <dd className="mono">
          {p.submittedBy}
          {mine && <span className="tag">내 요청</span>}
        </dd>
        <dt>요청 시각</dt>
        <dd className="num">{fmtTime(p.createdAt)}</dd>
        <dt>결재 기한</dt>
        <dd className="num">{fmtTime(p.decisionRequiredBy)}</dd>
        <dt>요청 코멘트</dt>
        <dd>{p.comment || "—"}</dd>
        <dt>내용 해시</dt>
        <dd className="mono break-all" title={p.contentHash}>{p.contentHash.slice(0, 16)}…</dd>
        <dt>발행 ID</dt>
        <dd className="mono break-all">{p.publicationId}</dd>
      </dl>
      <p>
        <Link to={`/reports/${p.reportId}`} className="link">리포트 #{p.reportId} 열어 보기</Link>
      </p>

      {selfApproval ? (
        <p className="banner" role="alert">
          <b>자기 승인 금지</b> — {describeError(error)} 이 건은 다른 Senior({p.submittedBy} 아닌 사람)가 결재해야 합니다.
        </p>
      ) : (
        <ErrorText error={error} fallback="결재를 처리하지 못했습니다." />
      )}

      {mode === "idle" && (
        <div className="row justify-end">
          <button type="button" className="btn ghost" disabled={busy} onClick={() => setMode("reject")}>반려</button>
          <button type="button" className="btn seal-btn" disabled={busy} onClick={() => setMode("approve")}>승인</button>
        </div>
      )}
      {mode === "approve" && (
        <div className="confirm">
          <p>
            승인하면 <b>{p.corpName} {p.periodLabel}</b> 리포트가 발행 원장에 v{p.version}으로 기록되고 더 이상 수정할 수 없습니다.
            {mine && " (내가 요청한 건이라 서버가 거절할 것입니다.)"}
          </p>
          <label htmlFor={`ap-${p.publicationId}`} className="flabel">승인 코멘트(선택)</label>
          <textarea id={`ap-${p.publicationId}`} rows={2} value={comment} onChange={(e) => setComment(e.target.value)} />
          <div className="row">
            <button type="button" className="btn ghost" onClick={() => setMode("idle")} disabled={busy}>취소</button>
            <button type="button" className="btn seal-btn" disabled={busy} onClick={() => approve.mutate()}>
              {approve.isPending ? "승인 중…" : "승인 확정"}
            </button>
          </div>
        </div>
      )}
      {mode === "reject" && (
        <div className="confirm">
          <label htmlFor={`rj-${p.publicationId}`} className="flabel">반려 사유(필수)</label>
          <textarea
            id={`rj-${p.publicationId}`}
            rows={2}
            required
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            placeholder="요청자가 무엇을 고쳐야 하는지 적어 주세요"
          />
          <div className="row">
            <button type="button" className="btn ghost" onClick={() => setMode("idle")} disabled={busy}>취소</button>
            <button type="button" className="btn danger" disabled={busy || !reason.trim()} onClick={() => reject.mutate()}>
              {reject.isPending ? "반려 중…" : "반려 확정"}
            </button>
          </div>
        </div>
      )}
    </article>
  );
}
