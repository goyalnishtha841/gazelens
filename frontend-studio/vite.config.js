import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

// Dev-server proxy target for the FastAPI backend. Override with
// VITE_PROXY_TARGET (e.g. in .env.local) when the API isn't on :8000.
// Production builds don't use this at all: either something same-origin
// forwards /api (nginx in the Docker image) or VITE_API_BASE_URL points the
// client straight at the API -- see src/api/base.js.
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  const target = env.VITE_PROXY_TARGET || "http://localhost:8000";
  const proxied = { target, changeOrigin: true };

  return {
    plugins: [react()],
    server: {
      port: 5181,
      // Without an explicit host, Vite resolves "localhost" via Node's DNS
      // lookup and binds only whichever address comes back first -- on this
      // machine that's IPv6 (::1). A browser request to http://localhost:PORT
      // that then resolves to 127.0.0.1 gets ERR_CONNECTION_REFUSED even
      // though the dev server is up. `host: true` listens on all interfaces
      // (both loopbacks) instead of picking one.
      host: true,
      proxy: {
        "/api": proxied,
        "/health": proxied,
        "/test-uis": proxied,
      },
    },
  };
});
