import { bannedHits, fmtKRW, fmtPct, LEVEL_KEY, overviewSentence, TOPIC_KEY } from './lib.js';
import { Checks, Cite, Edit, Empty, Level, Topic, VPill } from './ui.jsx';

const { useMemo, useState } = React;

// ---- 개요 -----------------------------------------------------------------------
export function Overview({ rep, go }) {
  const top = rep.changes.slice(0, 6);
  const vs = rep.metrics.verification || {};
  const loops = rep.relations.filter((r) => r.attempts.length > 1);
  return (
    <div className="stack">
      <p className="lead">{overviewSentence(rep)}</p>

      <section className="panel">
        <header className="panel-h">
          <h2>먼저 볼 변경</h2>
          <button type="button" className="link" onClick={() => go('changes')}>전체 {rep.changes.length}건 보기</button>
        </header>
        <ul className="brief">
          {top.map((c) => (
            <li key={c.id}>
              <button type="button" className="brief-row" onClick={() => go('changes', c.id)}>
                <span className="brief-chips"><Topic t={c.topic} /><Edit e={c.edit_type} /></span>
                <span className="brief-sum">{c.summary}</span>
                <span className="brief-sect">{c.section_path.split(' > ').slice(-1)[0]}</span>
              </button>
            </li>
          ))}
        </ul>
      </section>

      <section className="panel">
        <header className="panel-h">
          <h2>수치 변화와 회사 서술</h2>
          <button type="button" className="link" onClick={() => go('numbers')}>근거 보기</button>
        </header>
        <YoyChart rels={rep.relations} />
      </section>

      <section className="panel">
        <header className="panel-h"><h2>검증</h2></header>
        <div className="vsum">
          {Object.entries(vs).map(([k, n]) => (
            <span key={k} className="vsum-item"><VPill v={{ status: k }} /> <b className="num">{n}</b>건</span>
          ))}
        </div>
        {loops.map((r) => (
          <p key={r.account_key} className="note">
            {r.account_nm}: {r.attempts[0].status} → {r.attempts.length}차 {r.attempts[r.attempts.length - 1].status}
            {r.attempts[0].fault_injected ? ' (시연용 오류 주입)' : ''}. {r.attempts[0].reason}
          </p>
        ))}
      </section>
    </div>
  );
}

// 증감률을 한 축에 그린 막대(0을 기준선으로, 같은 척도)
export function YoyChart({ rels }) {
  const vals = rels.map((r) => r.yoy_pct || 0);
  const lo = Math.min(-100, Math.floor(Math.min(...vals) / 50) * 50);
  const hi = Math.max(100, Math.ceil(Math.max(...vals) / 50) * 50);
  const x = (v) => ((v - lo) / (hi - lo)) * 100;
  const ticks = [];
  for (let t = lo; t <= hi; t += 50) ticks.push(t);
  return (
    <div className="yoy" role="img" aria-label="계정별 전년 대비 증감률">
      <div className="yoy-axis">
        <span />
        <div className="yoy-ticks">
          {ticks.map((t) => (
            <span key={t} className={`tick${t === 0 ? ' zero' : ''}`} style={{ left: `${x(t)}%` }}>{t > 0 ? `+${t}` : t}%</span>
          ))}
        </div>
        <span />
      </div>
      {rels.map((r) => {
        const v = r.yoy_pct || 0;
        const a = x(Math.min(0, v));
        const b = x(Math.max(0, v));
        return (
          <div className="yoy-row" key={r.account_key}>
            <span className="yoy-name">{r.account_nm}</span>
            <div className="yoy-track">
              {ticks.map((t) => <span key={t} className={`grid${t === 0 ? ' zero' : ''}`} style={{ left: `${x(t)}%` }} />)}
              <span className={`bar ${v < 0 ? 'neg' : 'pos'}`} style={{ left: `${a}%`, width: `${Math.max(0.6, b - a)}%` }} />
              <span className={`bar-label ${v < 0 ? 'neg' : 'pos'}`} style={v < 0 ? { right: `${100 - a}%` } : { left: `${b}%` }}>
                {fmtPct(v)}
              </span>
            </div>
            <Level l={r.level} />
          </div>
        );
      })}
    </div>
  );
}

// ---- 변경 문단 --------------------------------------------------------------------
const TOPICS = ['위험·소송', '거래', '사업·시장', '기타'];
const EDITS = ['신설', '삭제', '표현 수정', '수치 수정'];

