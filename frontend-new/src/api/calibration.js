/**
 * calibration.js -- ported from frontend/src/api/calibration.js. Same backend
 * contract (backend/calibration/routes.py).
 *
 * Every calibration and gaze-model route requires a bearer token, and a
 * calibration is visible only to the user who started it -- callers pass the
 * `token` from useAuth() first, same as client.js.
 */

import { apiUrl } from "./base.js";

const BASE = apiUrl("/api/calibration");

function authHeaders(token) {
  return { Authorization: `Bearer ${token}` };
}

async function handleResponse(res) {
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    const { detail } = body;
    const message = typeof detail === "string" ? detail : `Request failed (${res.status})`;
    const err = new Error(message);
    err.status = res.status;
    throw err;
  }
  return res.json();
}

export async function startCalibration(token, { participantId, pattern = 16, screenWidth, screenHeight, samplesPerPoint }) {
  const res = await fetch(`${BASE}/sessions`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders(token) },
    body: JSON.stringify({
      participant_id: participantId,
      pattern,
      screen_width: screenWidth,
      screen_height: screenHeight,
      ...(samplesPerPoint ? { samples_per_point: samplesPerPoint } : {}),
    }),
  });
  return handleResponse(res);
}

export async function submitCalibrationSamples(token, sessionId, pointIndex, frames, targetX, targetY) {
  const res = await fetch(`${BASE}/sessions/${sessionId}/samples`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders(token) },
    body: JSON.stringify({
      point_index: pointIndex,
      frames,
      target_x: targetX ?? null,
      target_y: targetY ?? null,
    }),
  });
  return handleResponse(res);
}

export async function completeCalibration(token, sessionId) {
  const res = await fetch(`${BASE}/sessions/${sessionId}/complete`, {
    method: "POST",
    headers: authHeaders(token),
  });
  return handleResponse(res);
}

export async function getCalibrationSession(token, sessionId) {
  const res = await fetch(`${BASE}/sessions/${sessionId}`, { headers: authHeaders(token) });
  return handleResponse(res);
}

/** The caller's own calibration sessions (summaries, no screen size). */
export async function listCalibrationSessions(token) {
  const res = await fetch(`${BASE}/sessions`, { headers: authHeaders(token) });
  return handleResponse(res);
}

/** A trained model's stored accuracy; validation_pass holds the accuracy
 *  check's verdict (null if none ran). 404 when it was never trained. */
export async function getGazeModel(token, sessionId) {
  const res = await fetch(apiUrl(`/api/gaze/models/${sessionId}`), { headers: authHeaders(token) });
  return handleResponse(res);
}

// Same 2% as backend/api/session_routes.py SCREEN_MATCH_TOLERANCE: linking a
// calibration recorded on a differently sized window is refused there.
const SCREEN_MATCH_TOLERANCE = 0.02;

export function screenMatches(width, height, current = { width: window.innerWidth, height: window.innerHeight }) {
  if (!width || !height) return false;
  return Math.abs(current.width - width) / width <= SCREEN_MATCH_TOLERANCE
    && Math.abs(current.height - height) / height <= SCREEN_MATCH_TOLERANCE;
}

/**
 * The newest calibration a live session would accept right now: completed,
 * recorded on a window this size, and whose precision check passed (good or
 * fair -- the same verdicts Calibration lets you continue with). Returns
 * { id, screenWidth, screenHeight } or null. Only checks the few newest, so a
 * long history doesn't turn sign-in into dozens of requests.
 */
export async function findUsableCalibration(token, { maxChecked = 5 } = {}) {
  const sessions = await listCalibrationSessions(token);
  const candidates = sessions
    .filter((s) => s.session_id && s.status === "complete" && s.usable !== false)
    .sort((a, b) => (b.created_at ?? 0) - (a.created_at ?? 0))
    .slice(0, maxChecked);

  for (const s of candidates) {
    try {
      const detail = await getCalibrationSession(token, s.session_id);
      if (!screenMatches(detail.screen_width, detail.screen_height)) continue;
      const model = await getGazeModel(token, s.session_id);
      const verdict = model.validation_pass?.verdict;
      if (verdict !== "good" && verdict !== "fair") continue;
      return { id: s.session_id, screenWidth: detail.screen_width, screenHeight: detail.screen_height };
    } catch {
      // never trained (404) or since deleted -- try the next one
    }
  }
  return null;
}

/**
 * One validation dot (backend/gaze_estimation/routes.py validate): frames
 * captured while a NEW dot was on screen, after calibration. The server
 * trains the model on first call, scores this dot, and returns the running
 * summary (median_error_px, verdict: good | fair | poor | insufficient).
 */
export async function validateGaze(token, sessionId, pointIndex, frames, targetX, targetY) {
  const res = await fetch(apiUrl(`/api/gaze/models/${sessionId}/validate`), {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders(token) },
    body: JSON.stringify({ point_index: pointIndex, frames, target_x: targetX, target_y: targetY }),
  });
  return handleResponse(res);
}

/**
 * Before a new test (backend/gaze_estimation/routes.py check_position): a
 * short burst of frames compared with the head pose saved at calibration.
 * status: ok | moved | no_face | unknown; `reasons` are plain sentences.
 */
export async function checkPosition(token, sessionId, frames) {
  const res = await fetch(apiUrl(`/api/gaze/models/${sessionId}/position-check`), {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders(token) },
    body: JSON.stringify({ frames }),
  });
  return handleResponse(res);
}

// Shared by calibration and the live session so both see the same camera
// geometry. 640x480 (the browser default) left the eye ~30px wide, too small
// for the iris to move measurably across the screen.
export const CAMERA_CONSTRAINTS = {
  video: { width: { ideal: 1280 }, height: { ideal: 720 }, facingMode: "user" },
};
