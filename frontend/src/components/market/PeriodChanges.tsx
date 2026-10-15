// 시장 화면 공용 부품: "이전 시점 대비" 4칸 표, 기간(1년·3년·5년) 단추, 기간별 시계열 자르기.
// 등락 색은 한국 시장 관례(상승 빨강·하락 파랑)를 따르되, 색만으로 알리지 않게 ▲▼와 부호를 함께 쓴다.
import type { MarketRange, PeriodChange, SeriesPoint } from "../../api/types";
import { fmtDelta, fmtPct, fmtYmd } from "../../lib/format";

export const RANGES: { id: MarketRange; label: string; years: number }[] = [
  { id: "1Y", label: "1년", years: 1 },
  { id: "3Y", label: "3년", years: 3 },
  { id: "5Y", label: "5년", years: 5 },
];

// 처음 고를 기간: 1년이 있으면 1년, 없으면 데이터가 있는 첫 기간
export function defaultRange(available: MarketRange[]): MarketRange {
  return available.includes("1Y") ? "1Y" : available[0] ?? "1Y";
}

// 최신 날짜에서 N년 전까지만 남긴다(시리즈는 오래된 날짜 → 최신 순)
export function sliceRange(series: SeriesPoint[], range: MarketRange): SeriesPoint[] {
  if (!series.length) return series;
  const years = RANGES.find((r) => r.id === range)?.years ?? 1;
  const m = /^(\d{4})-?(\d{2})-?(\d{2})/.exec(series[series.length - 1].d);
  if (!m) return series;
  const cut = `${Number(m[1]) - years}-${m[2]}-${m[3]}`;
  return series.filter((p) => {
    const q = /^(\d{4})-?(\d{2})-?(\d{2})/.exec(p.d);
    return q ? `${q[1]}-${q[2]}-${q[3]}` >= cut : true;
  });
}

function tone(n: number | null | undefined): "up" | "down" | "flat" {
  if (n == null || n === 0 || Number.isNaN(n)) return "flat";
  return n > 0 ? "up" : "down";
}
const ARROW = { up: "▲", down: "▼", flat: "" } as const;
const TONE_SR = { up: "상승", down: "하락", flat: "보합" } as const;

export function PeriodChanges({ changes, kind }: { changes: PeriodChange[]; kind: "pt" | "won" }) {
  if (!changes.length) return null;
  return (
    <div className="pchg" role="list" aria-label="이전 시점 대비">
      {changes.map((c) => {
        const t = tone(c.pct);
        const span = c.from && c.to ? `${fmtYmd(c.from)} → ${fmtYmd(c.to)}` : undefined;
        return (
          <div key={c.period} className="pchg-cell" role="listitem" title={c.pct == null ? c.reason ?? "비교할 데이터가 없습니다" : span}>
            <span className="pchg-h">{c.label}</span>
            {c.pct == null ? (
              <>
                <span className="pchg-pct flat">—</span>
                <span className="pchg-d">{c.reason ?? "데이터 부족"}</span>
              </>
            ) : (
              <>
                <span className={`pchg-pct num ${t}`}>
                  <span aria-hidden="true">{ARROW[t]} </span>
                  <span className="sr-only">{TONE_SR[t]} </span>
                  {fmtPct(c.pct, 2)}
                </span>
                <span className={`pchg-d num ${t}`}>{fmtDelta(c.delta, kind)}</span>
              </>
            )}
          </div>
        );
      })}
    </div>
  );
}

// 기간 단추. 데이터가 없는 기간은 aria-disabled로 두어 초점·툴팁(사유)은 살린다
export function RangeToggle({
  value,
  available,
  onChange,
  note,
  label,
}: {
  value: MarketRange;
  available: MarketRange[];
  onChange: (r: MarketRange) => void;
  note?: string | null;
  label: string;
}) {
  return (
    <div className="seg" role="group" aria-label={`${label} 기간`}>
      {RANGES.map((r) => {
        const ok = available.includes(r.id);
        const why = note || "이 기간의 데이터가 없습니다";
        return (
          <button
            key={r.id}
            type="button"
            aria-pressed={value === r.id}
            aria-disabled={!ok}
            title={ok ? undefined : why}
            aria-label={ok ? undefined : `${r.label} (사용 불가: ${why})`}
            onClick={() => ok && onChange(r.id)}
          >
            {r.label}
          </button>
        );
      })}
    </div>
  );
}
