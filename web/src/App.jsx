import { applyLocalReview, reportLabel } from './lib.js';
import { ReviewPanel } from './review.jsx';
import { Changes, Numbers, Overview, Parsing, Runs, Tables, useCounts } from './views.jsx';

const { useCallback, useEffect, useState } = React;

const TABS = [
  ['overview', '개요'], ['changes', '변경 문단'], ['numbers', '수치·관련 서술'],
  ['tables', '표'], ['runs', '실행 기록'], ['parsing', '원문 파싱'],
];
const TAB_IDS = TABS.map((t) => t[0]);

function tabFromHash() {
  const h = (location.hash || '').replace('#', '');
  return TAB_IDS.includes(h) ? h : 'overview';
}

async function api(path, opts) {
  const r = await fetch(path, opts);
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(j.detail || `요청 실패(${r.status})`);
  return j;
}

export function App({ embedded }) {
  const [report, setReport] = useState(embedded);
  const [mode, setMode] = useState(embedded ? 'embedded' : 'probe');
  const [list, setList] = useState([]);

  useEffect(() => {
    if (embedded) return;
    api('api/analyses').then((rows) => {
      setMode('server');
      setList(rows);
    }).catch(() => setMode('offline'));
  }, [embedded]);

  const open = useCallback((aid) => api(`api/analyses/${aid}/report`).then(setReport), []);

  const onReview = useCallback(async (body) => {
    if (mode === 'server') {
      setReport(await api(`api/analyses/${report.meta.analysis_id}/review`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
      }));
    } else {
      setReport(applyLocalReview(report, body));
    }
  }, [mode, report]);

  if (!report) {
    return <Launcher mode={mode} list={list} onOpen={open} onLoad={setReport} onRefresh={() => api('api/analyses').then(setList)} />;
  }
  return <ReportView rep={report} mode={mode} onReview={onReview} onBack={mode === 'server' ? () => { setReport(null); api('api/analyses').then(setList); } : null} onLoad={setReport} />;
}

function ReportView({ rep, mode, onReview, onBack, onLoad }) {
  const [tab, setTab] = useState(tabFromHash);
  const [focus, setFocus] = useState(null);
  const [reviewer, setReviewer] = useState('');
  const counts = useCounts(rep);
  const locked = rep.review.status === '승인됨';
  const m = rep.meta;

  useEffect(() => {
    const on = () => setTab(tabFromHash());
    window.addEventListener('hashchange', on);
    return () => window.removeEventListener('hashchange', on);
  }, []);

  const go = (t, id) => {
    setFocus(id || null);
    setTab(t);
    try { history.replaceState(null, '', `#${t}`); } catch (e) { /* 프레임에서 막힐 수 있음 */ }
    if (id) setTimeout(() => { const el = document.getElementById(`c-${id}`); if (el) el.scrollIntoView({ block: 'start' }); }, 30);
  };

  // 항목 수정: 결재란의 검토자 이름이 필요하다
  const onEdit = async (itemId, value) => {
    const name = (document.getElementById('reviewer') || {}).value || reviewer;
    if (!name.trim()) throw new Error('오른쪽 결재란에 검토자 이름을 먼저 입력하세요.');
    setReviewer(name);
    await onReview({ reviewer: name, action: 'edit', edits: [{ item_id: itemId, value }] });
  };

  return (
    <div className="shell">
      <header className="top">
        <div className="top-inner">
          <div className="brand">
            <span className="mark" aria-hidden="true" />
            <span className="brand-name">공시레이더</span>
            <span className="proto">프로토타입</span>
            {onBack && <button type="button" className="link" onClick={onBack}>분석 목록</button>}
          </div>
          <div className="title-block">
            <h1>{m.company.corp_name}{m.sample_data ? <span className="sample">가상 기업 샘플</span> : null}</h1>
            <p className="cmp">
              <a href={m.prior.url} target="_blank" rel="noreferrer">{reportLabel(m.prior)}</a>
              <span className="arrow" aria-hidden="true">→</span>
              <a href={m.current.url} target="_blank" rel="noreferrer">{reportLabel(m.current)}</a>
              <span className="rno mono">{m.current.rcept_no}</span>
            </p>
          </div>
          <div className="badges">
            <span className="ai-badge">AI 생성 · 사람 검토</span>
            <span className={`pill review r-${locked ? 'done' : rep.review.status === '수정 요청' ? 'back' : 'wait'}`}>{rep.review.status}</span>
          </div>
        </div>
        <nav className="tabs" aria-label="리포트 구역">
          <div className="tabs-inner" role="tablist">
            {TABS.map(([id, label]) => (
              <button key={id} type="button" role="tab" aria-selected={tab === id} className="tab" onClick={() => go(id)}>
                {label}{id === 'changes' ? <span className="count num">{counts.changes}</span> : null}
                {id === 'numbers' ? <span className="count num">{counts.numbers}</span> : null}
              </button>
            ))}
          </div>
        </nav>
      </header>

      <div className="body">
        <main className="main" aria-live="polite">
          {tab === 'overview' && <Overview rep={rep} go={go} />}
          {tab === 'changes' && <Changes rep={rep} focus={focus} editable={!locked} onEdit={onEdit} key={focus || 'all'} />}
          {tab === 'numbers' && <Numbers rep={rep} editable={!locked} onEdit={onEdit} />}
          {tab === 'tables' && <Tables rep={rep} />}
          {tab === 'runs' && <Runs rep={rep} />}
          {tab === 'parsing' && <Parsing rep={rep} />}
          <footer className="foot">
            <span>출처: DART(금융감독원 전자공시) · {m.sample_data ? '이 화면의 회사·수치는 시연용 가상 데이터입니다.' : '원문 링크에서 반드시 확인하세요.'}</span>
            <JsonLoader onLoad={onLoad} />
          </footer>
        </main>
        <ReviewPanel rep={rep} mode={mode} onReview={onReview} counts={counts} />
      </div>
    </div>
  );
}

