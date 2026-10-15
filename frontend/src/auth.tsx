// 로그인 상태. 토큰은 client.ts(sessionStorage + 메모리), 사용자 정보는 여기서 함께 관리한다.
import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { api, setRefreshToken, setToken, setUnauthorizedHandler } from "./api/client";
import type { LoginResponse, LoginUser } from "./api/types";

const USER_KEY = "gongsi.user";

interface AuthState {
  user: LoginUser | null;
  isSenior: boolean;
  login: (userId: string, password: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthState | null>(null);

function loadUser(): LoginUser | null {
  try {
    const raw = sessionStorage.getItem(USER_KEY);
    return raw ? (JSON.parse(raw) as LoginUser) : null;
  } catch {
    return null;
  }
}

function saveUser(u: LoginUser | null) {
  try {
    if (u) sessionStorage.setItem(USER_KEY, JSON.stringify(u));
    else sessionStorage.removeItem(USER_KEY);
  } catch {
    /* 저장이 막힌 환경: 이번 탭 메모리에서만 유지 */
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<LoginUser | null>(loadUser);
  const queryClient = useQueryClient();

  const clear = useCallback(() => {
    setToken(null);
    setRefreshToken(null);
    saveUser(null);
    setUser(null);
    // 다른 사용자로 다시 로그인했을 때 이전 사용자의 캐시가 보이면 안 된다
    queryClient.clear();
  }, [queryClient]);

  // client.ts가 401(갱신 실패)을 받으면 여기로 알려 준다
  useEffect(() => {
    setUnauthorizedHandler(clear);
    return () => setUnauthorizedHandler(null);
  }, [clear]);

  async function login(userId: string, password: string) {
    const res = await api.post<LoginResponse>("/api/auth/login", { userId, password });
    setToken(res.accessToken);
    setRefreshToken(res.refreshToken ?? null);
    saveUser(res.user);
    queryClient.clear();
    setUser(res.user);
  }

  function logout() {
    // 서버 쪽 로그아웃(감사 기록·refresh 폐기)은 실패해도 화면은 로그아웃한다
    api.post("/api/auth/logout").catch(() => undefined).finally(clear);
  }

  // isSenior는 **메뉴를 숨기는 용도**다. 강제는 서버의 @PreAuthorize가 한다.
  // 브라우저의 role 값은 사용자가 개발자 도구로 얼마든지 바꿀 수 있다 —
  // 바꿔 봐야 서버가 403을 돌려줄 뿐이지만, 화면 분기를 보안이라 착각하면 안 된다
  const isSenior = user?.role === "SENIOR_MANAGER";

  return <AuthContext.Provider value={{ user, isSenior, login, logout }}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("AuthProvider 밖에서 useAuth를 불렀다");
  return ctx;
}
