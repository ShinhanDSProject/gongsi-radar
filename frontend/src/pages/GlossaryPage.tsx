// 용어집(#14). 게시된 용어 검색 + 용어 관리(작성·검토 요청·승인·반려·게시 취소).
// 게시는 Senior만, 자기가 요청한 건은 승인할 수 없다 — 강제는 서버가 하고 화면은 버튼만 숨긴다.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api, qs } from "../api/client";
import type { GlossaryStatus, GlossaryTerm, GlossaryTermRequest } from "../api/types";
import { useAuth } from "../auth";
import { ErrorText } from "../components/ui";
import { useGlossary } from "../lib/glossary";

const STATUS_LABEL: Record<GlossaryStatus, string> = {
  DRAFT: "작성 중",
  PENDING: "검토 대기",
  PUBLISHED: "게시",
  REJECTED: "반려",
};
const STATUS_CLASS: Record<GlossaryStatus, string> = {
  DRAFT: "",
  PENDING: "r-wait",
  PUBLISHED: "r-done",
  REJECTED: "r-back",
};

function matches(t: GlossaryTerm, q: string): boolean {
  if (!q) return true;
  const s = q.toLowerCase();
  return [t.term, ...t.aliases, t.definition].some((x) => x.toLowerCase().includes(s));
}

export default function GlossaryPage() {
  const [params, setParams] = useSearchParams();
  const q = params.get("q") ?? "";
  const published = useGlossary();
  const list = useMemo(
    () => (published.data ?? []).filter((t) => matches(t, q)).sort((a, b) => a.term.localeCompare(b.term, "ko")),
    [published.data, q],
  );

  return (
    <div className="stack">
      <div className="page-h">
        <h1>용어집</h1>
        <span className="hint">화면의 점선 밑줄 용어에 마우스를 올리면 같은 정의가 뜹니다. 게시된 정의는 결재자가 검토한 것입니다.</span>
      </div>
      <section className="panel" aria-label="용어 찾기">
        <div className="field">
          <label htmlFor="gl-q">용어 찾기</label>
          <input
            id="gl-q"
            value={q}
            placeholder="예) TTM, 연결재무제표, 접수번호"
            onChange={(e) => setParams(e.target.value ? { q: e.target.value } : {}, { replace: true })}
          />
        </div>
      </section>
      <section className="panel" aria-label="게시된 용어">
        {published.isLoading && <p className="hint">불러오는 중…</p>}
        <ErrorText error={published.error} fallback="용어집을 가져올 수 없습니다." />
        {published.data && <p className="hint">{list.length}개{q && ` · "${q}" 검색`}</p>}
        {list.map((t) => (
          <article key={t.id} className="gl-item">
            <h3>{t.term}</h3>
            {t.aliases.length > 0 && <p className="gl-meta">같은 말: {t.aliases.join(", ")}</p>}
            <p>{t.definition}</p>
            {t.usageNote && <p className="gl-meta">공시레이더에서: {t.usageNote}</p>}
            {t.related.length > 0 && (
              <p className="gl-meta">
                관련:{" "}
                {t.related.map((r, i) => (
                  <button key={r} type="button" className="link" onClick={() => setParams({ q: r })}>
                    {r}
                    {i < t.related.length - 1 ? "," : ""}
                  </button>
                ))}
              </p>
            )}
            {t.source && <p className="gl-meta">근거: {t.source}</p>}
          </article>
        ))}
      </section>
      <Manage />
    </div>
  );
}

const EMPTY: GlossaryTermRequest = { term: "", aliases: [], definition: "", usageNote: "", related: [], source: "" };

function toReq(t: GlossaryTerm): GlossaryTermRequest {
  return {
    term: t.term,
    aliases: t.aliases,
    definition: t.definition,
    usageNote: t.usageNote ?? "",
    related: t.related,
    source: t.source ?? "",
  };
}

