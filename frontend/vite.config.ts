import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "path";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  server: {
    host: true,
    port: 5173,
    // Codespaces пробрасывает фронт через домен *.app.github.dev — разрешаем его,
    // иначе Vite 5 отвечает "Blocked request. This host is not allowed".
    allowedHosts: [".app.github.dev"],
    // В Codespaces публичен только порт 5173. Запросы фронта к FastAPI
    // проксируем на localhost:8000 — браузеру второй публичный порт не нужен.
    // /nutritionist/query — точечно, чтобы не перехватить SPA-страницу /nutritionist.
    proxy: {
      "/me": "http://localhost:8000",
      "/chat": "http://localhost:8000",
      "/clients": "http://localhost:8000",
      "/health": "http://localhost:8000",
      "/nutritionist/query": "http://localhost:8000",
    },
  },
});
