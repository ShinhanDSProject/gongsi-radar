// Spring Boot 하나만 부르는 얇은 HTTP 클라이언트.
// ApiResponse 껍데기를 여기서 벗겨서, 화면 코드는 data만 다룬다.
import type { ApiResponse, RefreshResponse } from "./types";

const TOKEN_KEY = "gongsi.token";
const REFRESH_KEY = "gongsi.refresh";

// [보안] 토큰은 sessionStorage에 둔다 — 탭을 닫으면 사라진다.
//        localStorage는 남아 있는 동안 계속 노출면이 된다.
//        (운영이라면 HttpOnly 쿠키가 정석이다)
//        sessionStorage가 막힌 환경(사생활 보호 모드 등)에서도 화면이 죽지 않게 메모리에 한 벌 더 둔다.
let memToken: string | null = null;
let memRefresh: string | null = null;

function readStore(key: string): string | null {
  try {
    return sessionStorage.getItem(key);
  } catch {
    return null;
  }
}
function writeStore(key: string, value: string | null): void {
  try {
    if (value) sessionStorage.setItem(key, value);
    else sessionStorage.removeItem(key);
  } catch {
    /* 저장이 막혀도 메모리 값으로 이번 탭은 계속 쓴다 */
  }
}

export function getToken(): string | null {
  return memToken ?? readStore(TOKEN_KEY);
}
export function setToken(token: string | null): void {
  memToken = token;
  writeStore(TOKEN_KEY, token);
}
export function getRefreshToken(): string | null {
  return memRefresh ?? readStore(REFRESH_KEY);
}
export function setRefreshToken(token: string | null): void {
  memRefresh = token;
  writeStore(REFRESH_KEY, token);
}

// 401을 받으면 auth.tsx가 등록한 콜백으로 로그인 상태를 비운다.
// (reference처럼 location을 바꾸기만 하면 React 상태에 사용자 정보가 남는다)
let onUnauthorized: (() => void) | null = null;
export function setUnauthorizedHandler(fn: (() => void) | null): void {
  onUnauthorized = fn;
}

export class ApiError extends Error {
  constructor(
    public code: string,
    message: string,
    public details?: unknown,
    public status?: number,
    public requestId?: string,
  ) {
    super(message);
  }
}

// 오류 코드 → 화면 문구. 서버 message는 보조로 덧붙인다(개발자용 영어 문구일 수 있다).
export const ERROR_MESSAGES: Record<string, string> = {
  UNAUTHORIZED: "로그인이 필요합니다. 다시 로그인해 주세요.",
  FORBIDDEN: "이 작업을 할 권한이 없습니다.",
  NOT_FOUND: "대상을 찾을 수 없습니다.",
  VALIDATION_ERROR: "입력값을 확인해 주세요.",
  GUARDRAIL_BLOCKED: "가드레일이 차단했습니다. 투자 권유·가치판단 표현이나 개인 정보가 들어 있는지 확인하세요.",
  KILL_SWITCH_ACTIVE: "Kill Switch가 켜져 있어 AI 분석이 정지된 상태입니다. 관리자에게 문의하세요.",
  LLM_PROVIDER_ERROR: "LLM 공급자 호출이 실패했습니다.",
  RATE_LIMIT_EXCEEDED: "요청이 너무 많습니다. 잠시 후 다시 시도하세요.",
  INTERNAL_ERROR: "서버 내부 오류가 발생했습니다.",
  AI_SERVER_UNAVAILABLE: "AI 서버에 연결할 수 없습니다.",
  CORE_PUBLICATION_REJECTED: "발행 원장(Core)이 요청을 거절했습니다.",
  CORE_UNAVAILABLE: "발행 원장(Core)에 연결할 수 없습니다.",
  REPORT_LOCKED: "발행 요청 이후에는 리포트를 수정할 수 없습니다.",
  SELF_APPROVAL_FORBIDDEN: "자기가 요청한 발행은 승인할 수 없습니다. 다른 Senior가 승인해야 합니다.",
  NETWORK_ERROR: "서버에 연결할 수 없습니다. Spring Boot(8180)가 실행 중인지 확인하세요.",
  UNKNOWN: "요청이 실패했습니다.",
};

// Core가 409로 거절할 때 details에 담겨 오는 사유 코드(§5)
const CORE_REASONS: Record<string, string> = {
  DUPLICATE_PUBLICATION: "같은 회사·기간에 이미 발행된 리포트가 있습니다(정정 발행이 아님).",
  PENDING_EXISTS: "이 리포트로 이미 결재 대기 중인 발행 요청이 있습니다.",
  DAILY_LIMIT_EXCEEDED: "하루 발행 요청 한도를 넘었습니다.",
  INVALID_SUPERSEDES: "정정 대상 발행 건이 올바르지 않습니다.",
  INVALID_STATE: "결재 대기 상태가 아닙니다.",
  CONTENT_CHANGED: "요청 이후 리포트 내용이 바뀌었습니다(내용 해시 불일치).",
  SELF_APPROVAL: "자기가 요청한 발행은 승인할 수 없습니다.",
  EXPIRED: "결재 기한이 지났습니다.",
};

