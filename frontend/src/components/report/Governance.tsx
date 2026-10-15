// 지배구조 탭(§6.4). 최대주주·임원·타법인 출자 표와 변동 목록, 그리고 관계도(인라인 SVG).
// 관계도는 대상 회사를 가운데, 주주(사람·법인)를 왼쪽 호, 출자 회사를 오른쪽 호에 놓는 방사형 배치다.
import type { ReactNode } from "react";
import { useNavigate } from "react-router-dom";
import type { Governance, GraphEdge, GraphNode } from "../../api/types";
import { dartUrl, fmtKRW, fmtNum, fmtRate } from "../../lib/format";
import { ChangeChip, Empty } from "../ui";

function fmtShares(n: number | null | undefined) {
  return n == null ? "—" : `${fmtNum(n, 0)}주`;
}
function fmtDeltaPct(p: number | null | undefined) {
  if (p == null) return "—";
  return `${p > 0 ? "+" : ""}${p.toFixed(2)}%p`;
}
function yesNo(v: string | boolean) {
  if (typeof v === "boolean") return v ? "예" : "아니오";
  return v || "—";
}

export function GovernanceView({ gov }: { gov: Governance | null | undefined }) {
  if (!gov) return <Empty>지배구조 정보가 없습니다. (이 리포트에는 지배구조 조회 결과가 포함되지 않았습니다.)</Empty>;
  return (
    <div className="stack">
      <section className="panel">
        <header className="panel-h">
          <h2>관계도</h2>
          <span className="hint">
            기준 <a href={dartUrl(gov.rceptNo)} target="_blank" rel="noreferrer" className="mono">{gov.rceptNo}</a>
            {gov.priorRceptNo && (
              <>
                {" "}· 비교 <a href={dartUrl(gov.priorRceptNo)} target="_blank" rel="noreferrer" className="mono">{gov.priorRceptNo}</a>
              </>
            )}
          </span>
        </header>
        <GovernanceGraph nodes={gov.graph?.nodes ?? []} edges={gov.graph?.edges ?? []} />
        {gov.note && <p className="note">{gov.note}</p>}
      </section>

      <section className="panel">
        <header className="panel-h">
          <h2>변동 내역</h2>
          <span className="hint">{gov.changes?.length ?? 0}건</span>
        </header>
        {gov.changes?.length ? (
          <ul className="flex flex-col gap-1.5">
            {gov.changes.map((c, i) => (
              <li key={i} className="flex gap-2 items-baseline">
                <span className="chip edit">{c.kind}</span>
                <span>{c.text}</span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="hint">전기 대비 바뀐 내용이 없습니다.</p>
        )}
      </section>

      <section className="panel">
        <header className="panel-h">
          <h2>최대주주 및 특수관계인</h2>
        </header>
        {gov.shareholders?.length ? (
          <div className="scroll-x">
            <table className="grid-table">
              <thead>
                <tr>
                  <th scope="col">성명</th>
                  <th scope="col">관계</th>
                  <th scope="col">주식 종류</th>
                  <th scope="col" className="r">기초 주식수</th>
                  <th scope="col" className="r">기초 지분율</th>
                  <th scope="col" className="r">기말 주식수</th>
                  <th scope="col" className="r">기말 지분율</th>
                  <th scope="col" className="r">증감</th>
                  <th scope="col">변동</th>
                </tr>
              </thead>
              <tbody>
                {gov.shareholders.map((s, i) => (
                  <tr key={i} className={s.change === "변동 없음" ? "" : "flagged"}>
                    <td>{s.name}</td>
                    <td>{s.relation}</td>
                    <td>{s.stockKind}</td>
                    <td className="r num">{fmtShares(s.beginShares)}</td>
                    <td className="r num">{fmtRate(s.beginPct)}</td>
                    <td className="r num">{fmtShares(s.endShares)}</td>
                    <td className="r num">{fmtRate(s.endPct)}</td>
                    <td className="r num">{fmtDeltaPct(s.deltaPct)}</td>
                    <td><ChangeChip c={s.change} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="hint">주주 정보가 없습니다.</p>
        )}
      </section>

      <section className="panel">
        <header className="panel-h">
          <h2>임원</h2>
        </header>
        {gov.executives?.length ? (
          <div className="scroll-x">
            <table className="grid-table">
              <thead>
                <tr>
                  <th scope="col">성명</th>
                  <th scope="col">직위</th>
                  <th scope="col">등기</th>
                  <th scope="col">상근</th>
                  <th scope="col">담당 업무</th>
                  <th scope="col">변동</th>
                </tr>
              </thead>
              <tbody>
                {gov.executives.map((e, i) => (
                  <tr key={i} className={e.change === "유지" ? "" : "flagged"}>
                    <td>{e.name}</td>
                    <td>
                      {e.position}
                      {e.priorPosition && e.priorPosition !== e.position && <span className="hint"> (이전 {e.priorPosition})</span>}
                    </td>
                    <td>{yesNo(e.registered)}</td>
                    <td>{yesNo(e.fullTime)}</td>
                    <td>{e.duty || "—"}</td>
                    <td><ChangeChip c={e.change} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="hint">임원 정보가 없습니다.</p>
        )}
      </section>

      <section className="panel">
        <header className="panel-h">
          <h2>타법인 출자</h2>
        </header>
        {gov.investments?.length ? (
          <div className="scroll-x">
            <table className="grid-table">
              <thead>
                <tr>
                  <th scope="col">법인명</th>
                  <th scope="col">출자 목적</th>
                  <th scope="col" className="r">기초 지분율</th>
                  <th scope="col" className="r">기말 지분율</th>
                  <th scope="col" className="r">장부가액</th>
                  <th scope="col">변동</th>
                </tr>
              </thead>
              <tbody>
                {gov.investments.map((v, i) => (
                  <tr key={i} className={v.change === "변동 없음" ? "" : "flagged"}>
                    <td>
                      <CorpLink corpCode={v.corpCode}>{v.name}</CorpLink>
                    </td>
                    <td>{v.purpose}</td>
                    <td className="r num">{fmtRate(v.beginPct)}</td>
                    <td className="r num">{fmtRate(v.endPct)}</td>
                    <td className="r num">{fmtKRW(v.bookValue)}</td>
                    <td><ChangeChip c={v.change} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="hint">출자 정보가 없습니다.</p>
        )}
      </section>
    </div>
  );
}

function CorpLink({ corpCode, children }: { corpCode: string | null; children: ReactNode }) {
  const navigate = useNavigate();
  if (!corpCode) return <>{children}</>;
  const href = `/companies/${encodeURIComponent(corpCode)}`;
  return (
    <a
      href={href}
      onClick={(e) => {
        e.preventDefault();
        navigate(href);
      }}
    >
      {children}
    </a>
  );
}

// ---- 관계도 ----------------------------------------------------------------------
const W = 760;
const NODE_H = 28;
const MAX_CHARS = 11;

interface Placed {
  n: GraphNode;
  x: number;
  y: number;
  w: number;
  text: string;
}

// 선을 상자 가장자리에서 끊는다(화살표가 상자 밑에 묻히지 않게)
function clip(from: Placed, to: Placed): [number, number] {
  const dx = from.x - to.x;
  const dy = from.y - to.y;
  if (!dx && !dy) return [to.x, to.y];
  const t = Math.min(
    dx ? (to.w / 2 + 4) / Math.abs(dx) : Infinity,
    dy ? (NODE_H / 2 + 4) / Math.abs(dy) : Infinity,
  );
  return [to.x + dx * Math.min(1, t), to.y + dy * Math.min(1, t)];
}

function shorten(s: string) {
  return s.length > MAX_CHARS ? `${s.slice(0, MAX_CHARS - 1)}…` : s;
}
function boxWidth(text: string) {
  // 한글 한 글자 ≈ 12px(12px 글꼴), 라틴 문자 ≈ 7px
  let w = 0;
  for (const ch of text) w += /[ㄱ-힝]/.test(ch) ? 12.5 : 7.2;
  return Math.max(56, Math.min(160, w + 20));
}

export function GovernanceGraph({ nodes, edges }: { nodes: GraphNode[]; edges: GraphEdge[] }) {
  const navigate = useNavigate();
  if (!nodes.length) return <p className="hint">관계도를 그릴 노드가 없습니다.</p>;

  const center = nodes.find((n) => n.kind === "company") ?? nodes[0];
  const left = nodes.filter((n) => n !== center && (n.kind === "shareholder" || n.kind === "person"));
  const right = nodes.filter((n) => n !== center && !left.includes(n));
  const rows = Math.max(left.length, right.length, 1);
  const H = Math.max(240, 70 + rows * 44);
  const cx = W / 2;
  const cy = H / 2 + 8;
  const rx = 270;
  const ry = (H - 70) / 2;

  const place = (list: GraphNode[], side: -1 | 1): Placed[] =>
    list.map((n, i) => {
      // 호 위 각도: 위(-72°)에서 아래(+72°)까지 고르게. 하나면 정중앙
      const t = list.length === 1 ? 0.5 : i / (list.length - 1);
      const phi = ((-72 + 144 * t) * Math.PI) / 180;
      const text = shorten(n.label);
      return { n, x: cx + side * rx * Math.cos(phi), y: cy + ry * Math.sin(phi), w: boxWidth(text), text };
    });

  const centerText = shorten(center.label);
  const placed: Placed[] = [
    { n: center, x: cx, y: cy, w: boxWidth(centerText) + 8, text: centerText },
    ...place(left, -1),
    ...place(right, 1),
  ];
  const byId = new Map(placed.map((p) => [p.n.id, p]));

  const desc = edges
    .map((e) => {
      const a = byId.get(e.from)?.n.label;
      const b = byId.get(e.to)?.n.label;
      return a && b ? `${a} → ${b}${e.pct != null ? ` ${fmtRate(e.pct)}` : ""}` : null;
    })
    .filter(Boolean)
    .join(", ");

  return (
    <div className="scroll-x">
      <svg className="gov-graph" viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`지배구조 관계도: ${desc || center.label}`}>
        <text className="side-label" x={24} y={20}>주주</text>
        <text className="side-label" x={W - 24} y={20} textAnchor="end">출자 회사</text>
        {edges.map((e, i) => {
          const a = byId.get(e.from);
          const b = byId.get(e.to);
          if (!a || !b) return null;
          const [x1, y1] = clip(b, a);
          const [x2, y2] = clip(a, b);
          const mx = (x1 + x2) / 2;
          const my = (y1 + y2) / 2;
          const label = e.pct != null ? fmtRate(e.pct) : e.label;
          return (
            <g key={i}>
              <title>{`${a.n.label} → ${b.n.label}: ${e.label}${e.pct != null ? ` ${fmtRate(e.pct)}` : ""}`}</title>
              <line className="edge" x1={x1} y1={y1} x2={x2} y2={y2} markerEnd="url(#gov-arrow)" />
              {label && (
                <text className="edge-label" x={mx} y={my - 4} textAnchor="middle">
                  {label}
                </text>
              )}
            </g>
          );
        })}
        <defs>
          <marker id="gov-arrow" viewBox="0 0 10 10" refX="10" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
            <path d="M0,0 L10,5 L0,10 z" fill="var(--muted)" />
          </marker>
        </defs>
        {placed.map((p) => {
          const box = (
            <g className={`node k-${p.n.kind}`} transform={`translate(${p.x - p.w / 2}, ${p.y - NODE_H / 2})`}>
              <title>{`${p.n.label}${p.n.corpCode ? ` (${p.n.corpCode})` : ""}`}</title>
              <rect width={p.w} height={NODE_H} rx={p.n.kind === "person" ? 14 : 5} />
              <text x={p.w / 2} y={NODE_H / 2 + 4} textAnchor="middle">
                {p.text}
              </text>
            </g>
          );
          // 고유번호가 있는 노드는 기업 상세로 이동(키보드 Tab·Enter로도)
          if (p.n.corpCode && p.n !== center) {
            const href = `/companies/${encodeURIComponent(p.n.corpCode)}`;
            return (
              <a
                key={p.n.id}
                href={href}
                aria-label={`${p.n.label} 기업 상세`}
                onClick={(e) => {
                  e.preventDefault();
                  navigate(href);
                }}
              >
                {box}
              </a>
            );
          }
          return <g key={p.n.id}>{box}</g>;
        })}
      </svg>
    </div>
  );
}
