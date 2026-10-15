import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Separate port from frontend/ (5173) so both can run side by side while
// this redesign is being evaluated. Same backend, same proxy shape.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5180,
    // Without an explicit host, Vite resolves "localhost" via Node's DNS
    // lookup and binds only whichever address comes back first -- on this
    // machine that's IPv6 (::1). A browser request to http://localhost:PORT
    // that then resolves to 127.0.0.1 gets ERR_CONNECTION_REFUSED even
    // though the dev server is up. `host: true` listens on all interfaces
    // (both loopbacks) instead of picking one.
    host: true,
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
