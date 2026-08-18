import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      // once backend/api is running (FastAPI, default port 8000), this
      // forwards /api/* calls so the frontend never needs CORS config
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
      },
      // /health lives outside /api/* (see backend/api/main.py) -- SystemStatus
      // fetches it directly, so it needs the same proxy treatment.
      "/health": {
        target: "http://localhost:8000",
        changeOrigin: true,
      },
    },
  },
});
