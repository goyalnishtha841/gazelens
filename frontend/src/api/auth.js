/**
 * auth.js
 *
 * Real network calls (not mocked) since backend/api/ now actually exists
 * for auth specifically. Everything else in api/client.js stays mocked
 * until the rest of the API (sessions, reports) is built.
 */

const BASE = "/api/auth"; // Vite proxies this to http://localhost:8000

function extractErrorMessage(body, status) {
  const { detail } = body;

  if (typeof detail === "string") {
    return detail;
  }

  if (Array.isArray(detail)) {
    // FastAPI/Pydantic validation errors come back as a list of
    // {loc, msg, type} objects, e.g. invalid email format, password too
    // short. Turn the first one into readable text instead of letting it
    // stringify to "[object Object]".
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
