import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api, qs } from "../../api/client";
import type { GuardrailEventDto } from "../../api/types";
import { ErrorText } from "../../components/ui";
import { fmtTime } from "../../lib/format";

const SEVERITIES = ["", "SAFE", "WARNING", "BLOCKED"];
const SEV_TONE: Record<string, string> = { BLOCKED: "v-bad", WARNING: "v-warn", SAFE: "v-good" };

// 입력(관심 질문)·출력(리포트 문구 수정) 가드레일이 걸린 기록
export default function GuardrailEventsCard() {
  const [severity, setSeverity] = useState("");
  const events = useQuery({
    queryKey: ["guardrail-events", severity],
    queryFn: () => api.get<GuardrailEventDto[]>(`/api/admin/guardrail-events${qs({ severity, limit: 50 })}`),
  });

  return (
    <section className="panel" aria-labelledby="gr-title">
      <header className="panel-h">
        <h2 id="gr-title">가드레일 이벤트</h2>
        <div className="flex items-center gap-2">
          <label htmlFor="gr-sev" className="hint">심각도</label>
          <select id="gr-sev" className="w-auto" value={severity} onChange={(e) => setSeverity(e.target.value)}>
            {SEVERITIES.map((s) => (
              <option key={s} value={s}>{s || "전체"}</option>
            ))}
          </select>
          <button type="button" className="link" onClick={() => events.refetch()}>새로고침</button>
        </div>
      </header>
      <ErrorText error={events.error} />
      {events.data?.length === 0 && <p className="hint">기록이 없습니다.</p>}
      {!!events.data?.length && (
        <div className="scroll-x max-h-80 overflow-y-auto">
          <table className="grid-table">
            <thead>
              <tr>
                <th scope="col">시각</th>
                <th scope="col">종류</th>
                <th scope="col">심각도</th>
                <th scope="col">차단</th>
                <th scope="col">사용자</th>
                <th scope="col">감지 내용</th>
                <th scope="col">요청 UID</th>
              </tr>
            </thead>
            <tbody>
              {events.data.map((e) => (
                <tr key={e.id}>
                  <td className="num whitespace-nowrap">{fmtTime(e.createdAt)}</td>
                  <td className="mono text-xs">{e.type}</td>
                  <td><span className={`pill ${SEV_TONE[e.severity] ?? ""}`}>{e.severity}</span></td>
                  <td>{e.blocked ? "예" : "아니오"}</td>
                  <td className="mono text-xs">{e.userId ?? "—"}</td>
                  <td className="text-xs break-all">{e.detectedIssues ?? "—"}</td>
                  <td className="mono text-xs break-all">{e.requestUid ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
