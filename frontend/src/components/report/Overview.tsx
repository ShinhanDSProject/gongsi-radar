// 개요 탭. web/src/views.jsx의 Overview·YoyChart를 옮기고, §6.1 summary·reviewPassed가 있으면 함께 보인다.
import type { RadarReport, Relation } from "../../api/types";
import { fmtPct, overviewSentence } from "../../lib/format";
import { Edit, Level, Topic, VPill } from "../ui";
import type { ReportTab } from "./ReportView";

export function Overview({ rep, go }: { rep: RadarReport; go: (t: ReportTab, id?: string) => void }) {
  const top = rep.changes.slice(0, 6);
  const vs = rep.metrics.verification || {};
  const loops = rep.relations.filter((r) => r.attempts.length > 1);
  return (
    <div className="stack">
      {/* AI가 쓴 개요 문장(summary)이 있으면 그것을, 없으면 코드가 만든 문장을 쓴다.
          dangerouslySetInnerHTML을 쓰지 않는다 — 모델 출력은 텍스트로만 그린다 */}
      <p className="lead">{rep.summary?.trim() || overviewSentence(rep)}</p>

      {rep.reviewPassed === false && (rep.reviewIssues?.length ?? 0) > 0 && (
        <section className="panel" aria-label="자동 검토 지적">
          <header className="panel-h">
            <h2>자동 검토 지적</h2>
            <span className="pill v-warn">사람 확인 필요</span>
          </header>
          <ul className="warns">
            {rep.reviewIssues!.map((s, i) => (
              <li key={i}>{s}</li>
            ))}
          </ul>
        </section>
      )}

      <section className="panel">
        <header className="panel-h">
          <h2>먼저 볼 변경</h2>
          <button type="button" className="link" onClick={() => go("changes")}>
            전체 {rep.changes.length}건 보기
          </button>
        </header>
        <ul className="brief">
          {top.map((c) => (
            <li key={c.id}>
              <button type="button" className="brief-row" onClick={() => go("changes", c.id)}>
                <span className="brief-chips">
                  <Topic t={c.topic} />
                  <Edit e={c.edit_type} />
                </span>
                <span className="brief-sum">{c.summary}</span>
                <span className="brief-sect">{c.section_path.split(" > ").slice(-1)[0]}</span>
              </button>
            </li>
          ))}
        </ul>
      </section>

      <section className="panel">
        <header className="panel-h">
          <h2>수치 변화와 회사 서술</h2>
          <button type="button" className="link" onClick={() => go("numbers")}>
            근거 보기
          </button>
        </header>
        <YoyChart rels={rep.relations} />
      </section>

      <section className="panel">
        <header className="panel-h">
          <h2>검증</h2>
        </header>
        <div className="vsum">
          {Object.entries(vs).map(([k, n]) => (
            <span key={k} className="vsum-item">
              <VPill v={{ status: k as never }} /> <b className="num">{n}</b>건
            </span>
          ))}
        </div>
        {loops.map((r) => (
          <p key={r.account_key} className="note">
            {r.account_nm}: {r.attempts[0].status} → {r.attempts.length}차 {r.attempts[r.attempts.length - 1].status}
            {r.attempts[0].fault_injected ? " (시연용 오류 주입)" : ""}. {r.attempts[0].reason}
          </p>
        ))}
      </section>

      {(rep.citations?.length ?? 0) > 0 && (
        <section className="panel">
          <header className="panel-h">
            <h2>근거 문서</h2>
            <span className="hint">{rep.citations!.length}건</span>
          </header>
          <ul className="flex flex-wrap gap-1.5">
            {rep.citations!.map((c) => (
              <li key={c}>
                <code className="bg-sunken rounded px-1.5 py-0.5">{c}</code>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}

// 증감률을 한 축에 그린 막대(0을 기준선으로, 같은 척도)
export function YoyChart({ rels }: { rels: Relation[] }) {
  if (!rels.length) return <p className="hint">관련 서술을 찾은 계정이 없습니다.</p>;
  const vals = rels.map((r) => r.yoy_pct || 0);
  const lo = Math.min(-100, Math.floor(Math.min(...vals) / 50) * 50);
  const hi = Math.max(100, Math.ceil(Math.max(...vals) / 50) * 50);
  const x = (v: number) => ((v - lo) / (hi - lo)) * 100;
  // 축 눈금이 너무 촘촘해지지 않게 범위에 따라 간격을 넓힌다
  const step = hi - lo > 400 ? 100 : 50;
  const ticks: number[] = [];
  for (let t = Math.ceil(lo / step) * step; t <= hi; t += step) ticks.push(t);
  return (
    <div className="yoy" role="img" aria-label={`계정별 전년 대비 증감률: ${rels.map((r) => `${r.account_nm} ${fmtPct(r.yoy_pct)}`).join(", ")}`}>
      <div className="yoy-axis" aria-hidden="true">
        <span />
        <div className="yoy-ticks">
          {ticks.map((t) => (
            <span key={t} className={`tick${t === 0 ? " zero" : ""}`} style={{ left: `${x(t)}%` }}>
              {t > 0 ? `+${t}` : t}%
            </span>
          ))}
        </div>
        <span />
      </div>
      {rels.map((r) => {
        const v = r.yoy_pct || 0;
        const a = x(Math.min(0, v));
        const b = x(Math.max(0, v));
        return (
          <div className="yoy-row" key={r.account_key} aria-hidden="true">
            <span className="yoy-name">{r.account_nm}</span>
            <div className="yoy-track">
              {ticks.map((t) => (
                <span key={t} className={`gridline${t === 0 ? " zero" : ""}`} style={{ left: `${x(t)}%` }} />
              ))}
              <span className={`bar ${v < 0 ? "neg" : "pos"}`} style={{ left: `${a}%`, width: `${Math.max(0.6, b - a)}%` }} />
              <span className={`bar-label ${v < 0 ? "neg" : "pos"}`} style={v < 0 ? { right: `${100 - a}%` } : { left: `${b}%` }}>
                {fmtPct(r.yoy_pct)}
              </span>
            </div>
            <Level l={r.level} />
          </div>
        );
      })}
    </div>
  );
}
