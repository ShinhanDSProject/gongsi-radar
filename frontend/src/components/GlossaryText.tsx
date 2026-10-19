// 문장 속 용어에 점선 밑줄을 긋고, 마우스를 올리거나 키보드로 초점을 주면 정의를 보여 준다(#14).
import { useId, useState, type CSSProperties, type SyntheticEvent } from "react";
import { Link } from "react-router-dom";
import type { GlossaryTerm } from "../api/types";
import { splitTerms, useGlossaryMatcher } from "../lib/glossary";

const POP_W = 320;
const POP_H = 220; // 위·아래 어느 쪽에 띄울지 고를 때 쓰는 대략의 높이

/**
 * 툴팁은 position: fixed로 띄운다. 표·패널이 overflow로 잘라도 화면 위에 그대로 보이게.
 * 아래 공간이 모자라면 위로 띄우고, 오른쪽 끝에서는 화면 안으로 당긴다.
 */
function place(el: HTMLElement): CSSProperties {
  const r = el.getBoundingClientRect();
  const w = Math.min(POP_W, window.innerWidth * 0.8);
  const left = Math.max(8, Math.min(r.left, window.innerWidth - w - 8));
  const below = window.innerHeight - r.bottom >= POP_H || r.top < POP_H;
  return below ? { left, top: r.bottom + 6, width: w } : { left, bottom: window.innerHeight - r.top + 6, width: w };
}

export function Term({ text, term }: { text: string; term: GlossaryTerm }) {
  const id = useId();
  const [pos, setPos] = useState<CSSProperties>();
  const open = (e: SyntheticEvent<HTMLElement>) => setPos(place(e.currentTarget));
  return (
    <span className="term" tabIndex={0} aria-describedby={id} onMouseEnter={open} onFocus={open}>
      {text}
      <span role="tooltip" id={id} className="term-pop" style={pos}>
        <strong className="term-title">{term.term}</strong>
        <span className="term-def">{term.definition}</span>
        {term.usageNote && <span className="term-use">공시레이더에서: {term.usageNote}</span>}
        {term.related.length > 0 && <span className="term-rel">관련: {term.related.join(", ")}</span>}
        <Link className="term-link" to={`/glossary?q=${encodeURIComponent(term.term)}`}>
          용어집에서 보기
        </Link>
      </span>
    </span>
  );
}

/** 글자만 받아 용어 툴팁을 붙인다. 용어집을 아직 못 받았으면 글자 그대로 보여 준다. */
export default function GlossaryText({ text }: { text: string | null | undefined }) {
  const m = useGlossaryMatcher();
  if (!text) return null;
  return (
    <>
      {splitTerms(text, m).map((p, i) =>
        typeof p === "string" ? <span key={i}>{p}</span> : <Term key={i} text={p.text} term={p.term} />,
      )}
    </>
  );
}
