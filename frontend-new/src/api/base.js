/**
 * base.js -- where the API lives.
 *
 * Empty by default: every call is same-origin ("/api/...") and something in
 * front of the app forwards it -- the Vite dev proxy locally, nginx in the
 * Docker image. Set VITE_API_BASE_URL at BUILD time when the frontend and API
 * are on different origins (e.g. Vercel + Render):
 *
 *   VITE_API_BASE_URL=https://gazelens-api.onrender.com npm run build
 *
 * and add the frontend's origin to the backend's GAZELENS_CORS_ORIGINS.
 */
export const API_BASE = (import.meta.env.VITE_API_BASE_URL || "").replace(/\/+$/, "");

export function apiUrl(path) {
  return `${API_BASE}${path}`;
}
