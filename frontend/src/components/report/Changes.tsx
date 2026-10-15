// 변경 문단 탭. web/src/views.jsx의 Changes·ChangeRow·EditBox를 옮겼다.
import { useState } from "react";
import { describeError } from "../../api/client";
import type { ChangeItem, DiffOp, RadarReport } from "../../api/types";
import { bannedHits, TOPIC_KEY } from "../../lib/format";
import { Checks, Cite, Edit, Empty, Topic, VPill } from "../ui";

const TOPICS = ["위험·소송", "거래", "사업·시장", "기타"];
const EDITS = ["신설", "삭제", "표현 수정", "수치 수정"];

export type OnEdit = (itemId: string, value: string) => Promise<void>;

export function Changes({
  rep,
  focus,
  editable,
  onEdit,
}: {
  rep: RadarReport;
  focus: string | null;
  editable: boolean;
  onEdit: OnEdit;
}) {
  const [topics, setTopics] = useState<string[]>([]);
  const [edits, setEdits] = useState<string[]>([]);
  const [onlyReview, setOnlyReview] = useState(false);
  const [open, setOpen] = useState<Set<string>>(
    () => new Set(focus ? [focus] : rep.changes[0] ? [rep.changes[0].id] : []),
  );
  const toggle = (arr: string[], set: (v: string[]) => void, v: string) =>
    set(arr.includes(v) ? arr.filter((x) => x !== v) : [...arr, v]);
  const list = rep.changes.filter(
    (c) =>
      (!topics.length || topics.includes(c.topic)) &&
      (!edits.length || edits.includes(c.edit_type)) &&
      (!onlyReview || c.verification.status !== "통과" || c.flags.length > 0),
  );
  const count = (k: "topic" | "edit_type", v: string) => rep.changes.filter((c) => c[k] === v).length;
  const years: [number, number] = [rep.meta.prior.bsns_year, rep.meta.current.bsns_year];
  return (
    <div className="stack">
      <div className="filters" role="group" aria-label="변경 문단 거르기">
        {TOPICS.map((t) => (
          <button
            key={t}
            type="button"
            aria-pressed={topics.includes(t)}
            className={`fchip t-${TOPIC_KEY[t]}`}
            onClick={() => toggle(topics, setTopics, t)}
          >
            {t} <span className="num">{count("topic", t)}</span>
          </button>
        ))}
        <span className="fsep" aria-hidden="true" />
        {EDITS.map((e) => (
          <button key={e} type="button" aria-pressed={edits.includes(e)} className="fchip" onClick={() => toggle(edits, setEdits, e)}>
            {e} <span className="num">{count("edit_type", e)}</span>
          </button>
        ))}
        <span className="fsep" aria-hidden="true" />
        <label className="fcheck">
          <input type="checkbox" checked={onlyReview} onChange={(e) => setOnlyReview(e.target.checked)} /> 표시가 붙은 항목만
        </label>
      </div>
      {!list.length && <Empty>조건에 맞는 변경이 없습니다.</Empty>}
      {list.length > 0 && (
        <ul className="chg-list">
          {list.map((c) => (
            <ChangeRow
              key={c.id}
              c={c}
              open={open.has(c.id)}
              editable={editable}
              onEdit={onEdit}
              onToggle={() =>
                setOpen((s) => {
                  const n = new Set(s);
                  if (n.has(c.id)) n.delete(c.id);
                  else n.add(c.id);
                  return n;
                })
              }
              years={years}
            />
          ))}
        </ul>
      )}
    </div>
  );
}

function DiffSide({ ops, side }: { ops: DiffOp[]; side: "del" | "ins" }) {
  return (
    <p className="diff-text">
      {ops
        .filter((o) => o.op === "eq" || o.op === side)
        .map((o, i) =>
          o.op === "eq" ? <span key={i}>{o.text}</span> : side === "del" ? <del key={i}>{o.text}</del> : <ins key={i}>{o.text}</ins>,
        )}
    </p>
  );
}

