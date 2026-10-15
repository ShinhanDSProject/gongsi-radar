import AuditPanel from "./admin/AuditPanel";
import GuardrailEventsCard from "./admin/GuardrailEventsCard";
import KillSwitchCard from "./admin/KillSwitchCard";
import ProviderCard from "./admin/ProviderCard";

// 이 페이지의 모든 API는 서버에서 SENIOR_MANAGER를 요구한다.
// Junior가 URL로 들어오면 카드마다 403이 뜬다 — 그게 정상 동작이다
export default function AdminPage() {
  return (
    <div className="stack">
      <div className="page-h">
        <h1>관리</h1>
        <span className="hint">Kill Switch·LLM 공급자·가드레일 차단·감사 로그</span>
      </div>
      <div className="grid gap-4 md:grid-cols-2">
        <KillSwitchCard />
        <ProviderCard />
      </div>
      <GuardrailEventsCard />
      <AuditPanel />
    </div>
  );
}
