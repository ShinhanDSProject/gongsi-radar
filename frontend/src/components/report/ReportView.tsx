// 리포트 본문 화면: 머리(회사·비교 보고서) + 탭 + 오른쪽 결재 레일.
// web/src/App.jsx의 ReportView를 옮겼다. 탭 상태는 ?tab= 으로 URL에 남겨 새로고침·공유에도 유지한다.
import { useMemo, useState, type ReactNode } from "react";
import { useSearchParams } from "react-router-dom";
import type { RadarReport } from "../../api/types";
import { reportLabel } from "../../lib/format";
import { TabList } from "../ui";
import { BusinessView } from "./Business";
import { Changes, type OnEdit } from "./Changes";
import { GovernanceView } from "./Governance";
import { MarketView } from "./Market";
import { Numbers } from "./Numbers";
import { Overview } from "./Overview";
import { Parsing } from "./Parsing";
import { Runs } from "./Runs";
import { Tables } from "./Tables";

export type ReportTab =
  | "overview" | "changes" | "numbers" | "business" | "governance" | "market" | "tables" | "runs" | "parsing";
const TAB_IDS: ReportTab[] = ["overview", "changes", "numbers", "business", "governance", "market", "tables", "runs", "parsing"];

export function useCounts(rep: RadarReport) {
  return useMemo(
    () => ({
      changes: rep.changes.length,
      numbers: rep.relations.length,
      tables: rep.tables.length,
      business: rep.business ? rep.business.groups.length : null,
      governance: rep.governance ? rep.governance.changes.length : null,
      review:
        rep.changes.filter((c) => c.verification.status === "검토 필요").length +
        rep.relations.filter((r) => r.verification.status === "검토 필요").length,
    }),
    [rep],
  );
}

export function ReportView({
  rep,
  editable,
  onEdit,
  rail,
  badges,
  footer,
}: {
  rep: RadarReport;
  editable: boolean;
  onEdit: OnEdit;
  rail?: ReactNode;
  badges?: ReactNode;
  footer?: ReactNode;
}) {
  const [params, setParams] = useSearchParams();
  const raw = params.get("tab") as ReportTab | null;
  const tab: ReportTab = raw && TAB_IDS.includes(raw) ? raw : "overview";
  const [focus, setFocus] = useState<string | null>(null);
  const counts = useCounts(rep);
  const m = rep.meta;

  const go = (t: ReportTab, id?: string) => {
    setFocus(id || null);
    const next = new URLSearchParams(params);
    next.set("tab", t);
    setParams(next, { replace: true });
    if (id) {
      setTimeout(() => {
        const el = document.getElementById(`c-${id}`);
        if (el) el.scrollIntoView({ block: "start" });
      }, 30);
    }
  };

  const tabs: { id: ReportTab; label: string; count?: number | null }[] = [
    { id: "overview", label: "개요" },
    { id: "changes", label: "변경 문단", count: counts.changes },
    { id: "numbers", label: "수치·관련 서술", count: counts.numbers },
    { id: "business", label: "사업 지표", count: counts.business },
    { id: "governance", label: "지배구조", count: counts.governance },
    { id: "market", label: "시장 지표" },
    { id: "tables", label: "표", count: counts.tables },
    { id: "runs", label: "실행 기록" },
    { id: "parsing", label: "원문 파싱" },
  ];

  return (
    <div>
      <header className="rhead">
        <div className="rhead-inner">
          <div className="title-block">
            <h1>
              {rep.title?.trim() || m.company?.corp_name || "공시 비교 리포트"}
              {m.sample_data ? <span className="sample">가상 기업 샘플</span> : null}
            </h1>
            <p className="cmp">
              {rep.title?.trim() && m.company?.corp_name ? <span>{m.company.corp_name} ·</span> : null}
              <a href={m.prior.url} target="_blank" rel="noreferrer">
                {reportLabel(m.prior)}
              </a>
              <span className="arrow" aria-hidden="true">→</span>
              <span className="sr-only">에서</span>
              <a href={m.current.url} target="_blank" rel="noreferrer">
                {reportLabel(m.current)}
              </a>
              <span className="rno mono">{m.current.rcept_no}</span>
            </p>
          </div>
          <div className="badges">
            <span className="ai-badge">AI 생성 · 사람 검토</span>
            {badges}
          </div>
        </div>
        <nav className="tabs" aria-label="리포트 구역">
          <TabList tabs={tabs} active={tab} onChange={(t) => go(t)} label="리포트 구역" idPrefix="report" />
        </nav>
      </header>

      <div className={`rbody${rail ? "" : " no-rail"}`}>
        <main className="rmain" id="report-panel" role="tabpanel" aria-labelledby={`report-tab-${tab}`} tabIndex={-1}>
          {tab === "overview" && <Overview rep={rep} go={go} />}
          {tab === "changes" && <Changes rep={rep} focus={focus} editable={editable} onEdit={onEdit} key={focus || "all"} />}
          {tab === "numbers" && <Numbers rep={rep} editable={editable} onEdit={onEdit} />}
          {tab === "business" && <BusinessView business={rep.business} />}
          {tab === "governance" && <GovernanceView gov={rep.governance} />}
          {tab === "market" && <MarketView valuation={rep.valuation} />}
          {tab === "tables" && <Tables rep={rep} />}
          {tab === "runs" && <Runs rep={rep} />}
          {tab === "parsing" && <Parsing rep={rep} />}
          <footer className="foot">
            <span>
              출처: DART(금융감독원 전자공시) ·{" "}
              {m.sample_data ? "이 화면의 회사·수치는 시연용 가상 데이터입니다." : "원문 링크에서 반드시 확인하세요."}
            </span>
            {footer}
          </footer>
        </main>
        {rail}
      </div>
    </div>
  );
}
