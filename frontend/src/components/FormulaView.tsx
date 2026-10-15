// 계산식(Formula, CONTRACT §6.2). 숫자는 코드가 계산하고, 화면은 "무엇을 어디서 가져와 어떻게 셈했는지"를 그대로 보인다.
// 값이 없으면 0으로 바꾸지 않는다 — status "계산 안 함"과 reason을 그대로 보여 준다.
import type { Formula, Source } from "../api/types";
import { dartUrl, fmtUnit } from "../lib/format";
import { Expander } from "./ui";

export function SourceChip({ s }: { s: Source | null | undefined }) {
  if (!s) return null;
  const ref = s.pid ?? s.rceptNo ?? null;
  // 원문 링크: 명시된 url이 우선, 없으면 접수번호로 DART 뷰어 링크를 만든다
  const href = s.url ?? (s.rceptNo ? dartUrl(s.rceptNo) : null);
  return (
    <span className="src" title={[s.kind, s.label, s.field, ref].filter(Boolean).join(" · ")}>
      <b>{s.kind}</b>
      <span>· {s.label}</span>
      {s.field && <span className="mono">· {s.field}</span>}
      {ref &&
        (href ? (
          <a href={href} target="_blank" rel="noreferrer" className="mono">
            · {ref}
          </a>
        ) : (
          <span className="mono">· {ref}</span>
        ))}
    </span>
  );
}

export function FormulaCard({ f }: { f: Formula }) {
  const done = f.status === "계산됨";
  return (
    <article className="fx" aria-label={`계산식 ${f.label}`}>
      <header className="fx-h">
        <h4>{f.label}</h4>
        <span className={`pill ${done ? "v-good" : "v-warn"}`}>{f.status}</span>
        <span className="hint mono">{f.id}</span>
      </header>
      <p className="fx-expr">{f.expr}</p>
      {f.inputs?.length > 0 && (
        <div className="scroll-x">
          <table className="fx-inputs">
            <tbody>
              {f.inputs.map((x, i) => (
                <tr key={i}>
                  <td>{x.name}</td>
                  <td className="r num" title={x.value == null ? "" : `${x.value.toLocaleString("ko-KR")} ${x.unit}`}>
                    {fmtUnit(x.value, x.unit)}
                  </td>
                  <td>
                    <SourceChip s={x.source} />
                    {x.note && <span className="tag">{x.note}</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <p className="flex flex-wrap items-baseline gap-2">
        <span className="hint">결과</span>
        <span className="fx-result" title={f.result == null ? "" : `${f.result.toLocaleString("ko-KR")} ${f.unit}`}>
          {done ? fmtUnit(f.result, f.unit) : "—"}
        </span>
      </p>
      {f.reason && <p className="note">{done ? f.reason : `계산하지 않은 이유: ${f.reason}`}</p>}
      {f.notes?.length > 0 && (
        <ul className="fx-notes">
          {f.notes.map((n, i) => (
            <li key={i}>{n}</li>
          ))}
        </ul>
      )}
    </article>
  );
}

export function FormulaList({ formulas }: { formulas: Formula[] | null | undefined }) {
  if (!formulas?.length) return <p className="hint">계산식이 없습니다.</p>;
  return (
    <div className="fx-list">
      {formulas.map((f) => (
        <FormulaCard key={f.id} f={f} />
      ))}
    </div>
  );
}

// "계산식" 펼침. 계산식이 아예 없으면(아직 §6.2를 안 채운 리포트) 단추를 그리지 않는다
export function FormulaExpander({ formulas, label = "계산식" }: { formulas: Formula[] | null | undefined; label?: string }) {
  if (!formulas?.length) return null;
  return (
    <Expander label={label} count={formulas.length}>
      <FormulaList formulas={formulas} />
    </Expander>
  );
}