export function Changes({ rep, focus, editable, onEdit }) {
  const [topics, setTopics] = useState([]);
  const [edits, setEdits] = useState([]);
  const [onlyReview, setOnlyReview] = useState(false);
  const [open, setOpen] = useState(() => new Set(focus ? [focus] : [rep.changes[0] && rep.changes[0].id]));
  const toggle = (arr, set, v) => set(arr.includes(v) ? arr.filter((x) => x !== v) : [...arr, v]);
  const list = rep.changes.filter((c) =>
    (!topics.length || topics.includes(c.topic)) && (!edits.length || edits.includes(c.edit_type)) &&
    (!onlyReview || c.verification.status !== '통과' || c.flags.length));
  const count = (k, v) => rep.changes.filter((c) => c[k] === v).length;
  return (
    <div className="stack">
      <div className="filters" role="group" aria-label="변경 문단 거르기">
        {TOPICS.map((t) => (
          <button key={t} type="button" aria-pressed={topics.includes(t)} className={`fchip t-${TOPIC_KEY[t]}`}
            onClick={() => toggle(topics, setTopics, t)}>{t} <span className="num">{count('topic', t)}</span></button>
        ))}
        <span className="fsep" />
        {EDITS.map((e) => (
          <button key={e} type="button" aria-pressed={edits.includes(e)} className="fchip"
            onClick={() => toggle(edits, setEdits, e)}>{e} <span className="num">{count('edit_type', e)}</span></button>
        ))}
        <span className="fsep" />
        <label className="fcheck"><input id="only-review" type="checkbox" checked={onlyReview} onChange={(e) => setOnlyReview(e.target.checked)} /> 표시가 붙은 항목만</label>
      </div>
      {!list.length && <Empty>조건에 맞는 변경이 없습니다.</Empty>}
      <ul className="chg-list">
        {list.map((c) => (
          <ChangeRow key={c.id} c={c} open={open.has(c.id)} editable={editable} onEdit={onEdit}
            onToggle={() => setOpen((s) => { const n = new Set(s); n.has(c.id) ? n.delete(c.id) : n.add(c.id); return n; })}
            years={[rep.meta.prior.bsns_year, rep.meta.current.bsns_year]} />
        ))}
      </ul>
    </div>
  );
}

function DiffSide({ ops, side }) {
  return (
    <p className="diff-text">
      {ops.filter((o) => o.op === 'eq' || o.op === side).map((o, i) =>
        o.op === 'eq' ? <span key={i}>{o.text}</span> : (side === 'del' ? <del key={i}>{o.text}</del> : <ins key={i}>{o.text}</ins>))}
    </p>
  );
}

function ChangeRow({ c, open, onToggle, editable, onEdit, years }) {
  const inj = c.flags.includes('지시문 의심');
  const tags = c.flags.filter((f) => f !== '지시문 의심');
  return (
    <li className={`chg${open ? ' open' : ''}${inj ? ' inj' : ''}`} id={`c-${c.id}`}>
      <button type="button" className="chg-head" aria-expanded={open} onClick={onToggle}>
        <span className="chg-id num">{c.id}</span>
        <span className="chg-chips"><Topic t={c.topic} /><Edit e={c.edit_type} />{inj && <span className="chip alert">지시문 의심</span>}</span>
        <span className="chg-sum">{c.summary}</span>
        <span className="chg-meta">
          <span className="chg-sect">{c.section_path}</span>
          {tags.map((f) => <span key={f} className="tag">{f}</span>)}
          <VPill v={c.verification} />
        </span>
      </button>
      {open && (
        <div className="chg-body">
          {inj && (
            <p className="banner">
              이 문단에는 AI에게 지시하는 문장이 들어 있습니다. 공시레이더는 원문을 데이터로만 다루므로 이 지시를 따르지 않았고,
              요약도 만들지 않았습니다. 공시 원문에 실제로 실린 문장인지 DART에서 확인하세요.
            </p>
          )}
          {c.summary_before_rewrite && (
            <p className="note">출력 필터가 투자 판단으로 읽힐 수 있는 표현을 고쳤습니다. 고치기 전: “{c.summary_before_rewrite}”</p>
          )}
          <div className={`diff ${c.old.length && c.new.length ? 'two' : 'one'}`}>
            {c.old.length > 0 && (
              <div className="diff-col">
                <h4>{years[0]} 보고서</h4>
                {c.new.length ? <DiffSide ops={c.diff} side="del" /> : <p className="diff-text"><del>{c.old.map((r) => r.text).join(' ')}</del></p>}
                {c.old.map((r) => <Cite key={r.pid} id={r.pid} />)}
              </div>
            )}
            {c.new.length > 0 && (
              <div className="diff-col">
                <h4>{years[1]} 보고서</h4>
                {c.old.length ? <DiffSide ops={c.diff} side="ins" /> : <p className="diff-text"><ins>{c.new.map((r) => r.text).join(' ')}</ins></p>}
                {c.new.map((r) => <Cite key={r.pid} id={r.pid} />)}
              </div>
            )}
          </div>
          {c.numbers.length > 0 && (
            <div className="scroll-x">
              <table className="nums">
                <thead><tr><th>이전</th><th>현재</th></tr></thead>
                <tbody>{c.numbers.map((n, i) => <tr key={i}><td>{n.old || '—'}</td><td>{n.new || '—'}</td></tr>)}</tbody>
              </table>
            </div>
          )}
          {c.duplicates.length > 0 && <p className="note">같은 변경이 {c.duplicates.join(', ')}에도 있어 한 번만 표시합니다.</p>}
          <h4 className="sub">검증</h4>
          <Checks checks={c.verification.checks} />
          {editable && !inj && <EditBox id={c.id} value={c.summary} onSave={onEdit} label="요약 고치기" />}
        </div>
      )}
    </li>
  );
}