function detailText(details: unknown): string | null {
  if (details == null) return null;
  if (typeof details === "string") return CORE_REASONS[details] ?? details;
  if (Array.isArray(details)) return details.map(String).join(", ");
  if (typeof details === "object") {
    const d = details as Record<string, unknown>;
    const reason = (d.reason ?? d.code ?? d.error) as string | undefined;
    if (reason && CORE_REASONS[reason]) return CORE_REASONS[reason];
    const issues = d.detectedIssues;
    if (Array.isArray(issues) && issues.length) return `감지: ${issues.map(String).join(", ")}`;
    if (typeof reason === "string") return reason;
  }
  return null;
}

// 화면에 보여 줄 한 줄. "코드: 한국어 문구 (서버 메시지 · 세부)"
export function describeError(err: unknown, fallback = "요청이 실패했습니다."): string {
  if (err instanceof ApiError) {
    const base = ERROR_MESSAGES[err.code] ?? fallback;
    const extra = [err.message, detailText(err.details)]
      .filter((s): s is string => !!s && s !== base)
      .join(" · ");
    return extra ? `${base} (${extra})` : base;
  }
  if (err instanceof Error) return err.message || fallback;
  return fallback;
}

let refreshing: Promise<boolean> | null = null;

// refreshToken이 있으면 한 번만 갱신을 시도한다. 동시에 여러 요청이 401을 받아도 갱신은 한 번.
async function tryRefresh(): Promise<boolean> {
  const rt = getRefreshToken();
  if (!rt) return false;
  if (!refreshing) {
    refreshing = (async () => {
      try {
        const res = await fetch("/api/auth/refresh", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ refreshToken: rt }),
        });
        if (!res.ok) return false;
        const body = (await res.json()) as ApiResponse<RefreshResponse>;
        if (!body.success || !body.data?.accessToken) return false;
        setToken(body.data.accessToken);
        return true;
      } catch {
        return false;
      } finally {
        setTimeout(() => (refreshing = null), 0);
      }
    })();
  }
  return refreshing;
}

async function request<T>(path: string, init?: RequestInit, retried = false): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(init?.headers as Record<string, string>),
  };
  const token = getToken();
  if (token) headers["Authorization"] = `Bearer ${token}`;

  let res: Response;
  try {
    res = await fetch(path, { ...init, headers });
  } catch {
    throw new ApiError("NETWORK_ERROR", "");
  }

  // 401이면 토큰이 만료됐거나 위조다. 갱신을 한 번 해 보고, 안 되면 로그아웃.
  // 로그인 요청 자체의 401은 "아이디·비밀번호 불일치"이므로 그대로 화면에 넘긴다
  const isAuthCall = path.startsWith("/api/auth/");
  if (res.status === 401 && !isAuthCall) {
    if (!retried && (await tryRefresh())) return request<T>(path, init, true);
    setToken(null);
    setRefreshToken(null);
    onUnauthorized?.();
    throw new ApiError("UNAUTHORIZED", "", undefined, 401);
  }

  const requestId = res.headers.get("X-Request-ID") ?? undefined;
  let body: ApiResponse<T> | null = null;
  try {
    body = (await res.json()) as ApiResponse<T>;
  } catch {
    // 프록시 대상(8180)이 꺼져 있으면 Vite가 빈 본문 502/504를 돌려준다
    if (res.status >= 500) throw new ApiError("NETWORK_ERROR", `HTTP ${res.status}`, undefined, res.status, requestId);
    throw new ApiError("UNKNOWN", `HTTP ${res.status}`, undefined, res.status, requestId);
  }
  if (!body || !body.success || !res.ok) {
    const e = body?.error;
    throw new ApiError(
      e?.code ?? (res.status === 403 ? "FORBIDDEN" : "UNKNOWN"),
      e?.message ?? "",
      e?.details,
      res.status,
      body?.requestId ?? requestId,
    );
  }
  return body.data as T;
}

export const api = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: "POST", body: body === undefined ? undefined : JSON.stringify(body) }),
};

// 목록 응답 모양이 엔드포인트마다 다를 수 있어(배열 / Page / Core식 {items,total}) 여기서 배열로 맞춘다.
// CONTRACT에 모양이 못 박히지 않은 /api/publications 등을 위한 방어다.
export function asList<T>(x: T[] | { content: T[] } | { items: T[] } | null | undefined): T[] {
  if (!x) return [];
  if (Array.isArray(x)) return x;
  if ("content" in x && Array.isArray(x.content)) return x.content;
  if ("items" in x && Array.isArray(x.items)) return x.items;
  return [];
}

export function qs(params: Record<string, string | number | null | undefined>): string {
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v !== undefined && v !== null && v !== "") p.set(k, String(v));
  const s = p.toString();
  return s ? `?${s}` : "";
}
