// 요소의 실제 가로 폭(px)을 따라간다. 그래프·트리맵이 화면 폭에 맞춰 다시 그리도록 쓴다.
// ResizeObserver가 없는 환경(구형 브라우저·SSR)에서는 fallback 폭을 그대로 쓴다.
import { useLayoutEffect, useRef, useState } from "react";

export function useElementWidth<T extends HTMLElement>(fallback = 640) {
  const ref = useRef<T | null>(null);
  const [width, setWidth] = useState(fallback);
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    const measure = () => {
      const w = Math.floor(el.getBoundingClientRect().width);
      if (w > 0) setWidth(w);
    };
    measure();
    if (typeof ResizeObserver === "undefined") return;
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  return [ref, width] as const;
}
