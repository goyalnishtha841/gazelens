import { apiUrl } from "./base.js";

/**
 * admin.js -- the private admin view (backend/api/admin_routes.py).
 *
 * The admin token lives in sessionStorage, so it is gone when the tab closes
 * and is never mixed up with a user's login (localStorage "fixation_token").
 */

const KEY = "gazelens_admin_token";

export function getAdminToken() {
  try { return sessionStorage.getItem(KEY); } catch { return null; }
}
export function setAdminToken(token) {
  try { token ? sessionStorage.setItem(KEY, token) : sessionStorage.removeItem(KEY); } catch { /* storage blocked */ }
}

async function parse(res) {
  if (res.ok) return res.json();
  const body = await res.json().catch(() => ({}));
  const err = new Error(typeof body.detail === "string" ? body.detail : `Request failed (${res.status})`);
  err.status = res.status;
  throw err;
}

export async function adminLogin(password) {
  const res = await fetch(apiUrl("/api/admin/login"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ password }),
  });
  return parse(res);
}

function authed(token) {
  return { headers: { Authorization: `Bearer ${token}` } };
}

export async function adminOverview(token) {
  return parse(await fetch(apiUrl("/api/admin/overview"), authed(token)));
}

export async function adminUser(token, userId) {
  return parse(await fetch(apiUrl(`/api/admin/users/${encodeURIComponent(userId)}`), authed(token)));
}
