// 수치·관련 서술 탭. 계정 변화(코드 계산)와 회사가 밝힌 이유(원문 인용)를 나란히 둔다.
// 각 계정에는 §6.2 계산식(변동액·증감률·robust z·중요성)을 펼쳐 볼 수 있는 단추가 붙는다.
import { Fragment, useState } from "react";
import type { Account, RadarReport } from "../../api/types";
import { fmtKRW, fmtPct, LEVEL_KEY } from "../../lib/format";
import { FormulaExpander, FormulaList } from "../FormulaView";
import { Checks, Cite, Level, VPill } from "../ui";
import { EditBox, type OnEdit } from "./Changes";
import { YoyChart } from "./Overview";

function Quote({ text, sentence, clause }: { text: string; sentence?: string | null; clause?: string | null }) {
  const s = sentence || text;
  if (clause && s.includes(clause)) {
    const a = s.indexOf(clause);
    const b = a + clause.length;
    return (
      <blockquote>
        {s.slice(0, a)}
        <mark>{clause}</mark>
        {s.slice(b)}
      </blockquote>
    );
  }
  return <blockquote>{s}</blockquote>;
}

export function Numbers({ rep, editable, onEdit }: { rep: RadarReport; editable: boolean; onEdit: OnEdit }) {
  const [showAll, setShowAll] = useState(false);
  const fsLabel = rep.meta.fs_div === "OFS" ? "별도 기준" : "연결 기준";
  return (
    <div className="stack">
      <section className="panel">
        <header className="panel-h">
          <h2>전년 대비 증감률</h2>
          <span className="hint">재무 API 값을 코드로 계산 · {fsLabel}</span>
        </header>
        <YoyChart rels={rep.relations} />
      </section>
      {rep.relations.map((r) => {
        const acct: Partial<Account> = rep.accounts.find((a) => a.key === r.account_key) || {};
        return (
          <article className={`rel l-${LEVEL_KEY[r.level]}`} key={r.account_key} id={`r-${r.account_key}`}>
            <header className="rel-h">
              <h3>{r.account_nm}</h3>
              <span className="rel-fig num">
                {fmtKRW(r.prior)} → {fmtKRW(r.current)} <b>{fmtPct(r.yoy_pct)}</b>
              </span>
              <Level l={r.level} />
              <VPill v={r.verification} />
            </header>
            {(acct.flags || []).length > 0 && (
              <p className="flags">
                {acct.flags!.map((f) => (
                  <span key={f} className="tag">
                    {f}
                  </span>
                ))}
              </p>
            )}
            <p className="statement">{r.statement}</p>
            {r.statement_before_rewrite && <p className="note">재작성 전: “{r.statement_before_rewrite}”</p>}
            {r.evidence.map((e, i) => (
              <div className="evidence" key={e.pid}>
                <span className="ev-label">
                  {i === 0 ? "근거" : "함께 본 문단"} · {e.section_path}
                </span>
                <Quote text={e.text} sentence={e.sentence} clause={i === 0 ? r.reason_clause : null} />
                <Cite id={e.pid} />
              </div>
            ))}
            <p className="why">판정 근거: {r.why}</p>
            <FormulaExpander formulas={acct.formulas} />
            <details className="rel-checks">
              <summary>
                검증 {r.verification.checks.length}항목{r.verification.judge ? ` · 2단 판정 ${r.verification.judge}` : ""}
              </summary>
              <Checks checks={r.verification.checks} />
            </details>
            {r.attempts.length > 1 && (
              <ol className="attempts">
                {r.attempts.map((a) => (
                  <li key={a.attempt} className={`att-${a.status === "반려" ? "bad" : "good"}`}>
                    <b>
                      {a.attempt}차 {a.status}
                    </b>
                    {a.fault_injected ? <span className="tag">시연용 오류 주입</span> : null}
                    <span>{a.reason}</span>
                  </li>
                ))}
              </ol>
            )}
            {editable && <EditBox id={r.account_key} value={r.statement} onSave={onEdit} label="문장 고치기" />}
          </article>
        );
      })}
      <section className="panel">
        <header className="panel-h">
          <h2>전체 계정</h2>
          <button type="button" className="link" aria-expanded={showAll} onClick={() => setShowAll((v) => !v)}>
            {showAll ? "접기" : `${rep.accounts.length}개 펼치기`}
          </button>
        </header>
        {showAll && <AccountsTable accounts={rep.accounts} />}
      </section>
    </div>
  );
}

function AccountsTable({ accounts }: { accounts: Account[] }) {
  const [open, setOpen] = useState<string | null>(null);
  const hasFx = accounts.some((a) => (a.formulas?.length ?? 0) > 0);
  return (
    <div className="scroll-x">
      <table className="grid-table">
        <thead>
          <tr>
            <th scope="col">계정</th>
            <th scope="col">구분</th>
            <th scope="col" className="r">전기</th>
            <th scope="col" className="r">당기</th>
            <th scope="col" className="r">증감률</th>
            <th scope="col" className="r">robust z</th>
            <th scope="col">플래그</th>
            {hasFx && <th scope="col">계산식</th>}
          </tr>
        </thead>
        <tbody>
          {accounts.map((a) => {
            const isOpen = open === a.key;
            const n = a.formulas?.length ?? 0;
            return (
              <Fragment key={a.key}>
                <tr className={a.flags.length ? "flagged" : ""}>
                  <td>
                    {a.account_nm}
                    {a.is_key ? <span className="tag">핵심</span> : null}
                  </td>
                  <td>{a.sj_div}</td>
                  <td className="r num">{fmtKRW(a.prior)}</td>
                  <td className="r num">{fmtKRW(a.current)}</td>
                  <td className="r num">{fmtPct(a.yoy_pct)}</td>
                  <td className="r num">{a.robust_z == null ? "—" : a.robust_z.toFixed(1)}</td>
                  <td>{a.flags.join(" · ")}</td>
                  {hasFx && (
                    <td>
                      {n > 0 && (
                        <button
                          type="button"
                          className="fx-toggle"
                          aria-expanded={isOpen}
                          aria-controls={`fx-${a.key}`}
                          onClick={() => setOpen(isOpen ? null : a.key)}
                        >
                          <span className="caret" aria-hidden="true">▸</span>
                          {n}
                        </button>
                      )}
                    </td>
                  )}
                </tr>
                {isOpen && (
                  <tr className="sub-row" id={`fx-${a.key}`}>
                    <td colSpan={8}>
                      <FormulaList formulas={a.formulas} />
                    </td>
                  </tr>
                )}
              </Fragment>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
