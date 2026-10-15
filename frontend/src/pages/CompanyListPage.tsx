import { useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api, qs } from "../api/client";
import type { CompanyRow } from "../api/types";
import { ErrorText } from "../components/ui";
import { fmtKRW, fmtMultiple, fmtRate } from "../lib/format";

type SortKey = "corpName" | "stockCode" | "induty" | "revenue" | "opMarginPct" | "marketCap" | "per" | "pbr" | "hasFilings";

const COLS: { key: SortKey; label: string; num?: boolean }[] = [
  { key: "corpName", label: "회사" },
  { key: "stockCode", label: "종목코드" },
  { key: "induty", label: "업종" },
  { key: "revenue", label: "매출", num: true },
  { key: "opMarginPct", label: "영업이익률", num: true },
  { key: "marketCap", label: "시가총액", num: true },
  { key: "per", label: "PER", num: true },
  { key: "pbr", label: "PBR", num: true },
  { key: "hasFilings", label: "원문" },
];

export default function CompanyListPage() {
  const [params, setParams] = useSearchParams();
  const q = params.get("q") ?? "";
  const [text, setText] = useState(q);
  const [sort, setSort] = useState<{ key: SortKey; dir: 1 | -1 }>({ key: "marketCap", dir: -1 });

  // 입력이 멈추고 0.3초 뒤에 검색한다(타자마다 서버를 부르지 않게)
  useEffect(() => {
    const t = setTimeout(() => {
      if (text !== q) setParams(text ? { q: text } : {}, { replace: true });
    }, 300);
    return () => clearTimeout(t);
  }, [text, q, setParams]);

  const list = useQuery({
    queryKey: ["companies", q],
    queryFn: () => api.get<CompanyRow[]>(`/api/companies${qs({ q, limit: 50 })}`),
  });

  const rows = useMemo(() => {
    const data = [...(list.data ?? [])];
    // null은 정렬 방향과 상관없이 항상 맨 아래로
    data.sort((a, b) => {
      const x = a[sort.key];
      const y = b[sort.key];
      if (x == null && y == null) return 0;
      if (x == null) return 1;
      if (y == null) return -1;
      if (typeof x === "number" && typeof y === "number") return (x - y) * sort.dir;
      return String(x).localeCompare(String(y), "ko") * sort.dir;
    });
    return data;
  }, [list.data, sort]);

  const toggleSort = (key: SortKey) =>
    setSort((s) => (s.key === key ? { key, dir: s.dir === 1 ? -1 : 1 } : { key, dir: COLS.find((c) => c.key === key)?.num ? -1 : 1 }));

  return (
    <div className="stack">
      <div className="page-h">
        <h1>기업</h1>
        <span className="hint">재무 API·시세로 코드가 계산한 값입니다. 계산 과정은 기업 상세에서 볼 수 있습니다.</span>
      </div>
      <div className="panel">
        <label htmlFor="company-q" className="flabel">회사명·종목코드·고유번호</label>
        <input id="company-q" type="search" value={text} placeholder="예) 샘플소재, 999001" onChange={(e) => setText(e.target.value)} />
      </div>
      <section className="panel" aria-label="기업 목록">
        {list.isLoading && <p className="hint">불러오는 중…</p>}
        <ErrorText error={list.error} />
        {list.data?.length === 0 && <p className="hint">조건에 맞는 기업이 없습니다.</p>}
        {rows.length > 0 && (
          <div className="scroll-x">
            <table className="grid-table">
              <thead>
                <tr>
                  {COLS.map((c) => {
                    const active = sort.key === c.key;
                    return (
                      <th
                        key={c.key}
                        scope="col"
                        className={c.num ? "r" : ""}
                        aria-sort={active ? (sort.dir === 1 ? "ascending" : "descending") : "none"}
                      >
                        <button type="button" className="sort" onClick={() => toggleSort(c.key)}>
                          {c.label}
                          <span aria-hidden="true">{active ? (sort.dir === 1 ? "▲" : "▼") : "↕"}</span>
                        </button>
                      </th>
                    );
                  })}
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.corpCode}>
                    <td>
                      <Link to={`/companies/${encodeURIComponent(r.corpCode)}`}>{r.corpName}</Link>
                    </td>
                    <td className="mono">{r.stockCode}</td>
                    <td>{r.induty ?? "—"}</td>
                    <td className="r num">{fmtKRW(r.revenue)}</td>
                    <td className="r num">{fmtRate(r.opMarginPct, 1)}</td>
                    <td className="r num">{fmtKRW(r.marketCap)}</td>
                    <td className="r num">{fmtMultiple(r.per)}</td>
                    <td className="r num">{fmtMultiple(r.pbr)}</td>
                    <td>{r.hasFilings ? <span className="pill v-good">있음</span> : <span className="pill">없음</span>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {rows.some((r) => r.basis) && (
          <p className="hint">기준: {Array.from(new Set(rows.map((r) => r.basis).filter(Boolean))).join(" · ")}</p>
        )}
      </section>
    </div>
  );
}
