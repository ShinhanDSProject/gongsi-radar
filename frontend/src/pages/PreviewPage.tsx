import { useState, type ChangeEvent } from "react";
import type { RadarReport } from "../api/types";
import { ReportView } from "../components/report/ReportView";

// 서버 없이 report.json 파일을 열어 보는 미리보기(web/src/App.jsx의 JsonLoader).
// 파일은 이 브라우저 안에서만 읽고 어디로도 보내지 않는다. 수정·발행은 할 수 없다.
export default function PreviewPage() {
  const [rep, setRep] = useState<RadarReport | null>(null);
  const [err, setErr] = useState("");

  const pick = (e: ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0];
    if (!f) return;
    const rd = new FileReader();
    rd.onload = () => {
      try {
        const j = JSON.parse(String(rd.result));
        const body = j && j.body && j.body.meta ? j.body : j; // ReportDto를 통째로 저장한 파일도 받는다
        if (!body.meta || !body.changes) throw new Error("공시레이더 report.json 형식이 아닙니다.");
        setErr("");
        setRep(body as RadarReport);
      } catch (x) {
        setErr(x instanceof Error ? x.message : "읽지 못했습니다.");
      }
    };
    rd.readAsText(f, "utf-8");
  };

  return (
    <div className="stack">
      <div className="page-h">
        <h1>리포트 미리보기</h1>
        <span className="hint">
          <code>python -m radar demo --out DIR</code>로 만든 report.json을 서버 없이 엽니다. 읽기 전용입니다.
        </span>
      </div>
      <div className="panel">
        <label htmlFor="report-file" className="flabel">report.json 고르기</label>
        <input id="report-file" type="file" accept="application/json,.json" onChange={pick} />
        {err && <p className="err" role="alert">{err}</p>}
      </div>
      {rep && <ReportView rep={rep} editable={false} onEdit={async () => undefined} />}
    </div>
  );
}
