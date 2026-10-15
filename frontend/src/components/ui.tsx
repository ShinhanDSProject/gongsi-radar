// 리포트 화면 공용 부품(칩·인용·검증 목록). web/src/ui.jsx를 TypeScript로 옮겼다.
import { useId, useRef, useState, type KeyboardEvent, type ReactNode } from "react";
import { describeError } from "../api/client";
import type { Check, Verification } from "../api/types";
import { EDIT_KEY, LEVEL_KEY, TOPIC_KEY, VSTATUS_KEY } from "../lib/format";

export function Topic({ t }: { t: string }) {
  return <span className={`chip topic t-${TOPIC_KEY[t] || "etc"}`}>{t}</span>;
}

export function Edit({ e }: { e: string }) {
  return <span className={`chip edit e-${EDIT_KEY[e] || "txt"}`}>{e}</span>;
}

export function Level({ l }: { l: string }) {
  return <span className={`chip level l-${LEVEL_KEY[l] || "none"}`}>{l}</span>;
}

export function VPill({ v }: { v: Pick<Verification, "status"> | null | undefined }) {
  if (!v) return null;
  return <span className={`pill v-${VSTATUS_KEY[v.status] || "warn"}`}>{v.status}</span>;
}

// 지배구조·출자의 변동 구분 칩
const CHANGE_TONE: Record<string, string> = {
  신규: "new", "신규 선임": "new", 증가: "up", "지분 증가": "up",
  감소: "down", "지분 감소": "down", "전량 처분": "out", 처분: "out", 퇴임: "out",
  "직위 변경": "mod", "변동 없음": "same", 유지: "same",
};
export function ChangeChip({ c }: { c: string }) {
  return <span className={`chip chg-chip c-${CHANGE_TONE[c] ?? "same"}`}>{c}</span>;
}

export function Cite({ id }: { id: string }) {
  const [copied, setCopied] = useState(false);
  const copy = () => {
    const done = () => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1200);
    };
    try {
      navigator.clipboard.writeText(`[${id}]`).then(done, () => undefined);
    } catch {
      /* 복사가 막힌 환경: 텍스트를 직접 선택해 복사 */
    }
  };
  return (
    <span className="cite">
      <code>[{id}]</code>
      <button type="button" className="cite-copy" onClick={copy} aria-label={`인용 ID ${id} 복사`}>
        {copied ? "복사됨" : "복사"}
      </button>
    </span>
  );
}

const CHECK_ICON: Record<Check["status"], string> = { pass: "✓", fail: "✕", warn: "!" };
const CHECK_SR: Record<Check["status"], string> = { pass: "통과", fail: "실패", warn: "주의" };

export function Checks({ checks }: { checks: Check[] | null | undefined }) {
  if (!checks?.length) return <p className="hint">검사 항목이 없습니다.</p>;
  return (
    <ul className="checks">
      {checks.map((c, i) => (
        <li key={i} className={`ck ck-${c.status}`}>
          <span className="ck-icon" aria-hidden="true">{CHECK_ICON[c.status] ?? "·"}</span>
          <span className="ck-name">
            <span className="sr-only">{CHECK_SR[c.status]}: </span>
            {c.name}
          </span>
          <span className="ck-detail">{c.detail}</span>
        </li>
      ))}
    </ul>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return <p className="empty">{children}</p>;
}

export function ErrorText({ error, fallback }: { error: unknown; fallback?: string }) {
  if (!error) return null;
  return (
    <p className="err-box" role="alert">
      {describeError(error, fallback)}
    </p>
  );
}

// 상태 배지: 분석 요청·Job·리포트 결재·발행 원장 상태를 한 곳에서 색·한국어로 맞춘다
const STATUS: Record<string, [string, string]> = {
  CREATED: ["생성됨", ""],
  RUNNING: ["실행 중", "v-info"],
  COMPLETED: ["완료", "v-good"],
  SUCCEEDED: ["성공", "v-good"],
  FAILED: ["실패", "v-bad"],
  BLOCKED: ["차단됨", "v-bad"],
  DRAFT: ["초안", ""],
  PENDING: ["결재 대기", "v-warn"],
  APPROVED: ["승인됨", "v-good"],
  REJECTED: ["반려됨", "v-bad"],
  PUBLISHED: ["발행됨", "v-good"],
  EXPIRED: ["기한 만료", ""],
  SUPERSEDED: ["정정됨", ""],
};
export function StatusBadge({ status }: { status: string | null | undefined }) {
  if (!status) return null;
  const [label, tone] = STATUS[status] ?? [status, ""];
  return (
    <span className={`pill ${tone}`} title={status}>
      {label}
    </span>
  );
}

// 펼침 단추: 키보드(Enter·Space)로 열고, aria-expanded·aria-controls로 상태를 알린다
export function Expander({
  label,
  children,
  defaultOpen = false,
  count,
}: {
  label: string;
  children: ReactNode;
  defaultOpen?: boolean;
  count?: number;
}) {
  const [open, setOpen] = useState(defaultOpen);
  const id = useId();
  return (
    <div className="flex flex-col gap-2 min-w-0">
      <button type="button" className="fx-toggle" aria-expanded={open} aria-controls={id} onClick={() => setOpen((v) => !v)}>
        <span className="caret" aria-hidden="true">▸</span>
        {label}
        {count != null && <span className="count num">{count}</span>}
      </button>
      {open && (
        <div id={id} className="min-w-0">
          {children}
        </div>
      )}
    </div>
  );
}

// 탭 목록: 좌우 화살표·Home·End로 옮겨 다닌다(WAI-ARIA Tabs 패턴)
export function TabList<T extends string>({
  tabs,
  active,
  onChange,
  label,
  idPrefix,
}: {
  tabs: { id: T; label: string; count?: number | null }[];
  active: T;
  onChange: (id: T) => void;
  label: string;
  idPrefix: string;
}) {
  const refs = useRef<(HTMLButtonElement | null)[]>([]);
  const onKey = (e: KeyboardEvent, i: number) => {
    let n = -1;
    if (e.key === "ArrowRight") n = (i + 1) % tabs.length;
    else if (e.key === "ArrowLeft") n = (i - 1 + tabs.length) % tabs.length;
    else if (e.key === "Home") n = 0;
    else if (e.key === "End") n = tabs.length - 1;
    if (n < 0) return;
    e.preventDefault();
    onChange(tabs[n].id);
    refs.current[n]?.focus();
  };
  return (
    <div className="tabs-inner" role="tablist" aria-label={label}>
      {tabs.map((t, i) => (
        <button
          key={t.id}
          ref={(el) => {
            refs.current[i] = el;
          }}
          type="button"
          role="tab"
          id={`${idPrefix}-tab-${t.id}`}
          aria-selected={active === t.id}
          aria-controls={`${idPrefix}-panel`}
          tabIndex={active === t.id ? 0 : -1}
          className="tab"
          onClick={() => onChange(t.id)}
          onKeyDown={(e) => onKey(e, i)}
        >
          {t.label}
          {t.count != null && <span className="count num">{t.count}</span>}
        </button>
      ))}
    </div>
  );
}
