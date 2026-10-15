// 저장된 리포트(ReportDto) 하나를 불러와 본문 + 결재 레일로 그린다.
// 분석 상세(/analyses/:id)와 리포트 직접 링크(/reports/:id, 결재함에서 들어옴)가 같이 쓴다.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api, asList, qs } from "../../api/client";
import type { PublicationDto, ReportDto, ReportEditRequest } from "../../api/types";
import { ErrorText, StatusBadge } from "../ui";
import { ReportView, useCounts } from "./ReportView";
import { ReviewRail } from "./ReviewRail";

export function ReportScreen({ reportId, showRequestLink = false }: { reportId: number; showRequestLink?: boolean }) {
  const queryClient = useQueryClient();
  const report = useQuery({
    queryKey: ["report", reportId],
    queryFn: () => api.get<ReportDto>(`/api/reports/${reportId}`),
    // 결재 대기 중이면 Senior의 결정이 반영되도록 가끔 다시 묻는다
    refetchInterval: (q) => (q.state.data?.approvalStatus === "PENDING" ? 10000 : false),
  });
  const r = report.data;
  const corpCode = r?.body.meta.company?.corp_code ?? null;

  // 발행 건 상세(요청자·결정자·버전)는 발행 원장에서 찾는다. 단건 조회 API가 계약에 없어 회사별 목록에서 고른다
  const publication = useQuery({
    queryKey: ["publication-of-report", reportId, r?.publicationId, r?.approvalStatus],
    queryFn: async () => {
      const list = asList(await api.get<PublicationDto[] | { items: PublicationDto[] }>(`/api/publications${qs({ corpCode })}`));
      return (
        list.find((p) => p.publicationId === r!.publicationId) ??
        // 가장 최근 것: 반려 후 publicationId가 비워지는 구현도 있을 수 있다
        list.filter((p) => p.reportId === reportId).sort((a, b) => b.createdAt.localeCompare(a.createdAt))[0] ??
        null
      );
    },
    enabled: !!r && (!!r.publicationId || r.approvalStatus !== "DRAFT"),
  });

  const refresh = () => {
    queryClient.invalidateQueries({ queryKey: ["report", reportId] });
    queryClient.invalidateQueries({ queryKey: ["publication-of-report", reportId] });
  };

  const edit = useMutation({
    mutationFn: (req: ReportEditRequest) => api.post<ReportDto>(`/api/reports/${reportId}/edits`, req),
    onSuccess: (data) => {
      // 수정 응답이 ReportDto면 바로 반영, 아니면 다시 읽는다
      if (data && typeof data === "object" && "body" in data) queryClient.setQueryData(["report", reportId], data);
      else refresh();
    },
  });
  const publish = useMutation({
    mutationFn: (comment: string | null) =>
      api.post<PublicationDto>("/api/publications", { reportId, ...(comment ? { comment } : {}) }),
    onSuccess: refresh,
  });

  if (report.isLoading) return <p className="hint">리포트를 불러오는 중…</p>;
  if (report.error || !r) return <ErrorText error={report.error ?? new Error("리포트를 찾을 수 없습니다.")} />;
  return <Loaded r={r} publication={publication.data ?? null} showRequestLink={showRequestLink}
    onEdit={async (itemId, value) => void (await edit.mutateAsync({ itemId, value }))}
    onPublish={async (comment) => void (await publish.mutateAsync(comment))} />;
}

function Loaded({
  r,
  publication,
  showRequestLink,
  onEdit,
  onPublish,
}: {
  r: ReportDto;
  publication: PublicationDto | null;
  showRequestLink: boolean;
  onEdit: (itemId: string, value: string) => Promise<void>;
  onPublish: (comment: string | null) => Promise<void>;
}) {
  const counts = useCounts(r.body);
  // 발행 요청 이후(PENDING·APPROVED)에는 서버가 409 REPORT_LOCKED를 돌려준다. 화면에서도 미리 막는다
  const editable = r.approvalStatus === "DRAFT" || r.approvalStatus === "REJECTED";
  return (
    <ReportView
      rep={r.body}
      editable={editable}
      onEdit={onEdit}
      badges={
        <>
          <StatusBadge status={r.approvalStatus} />
          {publication && publication.status !== "PENDING" && <StatusBadge status={publication.status} />}
        </>
      }
      footer={
        showRequestLink ? (
          <Link to={`/analyses/${r.requestId}`} className="link">
            분석 요청 #{r.requestId}로
          </Link>
        ) : undefined
      }
      rail={<ReviewRail report={r} publication={publication} reviewCount={counts.review} onPublish={onPublish} />}
    />
  );
}
