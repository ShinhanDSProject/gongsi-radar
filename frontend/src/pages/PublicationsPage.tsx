import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";
import { api, asList, qs } from "../api/client";
import type { PublicationDto, PublicationStatus } from "../api/types";
import { ErrorText, StatusBadge } from "../components/ui";
import { fmtTime } from "../lib/format";

const STATUSES: PublicationStatus[] = ["PENDING", "PUBLISHED", "REJECTED", "EXPIRED", "FAILED", "SUPERSEDED"];

// 발행 원장(Core Zone)을 Spring을 거쳐 읽는다. 원장은 지우지 않는다 — 정정은 새 버전 + supersedes로 남는다
export default function PublicationsPage() {
  const [corpCode, setCorpCode] = useState("");
  const [status, setStatus] = useState("");
  const [applied, setApplied] = useState({ corpCode: "", status: "" });

  const list = useQuery({
    queryKey: ["publications", applied],
    queryFn: async () =>
      asList(await api.get<PublicationDto[] | { items: PublicationDto[] }>(`/api/publications${qs(applied)}`)),
  });

  return (
    <div className="stack">
      <div className="page-h">
        <h1>발행 원장</h1>
        <span className="hint">Senior가 승인한 리포트만 PUBLISHED로 남습니다. 같은 회사·기간의 정정 발행은 버전이 올라갑니다.</span>
      </div>
      <form
        className="panel"
        aria-label="발행 원장 거르기"
        onSubmit={(e) => {
          e.preventDefault();
          setApplied({ corpCode: corpCode.trim(), status });
        }}
      >
        <div className="flex flex-wrap gap-3 items-end">
          <div className="field">
            <label htmlFor="pub-corp">고유번호(corpCode)</label>
            <input id="pub-corp" value={corpCode} placeholder="예) 00999001" onChange={(e) => setCorpCode(e.target.value)} />
          </div>
          <div className="field">
            <label htmlFor="pub-status">상태</label>
            <select id="pub-status" value={status} onChange={(e) => setStatus(e.target.value)}>
              <option value="">전체</option>
              {STATUSES.map((s) => (
                <option key={s} value={s}>{s}</option>
              ))}
            </select>
          </div>
          <button type="submit" className="btn">조회</button>
        </div>
      </form>
      <section className="panel" aria-label="발행 목록">
        {list.isLoading && <p className="hint">불러오는 중…</p>}
        <ErrorText error={list.error} fallback="발행 원장을 가져올 수 없습니다." />
        {list.data?.length === 0 && <p className="hint">조건에 맞는 발행 건이 없습니다.</p>}
        {!!list.data?.length && (
          <div className="scroll-x">
            <table className="grid-table">
              <thead>
                <tr>
                  <th scope="col">회사</th>
                  <th scope="col">기간</th>
                  <th scope="col">제목</th>
                  <th scope="col" className="r">버전</th>
                  <th scope="col">정정 대상</th>
                  <th scope="col">상태</th>
                  <th scope="col">요청</th>
                  <th scope="col">결정</th>
                  <th scope="col">발행 ID</th>
                </tr>
              </thead>
              <tbody>
                {list.data.map((p) => (
                  <tr key={p.publicationId} className={p.status === "SUPERSEDED" ? "dim" : ""}>
                    <td>
                      {p.corpName}
                      <div className="hint mono">{p.corpCode}</div>
                    </td>
                    <td className="whitespace-nowrap">{p.periodLabel}</td>
                    <td>
                      <Link to={`/reports/${p.reportId}`}>{p.title}</Link>
                    </td>
                    <td className="r num">v{p.version}</td>
                    <td className="mono text-xs">{p.supersedesId ?? "—"}</td>
                    <td><StatusBadge status={p.status} /></td>
                    <td className="whitespace-nowrap">
                      <span className="mono">{p.submittedBy}</span>
                      <div className="hint num">{fmtTime(p.createdAt)}</div>
                    </td>
                    <td className="whitespace-nowrap">
                      {p.decidedBy ? (
                        <>
                          <span className="mono">{p.decidedBy}</span>
                          <div className="hint num">{fmtTime(p.decidedAt)}</div>
                        </>
                      ) : (
                        "—"
                      )}
                      {p.comment && <div className="hint">{p.comment}</div>}
                    </td>
                    <td className="mono text-xs break-all">{p.publicationId}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}
