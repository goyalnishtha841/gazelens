/**
 * client.js
 *
 * Real network calls against backend/api's session lifecycle
 * (backend/api/session_routes.py, backend/api/schemas.py, backend/api/CONTRACT.md).
 * Every session route requires a bearer token -- callers pass the `token`
 * from useAuth() as the first argument, same convention api/auth.js already
 * uses for fetchCurrentUser(token).
 *
 * Endpoint map (see CONTRACT.md for the full rationale):
 *   POST   /api/sessions                    create
 *   GET    /api/sessions                    list (paginated)
 *   GET    /api/sessions/{id}               status + next_action
 *   POST   /api/sessions/{id}/calibration   link calibration, train gaze model
 *   POST   /api/sessions/{id}/gaze          append a batch of gaze points
 *   POST   /api/sessions/{id}/finalize      run attribution -> agents -> report (async)
 *   GET    /api/sessions/{id}/report        the report, or 202 while pending
 *   GET    /api/sessions/meta/test-uis      which ui_page values are valid
 */

const BASE = "/api/sessions";

function authHeaders(token) {
  return { Authorization: `Bearer ${token}` };
}

async function handleResponse(res) {
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    const { detail } = body;
    let message = `Request failed (${res.status})`;
    if (typeof detail === "string") {
      message = detail;
    } else if (Array.isArray(detail) && detail[0]?.msg) {
      const field = Array.isArray(detail[0].loc) ? detail[0].loc[detail[0].loc.length - 1] : null;
      message = field ? `${field}: ${detail[0].msg}` : detail[0].msg;
    }
    const err = new Error(message);
    err.status = res.status;
    throw err;
  }
  if (res.status === 204) return null;
  return res.json();
}

/** mode="test_ui" needs ui_page; mode="url" needs target_url. */
export async function startSession(token, { mode = "test_ui", uiPage, targetUrl, label, calibrationSessionId } = {}) {
  const res = await fetch(BASE, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders(token) },
    body: JSON.stringify({
      mode,
      ui_page: uiPage ?? null,
      target_url: targetUrl ?? null,
      label: label ?? null,
      calibration_session_id: calibrationSessionId ?? null,
    }),
  });
  return handleResponse(res);
}

export async function listSessions(token, { limit = 20, offset = 0, status } = {}) {
  const params = new URLSearchParams({ limit: String(limit), offset: String(offset) });
  if (status) params.set("status", status);
  const res = await fetch(`${BASE}?${params}`, { headers: authHeaders(token) });
  return handleResponse(res);
}

export async function getSession(token, sessionId) {
  const res = await fetch(`${BASE}/${sessionId}`, { headers: authHeaders(token) });
  return handleResponse(res);
}

export async function listTestUis(token) {
  const res = await fetch(`${BASE}/meta/test-uis`, { headers: authHeaders(token) });
  return handleResponse(res);
}

/**
 * Attach a completed calibration session (backend/calibration) and train its
 * gaze model. Sends the CURRENT window size so the server can refuse to
 * link against a calibration recorded at a different screen size -- see
 * CalibrationLinkRequest/screen_mismatch in backend/api/schemas.py. Defaults
 * to the live window's own size, since that's what "the current screen"
 * means at the call site (starting a session); pass explicit values only if
 * a caller needs to check on the participant's behalf ahead of time.
 */
export async function linkCalibration(
  token, sessionId, calibrationSessionId, trainModel = true,
  screenWidth = window.innerWidth, screenHeight = window.innerHeight,
) {
  const res = await fetch(`${BASE}/${sessionId}/calibration`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders(token) },
    body: JSON.stringify({
      calibration_session_id: calibrationSessionId,
      train_model: trainModel,
      screen_width: screenWidth,
      screen_height: screenHeight,
    }),
  });
  return handleResponse(res);
}

/**
 * Append a batch of estimated gaze points.
 * points: [{ timestamp, x, y, valid, confidence, scroll_x, scroll_y }]
 */
