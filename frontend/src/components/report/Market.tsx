// 시장 지표 탭(§6.5). TTM·PER·PBR은 전부 계산식 카드로만 보인다.
// [원칙] 판단 문구(저평가·고평가·매수 등)를 화면에서도 만들지 않는다 — 숫자와 계산 과정, 기준일, 출처만.
import type { Valuation } from "../../api/types";
import { dartUrl, fmtKRW, fmtNum, fmtYmd, REPRT_LABEL } from "../../lib/format";
import { FormulaCard } from "../FormulaView";
import { Empty } from "../ui";

const MARKET_SOURCE: Record<string, string> = {
  sample: "시연용 샘플 시세",
  "data.go.kr": "공공데이터포털 금융위원회 주식시세정보",
};

export function MarketView({ valuation, note }: { valuation: Valuation | null | undefined; note?: string | null }) {
  if (!valuation) {
    return (
      <div className="stack">
        <Empty>시장 지표가 없습니다.</Empty>
        {note && <p className="note">{note}</p>}
      </div>
    );
  }
  const v = valuation;
  return (
    <div className="stack">
      <section className="panel">
        <header className="panel-h">
          <h2>기준</h2>
          <span className="hint">
            기준일 {fmtYmd(v.asOf)} · {v.marketSource ? MARKET_SOURCE[v.marketSource] ?? v.marketSource : "시세 출처 없음"}
          </span>
        </header>
        <dl className="kv">
          <dt>재무 범위</dt>
          <dd>{v.fsDiv === "OFS" ? "별도" : "연결"}</dd>
          <dt>연간</dt>
          <dd>
            {v.annual.year} 사업보고서 ·{" "}
            <a href={dartUrl(v.annual.rceptNo)} target="_blank" rel="noreferrer" className="mono">
              {v.annual.rceptNo}
            </a>
          </dd>
          <dt>중간</dt>
          <dd>
            {v.interim ? (
              <>
                {v.interim.year} {REPRT_LABEL[v.interim.reprtCode] ?? v.interim.reprtCode} ·{" "}
                <a href={dartUrl(v.interim.rceptNo)} target="_blank" rel="noreferrer" className="mono">
                  {v.interim.rceptNo}
                </a>
              </>
            ) : (
              "없음(연간 값만 사용)"
            )}
          </dd>
          {v.price && (
            <>
              <dt>종가</dt>
              <dd className="num">
                {fmtNum(v.price.close, 0)}원 <span className="hint">({fmtYmd(v.price.basDt)})</span>
              </dd>
              <dt>상장주식수</dt>
              <dd className="num">{fmtNum(v.price.listedShares, 0)}주</dd>
              <dt>시가총액</dt>
              <dd className="num">{fmtKRW(v.price.marketCap)}</dd>
            </>
          )}
        </dl>
      </section>

      <section className="panel">
        <header className="panel-h">
          <h2>종가 추이</h2>
          <span className="hint">{v.prices.length ? `${fmtYmd(v.prices[0].d)} ~ ${fmtYmd(v.prices[v.prices.length - 1].d)}` : ""}</span>
        </header>
        <PriceSparkline prices={v.prices} />
      </section>

      <section className="panel">
        <header className="panel-h">
          <h2>지표 계산</h2>
          <span className="hint">TTM = 최근 연간 + 당해 중간 누적 − 전년 같은 중간 누적</span>
        </header>
        {v.metrics.length ? (
          <div className="fx-grid">
            {v.metrics.map((f) => (
              <FormulaCard key={f.id} f={f} />
            ))}
          </div>
        ) : (
          <p className="hint">계산한 지표가 없습니다.</p>
        )}
      </section>

      {(v.notes.length > 0 || note) && (
        <section className="panel">
          <header className="panel-h">
            <h2>참고</h2>
          </header>
          <ul className="fx-notes">
            {note && <li>{note}</li>}
            {v.notes.map((n, i) => (
              <li key={i}>{n}</li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}

// 종가 선 그래프. 축은 시작·끝 날짜와 최고·최저가만 적는다(값 판단 없이 모양만)
export function PriceSparkline({ prices }: { prices: { d: string; c: number }[] }) {
  if (prices.length < 2) return <p className="hint">시세 이력이 없습니다.</p>;
  const W = 640;
  const H = 180;
  const padL = 64;
  const padR = 12;
  const padT = 12;
  const padB = 28;
  const cs = prices.map((p) => p.c);
  const lo = Math.min(...cs);
  const hi = Math.max(...cs);
  const span = hi - lo || 1;
  const x = (i: number) => padL + (i / (prices.length - 1)) * (W - padL - padR);
  const y = (c: number) => padT + (1 - (c - lo) / span) * (H - padT - padB);
  const pts = prices.map((p, i) => `${x(i).toFixed(1)},${y(p.c).toFixed(1)}`).join(" ");
  const area = `${padL},${H - padB} ${pts} ${x(prices.length - 1).toFixed(1)},${H - padB}`;
  const last = prices[prices.length - 1];
  const mid = prices[Math.floor((prices.length - 1) / 2)];
  return (
    <svg
      className="spark"
      viewBox={`0 0 ${W} ${H}`}
      role="img"
      aria-label={`종가 추이 ${fmtYmd(prices[0].d)} ${fmtNum(prices[0].c, 0)}원부터 ${fmtYmd(last.d)} ${fmtNum(last.c, 0)}원까지, 최고 ${fmtNum(hi, 0)}원 최저 ${fmtNum(lo, 0)}원`}
    >
      <line className="axis" x1={padL} y1={H - padB} x2={W - padR} y2={H - padB} />
      <line className="axis" x1={padL} y1={padT} x2={padL} y2={H - padB} />
      <text className="lbl" x={padL - 6} y={y(hi) + 4} textAnchor="end">{fmtNum(hi, 0)}</text>
      <text className="lbl" x={padL - 6} y={y(lo) + 4} textAnchor="end">{fmtNum(lo, 0)}</text>
      <polygon className="area" points={area} />
      <polyline className="line" points={pts} />
      <circle className="dot" cx={x(prices.length - 1)} cy={y(last.c)} r={4} />
      <text className="lbl" x={padL} y={H - 8}>{fmtYmd(prices[0].d)}</text>
      <text className="lbl" x={x(Math.floor((prices.length - 1) / 2))} y={H - 8} textAnchor="middle">{fmtYmd(mid.d)}</text>
      <text className="lbl" x={W - padR} y={H - 8} textAnchor="end">{fmtYmd(last.d)}</text>
    </svg>
  );
}
