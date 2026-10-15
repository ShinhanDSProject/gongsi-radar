// 시장 화면(§9, 알파인더 /market 참고): 지수 추이 · 시가총액 추이 · 업종 지도 · 최근 정기보고서.
// 시장 필터(전체·유가·코스닥·코넥스)는 시가총액·업종 지도·최근 정기보고서에 적용되고, 지수 추이는 필터와 무관하다.
// [원칙] 판단 문구(저평가·매수 등)를 만들지 않는다 — 숫자·기준일·출처만.
// [원칙] 대체 지수(kind "proxy")는 추적 기업 시가총액으로 만든 값이다. 공식 코스피·코스닥처럼 보이게 두지 않는다.
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { ApiError, api, qs } from "../api/client";
import type { MarketCode, MarketIndex, MarketOverview, MarketRange, Source } from "../api/types";
import { SourceChip } from "../components/FormulaView";
import LineChart from "../components/LineChart";
import { defaultRange, PeriodChanges, RangeToggle, sliceRange } from "../components/market/PeriodChanges";
import SectorTreemap from "../components/market/SectorTreemap";
import { ErrorText, Expander } from "../components/ui";
import { fmtKRW, fmtKRWAxis, fmtNum, fmtYmd, REPRT_LABEL } from "../lib/format";

const MARKETS: MarketCode[] = ["ALL", "KOSPI", "KOSDAQ", "KONEX"];
// 서버가 markets를 못 보낸 경우에만 쓰는 이름
const MARKET_LABEL: Record<MarketCode, string> = { ALL: "전체", KOSPI: "유가", KOSDAQ: "코스닥", KONEX: "코넥스" };

const fmtIndex = (v: number) => fmtNum(v, 2);
const fmtCap = (v: number) => fmtKRW(v, "");

function SourceBlock({ sources }: { sources: Source[] }) {
  if (!sources.length) return null;
  return (
    <Expander label="기준·출처">
      <div className="flex flex-wrap gap-1">
        {sources.map((s, i) => (
          <SourceChip key={i} s={s} />
        ))}
      </div>
    </Expander>
  );
}

function IndexCard({ ix }: { ix: MarketIndex }) {
  const [range, setRange] = useState<MarketRange>(() => defaultRange(ix.availableRanges));
  const proxy = ix.kind === "proxy";
  return (
    <section className="panel" aria-labelledby={`ix-${ix.code}`}>
      <header className="panel-h">
        <h3 id={`ix-${ix.code}`} className="ix-name">
          {ix.name}
          {proxy && (
            <span className="chip proxy" title={ix.note}>
              대체 지수
            </span>
          )}
        </h3>
        <RangeToggle label={ix.name} value={range} available={ix.availableRanges} onChange={setRange} />
      </header>
      {proxy && <p className="note">{ix.note}</p>}
      <div className="hero">
        <span className="hero-v num">{ix.last == null ? "—" : fmtIndex(ix.last)}</span>
        <span className="hint">{ix.asOf ? `${fmtYmd(ix.asOf)} 종가` : "기준일 없음"}</span>
      </div>
      <div className="flex flex-col gap-1">
        <span className="sub">이전 시점 대비</span>
        <PeriodChanges changes={ix.changes} kind="pt" />
      </div>
      <LineChart data={sliceRange(ix.series, range)} format={fmtIndex} label={`${ix.name}${proxy ? "(대체 지수)" : ""} 추이`} height={200} />
      {!proxy && ix.note && <p className="hint">{ix.note}</p>}
      <SourceBlock sources={[ix.source]} />
    </section>
  );
}

