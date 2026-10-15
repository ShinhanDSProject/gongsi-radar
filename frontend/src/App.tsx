import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import { useAuth } from "./auth";
import Layout from "./components/Layout";
import AdminPage from "./pages/AdminPage";
import AnalysisDetailPage from "./pages/AnalysisDetailPage";
import AnalysisListPage from "./pages/AnalysisListPage";
import ApprovalsPage from "./pages/ApprovalsPage";
import CompanyDetailPage from "./pages/CompanyDetailPage";
import CompanyListPage from "./pages/CompanyListPage";
import LoginPage from "./pages/LoginPage";
import MarketPage from "./pages/MarketPage";
import PreviewPage from "./pages/PreviewPage";
import PublicationsPage from "./pages/PublicationsPage";
import ReportPage from "./pages/ReportPage";

export default function App() {
  const { user } = useAuth();
  const location = useLocation();

  if (!user) {
    // 로그인 뒤 원래 가려던 주소로 돌려보내려고 from을 넘긴다
    const from = location.pathname === "/login" ? undefined : location.pathname + location.search;
    return (
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        {/* 미리보기는 서버를 부르지 않으므로 로그인 없이도 연다(백엔드 없이 시연·개발) */}
        <Route path="/preview" element={<main className="page gutter"><PreviewPage /></main>} />
        <Route path="*" element={<Navigate to="/login" replace state={from ? { from } : undefined} />} />
      </Routes>
    );
  }

  return (
    <Routes>
      <Route element={<Layout />}>
        <Route path="/" element={<Navigate to="/analyses" replace />} />
        <Route path="/analyses" element={<AnalysisListPage />} />
        <Route path="/analyses/:id" element={<AnalysisDetailPage />} />
        <Route path="/reports/:id" element={<ReportPage />} />
        <Route path="/companies" element={<CompanyListPage />} />
        <Route path="/companies/:corpCode" element={<CompanyDetailPage />} />
        {/* 시장 화면(§9). MARKET_DATA_READ가 없으면 서버가 403을 돌려주고 화면이 안내한다 */}
        <Route path="/market" element={<MarketPage />} />
        <Route path="/publications" element={<PublicationsPage />} />
        {/* 라우트는 열어 둔다. Junior가 URL을 쳐서 들어와도 서버가 403을 돌려주고,
            화면은 그 403을 그대로 보여 준다 — 막는 건 서버, 알리는 건 화면 */}
        <Route path="/approvals" element={<ApprovalsPage />} />
        <Route path="/admin" element={<AdminPage />} />
        {/* 서버 없이 report.json 파일을 열어 보는 미리보기(개발·시연용, 서버 호출 없음) */}
        <Route path="/preview" element={<PreviewPage />} />
        <Route path="/login" element={<Navigate to="/analyses" replace />} />
        <Route path="*" element={<Navigate to="/analyses" replace />} />
      </Route>
    </Routes>
  );
}