export function EditBox({ id, value, onSave, label }) {
  const [editing, setEditing] = useState(false);
  const [text, setText] = useState(value);
  const [err, setErr] = useState('');
  if (!editing) {
    return <button type="button" className="btn ghost small" onClick={() => { setText(value); setEditing(true); }}>{label}</button>;
  }
  const hits = bannedHits(text);
  const save = async () => {
    if (hits.length) return;
    try { setErr(''); await onSave(id, text); setEditing(false); } catch (e) { setErr(e.message); }
  };
  return (
    <div className="editbox">
      <label htmlFor={`edit-${id}`}>{label}</label>
      <textarea id={`edit-${id}`} rows={3} value={text} onChange={(e) => setText(e.target.value)} />
      {hits.length > 0 && <p className="err">투자 판단으로 읽힐 수 있는 표현({hits.join(', ')})은 저장할 수 없습니다.</p>}
      {err && <p className="err">{err}</p>}
      <div className="row">
        <button type="button" className="btn ghost small" onClick={() => setEditing(false)}>취소</button>
        <button type="button" className="btn small" disabled={!!hits.length || !text.trim()} onClick={save}>저장</button>
      </div>
    </div>
  );
}

// ---- 수치·관련 서술 ---------------------------------------------------------------
function Quote({ text, sentence, clause }) {
  const s = sentence || text;
  if (clause && s.includes(clause)) {
    const [a, b] = [s.indexOf(clause), s.indexOf(clause) + clause.length];
    return <blockquote>{s.slice(0, a)}<mark>{clause}</mark>{s.slice(b)}</blockquote>;
  }
  return <blockquote>{s}</blockquote>;
}

export function Numbers({ rep, editable, onEdit }) {
  const [showAll, setShowAll] = useState(false);
  return (
    <div className="stack">
      <section className="panel">
        <header className="panel-h"><h2>전년 대비 증감률</h2><span className="hint">재무 API 값을 코드로 계산 · 연결 기준</span></header>
        <YoyChart rels={rep.relations} />
      </section>
      {rep.relations.map((r) => {
        const acct = rep.accounts.find((a) => a.key === r.account_key) || {};
        return (
          <article className={`rel l-${LEVEL_KEY[r.level]}`} key={r.account_key} id={`r-${r.account_key}`}>
            <header className="rel-h">
              <h3>{r.account_nm}</h3>
              <span className="rel-fig num">{fmtKRW(r.prior)} → {fmtKRW(r.current)} <b>{fmtPct(r.yoy_pct)}</b></span>
              <Level l={r.level} />
              <VPill v={r.verification} />
            </header>
            {(acct.flags || []).length > 0 && <p className="flags">{acct.flags.map((f) => <span key={f} className="tag">{f}</span>)}</p>}
            <p className="statement">{r.statement}</p>
            {r.statement_before_rewrite && <p className="note">재작성 전: “{r.statement_before_rewrite}”</p>}
            {r.evidence.map((e, i) => (
              <div className="evidence" key={e.pid}>
                <span className="ev-label">{i === 0 ? '근거' : '함께 본 문단'} · {e.section_path}</span>
                <Quote text={e.text} sentence={e.sentence} clause={i === 0 ? r.reason_clause : null} />
                <Cite id={e.pid} />
              </div>
            ))}
            <p className="why">판정 근거: {r.why}</p>
            <details className="rel-checks">
              <summary>검증 {r.verification.checks.length}항목 · 2단 판정 {r.verification.judge}</summary>
              <Checks checks={r.verification.checks} />
            </details>
            {r.attempts.length > 1 && (
              <ol className="attempts">
                {r.attempts.map((a) => (
                  <li key={a.attempt} className={`att-${a.status === '반려' ? 'bad' : 'good'}`}>
                    <b>{a.attempt}차 {a.status}</b>{a.fault_injected ? <span className="tag">시연용 오류 주입</span> : null}
                    <span>{a.reason}</span>
                  </li>
                ))}
              </ol>
            )}
            {editable && <EditBox id={r.account_key} value={r.statement} onSave={onEdit} label="문장 고치기" />}
          </article>
        );
      })}
      <section className="panel">
        <header className="panel-h">
          <h2>전체 계정</h2>
          <button type="button" className="link" onClick={() => setShowAll((v) => !v)}>{showAll ? '접기' : `${rep.accounts.length}개 펼치기`}</button>
        </header>
        {showAll && <AccountsTable accounts={rep.accounts} />}
      </section>
    </div>
  );
}

