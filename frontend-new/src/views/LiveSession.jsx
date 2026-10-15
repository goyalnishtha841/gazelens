import { useState, useRef, useEffect, useCallback } from "react";
import { useAuth } from "../context/AuthContext.jsx";
import { startSession, linkCalibration, estimateGazeFrame, finalizeSession, listTestUis } from "../api/client.js";
import { renderUrl } from "../api/render.js";
import { CAMERA_CONSTRAINTS } from "../api/calibration.js";
import { OneEuroFilter2D } from "../lib/oneEuroFilter.js";
import { Label } from "../components/Primitives.jsx";

// Target spacing between frames. MUST stay under backend/attribution/
// fixations.py's MAX_GAP (150ms) -- see frontend/src/views/LiveSession.jsx's
// original note on why. Only one frame is ever in flight: the next is
// captured when the previous answer arrives (or after this interval,
// whichever is later), so a slow server drops frames instead of building
// a queue of stale ones that make the cursor lag further and further.
const GAZE_CAPTURE_INTERVAL_MS = 100;
const FRAME_QUALITY = 0.8;

const NOTE_WARNINGS = {
  head_moved: "You've moved since calibrating. Return to where you sat, or recalibrate.",
};

const TYPE_COLORS = { CTA: "rgb(var(--color-accent))", nav: "rgb(var(--color-text-secondary))", form_field: "rgb(var(--color-accent))" };

function formatClock(ms) {
  const totalSeconds = Math.floor(ms / 1000);
  const h = String(Math.floor(totalSeconds / 3600)).padStart(2, "0");
  const m = String(Math.floor((totalSeconds % 3600) / 60)).padStart(2, "0");
  const s = String(totalSeconds % 60).padStart(2, "0");
  return `${h}:${m}:${s}`;
}

/** Real webcam-driven recording session -- ported from
 * frontend/src/views/LiveSession.jsx, restyled. Same API calls, same gaze
 * capture loop, same gating logic. */
