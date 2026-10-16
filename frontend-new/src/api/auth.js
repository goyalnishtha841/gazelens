/**
 * auth.js -- ported unchanged from frontend/src/api/auth.js. Same backend
 * contract (backend/api/auth_routes.py), so this is a straight copy rather
 * than a reimplementation.
 */

import { apiUrl } from "./base.js";

const BASE = apiUrl("/api/auth");

function extractErrorMessage(body, status) {
  const { detail } = body;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    const first = detail[0];
    if (first?.msg) {
      const field = Array.isArray(first.loc) ? first.loc[first.loc.length - 1] : null;
      return field ? `${field}: ${first.msg}` : first.msg;
    }
  }
  return `Request failed (${status})`;
}

async function handleResponse(res) {
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(extractErrorMessage(body, res.status));
  }
  return res.json();
}

export async function signup({ email, password, fullName }) {
  const res = await fetch(`${BASE}/signup`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password, full_name: fullName || null }),
  });
  return handleResponse(res);
}

export async function login({ email, password }) {
  const res = await fetch(`${BASE}/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  return handleResponse(res);
}

export async function fetchCurrentUser(token) {
  const res = await fetch(`${BASE}/me`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  return handleResponse(res);
}
