// Squarified treemap (Bruls·Huizing·van Wijk, 2000). 외부 라이브러리 없이 직접 구현한다.
// 값이 큰 것부터 짧은 변을 따라 한 줄씩 채우고, 줄에 하나를 더 넣었을 때
// 가장 나쁜 가로세로비가 나빠지면 그 줄을 확정하고 남은 사각형으로 넘어간다.
export interface Rect {
  x: number;
  y: number;
  w: number;
  h: number;
}
export interface Tile<T> extends Rect {
  item: T;
}

// 줄(row) 안에서 가장 길쭉한 칸의 가로세로비(1에 가까울수록 정사각형)
function worst(areas: number[], side: number): number {
  let sum = 0;
  let max = -Infinity;
  let min = Infinity;
  for (const a of areas) {
    sum += a;
    if (a > max) max = a;
    if (a < min) min = a;
  }
  if (sum <= 0 || min <= 0) return Infinity;
  const s2 = side * side;
  return Math.max((s2 * max) / (sum * sum), (sum * sum) / (s2 * min));
}

export function squarify<T>(items: T[], value: (t: T) => number, rect: Rect): Tile<T>[] {
  // 0·음수·NaN은 면적을 가질 수 없으니 뺀다(표에는 따로 남긴다)
  const list = items
    .map((item) => ({ item, v: value(item) }))
    .filter((x) => Number.isFinite(x.v) && x.v > 0)
    .sort((a, b) => b.v - a.v);
  const total = list.reduce((s, x) => s + x.v, 0);
  const out: Tile<T>[] = [];
  if (!list.length || total <= 0 || rect.w <= 0 || rect.h <= 0) return out;

  // 값을 면적(px²)으로 바꾼다
  const scale = (rect.w * rect.h) / total;
  const areas = list.map((x) => x.v * scale);
  let r: Rect = { ...rect };

  // 확정한 줄을 남은 사각형의 짧은 변에 붙여 놓고, 남은 사각형을 돌려준다
  const layoutRow = (idx: number[], rr: Rect): Rect => {
    const sum = idx.reduce((s, i) => s + areas[i], 0);
    if (rr.w >= rr.h) {
      // 가로가 길다 → 왼쪽에 세로 기둥 하나
      const thick = rr.h > 0 ? sum / rr.h : 0;
      let y = rr.y;
      for (const i of idx) {
        const h = thick > 0 ? areas[i] / thick : 0;
        out.push({ item: list[i].item, x: rr.x, y, w: thick, h });
        y += h;
      }
      return { x: rr.x + thick, y: rr.y, w: Math.max(0, rr.w - thick), h: rr.h };
    }
    // 세로가 길다 → 위쪽에 가로 띠 하나
    const thick = rr.w > 0 ? sum / rr.w : 0;
    let x = rr.x;
    for (const i of idx) {
      const w = thick > 0 ? areas[i] / thick : 0;
      out.push({ item: list[i].item, x, y: rr.y, w, h: thick });
      x += w;
    }
    return { x: rr.x, y: rr.y + thick, w: rr.w, h: Math.max(0, rr.h - thick) };
  };

  let row: number[] = [];
  let i = 0;
  while (i < areas.length) {
    const side = Math.min(r.w, r.h);
    const rowAreas = row.map((k) => areas[k]);
    if (!row.length || worst([...rowAreas, areas[i]], side) <= worst(rowAreas, side)) {
      row.push(i);
      i++;
    } else {
      r = layoutRow(row, r);
      row = [];
    }
  }
  if (row.length) layoutRow(row, r);
  return out;
}
