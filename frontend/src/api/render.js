/**
 * render.js
 *
 * Real network call to backend/render's /api/render/capture endpoint.
 *
 * CONTRACT MISMATCH, fixed here rather than upstream: this file previously
 * called POST /api/render (wrong path -- the real route is
 * /api/render/capture) and expected a response shape
 * ({ elements: [{element_id, element_type, element_importance, label,
 * bbox_normalized:{x,y,w,h}}] }) that backend/render never produced.
 * backend/render/routes.py's real CaptureResponse returns `layout` as a dict
 * keyed by element_id ({bbox: (x,y,w,h), importance, type}), with no label
 * field. adaptCaptureResponse() below reshapes `layout` into the array shape
 * the frontend components expect and fills `label` from the element id.
 *
 * screenshot_base64 previously came back null in every case -- the route
 * never asked capture_page() to write a screenshot file at all, so there was
 * nothing to encode. Fixed in backend/render/routes.py (capture() now passes
 * a temp screenshot_path and returns it base64-encoded); this adapter just
 * passes that field through.
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
    // May still be null if the screenshot itself failed to capture even
    // though element detection succeeded -- callers must handle that case.
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
