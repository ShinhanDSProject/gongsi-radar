// 공용 선 그래프(SVG). 시장 화면의 지수·시가총액 추이와 기업 종가 추이가 같이 쓴다.
// - 폭은 부모 요소를 따라간다(ResizeObserver). viewBox를 실제 px 폭과 같게 둬서 글자가 늘어나지 않는다.
// - y축은 1·2·2.5·5×10ⁿ 간격의 "보기 좋은" 눈금, x축은 월 눈금("25.12")을 폭에 맞춰 솎아 낸다.
// - 마우스를 올리거나, 초점을 둔 뒤 ←·→(PageUp·PageDown·Home·End)로 십자선을 옮기면 날짜·값을 보여 준다.
// [원칙] 색은 값의 좋고 나쁨을 뜻하지 않는다 — 선은 한 가지 색(accent)으로만 그린다.
import { useId, useMemo, useState, type KeyboardEvent, type PointerEvent } from "react";
import { fmtYmd } from "../lib/format";
import { useElementWidth } from "../lib/useElementWidth";

export interface LinePoint {
  d: string; // YYYY-MM-DD (YYYYMMDD도 받는다)
  v: number;
}

// 눈금 간격: 대략 range/count 근처의 1·2·2.5·5·10 × 10ⁿ
function niceStep(raw: number): number {
  if (!(raw > 0)) return 1;
  const p = Math.pow(10, Math.floor(Math.log10(raw)));
  const e = raw / p;
  const m = e <= 1 ? 1 : e <= 2 ? 2 : e <= 2.5 ? 2.5 : e <= 5 ? 5 : 10;
  return m * p;
}

export function niceTicks(lo: number, hi: number, count: number): number[] {
  if (lo === hi) {
    const pad = Math.abs(lo) * 0.01 || 1;
    lo -= pad;
    hi += pad;
  }
  const step = niceStep((hi - lo) / Math.max(1, count));
  const start = Math.floor(lo / step) * step;
  const end = Math.ceil(hi / step) * step;
  const out: number[] = [];
  for (let v = start, k = 0; v <= end + step * 1e-9 && k < 50; v = start + ++k * step) {
    out.push(Number(v.toPrecision(12)));
  }
  return out;
}

function ym(d: string): { y: number; m: number } | null {
  const m = /^(\d{4})-?(\d{2})/.exec(d);
  return m ? { y: Number(m[1]), m: Number(m[2]) } : null;
}

// 월이 바뀌는 첫 점마다 눈금 후보를 두고, 폭에 맞게 1·2·3·6·12개월 간격으로 솎는다
function monthTicks(data: LinePoint[], maxTicks: number): { i: number; label: string }[] {
  const cand: { i: number; key: number; label: string }[] = [];
  let prev = -1;
  data.forEach((p, i) => {
    const t = ym(p.d);
    if (!t) return;
    const key = t.y * 12 + (t.m - 1);
    if (i > 0 && key !== prev) cand.push({ i, key, label: `${String(t.y).slice(2)}.${String(t.m).padStart(2, "0")}` });
    prev = key;
  });
  if (cand.length < 2) return [];
  const stride = [1, 2, 3, 6, 12, 24].find((k) => Math.ceil(cand.length / k) <= Math.max(2, maxTicks)) ?? 24;
  return cand.filter((c) => c.key % stride === 0).map(({ i, label }) => ({ i, label }));
}

