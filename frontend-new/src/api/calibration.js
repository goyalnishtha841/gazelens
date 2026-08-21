/**
 * calibration.js -- ported unchanged from frontend/src/api/calibration.js.
 * Same backend contract (backend/calibration/routes.py).
 */

const BASE = "/api/calibration";

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

export async function startCalibration({ participantId, pattern = 16, screenWidth, screenHeight, samplesPerPoint }) {
  const res = await fetch(`${BASE}/sessions`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
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

export async function submitCalibrationSamples(sessionId, pointIndex, frames, targetX, targetY) {
  const res = await fetch(`${BASE}/sessions/${sessionId}/samples`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      point_index: pointIndex,
      frames,
      target_x: targetX ?? null,
      target_y: targetY ?? null,
    }),
  });
  return handleResponse(res);
}

export async function completeCalibration(sessionId) {
  const res = await fetch(`${BASE}/sessions/${sessionId}/complete`, { method: "POST" });
  return handleResponse(res);
}

export async function getCalibrationSession(sessionId) {
  const res = await fetch(`${BASE}/sessions/${sessionId}`);
  return handleResponse(res);
}