function ChangeRow({
  c,
  open,
  onToggle,
  editable,
  onEdit,
  years,
}: {
  c: ChangeItem;
  open: boolean;
  onToggle: () => void;
  editable: boolean;
  onEdit: OnEdit;
  years: [number, number];
}) {
  const inj = c.flags.includes("지시문 의심");
  const tags = c.flags.filter((f) => f !== "지시문 의심");
  const bodyId = `chg-body-${c.id}`;
  return (
    <li className={`chg${open ? " open" : ""}${inj ? " inj" : ""}`} id={`c-${c.id}`}>
      <button type="button" className="chg-head" aria-expanded={open} aria-controls={bodyId} onClick={onToggle}>
        <span className="chg-id num">{c.id}</span>
        <span className="chg-chips">
          <Topic t={c.topic} />
          <Edit e={c.edit_type} />
          {inj && <span className="chip alert">지시문 의심</span>}
        </span>
        <span className="chg-sum">{c.summary}</span>
        <span className="chg-meta">
          <span className="chg-sect">{c.section_path}</span>
          {tags.map((f) => (
            <span key={f} className="tag">
              {f}
            </span>
          ))}
          <VPill v={c.verification} />
        </span>
      </button>
      {open && (
        <div className="chg-body" id={bodyId}>
          {inj && (
            <p className="banner">
              이 문단에는 AI에게 지시하는 문장이 들어 있습니다. 공시레이더는 원문을 데이터로만 다루므로 이 지시를 따르지 않았고,
              요약도 만들지 않았습니다. 공시 원문에 실제로 실린 문장인지 DART에서 확인하세요.
            </p>
          )}
          {c.summary_before_rewrite && (
            <p className="note">출력 필터가 투자 판단으로 읽힐 수 있는 표현을 고쳤습니다. 고치기 전: “{c.summary_before_rewrite}”</p>
          )}
          <div className={`diff ${c.old.length && c.new.length ? "two" : "one"}`}>
            {c.old.length > 0 && (
              <div className="diff-col">
                <h4>{years[0]} 보고서</h4>
                {c.new.length ? (
                  <DiffSide ops={c.diff} side="del" />
                ) : (
                  <p className="diff-text">
                    <del>{c.old.map((r) => r.text).join(" ")}</del>
                  </p>
                )}
                <p className="ids">{c.old.map((r) => <Cite key={r.pid} id={r.pid} />)}</p>
              </div>
            )}
            {c.new.length > 0 && (
              <div className="diff-col">
                <h4>{years[1]} 보고서</h4>
                {c.old.length ? (
                  <DiffSide ops={c.diff} side="ins" />
                ) : (
                  <p className="diff-text">
                    <ins>{c.new.map((r) => r.text).join(" ")}</ins>
                  </p>
                )}
                <p className="ids">{c.new.map((r) => <Cite key={r.pid} id={r.pid} />)}</p>
              </div>
            )}
          </div>
          {c.numbers.length > 0 && (
            <div className="scroll-x">
              <table className="nums">
                <thead>
                  <tr>
                    <th scope="col">이전</th>
                    <th scope="col">현재</th>
                  </tr>
                </thead>
                <tbody>
                  {c.numbers.map((n, i) => (
                    <tr key={i}>
                      <td>{n.old || "—"}</td>
                      <td>{n.new || "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {c.duplicates.length > 0 && <p className="note">같은 변경이 {c.duplicates.join(", ")}에도 있어 한 번만 표시합니다.</p>}
          <h4 className="sub">검증</h4>
          <Checks checks={c.verification.checks} />
          {editable && !inj && <EditBox id={c.id} value={c.summary} onSave={onEdit} label="요약 고치기" />}
        </div>
      )}
    </li>
  );
}

// 검토자 문구 수정. 금지 표현은 화면에서 먼저 막고, 서버(output-check 가드레일)가 다시 검사한다
export function EditBox({ id, value, onSave, label }: { id: string; value: string; onSave: OnEdit; label: string }) {
  const [editing, setEditing] = useState(false);
  const [text, setText] = useState(value);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  if (!editing) {
    return (
      <button
        type="button"
        className="btn ghost small"
        onClick={() => {
          setText(value);
          setErr("");
          setEditing(true);
        }}
      >
        {label}
      </button>
    );
  }
  const hits = bannedHits(text);
  const save = async () => {
    if (hits.length) return;
    setBusy(true);
    try {
      setErr("");
      await onSave(id, text);
      setEditing(false);
    } catch (e) {
      setErr(describeError(e, "저장하지 못했습니다."));
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="editbox">
      <label htmlFor={`edit-${id}`}>{label}</label>
      <textarea id={`edit-${id}`} rows={3} value={text} onChange={(e) => setText(e.target.value)} />
      {hits.length > 0 && <p className="err">투자 판단으로 읽힐 수 있는 표현({hits.join(", ")})은 저장할 수 없습니다.</p>}
      {err && (
        <p className="err" role="alert">
          {err}
        </p>
      )}
      <div className="row">
        <button type="button" className="btn ghost small" onClick={() => setEditing(false)}>
          취소
        </button>
        <button type="button" className="btn small" disabled={busy || !!hits.length || !text.trim()} onClick={save}>
          {busy ? "저장 중…" : "저장"}
        </button>
      </div>
    </div>
  );
}
