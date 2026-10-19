// 문장 속 용어에 점선 밑줄을 긋고, 마우스를 올리거나 키보드로 초점을 주면 정의를 보여 준다(#14).
import { useId } from "react";
import { Link } from "react-router-dom";
import type { GlossaryTerm } from "../api/types";
import { splitTerms, useGlossaryMatcher } from "../lib/glossary";

export function Term({ text, term }: { text: string; term: GlossaryTerm }) {
  const id = useId();
  return (
    <span className="term" tabIndex={0} aria-describedby={id}>
      {text}
      <span role="tooltip" id={id} className="term-pop">
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