function CapSection({ data, busy }: { data: MarketOverview; busy: boolean }) {
  const cap = data.capitalization;
  const [range, setRange] = useState<MarketRange>(() => defaultRange(cap.availableRanges));
  // 필터를 바꿔 고른 기간이 사라지면 쓸 수 있는 기간으로 돌린다
  const shown = cap.availableRanges.includes(range) ? range : defaultRange(cap.availableRanges);
  return (
    <section className="panel" aria-labelledby="sec-cap" aria-busy={busy}>
      <header className="panel-h">
        <h2 id="sec-cap">시가총액 추이</h2>
        <RangeToggle label="시가총액" value={shown} available={cap.availableRanges} onChange={setRange} note={cap.rangeNote} />
      </header>
      <div className="hero">
        <span className="hero-v num">{cap.total == null ? "—" : fmtCap(cap.total)}</span>
        <span className="hint">{data.asOf ? `${fmtYmd(data.asOf)} 기준` : "기준일 없음"}</span>
      </div>
      <div className="flex flex-col gap-1">
        <span className="sub">이전 시점 대비</span>
        <PeriodChanges changes={cap.changes} kind="won" />
      </div>
      <LineChart data={sliceRange(cap.series, shown)} format={fmtCap} axisFormat={fmtKRWAxis} label="시가총액 합계 추이" height={240} />
      {cap.rangeNote && <p className="hint">{cap.rangeNote}</p>}
      <SourceBlock sources={[cap.source]} />
    </section>
  );
}

