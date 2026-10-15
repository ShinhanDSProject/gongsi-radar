import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api, qs } from "../../api/client";
import type { AuditLogDto } from "../../api/types";
import { ErrorText } from "../../components/ui";

const TYPES = [
  "", "USER_LOGIN", "USER_LOGIN_FAILED", "ANALYSIS_REQUEST_CREATED", "ANALYSIS_EXECUTED", "ANALYSIS_COMPLETED",
  "REPORT_EDITED", "PUBLICATION_SUBMITTED", "PUBLICATION_APPROVED", "PUBLICATION_REJECTED", "GUARDRAIL_BLOCKED",
  "KILL_SWITCH_TOGGLED", "LLM_PROVIDER_SWITCHED", "AGENT_EXECUTION",
];

// 상관관계 ID(X-Request-ID)의 쓸모가 눈에 보이는 자리.
// 최근 목록에서 한 줄을 고르면(또는 UID를 직접 넣으면) 같은 요청이 남긴 기록 전부를 시간순으로 모아 본다
export default function AuditPanel() {
  const [type, setType] = useState("");
  const [selectedUid, setSelectedUid] = useState<string | null>(null);
  const [uidInput, setUidInput] = useState("");

  const recent = useQuery({
    queryKey: ["audit-recent", type],
    queryFn: () => api.get<AuditLogDto[]>(`/api/audit${qs({ type, limit: 50 })}`),
  });

  const trace = useQuery({
    queryKey: ["audit-trace", selectedUid],
    queryFn: () => api.get<AuditLogDto[]>(`/api/audit/trace/${encodeURIComponent(selectedUid!)}`),
    enabled: !!selectedUid,
  });

  return (
    <section className="panel" aria-labelledby="audit-title">
      <header className="panel-h">
        <h2 id="audit-title">감사 로그</h2>
        <div className="flex items-center gap-2">
          <label htmlFor="audit-type" className="hint">종류</label>
          <select id="audit-type" className="w-auto max-w-[200px]" value={type} onChange={(e) => setType(e.target.value)}>
            {TYPES.map((t) => (
              <option key={t} value={t}>{t || "전체"}</option>
            ))}
          </select>
          <button type="button" onClick={() => recent.refetch()} className="link">새로고침</button>
        </div>
      </header>

      <form
        className="flex flex-wrap gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          if (uidInput.trim()) setSelectedUid(uidInput.trim());
        }}
      >
        <label htmlFor="audit-uid" className="sr-only">요청 UID로 추적</label>
        <input
          id="audit-uid"
          className="flex-1 min-w-[180px] w-auto mono"
          placeholder="요청 UID로 추적"
          value={uidInput}
          onChange={(e) => setUidInput(e.target.value)}
        />
        <button type="submit" className="btn ghost" disabled={!uidInput.trim()}>추적</button>
      </form>

      <ErrorText error={recent.error} />
      <div className="max-h-72 overflow-y-auto divide-y divide-line">
        {recent.data?.length === 0 && <p className="py-3 hint">기록이 없습니다.</p>}
        {recent.data?.map((log) => (
          <button
            key={log.id}
            type="button"
            onClick={() => {
              setSelectedUid(log.requestUid);
              setUidInput(log.requestUid ?? "");
            }}
            disabled={!log.requestUid}
            aria-pressed={!!log.requestUid && log.requestUid === selectedUid}
            className={`w-full grid grid-cols-[minmax(0,1fr)_auto] sm:grid-cols-[140px_200px_100px_minmax(0,1fr)] gap-x-2 py-2 px-1 text-left text-xs hover:bg-sunken disabled:cursor-default ${
              log.requestUid && log.requestUid === selectedUid ? "bg-accent-weak" : ""
            }`}
          >
            <span className="text-muted num">{log.createdAt?.slice(0, 19).replace("T", " ")}</span>
            <span className="font-semibold truncate">{log.type}</span>
            <span className="text-muted truncate">{log.userId ?? log.agentId ?? ""}</span>
            <span className="mono text-muted truncate">{log.requestUid}</span>
          </button>
        ))}
      </div>

      {selectedUid && (
        <div className="border-t border-line pt-3 flex flex-col gap-2">
          <h3 className="text-sm font-semibold">
            요청 추적 <span className="mono hint break-all">{selectedUid}</span>
          </h3>
          <ErrorText error={trace.error} />
          {trace.data?.length === 0 && <p className="hint">이 UID로 남은 기록이 없습니다.</p>}
          {trace.data?.map((log) => (
            <div key={log.id} className="text-xs bg-sunken rounded-md p-2">
              <div className="flex flex-wrap gap-2">
                <span className="font-semibold">{log.type}</span>
                <span className="text-muted">{log.userId ?? log.agentId}</span>
                {log.requestId != null && <span className="text-muted">요청 #{log.requestId}</span>}
                <span className="text-muted ml-auto num">{log.createdAt?.slice(11, 19)}</span>
              </div>
              {log.payloadJson && <pre className="mt-1 text-muted whitespace-pre-wrap break-all font-mono">{log.payloadJson}</pre>}
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
