/**
 * render.js -- ported from frontend/src/api/render.js. Same backend
 * contract (backend/render/routes.py's /api/render/capture) and the same
 * adapter reshaping `layout` (dict keyed by element_id) into the array shape
 * components expect. The endpoint drives a server-side browser, so it
 * requires a bearer token: pass the `token` from useAuth().
 */

import { apiUrl } from "./base.js";

function adaptCaptureResponse(data) {
  const elements = Object.entries(data.layout || {}).map(([elementId, info]) => {
    const [x, y, w, h] = info.bbox;
    return {
      element_id: elementId,
      element_type: info.type,
      element_importance: info.importance,
      label: elementId.replace(/_/g, " "),
      bbox_normalized: { x, y, w, h },
    };
  });

  return {
    url: data.url,
    final_url: data.final_url,
    title: data.title,
    viewport: data.viewport,
    elements,
    detected: data.detected,
    kept: data.kept,
    low_confidence_fraction: data.low_confidence_fraction,
    warnings: data.warnings || [],
    screenshot_base64: data.screenshot_base64 ?? null,
  };
}

export async function renderUrl(token, url) {
  const res = await fetch(apiUrl("/api/render/capture"), {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
    body: JSON.stringify({ url }),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    const detail = typeof body.detail === "string" ? body.detail : `Couldn't render that URL (${res.status})`;
    throw new Error(detail);
  }
  const data = await res.json();
  return adaptCaptureResponse(data);
}

/**
 * Suggested element boxes for an uploaded screenshot (OCR + OpenCV on the
 * server, backend/render/image_detect.py). Nothing is stored. Returns
 * { width, height, elements: [{ label, type, importance, bbox, confidence, why }], seconds }.
 */
export async function detectImageElements(token, imageBase64) {
  const res = await fetch(apiUrl("/api/render/detect-image"), {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
    body: JSON.stringify({ image_base64: imageBase64 }),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(typeof data.detail === "string" ? data.detail : `Detection failed (${res.status})`);
  return data;
}
