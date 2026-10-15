import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../../api/client";
import type { LlmProviders } from "../../api/types";
import { ErrorText } from "../../components/ui";

const STATUS_LABEL: Record<string, string> = {
  healthy: "정상",
  available: "사용 가능",
  blocked: "차단됨 (폐쇄망)",
  unreachable: "응답 없음",
};

// LLM 공급자 전환. blocked인 항목도 목록에 보인다 —
// 지워 버리면 "선택지가 없다"와 "있지만 막았다"를 구분할 수 없다
export default function ProviderCard() {
  const queryClient = useQueryClient();

  const providers = useQuery({
    queryKey: ["llm-providers"],
    queryFn: () => api.get<LlmProviders>("/api/admin/llm/providers"),
  });

  const switchTo = useMutation({
    mutationFn: (provider: string) => api.post<LlmProviders>("/api/admin/llm/switch", { provider }),
    onSuccess: (data) => {
      // 전환 응답이 곧 최신 현황이다. 한 번 더 GET 하지 않는다(모양이 다르면 다시 읽는다)
      if (data && Array.isArray(data.providers)) queryClient.setQueryData(["llm-providers"], data);
      else queryClient.invalidateQueries({ queryKey: ["llm-providers"] });
    },
  });

  return (
    <section className="panel" aria-labelledby="llm-title">
      <h2 id="llm-title">LLM 공급자</h2>
      {providers.isLoading && <p className="hint">불러오는 중…</p>}
      <ErrorText error={providers.error} />
      <ul className="flex flex-col gap-2">
        {providers.data?.providers.map((p) => {
          const isActive = p.name === providers.data.active;
          return (
            <li key={p.name} className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm">
              <span className={`w-20 font-semibold ${isActive ? "" : "text-muted"}`}>{p.name}</span>
              <span className="flex-1 min-w-[140px] hint">
                {p.model} · {p.type === "external" ? "외부망" : "로컬"} · {STATUS_LABEL[p.status] ?? p.status}
              </span>
              {isActive ? (
                <span className="pill v-info">사용 중</span>
              ) : (
                <button
                  type="button"
                  onClick={() => switchTo.mutate(p.name)}
                  disabled={switchTo.isPending || p.status === "blocked"}
                  className="btn ghost small"
                  aria-label={`${p.name}로 전환`}
                >
                  전환
                </button>
              )}
            </li>
          );
        })}
      </ul>
      <ErrorText error={switchTo.error} fallback="전환하지 못했습니다." />
      <p className="hint">
        전환은 AI 서버 메모리에서만 이뤄집니다 — 재기동하면 .env의 LLM_PROVIDER로 돌아갑니다. 전환 기록은 감사 로그(LLM_PROVIDER_SWITCHED)에 남습니다.
      </p>
    </section>
  );
}
