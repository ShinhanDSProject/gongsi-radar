import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState, type FormEvent } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { api, ApiError, qs } from "../api/client";
import type { AnalysisRequestDto, AnalysisStatus, CreateAnalysisRequest, ExecuteResponse, Page, ReprtCode } from "../api/types";
import { ErrorText, StatusBadge } from "../components/ui";
import { fmtTime, REPRT_LABEL } from "../lib/format";

const POLL_MS = 3000;
const STATUSES: AnalysisStatus[] = ["CREATED", "RUNNING", "COMPLETED", "FAILED", "BLOCKED"];

export default function AnalysisListPage() {
  const [statusFilter, setStatusFilter] = useState<string>("");

  // RUNNING이 하나라도 있으면 목록을 주기적으로 다시 묻는다. 다 끝나면 폴링도 멈춘다
  const list = useQuery({
    queryKey: ["analysis-requests", statusFilter],
    queryFn: () => api.get<Page<AnalysisRequestDto>>(`/api/analysis-requests${qs({ status: statusFilter, page: 0, size: 20 })}`),
    refetchInterval: (q) => (q.state.data?.content.some((r) => r.status === "RUNNING") ? POLL_MS : false),
  });

  return (
    <div className="stack">
      <div className="page-h">
        <h1>분석</h1>
        <span className="hint">전년 같은 보고서와 비교해 바뀐 문단·수치·이유를 찾습니다.</span>
      </div>
      <NewAnalysisForm />

      <section className="panel" aria-labelledby="list-title">
        <header className="panel-h">
          <h2 id="list-title">분석 요청</h2>
          <div className="flex items-center gap-2">
            <label htmlFor="status-filter" className="hint">상태</label>
            <select id="status-filter" className="w-auto" value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
              <option value="">전체</option>
              {STATUSES.map((s) => (
                <option key={s} value={s}>{s}</option>
              ))}
            </select>
          </div>
        </header>
        {list.isLoading && <p className="hint">불러오는 중…</p>}
        <ErrorText error={list.error} />
        {list.data?.content.length === 0 && <p className="hint">아직 분석 요청이 없습니다. 위에서 첫 분석을 시작하세요.</p>}
        {!!list.data?.content.length && (
          <div className="scroll-x">
            <table className="grid-table">
              <thead>
                <tr>
                  <th scope="col">#</th>
                  <th scope="col">회사</th>
                  <th scope="col">보고서</th>
                  <th scope="col">관심 질문</th>
                  <th scope="col">요청자</th>
                  <th scope="col">생성</th>
                  <th scope="col">상태</th>
                </tr>
              </thead>
              <tbody>
                {list.data.content.map((r) => (
                  <tr key={r.id}>
                    <td className="num">
                      <Link to={`/analyses/${r.id}`}>#{r.id}</Link>
                    </td>
                    <td>
                      <Link to={`/analyses/${r.id}`}>{r.corpName ?? r.company}</Link>
                      {r.demoFaultInjection && <span className="tag">오류 주입</span>}
                    </td>
                    <td className="whitespace-nowrap">
                      {r.bsnsYear} {REPRT_LABEL[r.reprtCode] ?? r.reprtCode}
                    </td>
                    <td className="max-w-[260px] truncate" title={r.query ?? ""}>{r.query ?? "—"}</td>
                    <td className="mono">{r.userId}</td>
                    <td className="num whitespace-nowrap">{fmtTime(r.createdAt)}</td>
                    <td><StatusBadge status={r.status} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {list.data && list.data.totalElements > list.data.content.length && (
          <p className="hint">최근 {list.data.content.length}건 / 전체 {list.data.totalElements}건</p>
        )}
      </section>
    </div>
  );
}

function NewAnalysisForm() {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const [form, setForm] = useState<CreateAnalysisRequest>({
    company: "999001",
    bsnsYear: 2025,
    reprtCode: "11011",
    query: "",
    demoFaultInjection: false,
  });
  const [error, setError] = useState<unknown>(null);
  const [prefilled, setPrefilled] = useState(false);

  // 기업 상세의 "이 보고서로 분석"이 ?company=&bsnsYear=&reprtCode= 로 채워 보낸다
  useEffect(() => {
    const company = params.get("company");
    if (!company) return;
    const year = Number(params.get("bsnsYear"));
    const code = params.get("reprtCode") as ReprtCode | null;
    setForm((f) => ({
      ...f,
      company,
      bsnsYear: Number.isFinite(year) && year > 0 ? year : f.bsnsYear,
      reprtCode: code && code in REPRT_LABEL ? code : f.reprtCode,
    }));
    setPrefilled(true);
  }, [params]);

  // 생성 → 곧바로 실행. 생성은 됐는데 실행이 거절되면(Kill Switch 등) 상세 화면에서 다시 실행할 수 있다
  const run = useMutation({
    mutationFn: async (req: CreateAnalysisRequest) => {
      const created = await api.post<AnalysisRequestDto>("/api/analysis-requests", req);
      try {
        await api.post<ExecuteResponse>(`/api/analysis-requests/${created.id}/execute`);
      } catch (e) {
        throw Object.assign(e instanceof ApiError ? e : new ApiError("UNKNOWN", ""), { createdId: created.id });
      }
      return created;
    },
    onSuccess: (created) => {
      setError(null);
      queryClient.invalidateQueries({ queryKey: ["analysis-requests"] });
      navigate(`/analyses/${created.id}`);
    },
    onError: (err) => {
      setError(err);
      queryClient.invalidateQueries({ queryKey: ["analysis-requests"] });
    },
  });

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    const q = form.query?.trim();
    run.mutate({
      company: form.company.trim(),
      bsnsYear: form.bsnsYear,
      reprtCode: form.reprtCode,
      ...(q ? { query: q } : {}),
      demoFaultInjection: !!form.demoFaultInjection,
    });
  }

  const createdId = (error as { createdId?: number } | null)?.createdId;

  return (
    <form onSubmit={onSubmit} className="panel" aria-labelledby="new-title">
      <header className="panel-h">
        <h2 id="new-title">새 분석</h2>
        {prefilled && <span className="pill v-info">기업 공시 목록에서 채움</span>}
      </header>
      <div className="grid gap-3 sm:grid-cols-[minmax(0,2fr)_minmax(0,1fr)_minmax(0,1fr)]">
        <div className="field">
          <label htmlFor="f-company">회사(종목코드·고유번호·회사명)</label>
          <input id="f-company" required value={form.company} onChange={(e) => setForm({ ...form, company: e.target.value })} />
        </div>
        <div className="field">
          <label htmlFor="f-year">사업연도</label>
          <input
            id="f-year"
            type="number"
            inputMode="numeric"
            min={2015}
            max={2100}
            required
            value={form.bsnsYear}
            onChange={(e) => setForm({ ...form, bsnsYear: Number(e.target.value) })}
          />
        </div>
        <div className="field">
          <label htmlFor="f-reprt">보고서</label>
          <select id="f-reprt" value={form.reprtCode} onChange={(e) => setForm({ ...form, reprtCode: e.target.value as ReprtCode })}>
            {Object.entries(REPRT_LABEL).map(([code, label]) => (
              <option key={code} value={code}>{label}</option>
            ))}
          </select>
        </div>
      </div>
      <div className="field">
        <label htmlFor="f-query">관심 질문(선택)</label>
        <textarea
          id="f-query"
          rows={2}
          maxLength={1000}
          placeholder="예) 소송 관련 변화 중심으로"
          value={form.query ?? ""}
          onChange={(e) => setForm({ ...form, query: e.target.value })}
        />
        <span className="hint">질문은 입력 가드레일을 거칩니다. 투자 권유·가치판단을 요구하는 질문은 차단됩니다.</span>
      </div>
      <label className="fcheck">
        <input
          type="checkbox"
          checked={!!form.demoFaultInjection}
          onChange={(e) => setForm({ ...form, demoFaultInjection: e.target.checked })}
        />
        시연용 오류 주입(검증 반려 → 재작성 루프 보기)
      </label>
      <p className="hint">샘플 모드의 회사는 999001(샘플소재㈜, 가상)입니다.</p>
      <ErrorText error={error} fallback="분석을 시작하지 못했습니다." />
      {createdId != null && (
        <p className="hint">
          요청은 만들어졌습니다(#{createdId}). <Link to={`/analyses/${createdId}`}>상세 화면</Link>에서 다시 실행할 수 있습니다.
        </p>
      )}
      <div className="row justify-end">
        <button type="submit" className="btn" disabled={run.isPending || !form.company.trim()}>
          {run.isPending ? "시작 중…" : "분석 시작"}
        </button>
      </div>
    </form>
  );
}