export async function appendGaze(token, sessionId, points) {
  const res = await fetch(`${BASE}/${sessionId}/gaze`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders(token) },
    body: JSON.stringify({ gaze: points }),
  });
  return handleResponse(res);
}

/** Starts analysis in the background; poll getReport() until it's no longer 202. */
export async function finalizeSession(token, sessionId) {
  const res = await fetch(`${BASE}/${sessionId}/finalize`, {
    method: "POST",
    headers: authHeaders(token),
  });
  return handleResponse(res);
}

/**
 * Returns { ready: false, ... } (HTTP 202) while the pipeline is still
 * running, or the full ReportResponse once it's done. Never throws for the
 * pending case -- callers poll this instead of treating 202 as an error.
 */
export async function getSessionReport(token, sessionId) {
  const res = await fetch(`${BASE}/${sessionId}/report`, { headers: authHeaders(token) });
  if (res.status === 202) {
    const body = await res.json();
    return { ...body, ready: false };
  }
  const body = await handleResponse(res);
  return { ...body, ready: true };
}

/**
 * Fetches the report's heatmap or scanpath PNG as an authenticated request
 * and returns an object URL for it. An <img src> can't carry a bearer
 * token, and these images are ownership-scoped like everything else in the
 * session API (see session_routes.py's _report_image) -- so this exists to
 * bridge that gap, not because a plain <img src="/api/..."> would work.
 *
 * Caller owns the returned URL and should URL.revokeObjectURL() it when the
 * <img> unmounts, the same way you'd clean up any other object URL.
 */
export async function getSessionImage(token, sessionId, kind) {
  const res = await fetch(`${BASE}/${sessionId}/${kind}`, { headers: authHeaders(token) });
  if (!res.ok) {
    const err = new Error(`No ${kind} image for this session`);
    err.status = res.status;
    throw err;
  }
  const blob = await res.blob();
  return URL.createObjectURL(blob);
}

/**
 * One webcam frame -> one on-screen gaze point, appended server-side to the
 * session's gaze stream and returned so the UI can draw the live cursor.
 * Requires the session's calibration to be linked and its gaze model
 * trained (POST /api/sessions/{id}/calibration) first.
 */
export async function estimateGazeFrame(token, sessionId, frameB64, timestamp, stage, scrollY = 0) {
  // stage: {x, y, w, h} as viewport fractions -- where the evaluated page is
  // drawn. The server remaps gaze into it (api/pipeline.py to_stage_space).
  // scrollY: how far a long captured page is scrolled inside the stage, in
  // the page's own CSS pixels (pipeline.to_document_space needs it).
  const res = await fetch(`${BASE}/${sessionId}/gaze/frame`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders(token) },
    body: JSON.stringify({ frame: frameB64, timestamp: timestamp ?? null, stage: stage ?? null, scroll_y: Math.max(0, scrollY || 0) }),
  });
  return handleResponse(res);
}

/**
 * Fetches the report's rendered PDF as an authenticated blob and triggers a
 * browser download for it. Same auth-blob reasoning as getSessionImage: a
 * plain <a href> can't carry a bearer token, and this file is
 * ownership-scoped like everything else in the session API.
 */
export async function downloadSessionPdf(token, sessionId) {
  const res = await fetch(`${BASE}/${sessionId}/pdf`, { headers: authHeaders(token) });
  if (!res.ok) {
    const err = new Error("No PDF available for this session");
    err.status = res.status;
    throw err;
  }
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `gazelens-report-${sessionId}.pdf`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

export async function deleteSession(token, sessionId) {
  const res = await fetch(`${BASE}/${sessionId}`, { method: "DELETE", headers: authHeaders(token) });
  return handleResponse(res);
}

/**
 * GET /health -- liveness plus whether live capture can actually run
 * (backend/api/main.py). Unauthenticated, like the route itself.
 */
export async function getHealth() {
  const res = await fetch("/health");
  return handleResponse(res);
}
