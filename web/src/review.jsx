import { fmtTime } from './lib.js';

const { useState } = React;

// 결재란: 작성(AI) · 검토 · 승인. 승인되면 승인 칸에 인주색 도장이 찍힌다.
export function ReviewPanel({ rep, mode, onReview, counts }) {
  const rv = rep.review;
  const [name, setName] = useState(rv.reviewer || '');
  const [comment, setComment] = useState('');
  const [confirm, setConfirm] = useState(false);
  const [err, setErr] = useState('');
  const [busy, setBusy] = useState(false);
  const locked = rv.status === '승인됨';

  const act = async (action) => {
    setErr('');
    setBusy(true);
    try {
      await onReview({ reviewer: name, action, comment: comment || null, edits: [] });
      setConfirm(false);
      setComment('');
    } catch (e) {
      setErr(e.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <aside className="rail">
      <section className="kj" aria-label="결재">
        <h2 className="kj-title">결재</h2>
        <div className="kj-grid">
          <div className="kj-cell">
            <span className="kj-role">작성</span>
            <span className="kj-who">AI 초안</span>
            <span className="kj-when num">{fmtTime(rep.meta.created_at)}</span>
          </div>
          <div className="kj-cell">
            <span className="kj-role">검토</span>
            <span className="kj-who">{rv.reviewer || '—'}</span>
            <span className="kj-when num">{rv.status === '수정 요청' ? '수정 요청' : ''}</span>
          </div>
          <div className="kj-cell">
            <span className="kj-role">승인</span>
            {locked ? (
              <span className="seal" aria-label={`${rv.reviewer} 승인`}>
                <span className="seal-word">승인</span>
                <span className="seal-name">{rv.reviewer}</span>
              </span>
            ) : <span className="kj-who">—</span>}
            <span className="kj-when num">{locked ? fmtTime(rv.decided_at) : ''}</span>
          </div>
        </div>
        <p className={`kj-status s-${locked ? 'done' : rv.status === '수정 요청' ? 'back' : 'wait'}`}>
          {locked ? '승인되어 팀에 공유되었습니다. 이후 수정은 새 분석으로 합니다.' :
            rv.status === '수정 요청' ? `수정 요청: ${rv.comment || '사유 없음'}` :
              counts.review ? `사람 확인이 필요한 항목 ${counts.review}건이 있습니다.` : '모든 항목이 자동 검증을 통과했습니다. 내용을 확인하고 승인하세요.'}
        </p>

        {!locked && (
          <form className="kj-form" onSubmit={(e) => { e.preventDefault(); setConfirm(true); }}>
            <label htmlFor="reviewer">검토자</label>
            <input id="reviewer" value={name} onChange={(e) => setName(e.target.value)} placeholder="이름" autoComplete="name" />
            <label htmlFor="review-comment">코멘트</label>
            <textarea id="review-comment" rows={2} value={comment} onChange={(e) => setComment(e.target.value)} placeholder="승인·수정 요청 사유" />
            {err && <p className="err">{err}</p>}
            {!confirm ? (
              <div className="row">
                <button type="button" className="btn ghost" disabled={busy || !name.trim()} onClick={() => act('request_changes')}>수정 요청</button>
                <button type="submit" className="btn" disabled={busy || !name.trim()}>승인하고 공유</button>
              </div>
            ) : (
              <div className="confirm">
                <p>승인하면 리포트가 잠기고 팀에 공유됩니다. 승인할까요?</p>
                <div className="row">
                  <button type="button" className="btn ghost" onClick={() => setConfirm(false)}>취소</button>
                  <button type="button" className="btn seal-btn" disabled={busy} onClick={() => act('approve')}>승인</button>
                </div>
              </div>
            )}
          </form>
        )}
        <p className="kj-mode">
          {mode === 'server' ? '승인·수정은 서버 감사 로그(append-only)에 기록됩니다.' :
            '이 화면은 서버 없이 열린 프로토타입입니다. 승인·수정은 이 브라우저 화면에만 반영됩니다.'}
        </p>
      </section>

      <section className="log" aria-label="기록">
        <h2>기록</h2>
        <ol>
          {[...rv.events].reverse().map((e, i) => (
            <li key={i}>
              <span className="log-when num">{fmtTime(e.at)}</span>
              <span className="log-what"><b>{e.actor === 'system' ? '시스템' : e.actor}</b> {e.action}{e.item_id ? ` · ${e.item_id}` : ''}</span>
              {e.detail && <span className="log-detail">{e.detail}</span>}
            </li>
          ))}
        </ol>
      </section>

      <p className="disclaimer">{rep.meta.disclaimer}</p>
    </aside>
  );
}