function AccountsTable({ accounts }) {
  return (
    <div className="scroll-x">
      <table className="grid-table">
        <thead><tr><th>계정</th><th>구분</th><th className="r">전기</th><th className="r">당기</th><th className="r">증감률</th><th className="r">robust z</th><th>플래그</th></tr></thead>
        <tbody>
          {accounts.map((a) => (
            <tr key={a.key} className={a.flags.length ? 'flagged' : ''}>
              <td>{a.account_nm}{a.is_key ? <span className="tag">핵심</span> : null}</td>
              <td>{a.sj_div}</td>
              <td className="r num">{fmtKRW(a.prior)}</td>
              <td className="r num">{fmtKRW(a.current)}</td>
              <td className="r num">{fmtPct(a.yoy_pct)}</td>
              <td className="r num">{a.robust_z == null ? '—' : a.robust_z.toFixed(1)}</td>
              <td>{a.flags.join(' · ')}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ---- 표 -------------------------------------------------------------------------
const CELL_KIND = { changed: '값 변경', row_added: '행 추가', row_removed: '행 삭제' };

export function Tables({ rep }) {
  if (!rep.tables.length) return <Empty>바뀐 표가 없습니다.</Empty>;
  return (
    <div className="stack">
      <p className="hint">표는 LLM에 보내지 않고 항목명(첫 열)과 머리글로 맞춰 규칙으로 비교합니다.</p>
      {rep.tables.map((t) => (
        <section className="panel" key={t.id}>
          <header className="panel-h">
            <h2>{t.section_path.split(' > ').slice(-1)[0]}</h2>
            <span className="hint">{t.title}{t.unit ? ` · ${t.unit}` : ''}</span>
          </header>
          {t.note && <p className="note">{t.note}</p>}
          {t.cells.length > 0 && (
            <div className="scroll-x">
              <table className="grid-table">
                <thead><tr><th>항목</th><th>열</th><th className="r">이전</th><th className="r">현재</th><th>구분</th></tr></thead>
                <tbody>
                  {t.cells.map((c, i) => (
                    <tr key={i}>
                      <td>{c.row}</td><td>{c.column || '—'}</td>
                      <td className="r num">{c.old || '—'}</td><td className="r num">{c.new || '—'}</td>
                      <td>{CELL_KIND[c.kind]}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <p className="ids">{t.old_id && <Cite id={t.old_id} />}{t.new_id && <Cite id={t.new_id} />}</p>
        </section>
      ))}
    </div>
  );
}

// ---- 실행 기록 -------------------------------------------------------------------
export function Runs({ rep }) {
  const tl = rep.timeline;
  const maxMs = Math.max(1, ...tl.map((t) => t.ended_ms - t.started_ms));
  const m = rep.meta;
  const usage = rep.metrics.llm_usage || {};
  return (
    <div className="stack">
      <section className="panel">
        <header className="panel-h"><h2>파이프라인</h2><span className="hint">고정 순서 · 검증 반려 시에만 되돌아감(최대 2회)</span></header>
        <ol className="runs">
          {tl.map((t, i) => (
            <li key={i} className={`run run-${t.status}`}>
              <span className="run-name">{t.label}{t.round && (t.node === 'relate' || t.node === 'verify') ? ` · ${t.round + 1}차` : ''}</span>
              <span className="run-bar"><span style={{ width: `${Math.max(2, ((t.ended_ms - t.started_ms) / maxMs) * 100)}%` }} /></span>
              <span className="run-ms num">{t.ended_ms - t.started_ms}ms</span>
              <span className="run-note">{t.status === 'rejected' ? '반려 · ' : ''}{t.note}</span>
            </li>
          ))}
        </ol>
      </section>
      <section className="panel">
        <header className="panel-h"><h2>실행 정보</h2></header>
        <dl className="kv">
          <dt>분석 ID</dt><dd className="mono">{m.analysis_id}</dd>
          <dt>요청 UID</dt><dd className="mono">{m.request_uid || '—'}</dd>
          <dt>데이터</dt><dd>{m.sample_data ? '가상 기업 샘플' : 'OpenDART'} · 재무 {m.fs_div === 'CFS' ? '연결' : '별도'}</dd>
          <dt>임베딩</dt><dd>{m.embedder}</dd>
          <dt>LLM</dt><dd>{m.llm}</dd>
          <dt>그래프</dt><dd>{m.graph_engine === 'langgraph' ? 'LangGraph StateGraph' : '내장 러너(LangGraph와 같은 토폴로지)'}</dd>
          <dt>버전</dt><dd className="mono">{m.pipeline_version}</dd>
          <dt>소요 시간</dt><dd className="num">{rep.metrics.elapsed_ms}ms</dd>
          <dt>데이터 호출</dt><dd className="num">{rep.metrics.source_calls}회</dd>
          <dt>LLM 호출</dt><dd className="num">{usage.calls || 0}회 · 입력 {usage.input_tokens || 0} / 출력 {usage.output_tokens || 0} 토큰</dd>
          <dt>LLM 비용 추정</dt><dd className="num">약 ${rep.metrics.llm_cost_estimate_usd} <span className="hint">{rep.metrics.llm_cost_note}</span></dd>
        </dl>
      </section>
    </div>
  );
}

// ---- 원문 파싱 -------------------------------------------------------------------
export function Parsing({ rep }) {
  const sides = [['prior', rep.meta.prior], ['current', rep.meta.current]];
  return (
    <div className="stack">
      <p className="hint">DART 원문(document.xml)은 정상적인 XML이 아닙니다. 파서가 처리한 함정을 숫자로 남깁니다.</p>
      <div className="two-col">
        {sides.map(([k, f]) => {
          const p = rep.parse[k];
          const te = (p.cell_counts.TE || 0) + (p.cell_counts.TU || 0);
          return (
            <section className="panel" key={k}>
              <header className="panel-h"><h2>{f.report_nm}</h2><span className="hint mono">{p.rcept_no}</span></header>
              <dl className="kv">
                <dt>ZIP 안 파일</dt>
                <dd>{p.files.map((n) => <span key={n} className={`file${n === p.chosen_file ? ' chosen' : ''}`}>{n}{n === p.chosen_file ? ' ← 본문' : ''}</span>)}</dd>
                <dt>인코딩</dt><dd>선언 {p.encoding_declared || '없음'} · 실제 {p.encoding_used}</dd>
                <dt>파싱</dt><dd>{p.mode === 'strict' ? '엄격 파싱 성공' : '복구 모드(손실 가능)'}</dd>
                <dt>&amp; 수리</dt><dd className="num">{p.amp_fixed}곳</dd>
                <dt>가짜 태그</dt><dd className="num">{p.fake_tags_escaped}개를 텍스트로</dd>
                <dt>표 셀</dt><dd className="num">TH {p.cell_counts.TH} · TD {p.cell_counts.TD} · TE {p.cell_counts.TE} · TU {p.cell_counts.TU}</dd>
                <dt>구조</dt><dd className="num">섹션 {p.sections} · 문단 {p.paragraphs} · 표 {p.tables}</dd>
              </dl>
              {te > 0 && <p className="note">TD/TH만 읽었다면 셀 {te}개가 오류 없이 빠졌을 것입니다.</p>}
              {p.warnings.length > 0 && <ul className="warns">{p.warnings.map((w, i) => <li key={i}>{w}</li>)}</ul>}
            </section>
          );
        })}
      </div>
    </div>
  );
}

export function useCounts(rep) {
  return useMemo(() => ({
    changes: rep.changes.length,
    numbers: rep.relations.length,
    tables: rep.tables.length,
    review: rep.changes.filter((c) => c.verification.status === '검토 필요').length +
      rep.relations.filter((r) => r.verification.status === '검토 필요').length,
  }), [rep]);
}