function RecentFilings({ data }: { data: MarketOverview }) {
  const rows = data.recentFilings;
  return (
    <section className="panel" aria-labelledby="sec-filings">
      <header className="panel-h">
        <h2 id="sec-filings">최근 정기보고서</h2>
        <span className="hint">접수일 최신순 · 최대 30건</span>
      </header>
      {rows.length === 0 ? (
        <p className="hint">이 시장의 정기보고서가 없습니다.</p>
      ) : (
        <div className="scroll-x relative">
          <table className="grid-table">
            <thead>
              <tr>
                <th scope="col">접수일</th>
                <th scope="col">기업</th>
                <th scope="col">보고서</th>
                <th scope="col" className="r">시가총액</th>
                <th scope="col">원문</th>
                <th scope="col">
                  <span className="sr-only">분석</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {rows.map((f) => (
                <tr key={f.rceptNo}>
                  <td className="num whitespace-nowrap">{fmtYmd(f.rceptDt)}</td>
                  <td className="whitespace-nowrap">
                    <Link to={`/companies/${encodeURIComponent(f.corpCode)}`}>{f.corpName}</Link>
                    {f.stockCode && <span className="mono hint"> {f.stockCode}</span>}
                  </td>
                  <td className="whitespace-nowrap">
                    <a href={f.url} target="_blank" rel="noreferrer" title={`DART 원문 ${f.rceptNo}`}>
                      {f.reportNm}
                    </a>
                    {f.isCorrection && <span className="chip corr">정정</span>}
                  </td>
                  <td className="r num whitespace-nowrap">{fmtKRW(f.marketCap)}</td>
                  <td className="whitespace-nowrap">{f.hasDocument ? <span className="pill v-good">있음</span> : <span className="pill">없음</span>}</td>
                  <td className="whitespace-nowrap">
                    {/* 원문이 없으면 분석이 원문을 찾지 못해 실패한다. 누를 수 없는 링크를 두지 않고 사유를 보인다 */}
                    {f.reprtCode && f.bsnsYear != null && f.hasDocument ? (
                      <Link
                        to={`/analyses${qs({ company: f.corpCode, bsnsYear: f.bsnsYear, reprtCode: f.reprtCode })}`}
                        title={`${f.corpName} ${f.bsnsYear} ${REPRT_LABEL[f.reprtCode] ?? f.reprtCode}`}
                      >
                        이 보고서로 분석
                      </Link>
                    ) : (
                      <span className="hint" title="원문이 없어 비교 분석을 할 수 없습니다">{f.hasDocument ? "—" : "원문 없음"}</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

export default function MarketPage() {
  const [params, setParams] = useSearchParams();
  const raw = (params.get("market") ?? "ALL").toUpperCase() as MarketCode;
  const market: MarketCode = MARKETS.includes(raw) ? raw : "ALL";

  // 필터를 바꾸는 동안 이전 화면을 그대로 둔다(placeholderData) — 화면이 비었다 찼다 하지 않게
  const q = useQuery({
    queryKey: ["market", market],
    queryFn: () => api.get<MarketOverview>(`/api/market${qs({ market })}`),
    placeholderData: keepPreviousData,
  });

  const forbidden = q.error instanceof ApiError && (q.error.status === 403 || q.error.code === "FORBIDDEN");
  const d = q.data;
  const busy = q.isFetching && q.isPlaceholderData;
  const chips = d?.markets?.length ? d.markets : MARKETS.map((code) => ({ code, label: MARKET_LABEL[code], count: null as number | null }));

  return (
    <div className="stack">
      <div className="page-h">
        <h1>시장</h1>
        {d?.sample && <span className="sample">가상 샘플</span>}
        <span className="hint">
          {d ? `기준일 ${fmtYmd(d.asOf)} · ${d.universeNote}` : "지수·시가총액·업종 지도와 최근 정기보고서"}
        </span>
      </div>

      {forbidden ? (
        <div className="panel" role="alert">
          <h2>시세 조회 권한이 없습니다</h2>
          <p>
            시장 화면은 시세 조회 권한(<code>MARKET_DATA_READ</code>)이 있는 사용자만 볼 수 있습니다. 관리자에게 권한을 요청하세요.
          </p>
          <p className="hint">
            기업별 공시는 <Link to="/companies">기업</Link> 메뉴에서 볼 수 있습니다.
          </p>
        </div>
      ) : (
        <>
          {q.isLoading && <p className="hint">불러오는 중…</p>}
          {!d && <ErrorText error={q.error} fallback="시장 데이터를 불러오지 못했습니다." />}
        </>
      )}

      {d && !forbidden && (
        <>
          {/* 1. 지수 추이 — 시장 필터와 무관 */}
          <section aria-labelledby="sec-index" className="flex flex-col gap-2">
            <h2 id="sec-index" className="sec-h">지수 추이</h2>
            {d.indices.length ? (
              <div className="ix-grid">
                {d.indices.map((ix) => (
                  <IndexCard key={ix.code} ix={ix} />
                ))}
              </div>
            ) : (
              <p className="hint">지수 데이터가 없습니다.</p>
            )}
          </section>

          {/* 시장 필터: 아래 세 구역(시가총액·업종 지도·최근 정기보고서)에 적용 */}
          <div className="mkt-filter">
            <div className="filters" role="group" aria-label="시장 필터">
              {chips.map((m) => (
                <button
                  key={m.code}
                  type="button"
                  className="fchip"
                  aria-pressed={market === m.code}
                  onClick={() => setParams(m.code === "ALL" ? {} : { market: m.code }, { replace: true })}
                >
                  {m.label} {m.count != null && <span className="num">{m.count.toLocaleString("ko-KR")}</span>}
                </button>
              ))}
            </div>
            <span className="hint" aria-live="polite">
              {busy ? "불러오는 중…" : "시가총액·업종 지도·최근 정기보고서에 적용됩니다"}
            </span>
          </div>
          {q.error && <ErrorText error={q.error} fallback="이 시장의 데이터를 불러오지 못했습니다. 이전 결과를 보여 주고 있습니다." />}

          <div className={busy ? "stack opacity-60 transition-opacity" : "stack"}>
            {/* 2. 시가총액 추이 */}
            <CapSection data={d} busy={busy} />

            {/* 3. 업종 지도 */}
            <section className="panel" aria-labelledby="sec-sector" aria-busy={busy}>
              <header className="panel-h">
                <h2 id="sec-sector">업종 지도 · KSIC</h2>
                <span className="hint">칸을 누르면 하위 업종으로 들어갑니다</span>
              </header>
              <SectorTreemap root={d.sectors} />
            </section>

            {/* 4. 최근 정기보고서 */}
            <RecentFilings data={d} />
          </div>

          <section className="panel" aria-labelledby="sec-notes">
            <header className="panel-h">
              <h2 id="sec-notes">기준·참고</h2>
              {d.sample && <span className="sample">가상 샘플</span>}
            </header>
            <dl className="kv">
              <dt>대상</dt>
              <dd>{d.universeNote}</dd>
              <dt>시세 기준일</dt>
              <dd className="num">{fmtYmd(d.asOf)}</dd>
              <dt>시장 필터</dt>
              <dd>{chips.find((m) => m.code === d.market)?.label ?? d.market}</dd>
            </dl>
            {d.notes.length > 0 && (
              <ul className="fx-notes">
                {d.notes.map((n, i) => (
                  <li key={i}>{n}</li>
                ))}
              </ul>
            )}
          </section>
        </>
      )}
    </div>
  );
}
