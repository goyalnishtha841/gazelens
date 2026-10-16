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

// Shared by calibration and the live session so both see the same camera
// geometry. 640x480 (the browser default) left the eye ~30px wide, too small
// for the iris to move measurably across the screen.
export const CAMERA_CONSTRAINTS = {
  video: { width: { ideal: 1280 }, height: { ideal: 720 }, facingMode: "user" },
};