export default function LineChart({
  data,
  format,
  axisFormat,
  label,
  height = 220,
  emptyText = "추이 데이터가 없습니다.",
}: {
  data: LinePoint[];
  format: (v: number) => string; // 툴팁·요약에 쓰는 값 표기
  axisFormat?: (v: number) => string; // y축 눈금 표기(없으면 format)
  label: string; // 그래프 이름(스크린리더 요약 앞머리)
  height?: number;
  emptyText?: string;
}) {
  const [wrapRef, width] = useElementWidth<HTMLDivElement>(640);
  const [active, setActive] = useState<number | null>(null);
  const [keyboard, setKeyboard] = useState(false);
  const liveId = useId();
  const axisFmt = axisFormat ?? format;

  const g = useMemo(() => {
    const n = data.length;
    if (n < 2) return null;
    const W = Math.max(200, width);
    const H = height;
    const vs = data.map((p) => p.v);
    let lo = Infinity;
    let hi = -Infinity;
    for (const v of vs) {
      if (v < lo) lo = v;
      if (v > hi) hi = v;
    }
    const padT = 10;
    const padB = 24;
    const padR = 12;
    const ticks = niceTicks(lo, hi, Math.max(3, Math.round((H - padT - padB) / 48)));
    const t0 = ticks[0];
    const t1 = ticks[ticks.length - 1];
    // 왼쪽 여백은 가장 긴 눈금 글자에 맞춘다(11px 글자 기준 대략 폭)
    const longest = Math.max(...ticks.map((t) => axisFmt(t).length));
    const padL = Math.min(96, 12 + longest * 7);
    const innerW = W - padL - padR;
    const innerH = H - padT - padB;
    const x = (i: number) => padL + (i / (n - 1)) * innerW;
    const y = (v: number) => padT + (1 - (v - t0) / (t1 - t0 || 1)) * innerH;
    const pts = data.map((p, i) => `${x(i).toFixed(1)},${y(p.v).toFixed(1)}`).join(" ");
    const area = `${padL},${(H - padB).toFixed(1)} ${pts} ${x(n - 1).toFixed(1)},${(H - padB).toFixed(1)}`;
    const months = monthTicks(data, Math.floor(innerW / 56));
    return { n, W, H, padL, padR, padT, padB, innerW, ticks, x, y, pts, area, months, lo, hi };
  }, [data, width, height, axisFmt]);

  if (!g) return <p className="hint">{emptyText}</p>;

  const first = data[0];
  const last = data[data.length - 1];
  const summary = `${label}: ${fmtYmd(first.d)} ${format(first.v)}부터 ${fmtYmd(last.d)} ${format(last.v)}까지, 최고 ${format(g.hi)}, 최저 ${format(g.lo)}. 초점을 두고 좌우 화살표로 날짜별 값을 볼 수 있습니다.`;

  const onMove = (e: PointerEvent<SVGSVGElement>) => {
    const box = e.currentTarget.getBoundingClientRect();
    const px = ((e.clientX - box.left) / (box.width || 1)) * g.W;
    const i = Math.round(((px - g.padL) / g.innerW) * (g.n - 1));
    setKeyboard(false);
    setActive(Math.max(0, Math.min(g.n - 1, i)));
  };
  const onKey = (e: KeyboardEvent<HTMLDivElement>) => {
    const cur = active ?? g.n - 1;
    const page = Math.max(1, Math.round(g.n / 12));
    let next: number | null = null;
    if (e.key === "ArrowLeft") next = cur - 1;
    else if (e.key === "ArrowRight") next = cur + 1;
    else if (e.key === "PageUp") next = cur - page;
    else if (e.key === "PageDown") next = cur + page;
    else if (e.key === "Home") next = 0;
    else if (e.key === "End") next = g.n - 1;
    else if (e.key === "Escape") {
      setActive(null);
      return;
    }
    if (next == null) return;
    e.preventDefault();
    setKeyboard(true);
    setActive(Math.max(0, Math.min(g.n - 1, next)));
  };

  const p = active != null ? data[active] : null;
  const ax = active != null ? g.x(active) : 0;
  // 툴팁이 카드 밖으로 나가지 않게 양 끝에서는 정렬을 바꾼다
  const tipAlign = ax < 90 ? "left" : ax > g.W - 90 ? "right" : "center";

  return (
    <div
      ref={wrapRef}
      className="lc"
      tabIndex={0}
      role="group"
      aria-roledescription="선 그래프"
      aria-label={summary}
      aria-describedby={keyboard && p ? liveId : undefined}
      onKeyDown={onKey}
      onFocus={() => {
        if (active == null) {
          setKeyboard(true);
          setActive(g.n - 1);
        }
      }}
      onBlur={() => {
        setActive(null);
        setKeyboard(false);
      }}
    >
      <svg
        className="lc-svg"
        width={g.W}
        height={g.H}
        viewBox={`0 0 ${g.W} ${g.H}`}
        aria-hidden="true"
        onPointerMove={onMove}
        onPointerLeave={() => !keyboard && setActive(null)}
      >
        {g.ticks.map((t) => (
          <g key={t}>
            <line className="lc-grid" x1={g.padL} x2={g.W - g.padR} y1={g.y(t)} y2={g.y(t)} />
            <text className="lc-lbl" x={g.padL - 8} y={g.y(t) + 4} textAnchor="end">
              {axisFmt(t)}
            </text>
          </g>
        ))}
        {g.months.length ? (
          g.months.map((m) => (
            <text key={m.i} className="lc-lbl" x={g.x(m.i)} y={g.H - 6} textAnchor="middle">
              {m.label}
            </text>
          ))
        ) : (
          <>
            <text className="lc-lbl" x={g.padL} y={g.H - 6}>{fmtYmd(first.d)}</text>
            <text className="lc-lbl" x={g.W - g.padR} y={g.H - 6} textAnchor="end">{fmtYmd(last.d)}</text>
          </>
        )}
        <polygon className="lc-area" points={g.area} />
        <polyline className="lc-line" points={g.pts} />
        {p ? (
          <>
            <line className="lc-cross" x1={ax} x2={ax} y1={g.padT} y2={g.H - g.padB} />
            <circle className="lc-dot" cx={ax} cy={g.y(p.v)} r={4.5} />
          </>
        ) : (
          <circle className="lc-dot" cx={g.x(g.n - 1)} cy={g.y(last.v)} r={4} />
        )}
      </svg>
      {p && (
        <div className={`lc-tip a-${tipAlign}`} style={{ left: ax }} aria-hidden="true">
          <span className="lc-tip-d">{fmtYmd(p.d)}</span>
          <b className="num">{format(p.v)}</b>
        </div>
      )}
      {/* 키보드로 옮길 때만 읽어 준다(마우스 이동마다 읽으면 시끄럽다) */}
      <span id={liveId} className="sr-only" aria-live="polite">
        {keyboard && p ? `${fmtYmd(p.d)} ${format(p.v)}` : ""}
      </span>
    </div>
  );
}
