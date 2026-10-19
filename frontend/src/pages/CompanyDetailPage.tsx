import { useQuery } from "@tanstack/react-query";
import { Fragment, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { api } from "../api/client";
import type { CompanyProfile, Financials } from "../api/types";
import { FormulaList } from "../components/FormulaView";
import { BusinessView } from "../components/report/Business";
import { GovernanceView } from "../components/report/Governance";
import { MarketView } from "../components/report/Market";
import { Empty, ErrorText, TabList } from "../components/ui";
import { dartUrl, fmtKRW, fmtYmd, REPRT_LABEL } from "../lib/format";
import GlossaryText from "../components/GlossaryText";

type CTab = "overview" | "financials" | "market" | "governance" | "filings";
const CTABS: CTab[] = ["overview", "financials", "market", "governance", "filings"];

export default function CompanyDetailPage() {
  const { corpCode = "" } = useParams();
  const [params, setParams] = useSearchParams();
  const raw = params.get("view") as CTab | null;
  const tab: CTab = raw && CTABS.includes(raw) ? raw : "overview";

  const profile = useQuery({
    queryKey: ["company", corpCode],
    queryFn: () => api.get<CompanyProfile>(`/api/companies/${encodeURIComponent(corpCode)}`),
  });

  if (profile.isLoading) return <p className="hint">불러오는 중…</p>;
  if (profile.error || !profile.data) return <ErrorText error={profile.error ?? new Error("기업을 찾을 수 없습니다.")} />;
  const p = profile.data;

  return (
    <div className="stack">
      <header className="rhead">
        <div className="rhead-inner">
          <div className="title-block">
            <h1>{p.company.corpName}</h1>
            <p className="cmp">
              <span className="mono">{p.company.stockCode}</span>
              <span>· 고유번호 <span className="mono">{p.company.corpCode}</span></span>
              {p.company.induty && <span>· {p.company.induty}</span>}
            </p>
          </div>
          <div className="badges">
            <Link to="/companies" className="link">기업 목록</Link>
          </div>
        </div>
        <nav className="tabs" aria-label="기업 정보 구역">
          <TabList
            label="기업 정보 구역"
            idPrefix="company"
            active={tab}
            onChange={(t) => setParams({ view: t }, { replace: true })}
            tabs={[
              { id: "overview", label: "개요" },
              { id: "financials", label: "재무" },
              { id: "market", label: "시장" },
              { id: "governance", label: "지배구조" },
              { id: "filings", label: "공시 목록", count: p.filings.length },
            ]}
          />
        </nav>
      </header>

      <div id="company-panel" role="tabpanel" aria-labelledby={`company-tab-${tab}`} className="min-w-0">
        {tab === "overview" && (
          <div className="stack">
            {p.notes.length > 0 && (
              <ul className="note list-disc pl-6">
                {p.notes.map((n, i) => (
                  <li key={i}><GlossaryText text={n} /></li>
                ))}
              </ul>
            )}
            <BusinessView business={p.business} />
          </div>
        )}
        {tab === "financials" && <FinancialsTable fin={p.financials} />}
        {tab === "market" && <MarketView valuation={p.valuation} note={p.valuationNote} />}
        {tab === "governance" && <GovernanceView gov={p.governance} />}
        {tab === "filings" && <Filings p={p} />}
      </div>
    </div>
  );
}

function FinancialsTable({ fin }: { fin: Financials | null | undefined }) {
  const [open, setOpen] = useState<number | null>(null);
  if (!fin || !fin.rows.length) return <Empty>재무 데이터가 없습니다.</Empty>;
  return (
    <section className="panel">
      <header className="panel-h">
        <h2>주요 계정</h2>
        <span className="hint">재무 API · {fin.fsDiv === "OFS" ? "별도" : "연결"} 기준 · 행을 펼치면 계산식</span>
      </header>
      <div className="scroll-x">
        <table className="grid-table">
          <thead>
            <tr>
              <th scope="col">계정</th>
              {fin.columns.map((c) => (
                <th key={c} scope="col" className="r">{c}</th>
              ))}
              <th scope="col">계산식</th>
            </tr>
          </thead>
          <tbody>
            {fin.rows.map((r, i) => {
              const isOpen = open === i;
              const n = r.formulas?.length ?? 0;
              return (
                <Fragment key={`${r.account}-${i}`}>
                  <tr>
                    <td><GlossaryText text={r.account} /></td>
                    {fin.columns.map((c, ci) => (
                      <td key={c} className="r num" title={r.values[ci] == null ? "" : `${r.values[ci]!.toLocaleString("ko-KR")}원`}>
                        {fmtKRW(r.values[ci] ?? null)}
                      </td>
                    ))}
                    <td>
                      {n > 0 ? (
                        <button
                          type="button"
                          className="fx-toggle"
                          aria-expanded={isOpen}
                          aria-controls={`fin-fx-${i}`}
                          aria-label={`${r.account} 계산식 ${n}개 ${isOpen ? "접기" : "펼치기"}`}
                          onClick={() => setOpen(isOpen ? null : i)}
                        >
                          <span className="caret" aria-hidden="true">▸</span>
                          {n}
                        </button>
                      ) : (
                        <span className="hint">—</span>
                      )}
                    </td>
                  </tr>
                  {isOpen && (
                    <tr className="sub-row" id={`fin-fx-${i}`}>
                      <td colSpan={fin.columns.length + 2}>
                        <FormulaList formulas={r.formulas} />
                      </td>
                    </tr>
                  )}
                </Fragment>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function Filings({ p }: { p: CompanyProfile }) {
  const navigate = useNavigate();
  if (!p.filings.length) return <Empty>공시 목록이 없습니다.</Empty>;
  const analyze = (bsnsYear: number, reprtCode: string) =>
    navigate(`/analyses?${new URLSearchParams({ company: p.company.stockCode || p.company.corpCode, bsnsYear: String(bsnsYear), reprtCode })}`);
  return (
    <section className="panel">
      <header className="panel-h">
        <h2>정기보고서</h2>
        <span className="hint">“이 보고서로 분석”은 새 분석 양식을 채워 줍니다(전년 같은 보고서와 비교).</span>
      </header>
      <div className="scroll-x">
        <table className="grid-table">
          <thead>
            <tr>
              <th scope="col">보고서</th>
              <th scope="col">접수일</th>
              <th scope="col">접수번호</th>
              <th scope="col">원문</th>
              <th scope="col"><span className="sr-only">분석</span></th>
            </tr>
          </thead>
          <tbody>
            {p.filings.map((f) => (
              <tr key={f.rceptNo}>
                <td>
                  {f.reportNm}
                  <span className="hint"> · {f.bsnsYear} {REPRT_LABEL[f.reprtCode] ?? f.reprtCode}</span>
                </td>
                <td className="num whitespace-nowrap">{fmtYmd(f.rceptDt)}</td>
                <td>
                  <a href={dartUrl(f.rceptNo)} target="_blank" rel="noreferrer" className="mono">{f.rceptNo}</a>
                </td>
                <td>{f.hasDocument ? <span className="pill v-good">있음</span> : <span className="pill">없음</span>}</td>
                <td>
                  <button type="button" className="btn ghost small" onClick={() => analyze(f.bsnsYear, f.reprtCode)}>
                    이 보고서로 분석
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
