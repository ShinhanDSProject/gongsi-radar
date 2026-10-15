// 결재란: 작성(AI) · 검토(발행 요청자) · 승인(Senior). 발행이 승인되면 승인 칸에 인주색 도장이 찍힌다.
// web/src/review.jsx의 ReviewPanel을 옮기되, 승인 자체는 이 화면에서 하지 않는다 —
// 여기서는 "발행 요청"까지만, 승인·반려는 Senior의 결재함(/approvals)에서 한다(자기 승인 금지).
import { useState } from "react";
import { describeError } from "../../api/client";
import type { PublicationDto, ReportDto } from "../../api/types";
import { fmtTime } from "../../lib/format";

export function ReviewRail({
  report,
  publication,
  reviewCount,
  onPublish,
}: {
  report: ReportDto;
  publication: PublicationDto | null;
  reviewCount: number;
  onPublish: (comment: string | null) => Promise<void>;
}) {
  const rv = report.body.review;
  const st = report.approvalStatus;
  const [comment, setComment] = useState("");
  const [confirm, setConfirm] = useState(false);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  const approved = st === "APPROVED" || publication?.status === "PUBLISHED";
  const canRequest = st === "DRAFT" || st === "REJECTED";
  const approver = publication?.decidedBy ?? rv?.reviewer ?? "";
  const reviewer = publication?.submittedBy ?? null;

  const submit = async () => {
    setErr("");
    setBusy(true);
    try {
      await onPublish(comment.trim() || null);
      setConfirm(false);
      setComment("");
    } catch (e) {
      setErr(describeError(e, "발행 요청이 실패했습니다."));
    } finally {
      setBusy(false);
    }
  };

  const tone = approved ? "done" : st === "REJECTED" ? "back" : st === "PENDING" ? "wait" : "";
  let statusText: string;
  if (approved) {
    statusText = `승인되어 발행 원장에 기록되었습니다${publication ? `(v${publication.version})` : ""}. 이후 수정은 새 분석으로 합니다.`;
  } else if (st === "PENDING") {
    statusText = `Senior 결재 대기 중입니다. 결재가 끝날 때까지 수정할 수 없습니다.${
      publication?.decisionRequiredBy ? ` 결재 기한 ${fmtTime(publication.decisionRequiredBy)}.` : ""
    }`;
  } else if (st === "REJECTED") {
    statusText = `반려: ${publication?.comment || rv?.comment || "사유 없음"} — 고친 뒤 다시 발행을 요청할 수 있습니다.`;
  } else {
    statusText = reviewCount
      ? `사람 확인이 필요한 항목 ${reviewCount}건이 있습니다. 확인·수정한 뒤 발행을 요청하세요.`
      : "모든 항목이 자동 검증을 통과했습니다. 내용을 확인하고 발행을 요청하세요.";
  }

  return (
    <aside className="rail" aria-label="결재">
      <section className="kj">
        <h2 className="kj-title">결재</h2>
        <div className="kj-grid">
          <div className="kj-cell">
            <span className="kj-role">작성</span>
            <span className="kj-who">AI 초안</span>
            <span className="kj-when num">{fmtTime(report.body.generatedAt ?? report.createdAt)}</span>
          </div>
          <div className="kj-cell">
            <span className="kj-role">검토</span>
            <span className="kj-who">{reviewer ?? "—"}</span>
            <span className="kj-when num">{publication ? fmtTime(publication.createdAt) : ""}</span>
          </div>
          <div className="kj-cell">
            <span className="kj-role">승인</span>
            {approved ? (
              <span className="seal" role="img" aria-label={`${approver} 승인`}>
                <span className="seal-word" aria-hidden="true">승인</span>
                <span className="seal-name" aria-hidden="true">{approver}</span>
              </span>
            ) : (
              <span className="kj-who">{st === "REJECTED" ? "반려" : "—"}</span>
            )}
            <span className="kj-when num">
              {approved || st === "REJECTED" ? fmtTime(publication?.decidedAt ?? rv?.decided_at ?? null) : ""}
            </span>
          </div>
        </div>
        <p className={`kj-status ${tone ? `s-${tone}` : ""}`} role="status">
          {statusText}
        </p>

        {canRequest && (
          <form
            className="kj-form"
            onSubmit={(e) => {
              e.preventDefault();
              setConfirm(true);
            }}
          >
            <label htmlFor="publish-comment">요청 코멘트</label>
            <textarea
              id="publish-comment"
              rows={2}
              value={comment}
              maxLength={1000}
              onChange={(e) => setComment(e.target.value)}
              placeholder="결재자에게 남길 말(선택)"
            />
            {err && (
              <p className="err" role="alert">
                {err}
              </p>
            )}
            {!confirm ? (
              <div className="row">
                <button type="submit" className="btn" disabled={busy}>
                  {st === "REJECTED" ? "다시 발행 요청" : "발행 요청"}
                </button>
              </div>
            ) : (
              <div className="confirm">
                <p>발행을 요청하면 결재가 끝날 때까지 리포트가 잠깁니다. 요청할까요?</p>
                <div className="row">
                  <button type="button" className="btn ghost" onClick={() => setConfirm(false)}>
                    취소
                  </button>
                  <button type="button" className="btn seal-btn" disabled={busy} onClick={submit}>
                    {busy ? "요청 중…" : "요청"}
                  </button>
                </div>
              </div>
            )}
          </form>
        )}
        <p className="kj-mode">
          수정·발행 요청·결재는 서버 감사 로그(append-only)에 기록됩니다. 자기가 요청한 발행은 승인할 수 없습니다.
        </p>
      </section>

      {(rv?.events?.length ?? 0) > 0 && (
        <section className="log" aria-label="기록">
          <h2>기록</h2>
          <ol>
            {[...rv.events].reverse().map((e, i) => (
              <li key={i}>
                <span className="log-when num">{fmtTime(e.at)}</span>
                <span className="log-what">
                  <b>{e.actor === "system" ? "시스템" : e.actor}</b> {e.action}
                  {e.item_id ? ` · ${e.item_id}` : ""}
                </span>
                {e.detail && <span className="log-detail">{e.detail}</span>}
              </li>
            ))}
          </ol>
        </section>
      )}

      <p className="disclaimer">{report.disclaimer || report.body.meta.disclaimer}</p>
    </aside>
  );
}
