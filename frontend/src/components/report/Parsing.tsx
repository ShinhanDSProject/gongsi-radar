// 원문 파싱 탭. DART document.xml의 함정을 파서가 어떻게 처리했는지 숫자로 남긴다.
import type { RadarReport } from "../../api/types";
import { Empty } from "../ui";

export function Parsing({ rep }: { rep: RadarReport }) {
  const sides = [
    ["prior", rep.meta.prior],
    ["current", rep.meta.current],
  ] as const;
  return (
    <div className="stack">
      <p className="hint">DART 원문(document.xml)은 정상적인 XML이 아닙니다. 파서가 처리한 함정을 숫자로 남깁니다.</p>
      <div className="two-col">
        {sides.map(([k, f]) => {
          const p = rep.parse?.[k];
          if (!p) return <Empty key={k}>{f.report_nm} 파싱 기록이 없습니다.</Empty>;
          const cc = p.cell_counts || {};
          const te = (cc.TE || 0) + (cc.TU || 0);
          return (
            <section className="panel" key={k}>
              <header className="panel-h">
                <h2>{f.report_nm}</h2>
                <span className="hint mono">{p.rcept_no}</span>
              </header>
              <dl className="kv">
                <dt>ZIP 안 파일</dt>
                <dd>
                  {p.files.map((n) => (
                    <span key={n} className={`file${n === p.chosen_file ? " chosen" : ""}`}>
                      {n}
                      {n === p.chosen_file ? " ← 본문" : ""}
                    </span>
                  ))}
                </dd>
                <dt>인코딩</dt>
                <dd>
                  선언 {p.encoding_declared || "없음"} · 실제 {p.encoding_used}
                </dd>
                <dt>파싱</dt>
                <dd>{p.mode === "strict" ? "엄격 파싱 성공" : "복구 모드(손실 가능)"}</dd>
                <dt>&amp; 수리</dt>
                <dd className="num">{p.amp_fixed}곳</dd>
                <dt>가짜 태그</dt>
                <dd className="num">{p.fake_tags_escaped}개를 텍스트로</dd>
                <dt>표 셀</dt>
                <dd className="num">
                  TH {cc.TH ?? 0} · TD {cc.TD ?? 0} · TE {cc.TE ?? 0} · TU {cc.TU ?? 0}
                </dd>
                <dt>구조</dt>
                <dd className="num">
                  섹션 {p.sections} · 문단 {p.paragraphs} · 표 {p.tables}
                </dd>
              </dl>
              {te > 0 && <p className="note">TD/TH만 읽었다면 셀 {te}개가 오류 없이 빠졌을 것입니다.</p>}
              {p.warnings.length > 0 && (
                <ul className="warns">
                  {p.warnings.map((w, i) => (
                    <li key={i}>{w}</li>
                  ))}
                </ul>
              )}
            </section>
          );
        })}
      </div>
    </div>
  );
}
