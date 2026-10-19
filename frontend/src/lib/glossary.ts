// 용어집(#14): 게시된 용어를 한 번 받아 두고, 화면 문장에서 용어를 찾아 툴팁을 붙인다.
// 툴팁은 서버를 다시 부르지 않는다(받아 둔 목록만 쓴다).
import { useQuery } from "@tanstack/react-query";
import { useMemo } from "react";
import { api } from "../api/client";
import type { GlossaryTerm } from "../api/types";

export function useGlossary() {
  return useQuery({
    queryKey: ["glossary", "published"],
    queryFn: () => api.get<GlossaryTerm[]>("/api/glossary"),
    staleTime: 10 * 60 * 1000,
  });
}

export interface Matcher {
  re: RegExp | null;
  byKey: Map<string, GlossaryTerm>;
}

const ASCII = /^[A-Za-z0-9 ._()\-[\]]+$/;

function escape(s: string): string {
  return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

/**
 * 표제어와 별칭으로 정규식을 만든다. 긴 말을 먼저 맞춘다("지배주주 순이익"이 "순이익"보다 먼저).
 * 영문 약어(PER·TTM·CFS 등)는 다른 단어 안에서 걸리지 않도록 앞뒤가 영숫자가 아닐 때만 맞춘다.
 * 한 글자짜리 별칭은 너무 흔해 쓰지 않는다.
 */
export function buildMatcher(terms: GlossaryTerm[]): Matcher {
  const byKey = new Map<string, GlossaryTerm>();
  for (const t of terms) {
    for (const k of [t.term, ...t.aliases]) {
      const key = k.trim();
      if (key.length < 2 || byKey.has(key.toLowerCase())) continue;
      byKey.set(key.toLowerCase(), t);
    }
  }
  const keys = [...byKey.keys()].sort((a, b) => b.length - a.length);
  if (keys.length === 0) return { re: null, byKey };
  const parts = keys.map((k) => (ASCII.test(k) ? `(?<![A-Za-z0-9])${escape(k)}(?![A-Za-z0-9])` : escape(k)));
  return { re: new RegExp(parts.join("|"), "gi"), byKey };
}

export function useGlossaryMatcher(): Matcher {
  const { data } = useGlossary();
  return useMemo(() => buildMatcher(data ?? []), [data]);
}

export type Piece = string | { text: string; term: GlossaryTerm };

/** 문장을 일반 글자와 용어 조각으로 나눈다. 같은 용어는 한 문장에서 처음 한 번만 표시한다(밑줄이 너무 많아지지 않게). */
export function splitTerms(text: string, m: Matcher): Piece[] {
  if (!m.re || !text) return [text];
  const out: Piece[] = [];
  const seen = new Set<number>();
  let last = 0;
  for (const hit of text.matchAll(m.re)) {
    const term = m.byKey.get(hit[0].toLowerCase());
    if (!term || seen.has(term.id) || hit.index === undefined) continue;
    seen.add(term.id);
    if (hit.index > last) out.push(text.slice(last, hit.index));
    out.push({ text: hit[0], term });
    last = hit.index + hit[0].length;
  }
  if (last < text.length) out.push(text.slice(last));
  return out;
}
