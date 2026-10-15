import { useParams } from "react-router-dom";
import { ReportScreen } from "../components/report/ReportScreen";
import { Empty } from "../components/ui";

// 리포트 직접 링크(결재함·발행 원장에서 들어온다)
export default function ReportPage() {
  const { id } = useParams();
  const reportId = Number(id);
  if (!Number.isFinite(reportId)) return <Empty>잘못된 리포트 번호입니다.</Empty>;
  return <ReportScreen reportId={reportId} showRequestLink />;
}
