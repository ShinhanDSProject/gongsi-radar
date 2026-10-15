import { useState, type FormEvent } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { describeError } from "../api/client";
import { useAuth } from "../auth";

const DEMO = [
  { id: "analyst_001", who: "주니어 김 · 분석 요청·발행 요청" },
  { id: "analyst_002", who: "주니어 박 · 분석 요청·발행 요청" },
  { id: "senior_001", who: "시니어 이 · 결재·관리" },
];

export default function LoginPage() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [userId, setUserId] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await login(userId.trim(), password);
      const from = (location.state as { from?: string } | null)?.from;
      navigate(from || "/analyses", { replace: true });
    } catch (err) {
      // [보안] "아이디가 없다/비밀번호가 틀렸다"를 나눠 알려 주지 않는다.
      //        서버(AuthService)가 이미 하나의 메시지로 합쳐 준다 — 계정 존재 여부 노출 방지
      setError(describeError(err, "로그인에 실패했습니다."));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center gutter py-10">
      <div className="w-full max-w-sm flex flex-col gap-4">
        <form onSubmit={onSubmit} className="panel gap-3 p-6" aria-labelledby="login-title">
          <div className="flex items-center gap-2 justify-center">
            <span className="mark" aria-hidden="true" />
            <h1 id="login-title" className="font-display text-[22px] font-extrabold">공시레이더</h1>
          </div>
          <p className="hint text-center">정기보고서 변경 문단 비교 · 사람 검토 · 발행 결재</p>
          <div className="field">
            <label htmlFor="login-id">사용자 ID</label>
            <input id="login-id" autoComplete="username" value={userId} onChange={(e) => setUserId(e.target.value)} autoFocus />
          </div>
          <div className="field">
            <label htmlFor="login-pw">비밀번호</label>
            <input
              id="login-pw"
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          </div>
          {error && (
            <p className="err-box" role="alert">
              {error}
            </p>
          )}
          <button className="btn w-full" disabled={busy || !userId.trim() || !password}>
            {busy ? "확인 중…" : "로그인"}
          </button>
        </form>
        <section className="panel" aria-label="시연 계정">
          <h2>시연 계정 · 비밀번호 모두 password</h2>
          <ul className="flex flex-col gap-1">
            {DEMO.map((d) => (
              <li key={d.id}>
                <button
                  type="button"
                  className="w-full text-left flex flex-wrap gap-x-2 items-baseline rounded px-1 py-0.5 hover:bg-sunken"
                  onClick={() => {
                    setUserId(d.id);
                    setPassword("password");
                  }}
                >
                  <code>{d.id}</code>
                  <span className="hint">{d.who}</span>
                </button>
              </li>
            ))}
          </ul>
        </section>
        <p className="hint text-center">
          서버 없이 보기: <Link to="/preview">report.json 미리보기</Link>
        </p>
      </div>
    </div>
  );
}
