import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import path from "node:path";
import { defineConfig } from "vite";

// `npm run dev` proxies to a manually started API on 8765:
//   python -m uvicorn playlist_downloader.server.app:app --port 8765
const DEV_API = "http://127.0.0.1:8765";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: { "@": path.resolve(import.meta.dirname, "src") },
  },
  build: {
    outDir: path.resolve(import.meta.dirname, "../src/playlist_downloader/web"),
    emptyOutDir: true,
  },
  server: {
    proxy: {
      "/api": DEV_API,
      "/ws": { target: DEV_API.replace("http", "ws"), ws: true },
    },
  },
});
