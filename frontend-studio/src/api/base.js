/**
 * base.js -- where the API lives.
 *
 * Empty by default: every call is same-origin ("/api/...") and the Vite dev
 * proxy forwards it locally. Set VITE_API_BASE_URL at BUILD time when the
 * frontend and API are on different origins (e.g. Vercel + a Hugging Face Space):
 *
 *   VITE_API_BASE_URL=https://<hf-username>-gazelens-api.hf.space npm run build
 *
 * and add the frontend's origin to the backend's GAZELENS_CORS_ORIGINS.
 */
export const API_BASE = (import.meta.env.VITE_API_BASE_URL || "").replace(/\/+$/, "");

export function apiUrl(path) {
  return `${API_BASE}${path}`;
}
