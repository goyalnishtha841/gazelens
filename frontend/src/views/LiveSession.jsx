import { useState, useRef, useEffect, useCallback } from "react";
import { useAuth } from "../context/AuthContext.jsx";
import { startSession, linkCalibration, estimateGazeFrame, finalizeSession, listTestUis } from "../api/client.js";
import { renderUrl } from "../api/render.js";

const GAZE_CAPTURE_INTERVAL_MS = 300; // ~3 fps -- conservative for a CPU-only mediapipe+YOLO pipeline
const FRAME_QUALITY = 0.7;

const TYPE_COLORS = {
  CTA: "#B23A2E",
  nav: "#57605C",
  form_field: "#1F6F78",
};

function formatClock(ms) {
  const totalSeconds = Math.floor(ms / 1000);
  const h = String(Math.floor(totalSeconds / 3600)).padStart(2, "0");
  const m = String(Math.floor((totalSeconds % 3600) / 60)).padStart(2, "0");
  const s = String(totalSeconds % 60).padStart(2, "0");
  return `${h}:${m}:${s}`;
}

export default function LiveSession({ calibrationSessionId, onSessionEnd, onNavigate }) {
  const { user, token } = useAuth();
  const [mode, setMode] = useState("fixed"); // "fixed" | "url"
  const [testPages, setTestPages] = useState([]);
  const [selectedPage, setSelectedPage] = useState(null);

  const [urlInput, setUrlInput] = useState("");
  const [rendering, setRendering] = useState(false);
  const [renderError, setRenderError] = useState(null);
  const [renderedPage, setRenderedPage] = useState(null); // {url, screenshot_base64, elements, viewport}

  const [session, setSession] = useState(null);
  const [cameraError, setCameraError] = useState(null);
  const [startError, setStartError] = useState(null);
  const [starting, setStarting] = useState(false);
  const [elapsedMs, setElapsedMs] = useState(0);
  const [tab, setTab] = useState("insights");
  const [noteDraft, setNoteDraft] = useState("");
  const [notes, setNotes] = useState([]);
  const [gazePoint, setGazePoint] = useState(null); // {x, y} normalised [0,1], or null while nothing valid yet
  const [gazeWarning, setGazeWarning] = useState(null);

  const videoRef = useRef(null);
  const canvasRef = useRef(null);
  const streamRef = useRef(null);
  const sessionStartRef = useRef(null);
  const gazeTimerRef = useRef(null);

  // Which ui_page values a test_ui session can actually use -- fetched
  // rather than hardcoded, since backend/api/layouts.py currently only has
  // 3 interim layouts (ecommerce_product_page, form_page, dashboard_page),
  // not the 5 this screen originally assumed. See CONTRACT.md item 5.
  useEffect(() => {
    listTestUis(token)
      .then((data) => {
        setTestPages(data.ui_pages);
        setSelectedPage((prev) => prev ?? data.ui_pages[0]);
      })
      .catch(() => {});
  }, [token]);

  useEffect(() => () => {
    streamRef.current?.getTracks().forEach((t) => t.stop());
    clearInterval(gazeTimerRef.current);
  }, []);

  // The setup screen and the recording view each render their own <video>
  // element (different JSX subtrees), so videoRef points at a fresh DOM node
  // whenever `session` flips -- reattach the already-granted stream each time.
  useEffect(() => {
    if (videoRef.current && streamRef.current) {
      videoRef.current.srcObject = streamRef.current;
    }
  }, [session]);

  useEffect(() => {
    if (!session) return;
    sessionStartRef.current = performance.now();
    const interval = setInterval(() => setElapsedMs(performance.now() - sessionStartRef.current), 250);
    return () => clearInterval(interval);
  }, [session]);

  // Grabs one frame from the live <video> as a base64 JPEG.
  const captureFrame = useCallback(() => {
    const video = videoRef.current;
    const canvas = canvasRef.current;
    if (!video || !canvas || video.readyState < 2) return null;
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    const ctx = canvas.getContext("2d");
    ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
    return canvas.toDataURL("image/jpeg", FRAME_QUALITY);
  }, []);

  // Real per-frame gaze loop: capture -> POST /gaze/frame -> draw the
  // returned point. Replaces the earlier illustrative random-drift cursor.
  useEffect(() => {
    if (!session) return;
    gazeTimerRef.current = setInterval(async () => {
      const frame = captureFrame();
      if (!frame) return;
      try {
        const result = await estimateGazeFrame(token, session.id, frame, performance.now() / 1000);
        if (result.gaze.valid) {
          setGazePoint({ x: result.gaze.x, y: result.gaze.y });
        }
      } catch (err) {
        // Transient per-frame failures shouldn't stop the session -- surface
        // once, keep trying.
        setGazeWarning((prev) => prev ?? (err.message || "Gaze estimation stalled"));
      }
    }, GAZE_CAPTURE_INTERVAL_MS);
    return () => clearInterval(gazeTimerRef.current);
  }, [session, token, captureFrame]);

  async function handlePreviewUrl() {
    if (!urlInput.trim()) return;
    setRendering(true);
    setRenderError(null);
    setRenderedPage(null);
    try {
      const result = await renderUrl(urlInput.trim());
      setRenderedPage(result);
    } catch (err) {
      setRenderError(err.message || "Couldn't render that URL");
    } finally {
      setRendering(false);
    }
  }

  async function handleStart() {
    if (mode === "url" && !renderedPage) return; // must preview successfully first
    if (!calibrationSessionId) {
      setStartError("No calibration on file for this sitting -- calibrate first.");
      return;
    }

    setStarting(true);
    setStartError(null);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ video: true });
      streamRef.current = stream;
      if (videoRef.current) {
        videoRef.current.srcObject = stream;
        await videoRef.current.play();
      }
      setCameraError(null);
    } catch {
      setCameraError("Couldn't access the webcam. Check browser permissions and that no other app is using it.");
      setStarting(false);
      return;
    }

    try {
      const created = await startSession(token, {
        mode: mode === "url" ? "url" : "test_ui",
        uiPage: mode === "fixed" ? selectedPage : undefined,
        targetUrl: mode === "url" ? renderedPage.url : undefined,
      });

      const link = await linkCalibration(token, created.id, calibrationSessionId, true);
      if (!link.gaze_model_trained) {
        setStartError(
          `Calibration wasn't usable enough to train a gaze model (${link.message}). ` +
            "Recalibrate before starting a session."
        );
        streamRef.current?.getTracks().forEach((t) => t.stop());
        setStarting(false);
        return;
      }

      setSession(created);
      setElapsedMs(0);
      setNotes([]);
      setGazePoint(null);
      setGazeWarning(null);
    } catch (err) {
      setStartError(err.message || "Couldn't start the session.");
      streamRef.current?.getTracks().forEach((t) => t.stop());
    } finally {
      setStarting(false);
    }
  }

  async function handleEnd() {
    streamRef.current?.getTracks().forEach((t) => t.stop());
    clearInterval(gazeTimerRef.current);
    const finishedSession = session;
    setSession(null);
    if (!finishedSession) return;

    try {
      await finalizeSession(token, finishedSession.id);
    } catch (err) {
      // No gaze data at all (422) is the one case finalize can't recover
      // from -- surfacing it here beats a silently stuck "processing" session.
      console.error("finalize failed:", err.message);
    }
    onSessionEnd?.(finishedSession.id);
  }

  function handleSaveNote() {
    if (!noteDraft.trim()) return;
    setNotes((prev) => [{ text: noteDraft.trim(), at: formatClock(elapsedMs) }, ...prev]);
    setNoteDraft("");
  }

  const initials = (user?.email || "?").slice(0, 1).toUpperCase();
  const pageLabel =
    mode === "url"
      ? (renderedPage?.url || urlInput).replace(/^https?:\/\//, "")
      : (selectedPage || "").replace(/_/g, " ");

  if (!session) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center px-4 relative py-12">
        {onNavigate && (
          <button
            onClick={() => onNavigate("dashboard")}
            className="absolute top-6 left-6 text-[11px] font-label-caps text-secondary hover:text-on-surface transition-colors flex items-center gap-1"
          >
            <span className="material-symbols-outlined text-[16px]">arrow_back</span>
            Dashboard
          </button>
        )}
        <div className="w-full max-w-lg bg-white border border-outline p-8 entrance-animation">
          <span className="font-label-caps text-label-caps text-primary-container tracking-widest block mb-2">
            NEW SESSION
          </span>
          <h1 className="font-headline-md text-headline-md mb-6">Choose what to evaluate</h1>

          <div className="flex bg-surface-container p-1 rounded-lg border border-outline-variant mb-6 w-fit">
            <button
              onClick={() => setMode("fixed")}
              className={`px-4 py-1.5 rounded-md font-label-caps text-label-caps transition-all ${
                mode === "fixed" ? "bg-primary text-white" : "text-secondary"
              }`}
            >
              Test page
            </button>
            <button
              onClick={() => setMode("url")}
              className={`px-4 py-1.5 rounded-md font-label-caps text-label-caps transition-all ${
                mode === "url" ? "bg-primary text-white" : "text-secondary"
              }`}
            >
              Any URL
            </button>
          </div>

          {mode === "fixed" && (
            <div className="space-y-2 mb-6">
              {testPages.length === 0 && <p className="text-xs text-secondary">Loading available pages…</p>}
              {testPages.map((pageId) => (
                <label
                  key={pageId}
                  className={`flex items-center gap-3 px-4 py-3 border cursor-pointer text-sm transition-colors ${
                    selectedPage === pageId
                      ? "border-primary-container bg-primary-container/5"
                      : "border-outline-variant hover:border-outline"
                  }`}
                >
                  <input
                    type="radio"
                    name="test-page"
                    checked={selectedPage === pageId}
                    onChange={() => setSelectedPage(pageId)}
                    className="accent-primary-container"
                  />
                  {pageId.replace(/_/g, " ")}
                </label>
              ))}
            </div>
          )}

          {mode === "url" && (
            <div className="mb-6">
              <p className="text-xs text-secondary mb-3 leading-relaxed">
                Renders a live screenshot and auto-detects interactive elements. This is a static snapshot, not an
                interactive page — clicks won't navigate, and dynamic/personalized content reflects whatever was
                served at render time.
              </p>
              <div className="flex gap-2 mb-3">
                <input
                  type="url"
                  value={urlInput}
                  onChange={(e) => setUrlInput(e.target.value)}
                  placeholder="https://example.com"
                  className="flex-1 h-11 px-3 border border-outline-variant text-sm focus:ring-0 focus:border-primary-container focus:border-2 outline-none"
                />
                <button
                  onClick={handlePreviewUrl}
                  disabled={rendering || !urlInput.trim()}
                  className="px-4 bg-primary text-white font-label-caps text-label-caps hover:opacity-90 transition-opacity disabled:opacity-50"
                >
                  {rendering ? "Rendering…" : "Preview"}
                </button>
              </div>

              {renderError && (
                <div className="text-sm text-[#B23A2E] bg-[#F6E6E4] border border-[#B23A2E] px-3 py-2 mb-3">
                  {renderError}
                </div>
              )}

              {rendering && (
                <div className="py-10 text-center border border-outline-variant">
                  <div className="w-5 h-5 border-2 border-outline-variant border-t-primary-container rounded-full animate-spin mx-auto mb-2" />
                  <p className="text-xs text-secondary">Loading the page and detecting elements…</p>
                </div>
              )}

              {renderedPage && !rendering && (
                <div className="entrance-animation">
                  <p className="text-[11px] font-label-caps text-secondary mb-2">
                    {renderedPage.elements.length} elements detected — preview only, overlays won't be shown to the
                    participant
                  </p>
                  {!renderedPage.screenshot_base64 && (
                    <p className="text-[11px] text-secondary mb-2 italic">
                      No screenshot image available from backend/render (it only returns element geometry, not image
                      bytes) — boxes are shown on a placeholder canvas.
                    </p>
                  )}
                  <div
                    className="relative border border-outline-variant bg-surface-container-low"
                    style={{ aspectRatio: `${renderedPage.viewport?.[0] || 16} / ${renderedPage.viewport?.[1] || 9}` }}
                  >
                    {renderedPage.screenshot_base64 && (
                      <img
                        src={`data:image/png;base64,${renderedPage.screenshot_base64}`}
                        alt="Rendered page preview"
                        className="w-full block"
                      />
                    )}
                    {renderedPage.elements.map((el) => (
                      <div
                        key={el.element_id}
                        title={`${el.element_type} · ${el.element_importance} · ${el.label}`}
                        className="absolute border-2"
                        style={{
                          left: `${el.bbox_normalized.x * 100}%`,
                          top: `${el.bbox_normalized.y * 100}%`,
                          width: `${el.bbox_normalized.w * 100}%`,
                          height: `${el.bbox_normalized.h * 100}%`,
                          borderColor: TYPE_COLORS[el.element_type] || "#1F6F78",
                          backgroundColor: `${TYPE_COLORS[el.element_type] || "#1F6F78"}1A`,
                        }}
                      />
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}

          {cameraError && (
            <div className="text-sm text-[#B23A2E] bg-[#F6E6E4] border border-[#B23A2E] px-3 py-2 mb-4">
              {cameraError}
            </div>
          )}
          {startError && (
            <div className="text-sm text-[#B23A2E] bg-[#F6E6E4] border border-[#B23A2E] px-3 py-2 mb-4">
              {startError}
            </div>
          )}

          <button
            onClick={handleStart}
            disabled={starting || (mode === "url" && !renderedPage) || (mode === "fixed" && !selectedPage)}
            className="w-full bg-primary-container text-white px-5 py-3 font-label-caps text-label-caps tracking-widest hover:opacity-90 transition-opacity disabled:opacity-50"
          >
            {starting ? "Starting…" : "Grant camera access and start"}
          </button>
        </div>
        <video ref={videoRef} muted playsInline style={{ position: "fixed", width: 1, height: 1, opacity: 0, pointerEvents: "none" }} />
        <canvas ref={canvasRef} style={{ display: "none" }} />
      </div>
    );
  }

  return (
    <div className="font-body-md text-on-surface h-screen flex flex-col overflow-hidden -mx-6 -my-8">
      {/* TopNavBar */}
      <header className="bg-surface border-b border-outline-variant flex justify-between items-center w-full px-margin-desktop py-4 z-50">
        <div className="flex items-center gap-8">
          <button onClick={handleEnd} className="font-display-lg text-display-lg text-primary hover:opacity-80 transition-opacity">
            GazeLens
          </button>
          <nav className="hidden md:flex gap-6 items-center">
            <span className="text-primary font-bold border-b-2 border-primary py-1">Live Session</span>
          </nav>
        </div>
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-2">
            <span className="material-symbols-outlined text-on-surface-variant">settings</span>
            <span className="material-symbols-outlined text-on-surface-variant">help</span>
          </div>
          <div className="w-8 h-8 rounded-full bg-secondary-container flex items-center justify-center overflow-hidden border border-outline-variant">
            <span className="text-xs font-bold text-primary">{initials}</span>
          </div>
        </div>
      </header>

      {/* Toolbar */}
      <div className="px-margin-desktop py-3 bg-surface-container-low border-b border-outline-variant flex items-center justify-between z-40">
        <div className="flex items-center gap-6">
          <div className="flex flex-col">
            <span className="font-label-caps text-label-caps text-secondary uppercase">Active Session</span>
            <span className="font-data-mono text-data-mono font-medium">{session.id}</span>
          </div>
          {mode === "fixed" ? (
            <div className="flex bg-surface-container p-1 rounded-lg border border-outline-variant flex-wrap">
              {testPages.map((pageId) => (
                <button
                  key={pageId}
                  disabled
                  className={`px-4 py-1.5 rounded-md font-label-caps text-label-caps transition-all ${
                    pageId === selectedPage ? "bg-primary text-white" : "text-secondary"
                  }`}
                >
                  {pageId.replace(/_/g, " ")}
                </button>
              ))}
            </div>
          ) : (
            <div className="px-4 py-1.5 rounded-md bg-primary text-white font-label-caps text-label-caps truncate max-w-xs">
              {pageLabel}
            </div>
          )}
        </div>
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2 px-3 py-1.5 bg-error-container text-on-error-container rounded border border-error/20">
            <div className="w-2 h-2 rounded-full bg-error animate-pulse" />
            <span className="font-label-caps text-label-caps font-bold">REC {formatClock(elapsedMs)}</span>
          </div>
          <button
            onClick={handleEnd}
            className="px-6 py-2 bg-[#B23A2E] text-white font-label-caps text-label-caps uppercase tracking-widest rounded hover:opacity-90 transition-all border-b-2 border-black/10"
          >
            End Session
          </button>
        </div>
      </div>

      {/* Main split layout */}
      <main className="flex-1 flex overflow-hidden">
        {/* Left: evaluated page + gaze overlay + floating webcam */}
        <section className="w-[70%] h-full relative bg-[#EFF0ED] p-gutter overflow-hidden flex flex-col">
          <div className="flex-1 bg-white relative rounded overflow-hidden">
            {mode === "url" && renderedPage && renderedPage.screenshot_base64 ? (
              // Real rendered screenshot -- deliberately NO element overlays here.
              // The participant must see exactly what a real visitor would see.
              <img
                src={`data:image/png;base64,${renderedPage.screenshot_base64}`}
                alt="Evaluated page"
                className="w-full h-full object-cover object-top"
              />
            ) : mode === "url" && renderedPage ? (
              // backend/render's /capture endpoint doesn't return image bytes
              // (see render.js) -- no screenshot to show, so at least name the
              // page being evaluated instead of a broken <img>.
              <div className="w-full h-full bg-surface-container-low flex items-center justify-center p-8 text-center">
                <p className="text-sm text-secondary">
                  Live page: <span className="font-data-mono">{renderedPage.url}</span>
                  <br />
                  No screenshot available from the API — the participant is looking at elements detected on this
                  page, without a rendered preview here.
                </p>
              </div>
            ) : (
              // Real page, served from test_uis/<page>/index.html (backend/api
              // mounts it as static files). Its elements sit at the exact
              // normalised bboxes in test_uis/<page>/elements.json -- the same
              // numbers backend/attribution scores gaze against -- so what the
              // participant sees and what the report measures can't drift
              // apart. Direct to :8000 rather than through the Vite proxy:
              // an iframe src doesn't need CORS the way a fetch would.
              <iframe
                key={selectedPage}
                src={`http://localhost:8000/test-uis/${selectedPage}/index.html`}
                title={`Test page: ${selectedPage}`}
                className="w-full h-full border-0"
              />
            )}

            {/* Real gaze cursor -- POST /api/sessions/{id}/gaze/frame, positioned by percentage
                so it doesn't need to re-measure this container's pixel size. */}
            {gazePoint && (
              <div
                className="absolute w-12 h-12 border-4 border-primary rounded-full -translate-x-1/2 -translate-y-1/2 flex items-center justify-center transition-all ease-out z-20 pointer-events-none"
                style={{ left: `${gazePoint.x * 100}%`, top: `${gazePoint.y * 100}%`, transitionDuration: "250ms" }}
              >
                <div className="w-1.5 h-1.5 bg-primary rounded-full" />
              </div>
            )}
            {gazeWarning && (
              <div className="absolute top-3 left-3 z-30 bg-error-container text-on-error-container text-[11px] px-3 py-1.5 rounded-sm max-w-xs">
                {gazeWarning}
              </div>
            )}

            {/* Floating webcam thumbnail -- real feed, and the source for gaze-frame capture */}
            <div className="absolute bottom-6 right-6 w-56 aspect-video bg-inverse-surface rounded-lg border border-outline overflow-hidden shadow-2xl">
              <div className="absolute top-2 left-2 z-10">
                <span className="bg-error text-white text-[9px] font-bold px-2 py-0.5 rounded-sm flex items-center gap-1 uppercase tracking-tighter">
                  <span className="w-1.5 h-1.5 rounded-full bg-white animate-pulse" />
                  LIVE
                </span>
              </div>
              <video ref={videoRef} autoPlay muted playsInline className="w-full h-full object-cover" />
              <canvas ref={canvasRef} style={{ display: "none" }} />
              <div className="absolute inset-0 bg-gradient-to-t from-black/60 to-transparent flex flex-col justify-end p-2 pointer-events-none">
                <span className="text-white font-label-caps text-[9px]">{user?.email}</span>
              </div>
            </div>
          </div>

          <div className="mt-4 flex justify-between items-center">
            <div className="flex gap-4">
              <div className="flex items-center gap-2">
                <span className="w-3 h-3 bg-primary rounded-full" />
                <span className="text-label-caps font-label-caps">Gaze Path</span>
              </div>
              <div className="flex items-center gap-2">
                <span className="w-3 h-3 bg-primary/40 border border-primary rounded-full" />
                <span className="text-label-caps font-label-caps">Fixation Point</span>
              </div>
            </div>
            <span className="text-label-caps font-label-caps text-secondary truncate max-w-xs">{pageLabel}</span>
          </div>
        </section>

        {/* Right: tabbed sidebar */}
        <aside className="w-[30%] h-full bg-surface-container-low border-l border-outline-variant flex flex-col">
          <div className="border-b border-outline-variant flex">
            {["Insights", "Heatmap", "Logs"].map((label) => {
              const id = label.toLowerCase();
              return (
                <button
                  key={id}
                  onClick={() => setTab(id)}
                  className={`flex-1 py-3 text-label-caps font-label-caps uppercase tracking-widest transition-all ${
                    tab === id ? "border-b-2 border-primary bg-white" : "text-secondary hover:bg-surface-container-high"
                  }`}
                >
                  {label}
                </button>
              );
            })}
          </div>

          <div className="flex-1 overflow-y-auto p-6 space-y-6">
            {tab === "insights" && (
              <div className="bg-white p-4 border border-outline-variant rounded-sm">
                <div className="flex justify-between items-center mb-4">
                  <h4 className="font-label-caps text-label-caps text-secondary uppercase tracking-wider">
                    Gaze Metrics
                  </h4>
                </div>
                <div className="grid grid-cols-2 gap-4">
                  <div className="space-y-1">
                    <span className="text-[10px] text-secondary font-label-caps">Avg Fixation Duration</span>
                    <p className="font-data-mono text-xl font-bold text-primary">—</p>
                  </div>
                  <div className="space-y-1">
                    <span className="text-[10px] text-secondary font-label-caps">Saccade Frequency</span>
                    <p className="font-data-mono text-xl font-bold text-primary">—</p>
                  </div>
                </div>
                <p className="text-[11px] text-secondary mt-3">
                  Populates once backend/gaze_estimation is wired in.
                </p>
                {mode === "url" && renderedPage && (
                  <p className="text-[11px] text-secondary mt-2 pt-2 border-t border-outline-variant">
                    {renderedPage.elements.length} elements auto-detected on this page.
                  </p>
                )}
              </div>
            )}
            {tab === "heatmap" && (
              <div className="bg-white p-4 border border-outline-variant rounded-sm text-center py-12">
                <p className="text-sm text-secondary">Heatmap renders once session metrics are computed.</p>
              </div>
            )}
            {tab === "logs" && (
              <div className="bg-white p-4 border border-outline-variant rounded-sm text-center py-12">
                <p className="text-sm text-secondary">No log entries yet.</p>
              </div>
            )}

            {/* Session Notes */}
            <div className="bg-surface-container p-4 border border-outline-variant rounded-sm">
              <h4 className="font-label-caps text-label-caps text-secondary uppercase tracking-wider mb-3">
                Researcher Notes
              </h4>
              <textarea
                value={noteDraft}
                onChange={(e) => setNoteDraft(e.target.value)}
                placeholder="Add time-stamped observation…"
                className="w-full h-32 bg-white border border-outline-variant p-3 text-sm focus:ring-0 focus:border-primary resize-none placeholder:text-outline"
              />
              <div className="mt-2 flex justify-end">
                <button
                  onClick={handleSaveNote}
                  className="bg-primary text-white font-label-caps text-[10px] px-3 py-1.5 uppercase tracking-widest rounded"
                >
                  Save Note
                </button>
              </div>
              {notes.length > 0 && (
                <div className="mt-3 space-y-2">
                  {notes.map((n, i) => (
                    <div key={i} className="text-xs border-t border-outline-variant pt-2">
                      <span className="font-mono text-secondary">{n.at}</span> — {n.text}
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </aside>
      </main>
    </div>
  );
}
