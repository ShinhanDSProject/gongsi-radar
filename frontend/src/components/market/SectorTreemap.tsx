// 업종 지도(§9 SectorNode). 면적 = 시가총액, 색 = KSIC 대분류 구분색(등락률이 아니다).
// 루트는 대분류, 칸을 누르면 중분류 → 기업으로 들어간다. 기업 칸은 기업 상세로 간다.
// 칸은 키보드로 초점이 가는 단추·링크이고, 아래 표가 같은 내용을 글로 한 번 더 보여 준다(접근성 대안).
import { useEffect, useMemo, useRef, useState, type CSSProperties } from "react";
import { Link } from "react-router-dom";
import type { SectorNode } from "../../api/types";
import { fmtKRW, fmtRate } from "../../lib/format";
import { squarify } from "../../lib/squarify";
import { useElementWidth } from "../../lib/useElementWidth";

// 대분류 문자 → 색 칸(index.css의 --sec-1 … --sec-8). 1~6은 색약 대비 검사를 통과한 순서, 7·8은 덧붙인 칸이다.
// 여기 없는 대분류는 회색(--sec-0)이고, 이름표와 표로 구분한다.
const SECTION_SLOT: Record<string, number> = { C: 1, J: 2, K: 3, G: 4, F: 5, M: 6, D: 7, H: 8 };
// 깊이별 진하기: 대분류는 원색, 중분류·기업은 바탕색과 섞어 옅게
const DEPTH_MIX = [100, 62, 44];

function sectionVar(code: string | null | undefined): string {
  const slot = code ? SECTION_SLOT[code.trim().toUpperCase()] ?? 0 : 0;
  return `var(--sec-${slot})`;
}

function nodeTitle(n: SectorNode): string {
  if (n.level === "root") return "전체 업종";
  if (n.level === "company" || !n.code) return n.name;
  // 서버가 이름에 코드를 붙여 보내면("C 제조업") 그대로, 아니면 앞에 붙인다
  return n.name.startsWith(`${n.code} `) ? n.name : `${n.code} ${n.name}`;
}

function capLine(n: SectorNode): string {
  const v = fmtKRW(n.value, "");
  return n.level === "company" ? v : `${v} · ${n.count.toLocaleString("ko-KR")}개사`;
}

function tipText(n: SectorNode): string {
  return [
    nodeTitle(n),
    `시가총액 ${fmtKRW(n.value)}`,
    n.level === "company" ? null : `기업 ${n.count.toLocaleString("ko-KR")}개`,
    `비중 ${fmtRate(n.share, 1)}`,
  ]
    .filter(Boolean)
    .join(" · ");
}

const CHILD_LABEL: Record<SectorNode["level"], string> = {
  root: "대분류",
  section: "중분류",
  division: "기업",
  company: "기업",
};

