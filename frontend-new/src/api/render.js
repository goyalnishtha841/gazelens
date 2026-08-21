/**
 * render.js -- ported unchanged from frontend/src/api/render.js. Same
 * backend contract (backend/render/routes.py's /api/render/capture) and the
 * same adapter reshaping `layout` (dict keyed by element_id) into the array
 * shape components expect.
 */

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

export async function renderUrl(url) {
  const res = await fetch("/api/render/capture", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
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