function TermForm({
  initial,
  submitLabel,
  busy,
  onSubmit,
  onCancel,
}: {
  initial: GlossaryTermRequest;
  submitLabel: string;
  busy: boolean;
  onSubmit: (r: GlossaryTermRequest) => void;
  onCancel?: () => void;
}) {
  const [f, setF] = useState({ ...initial, aliasText: initial.aliases.join(", "), relatedText: initial.related.join(", ") });
  const split = (s: string) => s.split(",").map((x) => x.trim()).filter(Boolean);
  return (
    <form
      className="stack"
      onSubmit={(e) => {
        e.preventDefault();
        onSubmit({ term: f.term, definition: f.definition, usageNote: f.usageNote, source: f.source,
          aliases: split(f.aliasText), related: split(f.relatedText) });
      }}
    >
      <div className="flex flex-wrap gap-3">
        <div className="field">
          <label>표제어</label>
          <input required maxLength={100} value={f.term} onChange={(e) => setF({ ...f, term: e.target.value })} />
        </div>
        <div className="field">
          <label>같은 말(쉼표로)</label>
          <input value={f.aliasText} onChange={(e) => setF({ ...f, aliasText: e.target.value })} />
        </div>
      </div>
      <div className="field">
        <label>정의(쉬운 말 2~3문장)</label>
        <textarea required maxLength={2000} rows={3} value={f.definition} onChange={(e) => setF({ ...f, definition: e.target.value })} />
      </div>
      <div className="field">
        <label>공시레이더에서 쓰이는 곳</label>
        <input maxLength={500} value={f.usageNote} onChange={(e) => setF({ ...f, usageNote: e.target.value })} />
      </div>
      <div className="flex flex-wrap gap-3">
        <div className="field">
          <label>관련 용어(쉼표로)</label>
          <input value={f.relatedText} onChange={(e) => setF({ ...f, relatedText: e.target.value })} />
        </div>
        <div className="field">
          <label>근거</label>
          <input maxLength={300} value={f.source} onChange={(e) => setF({ ...f, source: e.target.value })} />
        </div>
      </div>
      <div className="flex gap-2">
        <button type="submit" className="btn" disabled={busy}>{submitLabel}</button>
        {onCancel && <button type="button" className="btn ghost" onClick={onCancel}>취소</button>}
      </div>
    </form>
  );
}

