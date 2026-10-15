import { EDIT_KEY, LEVEL_KEY, TOPIC_KEY, VSTATUS_KEY } from './lib.js';

const { useState } = React;

export function Topic({ t }) {
  return <span className={`chip topic t-${TOPIC_KEY[t] || 'etc'}`}>{t}</span>;
}

export function Edit({ e }) {
  return <span className={`chip edit e-${EDIT_KEY[e] || 'txt'}`}>{e}</span>;
}

export function Level({ l }) {
  return <span className={`chip level l-${LEVEL_KEY[l] || 'none'}`}>{l}</span>;
}

export function VPill({ v }) {
  if (!v) return null;
  return <span className={`pill v-${VSTATUS_KEY[v.status] || 'warn'}`}>{v.status}</span>;
}

export function Cite({ id }) {
  const [copied, setCopied] = useState(false);
  const copy = (ev) => {
    ev.stopPropagation();
    const done = () => { setCopied(true); setTimeout(() => setCopied(false), 1200); };
    try {
      navigator.clipboard.writeText(`[${id}]`).then(done, () => {});
    } catch (e) { /* 복사가 막힌 환경: 텍스트를 직접 선택해 복사 */ }
  };
  return (
    <span className="cite">
      <code>[{id}]</code>
      <button type="button" className="cite-copy" onClick={copy} aria-label="인용 ID 복사">{copied ? '복사됨' : '복사'}</button>
    </span>
  );
}

const CHECK_ICON = { pass: '✓', fail: '✕', warn: '!' };

export function Checks({ checks }) {
  return (
    <ul className="checks">
      {checks.map((c, i) => (
        <li key={i} className={`ck ck-${c.status}`}>
          <span className="ck-icon" aria-hidden="true">{CHECK_ICON[c.status]}</span>
          <span className="ck-name">{c.name}</span>
          <span className="ck-detail">{c.detail}</span>
        </li>
      ))}
    </ul>
  );
}

export function Empty({ children }) {
  return <p className="empty">{children}</p>;
}
