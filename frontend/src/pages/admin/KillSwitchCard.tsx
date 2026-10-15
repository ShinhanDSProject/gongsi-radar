import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "../../api/client";
import type { KillSwitchDto } from "../../api/types";
import { ErrorText } from "../../components/ui";
import { fmtTime } from "../../lib/format";

// 비상 정지 버튼. Spring이 DB에 쓰고 FastAPI가 읽는다.
// FastAPI 캐시 TTL이 몇 초라 화면에서 켠 뒤 실제 차단까지 잠깐 걸릴 수 있다
export default function KillSwitchCard() {
  const queryClient = useQueryClient();
  const [reason, setReason] = useState("");
  const [confirm, setConfirm] = useState(false);

  const current = useQuery({
    queryKey: ["kill-switch"],
    queryFn: () => api.get<KillSwitchDto>("/api/admin/kill-switch"),
  });

  const toggle = useMutation({
    mutationFn: (enabled: boolean) =>
      api.post<KillSwitchDto>("/api/admin/kill-switch", {
        enabled,
        reason: reason || (enabled ? "관리 화면에서 정지" : "관리 화면에서 해제"),
      }),
    onSuccess: (data) => {
      setReason("");
      setConfirm(false);
      queryClient.setQueryData(["kill-switch"], data);
    },
  });

  const active = current.data?.killSwitchActive ?? false;

  return (
    <section className="panel" aria-labelledby="ks-title">
      <header className="panel-h">
        <h2 id="ks-title">Kill Switch</h2>
        <span className={`pill ${active ? "v-bad" : "v-good"}`} role="status">
          {active ? "정지됨" : "정상 운행"}
        </span>
      </header>
      <ErrorText error={current.error} />
      {active && current.data && (
        <p className="hint">
          {current.data.toggledBy} — {current.data.reason} ({fmtTime(current.data.since)})
        </p>
      )}
      <p className="hint">켜면 새 분석 실행이 503 KILL_SWITCH_ACTIVE로 거절됩니다. 이미 저장된 리포트·결재는 그대로입니다.</p>
      <div className="flex flex-wrap gap-2">
        <label htmlFor="ks-reason" className="sr-only">사유</label>
        <input
          id="ks-reason"
          className="flex-1 min-w-[160px] w-auto"
          placeholder="사유"
          value={reason}
          onChange={(e) => setReason(e.target.value)}
        />
        {!confirm ? (
          <button
            type="button"
            onClick={() => (active ? toggle.mutate(false) : setConfirm(true))}
            disabled={toggle.isPending || current.isLoading || !!current.error}
            className={`btn ${active ? "good" : "danger"}`}
          >
            {active ? "해제" : "긴급 정지"}
          </button>
        ) : (
          <span className="flex gap-2">
            <button type="button" className="btn ghost" onClick={() => setConfirm(false)}>취소</button>
            <button type="button" className="btn danger" disabled={toggle.isPending} onClick={() => toggle.mutate(true)}>
              정지 확정
            </button>
          </span>
        )}
      </div>
      <ErrorText error={toggle.error} />
    </section>
  );
}