export default function SectorTreemap({ root }: { root: SectorNode }) {
  // 들어간 경로(노드 id). 시장 필터가 바뀌어 트리가 달라지면 남아 있는 데까지만 유지한다
  const [path, setPath] = useState<string[]>([]);
  const trail = useMemo(() => {
    const out: SectorNode[] = [root];
    for (const id of path) {
      const next = out[out.length - 1].children?.find((c) => c.id === id);
      if (!next) break;
      out.push(next);
    }
    return out;
  }, [root, path]);
  useEffect(() => {
    if (trail.length - 1 !== path.length) setPath(path.slice(0, trail.length - 1));
  }, [trail, path]);

  const node = trail[trail.length - 1];
  const depth = trail.length - 1; // 0: 대분류 칸, 1: 중분류 칸, 2: 기업 칸
  // 색은 지금 보고 있는 대분류를 따른다(들어가도 같은 색 계열)
  const sectionCode = depth === 0 ? null : trail[1].code;
  const children = useMemo(() => [...(node.children ?? [])].sort((a, b) => b.value - a.value), [node]);

  const [wrapRef, width] = useElementWidth<HTMLDivElement>(800);
  const height = Math.round(Math.max(240, Math.min(520, width * 0.56)));
  const tiles = useMemo(() => squarify(children, (c) => c.value, { x: 0, y: 0, w: width, h: height }), [children, width, height]);

  // 칸을 눌러 들어가거나 경로로 돌아오면 누른 단추가 사라지므로, 초점을 경로 표시로 옮긴다
  const crumbsRef = useRef<HTMLElement | null>(null);
  const moved = useRef(false);
  const go = (ids: string[]) => {
    moved.current = true;
    setPath(ids);
  };
  useEffect(() => {
    if (!moved.current) return;
    moved.current = false;
    crumbsRef.current?.querySelector<HTMLElement>("[aria-current]")?.focus();
  }, [path]);
  const open = (n: SectorNode) => {
    if (n.children?.length) go([...trail.slice(1).map((t) => t.id), n.id]);
  };
  const childLabel = CHILD_LABEL[node.level];

  return (
    <div className="flex flex-col gap-3 min-w-0">
      <nav aria-label="업종 경로" className="crumbs" ref={crumbsRef}>
        {trail.map((t, i) => (
          <span key={t.id} className="crumb">
            {i > 0 && <span className="crumb-sep" aria-hidden="true">›</span>}
            {i < trail.length - 1 ? (
              <button type="button" className="link" onClick={() => go(trail.slice(1, i + 1).map((x) => x.id))}>
                {nodeTitle(t)}
              </button>
            ) : (
              <span aria-current="location" tabIndex={-1}>
                {nodeTitle(t)}
              </span>
            )}
          </span>
        ))}
      </nav>

      <div ref={wrapRef} className="tm" style={{ height }} role="group" aria-label={`${nodeTitle(node)} ${childLabel}별 시가총액 지도`}>
        {tiles.length === 0 && <p className="hint p-3">시가총액이 있는 {childLabel}이 없습니다.</p>}
        {tiles.map((t) => {
          const c = t.item;
          const w = Math.max(0, t.w - 2);
          const h = Math.max(0, t.h - 2);
          const base = sectionVar(depth === 0 ? c.code : sectionCode);
          const mix = DEPTH_MIX[Math.min(depth, DEPTH_MIX.length - 1)];
          const style: CSSProperties = {
            left: t.x + 1,
            top: t.y + 1,
            width: w,
            height: h,
            background: mix === 100 ? base : `color-mix(in oklab, ${base} ${mix}%, var(--surface))`,
          };
          // 글자가 들어갈 만큼 클 때만 이름·금액을 쓴다. 작은 칸은 이름만, 아주 작은 칸은 비운다(툴팁·표로 확인)
          const showName = w >= 44 && h >= 22;
          const showCap = w >= 110 && h >= 46;
          const cls = `tm-tile ${mix === 100 ? "solid" : "tint"}`;
          const body = (
            <>
              {showName && <span className="tm-name">{nodeTitle(c)}</span>}
              {showCap && <span className="tm-cap num">{capLine(c)}</span>}
            </>
          );
          const aria = `${tipText(c)}${c.level === "company" ? " — 기업 상세로 이동" : c.children?.length ? " — 하위 업종 보기" : ""}`;
          if (c.level === "company" && c.corpCode) {
            return (
              <Link key={c.id} to={`/companies/${encodeURIComponent(c.corpCode)}`} className={cls} style={style} title={tipText(c)} aria-label={aria}>
                {body}
              </Link>
            );
          }
          const canOpen = !!c.children?.length;
          return (
            <button
              key={c.id}
              type="button"
              className={cls}
              style={style}
              title={tipText(c)}
              aria-label={aria}
              aria-disabled={!canOpen}
              onClick={() => open(c)}
            >
              {body}
            </button>
          );
        })}
      </div>
      <p className="hint">면적 = 시가총액 · 색은 등락률을 나타내지 않습니다 · 한국표준산업분류(KSIC)</p>

      <div className="flex flex-col gap-1 min-w-0">
        <h3 className="sub">{childLabel} 목록 · 시가총액 순</h3>
        <div className="scroll-x relative">
          <table className="grid-table">
            <thead>
              <tr>
                <th scope="col">{node.level === "division" ? "기업" : "업종"}</th>
                <th scope="col" className="r">기업 수</th>
                <th scope="col" className="r">시가총액</th>
                <th scope="col" className="r">비중</th>
              </tr>
            </thead>
            <tbody>
              {children.map((c) => (
                <tr key={c.id}>
                  <td>
                    <span className="tm-namecell">
                      <span className="tm-swatch" aria-hidden="true" style={{ background: sectionVar(depth === 0 ? c.code : sectionCode) }} />
                      {c.level === "company" && c.corpCode ? (
                        <Link to={`/companies/${encodeURIComponent(c.corpCode)}`}>{nodeTitle(c)}</Link>
                      ) : c.children?.length ? (
                        <button type="button" className="link text-left" onClick={() => open(c)}>
                          {nodeTitle(c)}
                        </button>
                      ) : (
                        <span>{nodeTitle(c)}</span>
                      )}
                    </span>
                  </td>
                  <td className="r num">{c.count.toLocaleString("ko-KR")}</td>
                  <td className="r num whitespace-nowrap">{fmtKRW(c.value)}</td>
                  <td className="r num whitespace-nowrap">{fmtRate(c.share, 1)}</td>
                </tr>
              ))}
              {children.length === 0 && (
                <tr>
                  <td colSpan={4} className="hint">하위 항목이 없습니다.</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
