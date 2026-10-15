import { NavLink, Outlet, Link } from "react-router-dom";
import { useAuth } from "../auth";

const ROLE_LABEL: Record<string, string> = {
  JUNIOR_ANALYST: "주니어 애널리스트",
  SENIOR_MANAGER: "시니어 매니저",
};

const linkClass = ({ isActive }: { isActive: boolean }) => (isActive ? "active" : "");

export default function Layout() {
  const { user, isSenior, logout } = useAuth();

  return (
    <div className="min-h-screen">
      <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:top-2 focus:left-2 focus:z-50 btn">
        본문으로 건너뛰기
      </a>
      <header className="appbar">
        <div className="appbar-inner gutter">
          <Link to="/analyses" className="brand" aria-label="공시레이더 처음으로">
            <span className="mark" aria-hidden="true" />
            <span className="brand-name">공시레이더</span>
          </Link>
          <nav className="nav order-3 basis-full sm:order-none sm:basis-auto" aria-label="주 메뉴">
            <NavLink to="/analyses" className={linkClass}>분석</NavLink>
            <NavLink to="/companies" className={linkClass}>기업</NavLink>
            <NavLink to="/publications" className={linkClass}>발행 원장</NavLink>
            {/* Senior에게만 보이는 메뉴 — 숨김이지 방어가 아니다. 방어는 서버 몫 */}
            {isSenior && <NavLink to="/approvals" className={linkClass}>결재함</NavLink>}
            {isSenior && <NavLink to="/admin" className={linkClass}>관리</NavLink>}
          </nav>
          <span className="who ml-auto">
            {user?.name} <span className="hidden sm:inline">· {ROLE_LABEL[user?.role ?? ""] ?? user?.role}</span>
          </span>
          <button type="button" onClick={logout} className="link">
            로그아웃
          </button>
        </div>
      </header>
      <main id="main" className="page gutter" tabIndex={-1}>
        <Outlet />
      </main>
    </div>
  );
}
