import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { fileURLToPath, URL } from "node:url";
import { defineConfig } from "vite";

// 开发：npm run dev（5173）+ 后端 uv run mediaflow --reload（8765），接口走代理
export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: { alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) } },
  server: {
    proxy: {
      "/api": "http://127.0.0.1:8765",
      "/files": "http://127.0.0.1:8765",
    },
  },
});
