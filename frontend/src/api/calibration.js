/**
 * calibration.js
 *
 * Real network calls against backend/calibration (backend/calibration/routes.py,
 * backend/calibration/schemas.py). No auth dependency on these routes yet --
 * see calibration/CONTRACT.md -- so no bearer token here, unlike client.js.
 *
 *   POST   /api/calibration/sessions                  start
 *   POST   /api/calibration/sessions/{id}/samples      submit a burst of frames
 *   POST   /api/calibration/sessions/{id}/complete     finish + export
 *   GET    /api/calibration/sessions/{id}              progress + quality
 *   GET    /api/calibration/patterns                   the target grids
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

/** pattern: 9 or 16 targets. screenWidth/screenHeight: viewport px. */
export async function startCalibration({ participantId, pattern = 9, screenWidth, screenHeight, samplesPerPoint }) {
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

/**
 * frames: base64 JPEG strings (canvas.toDataURL("image/jpeg") output, or the
 * raw base64 without the data: prefix -- the server accepts either).
 *
 * targetX/targetY (both normalised [0,1], optional but must be given
 * together): the dot's ACTUAL on-screen position, when the client's layout
 * doesn't match the server's generated grid exactly. The server records
 * which source it used ("client" vs "server_grid") -- see
 * SubmitSamplesRequest in backend/calibration/schemas.py.
 */
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
