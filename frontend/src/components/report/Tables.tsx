// 표 탭. 표는 LLM에 보내지 않고 규칙으로 비교한 결과다(web/src/views.jsx Tables).
import type { RadarReport } from "../../api/types";
import { Cite, Empty } from "../ui";

const CELL_KIND: Record<string, string> = { changed: "값 변경", row_added: "행 추가", row_removed: "행 삭제" };

export function Tables({ rep }: { rep: RadarReport }) {
  if (!rep.tables.length) return <Empty>바뀐 표가 없습니다.</Empty>;
  return (
    <div className="stack">
      <p className="hint">표는 LLM에 보내지 않고 항목명(첫 열)과 머리글로 맞춰 규칙으로 비교합니다.</p>
      {rep.tables.map((t) => (
        <section className="panel" key={t.id}>
          <header className="panel-h">
            <h2>{t.section_path.split(" > ").slice(-1)[0]}</h2>
            <span className="hint">
              {t.title}
              {t.unit ? ` · ${t.unit}` : ""}
            </span>
          </header>
          {t.note && <p className="note">{t.note}</p>}
          {t.cells.length > 0 && (
            <div className="scroll-x">
              <table className="grid-table">
                <thead>
                  <tr>
                    <th scope="col">항목</th>
                    <th scope="col">열</th>
                    <th scope="col" className="r">이전</th>
                    <th scope="col" className="r">현재</th>
                    <th scope="col">구분</th>
                  </tr>
                </thead>
                <tbody>
                  {t.cells.map((c, i) => (
                    <tr key={i}>
                      <td>{c.row}</td>
                      <td>{c.column || "—"}</td>
                      <td className="r num">{c.old || "—"}</td>
                      <td className="r num">{c.new || "—"}</td>
                      <td>{CELL_KIND[c.kind] ?? c.kind}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <p className="ids">
            {t.old_id && <Cite id={t.old_id} />}
            {t.new_id && <Cite id={t.new_id} />}
          </p>
        </section>
      ))}
    </div>
  );
}
