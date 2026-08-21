import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Separate port from frontend/ (5173) so both can run side by side while
// this redesign is being evaluated. Same backend, same proxy shape.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5180,
    proxy: {
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
      },
      "/health": {
        target: "http://localhost:8000",
        changeOrigin: true,
      },
      "/test-uis": {
        target: "http://localhost:8000",
        changeOrigin: true,
      },
    },
  },
});
