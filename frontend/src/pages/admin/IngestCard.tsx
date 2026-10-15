import { useQuery } from "@tanstack/react-query";
import { api } from "../../api/client";
import type { IngestStatus, IngestStep } from "../../api/types";
import { ErrorText } from "../../components/ui";
import { fmtTime } from "../../lib/format";

const STEP_LABEL: Record<string, string> = {
  companies: "상장사 목록", filings: "정기공시", market: "시세", index: "지수",
  financials: "재무", induty: "업종 코드", documents: "원문", all: "전체",
};
const STATUS: Record<IngestStep["status"], { label: string; cls: string }> = {
  DONE: { label: "완료", cls: "v-good" },
  PARTIAL: { label: "예산 소진·다음에 이어서", cls: "v-warn" },
  FAILED: { label: "실패", cls: "v-bad" },
  SKIPPED: { label: "건너뜀", cls: "v-warn" },
  RUNNING: { label: "진행 중", cls: "" },
};

// 일일 수집(#3) 상태. 조회만 한다 — 수집은 원천 키와 적재 쓰기 권한을 가진 별도 작업(cron)이 돌리고,
// 이 화면·Spring·AI 서버는 그 자격 증명을 갖지 않는다
export default function IngestCard() {
  const q = useQuery({
    queryKey: ["ingest-status"],
    queryFn: () => api.get<IngestStatus>("/api/admin/ingest"),
    refetchInterval: 30_000,
  });
  const d = q.data;
  const used = d?.callsToday ?? 0;
  const pct = d && d.budget ? Math.min(100, Math.round((used / d.budget) * 100)) : 0;

  return (
    <section className="panel" aria-labelledby="ingest-title">
      <header className="panel-h">
        <h2 id="ingest-title">데이터 수집</h2>
        {d?.lastRun && <span className={`pill ${STATUS[d.lastRun.status].cls}`}>{STATUS[d.lastRun.status].label}</span>}
      </header>
      {q.isLoading && <p className="hint">불러오는 중…</p>}
      <ErrorText error={q.error} />
      {d && !d.lastRun && <p className="note">{d.reason}</p>}
      {d?.lastRun && (
        <>
          <dl className="kv">
            <dt>마지막 수집</dt>
            <dd className="num">{fmtTime(d.lastRun.finishedAt ?? d.lastRun.startedAt)} · {d.lastRun.mode} · 원천 {d.lastRun.source}</dd>
            <dt>시세 기준일</dt>
            <dd className="num">{d.lastMarketDate ? `${d.lastMarketDate.slice(0, 4)}.${d.lastMarketDate.slice(4, 6)}.${d.lastMarketDate.slice(6)}` : "—"}</dd>
            <dt>적재</dt>
            <dd className="num">
              기업 {(d.tables.ingest_company ?? 0).toLocaleString("ko-KR")} · 공시 {(d.tables.ingest_filing ?? 0).toLocaleString("ko-KR")} ·
              재무 {(d.tables.ingest_financial_line ?? 0).toLocaleString("ko-KR")}행 · 시세 {(d.tables.ingest_market_daily ?? 0).toLocaleString("ko-KR")}행
            </dd>
            <dt>오늘 호출</dt>
            <dd>
              <span className="num">{used.toLocaleString("ko-KR")} / {d.budget.toLocaleString("ko-KR")}회 · 남은 예산 {(d.budgetLeft ?? 0).toLocaleString("ko-KR")}회</span>
              <span className="block h-1.5 mt-1 rounded bg-sunken overflow-hidden" role="progressbar" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100} aria-label="오늘 쓴 호출 예산">
                <span className="block h-full bg-accent-bright" style={{ width: `${pct}%` }} />
              </span>
            </dd>
          </dl>
          <div className="scroll-x">
            <table className="grid-table">
              <caption className="sr-only">마지막 수집의 단계별 결과</caption>
              <thead>
                <tr><th scope="col">단계</th><th scope="col">결과</th><th scope="col" className="r">호출</th><th scope="col" className="r">행</th><th scope="col">비고</th></tr>
              </thead>
              <tbody>
                {d.steps.map((s) => (
                  <tr key={s.step}>
                    <td>{STEP_LABEL[s.step] ?? s.step}</td>
                    <td><span className={`pill ${STATUS[s.status]?.cls ?? ""}`}>{STATUS[s.status]?.label ?? s.status}</span></td>
                    <td className="r num">{s.calls.toLocaleString("ko-KR")}</td>
                    <td className="r num">{s.rows.toLocaleString("ko-KR")}</td>
                    <td className="hint">{s.error ?? (s.remaining > 0 ? `${s.remaining.toLocaleString("ko-KR")}건 다음 실행으로` : "")}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
      <p className="hint">수집은 서버의 예약 작업이 하루 한 번 돌립니다(<code>python -m radar ingest daily</code>). 이 화면에서는 시작할 수 없습니다.</p>
    </section>
  );
}
