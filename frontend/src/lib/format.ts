// 표시용 공용 함수. 금액 표기는 radar/parsing/textutil.py format_krw와 같은 규칙.
import type { Filing, RadarReport } from "../api/types";

// unit: 끝에 붙는 단위. 시장 화면은 "5,454조 1,041억"처럼 단위를 떼고 쓴다(unit "")
export function fmtKRW(won: number | null | undefined, unit = "원"): string {
  if (won == null || Number.isNaN(won)) return "—";
  const sign = won < 0 ? "-" : "";
  const eok = Math.round(Math.abs(won) / 1e8);
  if (eok === 0) return `${sign}${Math.round(Math.abs(won) / 1e4).toLocaleString("ko-KR")}만${unit}`;
  const jo = Math.floor(eok / 10000);
  const rest = eok % 10000;
  if (jo)
    return rest
      ? `${sign}${jo.toLocaleString("ko-KR")}조 ${rest.toLocaleString("ko-KR")}억${unit}`
      : `${sign}${jo.toLocaleString("ko-KR")}조${unit}`;
  return `${sign}${rest.toLocaleString("ko-KR")}억${unit}`;
}

// 그래프 축 눈금용 짧은 금액: "5,454조" · "820억" (소수 한 자리까지)
export function fmtKRWAxis(won: number): string {
  const a = Math.abs(won);
  const f = (n: number) => n.toLocaleString("ko-KR", { maximumFractionDigits: 1 });
  if (a >= 1e12) return `${f(won / 1e12)}조`;
  if (a >= 1e8) return `${f(won / 1e8)}억`;
  if (a >= 1e4) return `${f(won / 1e4)}만`;
  return f(won);
}

// 부호 붙은 증감. 지수는 포인트(pt), 시가총액은 원 → "+12.34pt" · "-1조 234억"
export function fmtDelta(n: number | null | undefined, kind: "pt" | "won"): string {
  if (n == null || Number.isNaN(n)) return "—";
  const sign = n > 0 ? "+" : n < 0 ? "-" : "";
  if (kind === "pt") return `${sign}${fmtNum(Math.abs(n), 2)}pt`;
  return `${sign}${fmtKRW(Math.abs(n), "")}`;
}

export function fmtPct(p: number | null | undefined, digits = 1): string {
  if (p == null || Number.isNaN(p)) return "—";
  return `${p > 0 ? "+" : ""}${p.toFixed(digits)}%`;
}

// 부호 없는 비율(지분율·영업이익률 등)
export function fmtRate(p: number | null | undefined, digits = 2): string {
  if (p == null || Number.isNaN(p)) return "—";
  return `${p.toLocaleString("ko-KR", { maximumFractionDigits: digits })}%`;
}

export function fmtNum(n: number | null | undefined, digits = 2): string {
  if (n == null || Number.isNaN(n)) return "—";
  return n.toLocaleString("ko-KR", { maximumFractionDigits: digits });
}

export function fmtMultiple(n: number | null | undefined): string {
  if (n == null || Number.isNaN(n)) return "—";
  return `${n.toLocaleString("ko-KR", { maximumFractionDigits: 2 })}배`;
}

// 계산식 입력·결과처럼 단위가 따로 오는 값. 원 단위 큰 금액은 억·조로 줄이고 원래 값은 title로 남긴다
export function fmtUnit(v: number | null | undefined, unit: string): string {
  if (v == null || Number.isNaN(v)) return "—";
  if (unit === "원" && Math.abs(v) >= 1e6) return fmtKRW(v);
  if (unit === "%") return `${fmtNum(v)}%`;
  return `${fmtNum(v)}${unit ? ` ${unit}` : ""}`;
}

export function fmtTime(iso: string | null | undefined): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const p = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}.${p(d.getMonth() + 1)}.${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`;
}

// "20260317" → "2026.03.17"
export function fmtYmd(s: string | null | undefined): string {
  if (!s) return "—";
  const m = /^(\d{4})-?(\d{2})-?(\d{2})/.exec(s);
  return m ? `${m[1]}.${m[2]}.${m[3]}` : s;
}

export function reportLabel(f: Pick<Filing, "report_nm">): string {
  // "사업보고서 (2025.12)" → "2025.12 사업보고서"
  const m = /^(.*?)\s*\((\d{4}\.\d{2})\)/.exec(f.report_nm || "");
  return m ? `${m[2]} ${m[1]}` : f.report_nm;
}

export const REPRT_LABEL: Record<string, string> = {
  "11011": "사업보고서",
  "11012": "반기보고서",
  "11013": "1분기보고서",
  "11014": "3분기보고서",
};

export function dartUrl(rceptNo: string): string {
  return `https://dart.fss.or.kr/dsaf001/main.do?rcpNo=${encodeURIComponent(rceptNo)}`;
}

export const TOPIC_KEY: Record<string, string> = { "위험·소송": "risk", 거래: "deal", "사업·시장": "biz", 기타: "etc" };
export const EDIT_KEY: Record<string, string> = { 신설: "new", 삭제: "del", "수치 수정": "num", "표현 수정": "txt" };
export const LEVEL_KEY: Record<string, string> = { "인과 명시": "cause", "관련 맥락": "context", "확인 불가": "none" };
export const VSTATUS_KEY: Record<string, string> = { 통과: "good", "재작성 후 통과": "good", 반려: "bad", "검토 필요": "warn" };

// 서버의 출력 필터(radar/evidence/verify.py BANNED)와 같은 목록. 화면에서 먼저 막고, 서버가 다시 검사한다.
const BANNED = [
  /강력\s*매수/, /매수/, /매도/, /목표\s*주?가/, /저평가/, /고평가/, /수익\s*보장/, /추천/, /급등/,
  /상승\s*(?:예상|전망|여력)/, /투자\s*(?:유망|적기|매력)/, /사야\s*(?:한다|할)/, /팔아야/,
];
export function bannedHits(text: string | null | undefined): string[] {
  return BANNED.map((rx) => (text || "").match(rx))
    .filter((m): m is RegExpMatchArray => !!m)
    .map((m) => m[0]);
}

export function josa(word: string, pair: string): string {
  const ch = (word || "").slice(-1);
  const code = ch.charCodeAt(0) - 0xac00;
  const has = code >= 0 && code <= 11171 && code % 28 !== 0;
  return has ? pair[0] : pair[1];
}

export function overviewSentence(rep: RadarReport): string {
  const n = rep.changes.length;
  const byTopic = rep.metrics.changes_by_topic || {};
  const parts = [`변경 문단 ${n}건 중 위험·소송 ${byTopic["위험·소송"] || 0}건, 거래 ${byTopic["거래"] || 0}건입니다.`];
  const names = (lv: string) => rep.relations.filter((r) => r.level === lv).map((r) => r.account_nm).join("·");
  const cause = names("인과 명시");
  const ctx = names("관련 맥락");
  const none = names("확인 불가");
  if (cause) parts.push(`${cause}${josa(cause, "은는")} 회사가 원인을 직접 밝혔습니다.`);
  if (ctx) parts.push(`${ctx}${josa(ctx, "은는")} 관련 서술만 있고 원인은 밝히지 않았습니다.`);
  if (none) parts.push(`${none} 변화는 본문에서 관련 서술을 찾지 못했습니다.`);
  return parts.join(" ");
}