function Manage() {
  const { user, isSenior } = useAuth();
  const qc = useQueryClient();
  const [status, setStatus] = useState<GlossaryStatus | "">("PENDING");
  const [creating, setCreating] = useState(false);
  const [editing, setEditing] = useState<number | null>(null);
  const [rejecting, setRejecting] = useState<number | null>(null);
  const [reason, setReason] = useState("");
  const [err, setErr] = useState<unknown>(null);

  const list = useQuery({
    queryKey: ["glossary", "manage", status],
    queryFn: () => api.get<GlossaryTerm[]>(`/api/glossary/manage${qs({ status })}`),
  });
  const refresh = () => qc.invalidateQueries({ queryKey: ["glossary"] });
  const act = useMutation({
    mutationFn: (fn: () => Promise<unknown>) => fn(),
    onSuccess: () => {
      setErr(null);
      setEditing(null);
      setRejecting(null);
      setCreating(false);
      setReason("");
      refresh();
    },
    onError: (e) => setErr(e),
  });
  const run = (fn: () => Promise<unknown>) => act.mutate(fn);

  return (
    <section className="panel stack" aria-label="용어 관리">
      <div className="flex flex-wrap items-center gap-3">
        <h2>용어 관리</h2>
        <span className="hint">누구나 초안을 쓰고 검토를 요청할 수 있습니다. 게시는 결재자가 합니다.</span>
        <button type="button" className="btn ghost ml-auto" onClick={() => setCreating((v) => !v)}>
          {creating ? "닫기" : "새 용어"}
        </button>
      </div>
      {creating && (
        <TermForm initial={EMPTY} submitLabel="초안 저장" busy={act.isPending}
          onSubmit={(r) => run(() => api.post("/api/glossary", r))} onCancel={() => setCreating(false)} />
      )}
      <nav className="flex flex-wrap gap-2" aria-label="상태">
        {(["PENDING", "DRAFT", "REJECTED", "PUBLISHED", ""] as const).map((s) => (
          <button key={s || "all"} type="button" className={`btn ${status === s ? "" : "ghost"} small`} onClick={() => setStatus(s)}>
            {s ? STATUS_LABEL[s] : "전체"}
          </button>
        ))}
      </nav>
      <ErrorText error={err} />
      <ErrorText error={list.error} fallback="관리 목록을 가져올 수 없습니다." />
      {list.data?.length === 0 && <p className="hint">해당 상태의 용어가 없습니다.</p>}
      {list.data?.map((t) => {
        const mine = t.createdBy === user?.userId;
        const canEdit = (t.status === "DRAFT" || t.status === "REJECTED") && (mine || isSenior);
        const canDecide = isSenior && t.status === "PENDING" && t.submittedBy !== user?.userId;
        return (
          <article key={t.id} className="gl-item">
            <div className="flex flex-wrap items-center gap-2">
              <h3>{t.term}</h3>
              <span className={`pill review ${STATUS_CLASS[t.status]}`}>{STATUS_LABEL[t.status]}</span>
              {t.aiDrafted && <span className="pill">AI 초안 · 검토 필요</span>}
              <span className="gl-meta">작성 {t.createdBy}{t.submittedBy && ` · 요청 ${t.submittedBy}`}{t.reviewedBy && ` · 결정 ${t.reviewedBy}`}</span>
            </div>
            {editing === t.id ? (
              <TermForm initial={toReq(t)} submitLabel="저장" busy={act.isPending}
                onSubmit={(r) => run(() => api.put(`/api/glossary/${t.id}`, r))} onCancel={() => setEditing(null)} />
            ) : (
              <>
                <p>{t.definition}</p>
                {t.usageNote && <p className="gl-meta">공시레이더에서: {t.usageNote}</p>}
                {t.reviewComment && <p className="note">{t.status === "REJECTED" ? "반려 사유" : "검토 의견"}: {t.reviewComment}</p>}
              </>
            )}
            <div className="flex flex-wrap gap-2 mt-2">
              {canEdit && editing !== t.id && (
                <>
                  <button type="button" className="btn ghost small" onClick={() => setEditing(t.id)}>고치기</button>
                  <button type="button" className="btn ghost small" disabled={act.isPending}
                    title="LLM이 정의 초안을 씁니다. 사람이 확인하고 검토를 요청해야 게시됩니다."
                    onClick={() => run(() => api.post(`/api/glossary/${t.id}/ai-draft`))}>AI 초안</button>
                  <button type="button" className="btn small" disabled={act.isPending}
                    onClick={() => run(() => api.post(`/api/glossary/${t.id}/submit`))}>검토 요청</button>
                </>
              )}
              {canDecide && rejecting !== t.id && (
                <>
                  <button type="button" className="btn small" disabled={act.isPending}
                    onClick={() => run(() => api.post(`/api/glossary/${t.id}/approve`, {}))}>승인·게시</button>
                  <button type="button" className="btn ghost small" onClick={() => setRejecting(t.id)}>반려</button>
                </>
              )}
              {isSenior && t.status === "PENDING" && t.submittedBy === user?.userId && (
                <span className="hint">본인이 요청한 건은 다른 결재자가 결정합니다.</span>
              )}
              {isSenior && t.status === "PUBLISHED" && (
                <button type="button" className="btn ghost small" disabled={act.isPending}
                  onClick={() => run(() => api.post(`/api/glossary/${t.id}/unpublish`))}>게시 취소</button>
              )}
            </div>
            {rejecting === t.id && (
              <div className="flex flex-wrap gap-2 items-end mt-2">
                <div className="field">
                  <label htmlFor={`gl-rj-${t.id}`}>반려 사유(필수)</label>
                  <input id={`gl-rj-${t.id}`} value={reason} placeholder="무엇을 고쳐야 하는지" onChange={(e) => setReason(e.target.value)} />
                </div>
                <button type="button" className="btn danger small" disabled={!reason.trim() || act.isPending}
                  onClick={() => run(() => api.post(`/api/glossary/${t.id}/reject`, { comment: reason }))}>반려 확정</button>
                <button type="button" className="btn ghost small" onClick={() => setRejecting(null)}>취소</button>
              </div>
            )}
          </article>
        );
      })}
    </section>
  );
}
