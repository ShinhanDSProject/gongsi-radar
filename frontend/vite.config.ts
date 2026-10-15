import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { defineConfig } from "vite";

// [보안] 프런트가 아는 서버는 Spring Boot 하나다. /api를 개발 서버가 8180으로
//        넘겨 주므로 브라우저 입장에서는 전부 같은 출처(3100)다.
//        FastAPI(8100)·Core(9100)를 여기 추가하지 않는다 — AI 서버 내부 키와
//        Core 시스템 키(발행 쓰기)가 브라우저에 나가는 순간 Middle Zone 경계가 사라지고,
//        사람 승인 없이 발행 원장에 쓸 길이 열린다. 운영에서는 이 역할을
//        DMZ의 리버스 프록시(Nginx 등)가 맡는다.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 3100,
    strictPort: true,
    proxy: {
      "/api": { target: "http://localhost:8180", changeOrigin: true },
    },
  },
});
