import { MutationCache, QueryCache, QueryClient, QueryClientProvider } from "@tanstack/react-query";
import React from "react";
import ReactDOM from "react-dom/client";
import { App } from "./App";
import "./index.css";

import { ApiError } from "./api/client";

// 在线版登录过期：任何请求 401 都回到登录框
const onError = (e: unknown) => { if (e instanceof ApiError && e.status === 401) qc.setQueryData(["me"], null); };
const qc: QueryClient = new QueryClient({
  defaultOptions: { queries: { retry: (n, e) => !(e instanceof ApiError && e.status < 500) && n < 1, refetchOnWindowFocus: false } },
  queryCache: new QueryCache({ onError }),
  mutationCache: new MutationCache({ onError }),
});

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <QueryClientProvider client={qc}>
      <App />
    </QueryClientProvider>
  </React.StrictMode>,
);