function JsonLoader({ onLoad }) {
  const [err, setErr] = useState('');
  const pick = (e) => {
    const f = e.target.files && e.target.files[0];
    if (!f) return;
    const rd = new FileReader();
    rd.onload = () => {
      try {
        const j = JSON.parse(rd.result);
        if (!j.meta || !j.changes) throw new Error('공시레이더 report.json 형식이 아닙니다.');
        setErr('');
        onLoad(j);
      } catch (x) { setErr(x.message); }
    };
    rd.readAsText(f, 'utf-8');
  };
  return (
    <span className="loader">
      <label htmlFor="report-file" className="link">다른 report.json 열기</label>
      <input id="report-file" type="file" accept="application/json,.json" onChange={pick} />
      {err && <span className="err">{err}</span>}
    </span>
  );
}

function Launcher({ mode, list, onOpen, onLoad, onRefresh }) {
  const [form, setForm] = useState({ company: '999001', bsns_year: 2025, reprt_code: '11011', demo_fault_injection: true });
  const [job, setJob] = useState(null);
  const [err, setErr] = useState('');

  const start = async (e) => {
    e.preventDefault();
    setErr('');
    try {
      const j = await api('api/analyses', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(form) });
      setJob({ ...j, events: [] });
      const poll = async () => {
        const s = await api(`api/analyses/${j.analysis_id}`);
        setJob(s);
        if (s.status === 'running') setTimeout(poll, 400);
        else if (s.status === 'done') { onRefresh(); onOpen(j.analysis_id); } else setErr(s.error || '분석이 실패했습니다.');
      };
      setTimeout(poll, 300);
    } catch (x) { setErr(x.message); }
  };

  if (mode === 'probe') return <div className="launch"><p className="hint">불러오는 중…</p></div>;
  return (
    <div className="launch">
      <header className="launch-h">
        <span className="mark" aria-hidden="true" /><span className="brand-name">공시레이더</span><span className="proto">프로토타입</span>
      </header>
      {mode === 'server' ? (
        <div className="launch-grid">
          <form className="panel" onSubmit={start}>
            <h2>새 분석</h2>
            <label htmlFor="f-company">회사(종목코드·고유번호·회사명)</label>
            <input id="f-company" value={form.company} onChange={(e) => setForm({ ...form, company: e.target.value })} />
            <div className="row">
              <span className="field">
                <label htmlFor="f-year">사업연도</label>
                <input id="f-year" type="number" value={form.bsns_year} onChange={(e) => setForm({ ...form, bsns_year: Number(e.target.value) })} />
              </span>
              <span className="field">
                <label htmlFor="f-reprt">보고서</label>
                <select id="f-reprt" value={form.reprt_code} onChange={(e) => setForm({ ...form, reprt_code: e.target.value })}>
                  <option value="11011">사업보고서</option><option value="11012">반기보고서</option>
                  <option value="11013">1분기보고서</option><option value="11014">3분기보고서</option>
                </select>
              </span>
            </div>
            <label className="fcheck"><input id="f-fault" type="checkbox" checked={form.demo_fault_injection} onChange={(e) => setForm({ ...form, demo_fault_injection: e.target.checked })} /> 시연용 수치 오류 주입(검증 반려 루프 보기)</label>
            <p className="hint">전년 같은 보고서와 비교합니다. 샘플 모드의 회사는 999001(샘플소재㈜, 가상)입니다.</p>
            {err && <p className="err">{err}</p>}
            <button type="submit" className="btn" disabled={job && job.status === 'running'}>분석 시작</button>
            {job && (
              <ol className="progress">
                {(job.events || []).filter((e) => e.type === 'node_end').map((e, i) => (
                  <li key={i} className={e.status === 'rejected' ? 'bad' : ''}><b>{e.label}</b> {e.note}</li>
                ))}
                {job.status === 'running' && <li className="running">진행 중…</li>}
              </ol>
            )}
          </form>
          <section className="panel">
            <h2>지난 분석</h2>
            {!list.length && <p className="hint">아직 분석이 없습니다. 왼쪽에서 첫 분석을 시작하세요.</p>}
            <ul className="past">
              {list.map((a) => (
                <li key={a.analysis_id}>
                  <button type="button" className="past-row" onClick={() => onOpen(a.analysis_id)}>
                    <b>{a.company}</b> <span>{a.prior} → {a.current}</span>
                    <span className="pill">{a.review}</span>
                  </button>
                </li>
              ))}
            </ul>
          </section>
        </div>
      ) : (
        <section className="panel">
          <h2>리포트 열기</h2>
          <p>서버 없이 열렸습니다. <code>python -m radar demo</code>로 만든 report.json을 고르거나, <code>python -m radar serve</code>로 서버를 띄우세요.</p>
          <JsonLoader onLoad={onLoad} />
        </section>
      )}
    </div>
  );
}
