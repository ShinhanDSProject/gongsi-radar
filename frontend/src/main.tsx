import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter } from "react-router-dom";
import App from "./App";
import { AuthProvider } from "./auth";
import { ApiError } from "./api/client";
import "./index.css";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      // 권한·인증 오류는 다시 물어도 결과가 같다. 네트워크 흔들림만 한 번 더 시도한다
      retry: (count, err) =>
        count < 1 && !(err instanceof ApiError && ["UNAUTHORIZED", "FORBIDDEN", "NOT_FOUND"].includes(err.code)),
      refetchOnWindowFocus: false,
    },
  },
});

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <BrowserRouter>
          <App />
        </BrowserRouter>
      </AuthProvider>
    </QueryClientProvider>
  </StrictMode>,
);
