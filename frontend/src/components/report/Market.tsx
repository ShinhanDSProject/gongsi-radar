// 시장 지표 탭(§6.5). TTM·PER·PBR은 전부 계산식 카드로만 보인다.
// [원칙] 판단 문구(저평가·고평가·매수 등)를 화면에서도 만들지 않는다 — 숫자와 계산 과정, 기준일, 출처만.
import type { Valuation } from "../../api/types";
import { dartUrl, fmtKRW, fmtNum, fmtYmd, REPRT_LABEL } from "../../lib/format";
import { FormulaCard } from "../FormulaView";
import LineChart from "../LineChart";
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

// 종가 선 그래프. 공용 LineChart로 그린다(축 눈금·십자선·키보드 탐색). 값 판단 없이 모양만
export function PriceSparkline({ prices }: { prices: { d: string; c: number }[] }) {
  return (
    <LineChart
      data={prices.map((p) => ({ d: p.d, v: p.c }))}
      format={(v) => `${fmtNum(v, 0)}원`}
      axisFormat={(v) => fmtNum(v, 0)}
      label="종가 추이"
      height={200}
      emptyText="시세 이력이 없습니다."
    />
  );
}
