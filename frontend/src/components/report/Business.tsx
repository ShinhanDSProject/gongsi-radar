// 사업 지표 탭(§6.3). 구조가 분명한 표만 규칙으로 뽑고, 검산을 통과한 행을 먼저 보인다.
// 검산에 실패한 행은 숨기지 않는다 — 토글을 끄면 그대로 보인다(사람이 원문과 대조할 몫).
import { Fragment, useState } from "react";
import type { Business, BusinessGroup, BusinessRowStatus } from "../../api/types";
import { fmtNum, fmtPct } from "../../lib/format";
import { FormulaExpander } from "../FormulaView";
import { Checks, Cite, Empty, Expander } from "../ui";

const ROW_TONE: Record<BusinessRowStatus, string> = {
  "검산 통과": "v-good",
  "검산 불일치": "v-bad",
  "검산 불가": "v-warn",
};

export function BusinessView({ business }: { business: Business | null | undefined }) {
  const [onlyPassed, setOnlyPassed] = useState(true);
  if (!business) return <Empty>사업 지표가 없습니다. (이 리포트에는 사업 지표 추출 결과가 포함되지 않았습니다.)</Empty>;
  const s = business.summary;
  return (
    <div className="stack">
      <section className="panel">
        <header className="panel-h">
          <h2>검산 요약</h2>
          <label className="fcheck">
            <input type="checkbox" checked={onlyPassed} onChange={(e) => setOnlyPassed(e.target.checked)} /> 검산 통과만 보기
          </label>
        </header>
        <div className="vsum">
          <span className="vsum-item">
            <span className="pill v-good">검산 통과</span> <b className="num">{s?.passed ?? 0}</b>행
          </span>
          <span className="vsum-item">
            <span className="pill v-bad">검산 불일치</span> <b className="num">{s?.failed ?? 0}</b>행
          </span>
          <span className="vsum-item">
            <span className="pill v-warn">검산 불가</span> <b className="num">{s?.unchecked ?? 0}</b>행
          </span>
        </div>
        {business.note && <p className="note">{business.note}</p>}
      </section>
      {!business.groups.length && <Empty>규칙으로 뽑을 수 있는 사업 지표 표가 없습니다.</Empty>}
      {business.groups.map((g, i) => (
        <GroupPanel key={`${g.kind}-${i}`} g={g} onlyPassed={onlyPassed} />
      ))}
    </div>
  );
}

function GroupPanel({ g, onlyPassed }: { g: BusinessGroup; onlyPassed: boolean }) {
  const rows = onlyPassed ? g.rows.filter((r) => r.status === "검산 통과") : g.rows;
  const hidden = g.rows.length - rows.length;
  return (
    <section className="panel" aria-label={g.title}>
      <header className="panel-h">
        <div className="flex flex-wrap items-baseline gap-2 min-w-0">
          <span className="chip topic t-biz">{g.kind}</span>
          <h3 className="text-[15px] font-semibold">{g.title}</h3>
          {g.unit && <span className="hint">단위 {g.unit}</span>}
        </div>
        <span className="hint">{g.sectionPath}</span>
      </header>
      <p className="ids">
        {g.priorPid && <Cite id={g.priorPid} />}
        {g.currentPid && <Cite id={g.currentPid} />}
      </p>
      {g.checks?.length > 0 && <Checks checks={g.checks} />}
      {rows.length > 0 ? (
        <div className="scroll-x">
          <table className="grid-table">
            <thead>
              <tr>
                <th scope="col">항목</th>
                <th scope="col">지표</th>
                <th scope="col" className="r">전기</th>
                <th scope="col" className="r">당기</th>
                <th scope="col" className="r">증감률</th>
                <th scope="col">검산</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r, ri) => {
                const vals = r.values.length ? r.values : [null];
                return (
                  <Fragment key={`${r.label}-${ri}`}>
                    {vals.map((v, vi) => (
                      <tr key={vi} className={r.status === "검산 통과" ? "" : "flagged"}>
                        {vi === 0 && <td rowSpan={vals.length}>{r.label}</td>}
                        <td>{v ? `${v.name}${v.unit ? ` (${v.unit})` : ""}` : "—"}</td>
                        <td className="r num">{v ? fmtNum(v.prior) : "—"}</td>
                        <td className="r num">{v ? fmtNum(v.current) : "—"}</td>
                        <td className="r num">{v ? fmtPct(v.yoyPct) : "—"}</td>
                        {vi === 0 && (
                          <td rowSpan={vals.length}>
                            <span className={`pill ${ROW_TONE[r.status] ?? ""}`}>{r.status}</span>
                            {r.checks?.length > 0 && (
                              <div className="mt-1">
                                <Expander label="검산 내역" count={r.checks.length}>
                                  <Checks checks={r.checks} />
                                </Expander>
                              </div>
                            )}
                          </td>
                        )}
                      </tr>
                    ))}
                  </Fragment>
                );
              })}
            </tbody>
          </table>
        </div>
      ) : (
        <p className="hint">검산을 통과한 행이 없습니다.</p>
      )}
      {hidden > 0 && <p className="hint">검산을 통과하지 못한 {hidden}행을 숨겼습니다. “검산 통과만 보기”를 끄면 보입니다.</p>}
      <FormulaExpander formulas={g.formulas} />
    </section>
  );
}