export default function LiveSession({ calibrationSessionId, onSessionEnd, onNavigate }) {
  const { user, token } = useAuth();
  const [mode, setMode] = useState("fixed");
  const [testPages, setTestPages] = useState([]);
  const [selectedPage, setSelectedPage] = useState(null);

  const [urlInput, setUrlInput] = useState("");
  const [rendering, setRendering] = useState(false);
  const [renderError, setRenderError] = useState(null);
  const [renderedPage, setRenderedPage] = useState(null);

  const [session, setSession] = useState(null);
  const [cameraError, setCameraError] = useState(null);
  const [startError, setStartError] = useState(null);
  const [startErrorDetail, setStartErrorDetail] = useState(null);
  const [needsRecalibration, setNeedsRecalibration] = useState(false);
  const [starting, setStarting] = useState(false);
  const [elapsedMs, setElapsedMs] = useState(0);
  const [tab, setTab] = useState("insights");
  const [noteDraft, setNoteDraft] = useState("");
  const [notes, setNotes] = useState([]);
  const [gazePoint, setGazePoint] = useState(null);
  const [gazeWarning, setGazeWarning] = useState(null);

  const videoRef = useRef(null);
  const canvasRef = useRef(null);
  const streamRef = useRef(null);
  const sessionStartRef = useRef(null);
  const gazeTimerRef = useRef(null);
  const stageRef = useRef(null);
  const smootherRef = useRef(new OneEuroFilter2D());

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
    clearTimeout(gazeTimerRef.current);
  }, []);

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

  // Where the evaluated page is drawn, as a fraction of the viewport. The
  // gaze model maps to the whole viewport (calibration dots were measured
  // there); the server remaps each point into this stage, so the cursor and
  // element attribution both work in the page's own coordinates.
  const stageRect = useCallback(() => {
    const el = stageRef.current;
    if (!el) return null;
    const r = el.getBoundingClientRect();
    return {
      x: r.left / window.innerWidth, y: r.top / window.innerHeight,
      w: r.width / window.innerWidth, h: r.height / window.innerHeight,
    };
  }, []);

  useEffect(() => {
    if (!session) return;
    let stopped = false;
    smootherRef.current.reset();

    async function tick() {
      if (stopped) return;
      const started = performance.now();
      const frame = captureFrame();
      if (frame) {
        try {
          const result = await estimateGazeFrame(token, session.id, frame, started / 1000, stageRect());
          if (stopped) return;
          const g = result.gaze;
          if (g.valid) {
            const p = smootherRef.current.filter(g.x, g.y, started / 1000);
            setGazePoint({ x: p.x, y: p.y, onPage: g.in_bounds });
          }
          setGazeWarning(NOTE_WARNINGS[g.note] ?? null);
        } catch (err) {
          if (stopped) return;
          setGazeWarning((prev) => prev ?? (err.message || "Gaze estimation stalled"));
        }
      }
      const wait = Math.max(0, GAZE_CAPTURE_INTERVAL_MS - (performance.now() - started));
      gazeTimerRef.current = setTimeout(tick, wait);
    }

    tick();
    return () => {
      stopped = true;
      clearTimeout(gazeTimerRef.current);
    };
  }, [session, token, captureFrame, stageRect]);

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
    if (mode === "url" && !renderedPage) return;
    if (!calibrationSessionId) {
      setStartError("No calibration on file for this sitting. Calibrate first.");
      return;
    }

    setStarting(true);
    setStartError(null);
    setStartErrorDetail(null);
    setNeedsRecalibration(false);
    try {
      const stream = await navigator.mediaDevices.getUserMedia(CAMERA_CONSTRAINTS);
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
          link.screen_mismatch
            ? "Your screen has changed since you calibrated. The gaze mapping is tied to that exact screen, so please recalibrate here."
            : "Calibration wasn't accurate enough to train a gaze model. Try even lighting on your face, sit square to the camera, and remove glasses glare if you can."
        );
        setStartErrorDetail(link.message);
        setNeedsRecalibration(true);
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
    clearTimeout(gazeTimerRef.current);
    const finishedSession = session;
    setSession(null);
    if (!finishedSession) return;

    try {
      await finalizeSession(token, finishedSession.id);
    } catch (err) {
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
  const pageLabel = mode === "url" ? (renderedPage?.url || urlInput).replace(/^https?:\/\//, "") : (selectedPage || "").replace(/_/g, " ");

  if (!calibrationSessionId) {
    return (
      <div className="flex min-h-[calc(100vh-73px)] items-center justify-center px-4">
        <div className="w-full max-w-md text-center">
          <Label>Live session</Label>
          <h1 className="mt-4 font-sans text-[24px] font-semibold text-text-primary">Calibrate first</h1>
          <p className="mt-3 text-[14px] leading-relaxed text-text-secondary">
            A live session needs a gaze model trained from your calibration. Run it once, and you'll come
            straight back here to record.
          </p>
          <button
            onClick={() => onNavigate?.("calibration")}
            className="mt-8 h-11 rounded-card bg-text-primary px-8 font-label-caps text-[13px] font-medium uppercase tracking-label text-bg transition-opacity hover:opacity-85"
          >
            Go to calibration
          </button>
        </div>
      </div>
    );
  }

  if (!session) {
    return (
      <div className="flex min-h-[calc(100vh-73px)] items-center justify-center px-4 py-12">
        <div className="w-full max-w-lg">
          <Label>New session</Label>
          <h1 className="mt-2 font-sans text-[24px] font-semibold text-text-primary">Choose what to evaluate</h1>
          <p className="mt-2 text-[13px] leading-relaxed text-text-secondary">
            Record against one of the built-in test pages, or point it at any live URL. Either way, your
            webcam starts a real gaze-tracking session the moment you press start.
          </p>

          <div className="mt-6 flex w-fit rounded-card border border-border p-1">
            <button
              onClick={() => setMode("fixed")}
              className={`rounded-md px-4 py-1.5 text-[13px] transition-colors ${mode === "fixed" ? "bg-text-primary text-bg" : "text-text-secondary"}`}
            >
              Test page
            </button>
            <button
              onClick={() => setMode("url")}
              className={`rounded-md px-4 py-1.5 text-[13px] transition-colors ${mode === "url" ? "bg-text-primary text-bg" : "text-text-secondary"}`}
            >
              Any URL
            </button>
          </div>

          {mode === "fixed" && (
            <div className="mt-6 space-y-2">
              {testPages.length === 0 && <p className="text-[12px] text-text-secondary">Loading available pages…</p>}
              {testPages.map((pageId) => (
                <label
                  key={pageId}
                  className={`flex cursor-pointer items-center gap-3 rounded-card border px-4 py-3 text-[13px] transition-colors ${
                    selectedPage === pageId ? "border-accent bg-accent-soft" : "border-border hover:border-text-secondary/40"
                  }`}
                >
                  <input type="radio" name="test-page" checked={selectedPage === pageId} onChange={() => setSelectedPage(pageId)} className="accent-[rgb(var(--color-accent))]" />
                  <span className="text-text-primary">{pageId.replace(/_/g, " ")}</span>
                </label>
              ))}
            </div>
          )}

          {mode === "url" && (
            <div className="mt-6">
              <p className="mb-3 text-[12px] leading-relaxed text-text-secondary">
                Renders a live screenshot and auto-detects interactive elements. Static snapshot, not interactive.
              </p>
              <div className="mb-3 flex gap-2">
                <input
                  type="url"
                  value={urlInput}
                  onChange={(e) => setUrlInput(e.target.value)}
                  placeholder="https://example.com"
                  className="h-11 flex-1 rounded-card border border-border bg-surface px-3 text-[13px] text-text-primary outline-none transition-colors focus:border-accent"
                />
                <button
                  onClick={handlePreviewUrl}
                  disabled={rendering || !urlInput.trim()}
                  className="rounded-card bg-text-primary px-4 font-label-caps text-[12px] font-medium uppercase tracking-label text-bg transition-opacity hover:opacity-85 disabled:opacity-50"
                >
                  {rendering ? "Rendering…" : "Preview"}
                </button>
              </div>

              {renderError && <div className="mb-3 rounded-card border border-accent/40 px-3 py-2 text-[13px] text-text-primary">{renderError}</div>}

              {rendering && (
                <div className="rounded-card border border-border py-10 text-center">
                  <div className="mx-auto mb-2 h-2 w-2 animate-pulse rounded-full bg-accent" />
                  <p className="text-[12px] text-text-secondary">Loading the page and detecting elements…</p>
                </div>
              )}

              {renderedPage && !rendering && (
                <div>
                  <p className="mb-2 font-mono text-[11px] text-text-secondary">
                    {renderedPage.elements.length} elements detected -- preview only.
                  </p>
                  <div
                    className="relative overflow-hidden rounded-card border border-border bg-bg"
                    style={{ aspectRatio: `${renderedPage.viewport?.[0] || 16} / ${renderedPage.viewport?.[1] || 9}` }}
                  >
                    {renderedPage.screenshot_base64 && (
                      <img src={`data:image/png;base64,${renderedPage.screenshot_base64}`} alt="Rendered page preview" className="block w-full" />
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
                          borderColor: TYPE_COLORS[el.element_type] || "rgb(var(--color-accent))",
                        }}
                      />
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}

          {cameraError && <div className="mt-4 rounded-card border border-accent/40 px-3 py-2 text-[13px] text-text-primary">{cameraError}</div>}
          {startError && (
            <div className="mt-4 rounded-card border border-accent/40 px-4 py-3 text-[13px] text-text-primary">
              <p>{startError}</p>
              {startErrorDetail && (
                <details className="mt-2">
                  <summary className="cursor-pointer text-[11px] uppercase tracking-wide text-text-secondary hover:text-text-primary">Technical detail</summary>
                  <p className="mt-1 break-words font-mono text-[11px] text-text-secondary">{startErrorDetail}</p>
                </details>
              )}
              {needsRecalibration && onNavigate && (
                <button onClick={() => onNavigate("calibration")} className="mt-3 text-[11px] font-medium text-accent underline underline-offset-2 hover:opacity-80">
                  Recalibrate now
                </button>
              )}
            </div>
          )}

          <button
            onClick={handleStart}
            disabled={starting || (mode === "url" && !renderedPage) || (mode === "fixed" && !selectedPage)}
            className="mt-6 h-11 w-full rounded-card bg-text-primary font-label-caps text-[13px] font-medium uppercase tracking-label text-bg transition-opacity hover:opacity-85 disabled:opacity-50"
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
    <div className="flex h-[calc(100vh-73px)] flex-col overflow-hidden">
      <div className="flex items-center justify-between border-b border-border bg-surface px-6 py-3">
        <div className="flex items-center gap-6">
          <div>
            <Label className="block">Active session</Label>
            <span className="font-mono text-[12px] font-medium text-text-primary">{session.id}</span>
          </div>
          <span className="rounded-card bg-accent-soft px-3 py-1.5 font-mono text-[12px] text-accent">{pageLabel}</span>
        </div>
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2 rounded-card border border-accent/40 px-3 py-1.5">
            <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-accent" />
            <span className="font-mono text-[12px] font-medium text-text-primary">REC {formatClock(elapsedMs)}</span>
          </div>
          <button
            onClick={handleEnd}
            className="rounded-card bg-text-primary px-5 py-2 font-label-caps text-[12px] font-medium uppercase tracking-label text-bg transition-opacity hover:opacity-85"
          >
            End session
          </button>
        </div>
      </div>

      <div className="flex flex-1 overflow-hidden">
        <section className="relative flex-1 overflow-hidden bg-bg p-4">
          <div ref={stageRef} className="relative h-full overflow-hidden rounded-card border border-border bg-surface">
            {mode === "url" && renderedPage?.screenshot_base64 ? (
              <img src={`data:image/png;base64,${renderedPage.screenshot_base64}`} alt="Evaluated page" className="h-full w-full object-cover object-top" />
            ) : mode === "url" && renderedPage ? (
              <div className="flex h-full w-full items-center justify-center p-8 text-center">
                <p className="text-[13px] text-text-secondary">
                  Live page: <span className="font-mono">{renderedPage.url}</span>
                  <br />
                  No screenshot available from the API.
                </p>
              </div>
            ) : (
              <iframe key={selectedPage} src={`/test-uis/${selectedPage}/index.html`} title={`Test page: ${selectedPage}`} className="h-full w-full border-0" />
            )}

            {gazePoint && (
              <div
                className="pointer-events-none absolute z-20 flex h-10 w-10 -translate-x-1/2 -translate-y-1/2 items-center justify-center rounded-full border-2 border-accent transition-all ease-out"
                style={{
                  left: `${gazePoint.x * 100}%`, top: `${gazePoint.y * 100}%`, transitionDuration: "60ms",
                  opacity: gazePoint.onPage ? 1 : 0.35,
                  boxShadow: "0 0 16px 2px rgb(var(--color-accent) / 0.4)",
                }}
              >
                <div className="h-1.5 w-1.5 rounded-full bg-accent" />
              </div>
            )}
            {gazeWarning && (
              <div className="absolute left-3 top-3 z-30 max-w-xs rounded-card border border-accent/40 bg-surface px-3 py-1.5 text-[11px] text-text-primary">
                {gazeWarning}
              </div>
            )}

            <div className="absolute bottom-4 right-4 aspect-video w-52 overflow-hidden rounded-card border border-border shadow-lg">
              <div className="absolute left-2 top-2 z-10 flex items-center gap-1 rounded-full bg-bg/80 px-2 py-0.5 backdrop-blur-sm">
                <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-accent" />
                <span className="font-mono text-[9px] uppercase tracking-wide text-text-primary">Live</span>
              </div>
              <video ref={videoRef} autoPlay muted playsInline className="h-full w-full object-cover" />
              <canvas ref={canvasRef} style={{ display: "none" }} />
            </div>
          </div>
        </section>

        <aside className="flex w-[320px] shrink-0 flex-col border-l border-border bg-surface">
          <div className="flex border-b border-border">
            {["Insights", "Heatmap", "Logs"].map((label) => {
              const id = label.toLowerCase();
              return (
                <button
                  key={id}
                  onClick={() => setTab(id)}
                  className={`flex-1 py-3 font-mono text-[11px] uppercase tracking-wide transition-colors ${
                    tab === id ? "border-b-2 border-accent text-text-primary" : "text-text-secondary hover:text-text-primary"
                  }`}
                >
                  {label}
                </button>
              );
            })}
          </div>

          <div className="flex-1 space-y-4 overflow-y-auto p-5">
            {tab === "insights" && (
              <div className="rounded-card border border-border p-4">
                <Label>Gaze metrics</Label>
                <div className="mt-4 grid grid-cols-2 gap-4">
                  <div>
                    <span className="block text-[10px] text-text-secondary">Avg fixation</span>
                    <p className="font-mono text-[18px] font-semibold text-text-primary">--</p>
                  </div>
                  <div>
                    <span className="block text-[10px] text-text-secondary">Saccade freq.</span>
                    <p className="font-mono text-[18px] font-semibold text-text-primary">--</p>
                  </div>
                </div>
                {mode === "url" && renderedPage && (
                  <p className="mt-3 border-t border-border pt-3 text-[11px] text-text-secondary">
                    {renderedPage.elements.length} elements auto-detected on this page.
                  </p>
                )}
              </div>
            )}
            {tab === "heatmap" && (
              <div className="rounded-card border border-border py-12 text-center">
                <p className="text-[13px] text-text-secondary">Heatmap renders once session metrics are computed.</p>
              </div>
            )}
            {tab === "logs" && (
              <div className="rounded-card border border-border py-12 text-center">
                <p className="text-[13px] text-text-secondary">No log entries yet.</p>
              </div>
            )}

            <div className="rounded-card border border-border p-4">
              <Label>Researcher notes</Label>
              <textarea
                value={noteDraft}
                onChange={(e) => setNoteDraft(e.target.value)}
                placeholder="Add time-stamped observation…"
                className="mt-3 h-28 w-full resize-none rounded-card border border-border bg-bg p-3 text-[13px] text-text-primary outline-none transition-colors focus:border-accent"
              />
              <div className="mt-2 flex justify-end">
                <button onClick={handleSaveNote} className="rounded-card bg-text-primary px-3 py-1.5 font-mono text-[10px] uppercase tracking-wide text-bg">
                  Save note
                </button>
              </div>
              {notes.length > 0 && (
                <div className="mt-3 space-y-2">
                  {notes.map((n, i) => (
                    <div key={i} className="border-t border-border pt-2 text-[12px] text-text-secondary">
                      <span className="font-mono text-text-primary">{n.at}</span> · {n.text}
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </aside>
      </div>
    </div>
  );
}
