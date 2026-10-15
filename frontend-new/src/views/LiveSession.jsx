import { useState, useRef, useEffect, useCallback } from "react";
import { useAuth } from "../context/AuthContext.jsx";
import { startSession, linkCalibration, estimateGazeFrame, finalizeSession, listTestUis } from "../api/client.js";
import { renderUrl } from "../api/render.js";
import { CAMERA_CONSTRAINTS } from "../api/calibration.js";
import { OneEuroFilter2D } from "../lib/oneEuroFilter.js";
import { motion } from "framer-motion";
import { Reveal, StaggerGroup, StaggerItem } from "../components/Motion.jsx";
import IrisMark from "../components/IrisMark.jsx";

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

const PAGES = {
  ecommerce_product_page: { name: "Shop product page", body: "A product with photos, price and an Add to cart button." },
  form_page: { name: "Sign-up form", body: "A form with several fields and a submit button." },
  dashboard_page: { name: "Dashboard", body: "Charts, numbers and menus, like an admin screen." },
  login_page: { name: "Login page", body: "Email, password and a Sign in button." },
  article_page: { name: "News article", body: "A long read with headings, images and links." },
};

function pageInfo(id) {
  if (!id) return { name: "", body: "" };
  if (PAGES[id]) return PAGES[id];
  const t = id.replace(/_/g, " ");
  return { name: t.charAt(0).toUpperCase() + t.slice(1), body: "A sample page to test with." };
}

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
  const { token } = useAuth();
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
  const areaRef = useRef(null);
  const scrollerRef = useRef(null);
  const [boxSize, setBoxSize] = useState(null);
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

  // A captured page is one tall screenshot shown at the stage's width. The
  // server needs the scroll in the page's own CSS pixels, so the on-screen
  // offset is scaled by (captured width / shown width).
  const pageScrollY = useCallback(() => {
    const el = scrollerRef.current;
    if (!el || !el.clientWidth) return 0;
    const capturedWidth = renderedPage?.viewport?.[0] || el.clientWidth;
    return el.scrollTop * (capturedWidth / el.clientWidth);
  }, [renderedPage]);

  // URL sessions: the stage keeps the captured window's shape (e.g. 1280x720)
  // so one screen of the page on this monitor is one screen of it as captured
  // -- that's what lets pipeline.to_document_space line gaze up with the boxes.
  useEffect(() => {
    if (!session || mode !== "url") return;
    const area = areaRef.current;
    if (!area) return;
    const [vw, vh] = renderedPage?.viewport || [16, 9];
    const fit = () => {
      const { width, height } = area.getBoundingClientRect();
      const w = Math.min(width, height * (vw / vh));
      setBoxSize({ w, h: w * (vh / vw) });
    };
    fit();
    const ro = new ResizeObserver(fit);
    ro.observe(area);
    return () => ro.disconnect();
  }, [session, mode, renderedPage]);

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
          const result = await estimateGazeFrame(token, session.id, frame, started / 1000, stageRect(), pageScrollY());
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
  }, [session, token, captureFrame, stageRect, pageScrollY]);

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

  const pageLabel = mode === "url" ? (renderedPage?.url || urlInput).replace(/^https?:\/\//, "") : pageInfo(selectedPage).name;
  const btn = "rounded-full bg-accent font-semibold text-[#0A0E14] transition-shadow hover:shadow-[0_0_30px_-6px_rgb(var(--color-accent)/0.7)]";
  const errorBox = "rounded-[16px] border border-coral/40 bg-coral/10 px-4 py-3 text-[15px] text-text-primary";

  if (!calibrationSessionId) {
    return (
      <div className="flex min-h-[calc(100vh-90px)] items-center justify-center px-4 py-12">
        <div className="relative w-full max-w-lg overflow-hidden rounded-[28px] border border-white/10 bg-surface/70 p-10 text-center backdrop-blur-xl">
          <div aria-hidden="true" className="pointer-events-none absolute inset-0" style={{ background: "radial-gradient(60% 70% at 50% 0%, rgb(var(--color-accent) / 0.14), transparent 70%)" }} />
          <div className="relative">
            <div className="mx-auto flex w-fit"><IrisMark size={56} wander /></div>
            <h1 className="mt-6 text-[32px] font-bold tracking-tight text-text-primary">
              Set up the <span className="font-serif font-normal italic text-accent">camera</span> first
            </h1>
            <p className="mt-3 text-[16px] leading-relaxed text-text-secondary">
              GazeLens needs about a minute to learn how your eyes move. After that you'll come straight back here to run your test.
            </p>
            <button onClick={() => onNavigate?.("calibration")} className={`mt-8 h-12 px-8 text-[15px] ${btn}`}>
              Start the setup
            </button>
          </div>
        </div>
      </div>
    );
  }

  if (!session) {
    const canStart = !starting && !(mode === "url" && !renderedPage) && !(mode === "fixed" && !selectedPage);
    return (
      <div className="mx-auto max-w-[1100px] px-4 py-10 sm:px-8 sm:py-14">
        <Reveal>
          <h1 className="text-[40px] font-bold leading-[1.05] tracking-[-0.03em] text-text-primary sm:text-[52px]">
            What do you want to <span className="font-serif font-normal italic text-accent">test?</span>
          </h1>
          <p className="mt-3 max-w-xl text-[17px] leading-relaxed text-text-secondary">
            Pick one of our sample pages, or paste a link to your own site. When you press start, use the page the way a visitor would.
          </p>
        </Reveal>

        <div className="mt-8 flex w-fit rounded-full border border-white/10 bg-surface/60 p-1 backdrop-blur">
          {[["fixed", "Sample pages"], ["url", "My own website"]].map(([id, label]) => (
            <button
              key={id}
              onClick={() => setMode(id)}
              className={`relative rounded-full px-5 py-2.5 text-[15px] font-medium transition-colors ${mode === id ? "text-[#0A0E14]" : "text-text-secondary hover:text-text-primary"}`}
            >
              {mode === id && <motion.span layoutId="test-mode-pill" className="absolute inset-0 -z-10 rounded-full bg-accent" transition={{ type: "spring", stiffness: 380, damping: 32 }} />}
              {label}
            </button>
          ))}
        </div>

        {mode === "fixed" && (
          <div className="mt-8">
            {testPages.length === 0 && <p className="text-[15px] text-text-secondary">Loading sample pages…</p>}
            <StaggerGroup className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {testPages.map((pageId) => {
                const info = pageInfo(pageId);
                const picked = selectedPage === pageId;
                return (
                  <StaggerItem key={pageId}>
                    <button
                      onClick={() => setSelectedPage(pageId)}
                      className={`group relative block w-full overflow-hidden rounded-[22px] border bg-surface/60 p-3 text-left backdrop-blur transition-all duration-300 ${
                        picked
                          ? "border-accent/70 shadow-[0_20px_60px_-25px_rgb(var(--color-accent)/0.6)]"
                          : "border-white/10 hover:-translate-y-0.5 hover:border-white/25"
                      }`}
                    >
                      <div className="relative aspect-[16/10] overflow-hidden rounded-[14px] border border-white/10 bg-white">
                        <iframe
                          src={`/test-uis/${pageId}/index.html`}
                          title={`${info.name} preview`}
                          tabIndex={-1}
                          loading="lazy"
                          className="pointer-events-none absolute left-0 top-0 h-[400%] w-[400%] origin-top-left scale-[0.25] border-0"
                        />
                        {picked && (
                          <span className="absolute right-2 top-2 flex h-7 w-7 items-center justify-center rounded-full bg-accent text-[14px] font-bold text-[#0A0E14] shadow-lg">✓</span>
                        )}
                      </div>
                      <div className="px-2 pb-2 pt-4">
                        <div className={`text-[17px] font-semibold transition-colors ${picked ? "text-accent" : "text-text-primary"}`}>{info.name}</div>
                        <div className="mt-1 text-[14px] leading-snug text-text-secondary">{info.body}</div>
                      </div>
                    </button>
                  </StaggerItem>
                );
              })}
            </StaggerGroup>
          </div>
        )}

        {mode === "url" && (
          <div className="mt-8 rounded-[24px] border border-white/10 bg-surface/60 p-6 backdrop-blur sm:p-8">
            <p className="text-[15px] leading-relaxed text-text-secondary">
              We take a picture of your page and find the buttons, links and forms on it. You'll look at that picture during the test, so it won't scroll or click.
            </p>
            <div className="mt-5 flex flex-col gap-3 sm:flex-row">
              <input
                type="url"
                value={urlInput}
                onChange={(e) => setUrlInput(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && handlePreviewUrl()}
                placeholder="https://your-website.com"
                className="h-12 flex-1 rounded-full border border-white/10 bg-bg/60 px-5 text-[15px] text-text-primary outline-none transition-all placeholder:text-text-secondary/60 focus:border-accent/70 focus:ring-4 focus:ring-accent/15"
              />
              <button onClick={handlePreviewUrl} disabled={rendering || !urlInput.trim()} className={`h-12 px-6 text-[15px] disabled:opacity-50 ${btn}`}>
                {rendering ? "Loading…" : "Load page"}
              </button>
            </div>

            {renderError && <div className={`mt-4 ${errorBox}`}>{renderError}</div>}

            {rendering && (
              <div className="mt-5 flex flex-col items-center rounded-[18px] border border-white/10 bg-bg/40 py-12 text-center">
                <IrisMark size={40} wander />
                <p className="mt-3 text-[15px] text-text-secondary">Opening the page and finding what's clickable…</p>
              </div>
            )}

            {renderedPage && !rendering && (
              <div className="mt-5">
                <p className="mb-3 text-[14px] text-text-secondary">
                  Found <span className="font-semibold text-accent">{renderedPage.elements.length}</span> things people can click or read. Each one is outlined below.
                </p>
                <div className="max-h-[520px] overflow-y-auto rounded-[18px] border border-white/10 bg-bg">
                <div className="relative">
                  {renderedPage.screenshot_base64 && (
                    <img src={`data:image/png;base64,${renderedPage.screenshot_base64}`} alt="Your page" className="block w-full" />
                  )}
                  {renderedPage.elements.map((el) => (
                    <div
                      key={el.element_id}
                      title={el.label}
                      className="absolute rounded-[4px] border-2"
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
                {renderedPage.warnings?.length > 0 && (
                  <p className="mt-3 text-[13px] text-text-secondary">
                    Note: {renderedPage.kept < renderedPage.detected
                      ? `this page is busy, so we kept the ${renderedPage.kept} biggest things to track.`
                      : "parts of this page loaded slowly and may be missing."}
                  </p>
                )}
              </div>
            )}
          </div>
        )}

        {cameraError && <div className={`mt-6 ${errorBox}`}>{cameraError}</div>}
        {startError && (
          <div className={`mt-6 ${errorBox}`}>
            <p>{startError}</p>
            {startErrorDetail && (
              <details className="mt-2">
                <summary className="cursor-pointer text-[13px] text-text-secondary hover:text-text-primary">More detail</summary>
                <p className="mt-1 break-words font-mono text-[12px] text-text-secondary">{startErrorDetail}</p>
              </details>
            )}
            {needsRecalibration && onNavigate && (
              <button onClick={() => onNavigate("calibration")} className={`mt-4 h-10 px-5 text-[14px] ${btn}`}>
                Redo the camera setup
              </button>
            )}
          </div>
        )}

        <div className="sticky bottom-4 z-20 mt-10 flex flex-col items-center justify-between gap-4 rounded-full border border-white/10 bg-surface/80 py-3 pl-6 pr-3 shadow-[0_20px_60px_-20px_rgba(0,0,0,0.9)] backdrop-blur-xl sm:flex-row">
          <div className="flex items-center gap-3 text-[15px]">
            <span className="h-2 w-2 shrink-0 rounded-full bg-accent shadow-[0_0_10px_rgb(var(--color-accent))]" />
            <span className="text-text-secondary">Testing:</span>
            <span className="truncate font-semibold text-text-primary">{pageLabel || "pick a page"}</span>
          </div>
          <button onClick={handleStart} disabled={!canStart} className={`h-12 w-full px-7 text-[15px] disabled:opacity-50 sm:w-auto ${btn}`}>
            {starting ? "Starting…" : "Turn on camera and start"}
          </button>
        </div>

        <video ref={videoRef} muted playsInline style={{ position: "fixed", width: 1, height: 1, opacity: 0, pointerEvents: "none" }} />
        <canvas ref={canvasRef} style={{ display: "none" }} />
      </div>
    );
  }

  return (
    <div className="flex h-[calc(100vh-90px)] flex-col gap-3 overflow-hidden px-3 pb-3 pt-3 sm:px-5">
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-full border border-white/10 bg-surface/70 py-2 pl-5 pr-2 backdrop-blur-xl">
        <div className="flex min-w-0 items-center gap-3">
          <span className="flex items-center gap-2 rounded-full bg-coral/15 px-3 py-1.5 text-[14px] font-semibold text-coral">
            <span className="h-2 w-2 animate-pulse rounded-full bg-coral" />
            Recording
          </span>
          <span className="font-mono text-[15px] tabular-nums text-text-primary">{formatClock(elapsedMs)}</span>
          <span className="hidden truncate text-[15px] text-text-secondary sm:inline">· {pageLabel}</span>
        </div>
        <button onClick={handleEnd} className={`h-10 px-6 text-[14px] ${btn}`}>
          Finish and see report
        </button>
      </div>

      <div className="flex flex-1 gap-3 overflow-hidden">
        <section ref={areaRef} className="relative flex flex-1 items-center justify-center overflow-hidden">
          <div
            ref={stageRef}
            className={`relative overflow-hidden rounded-[20px] border border-white/10 bg-surface ${mode === "url" ? "" : "h-full w-full"}`}
            style={mode === "url" && boxSize ? { width: boxSize.w, height: boxSize.h } : undefined}
          >
            {mode === "url" && renderedPage?.screenshot_base64 ? (
              <div ref={scrollerRef} className="h-full w-full overflow-y-auto overflow-x-hidden" style={{ scrollbarWidth: "none" }}>
                <img src={`data:image/png;base64,${renderedPage.screenshot_base64}`} alt="Page being tested" className="block h-auto w-full" draggable={false} />
              </div>
            ) : mode === "url" && renderedPage ? (
              <div className="flex h-full w-full items-center justify-center p-8 text-center">
                <p className="text-[15px] text-text-secondary">We couldn't get a picture of {renderedPage.url}.</p>
              </div>
            ) : (
              <iframe key={selectedPage} src={`/test-uis/${selectedPage}/index.html`} title={`Test page: ${pageLabel}`} className="h-full w-full border-0" />
            )}
            {mode === "url" && renderedPage?.screenshot_base64 && (
              <div className="pointer-events-none absolute bottom-3 left-1/2 z-10 -translate-x-1/2 rounded-full bg-bg/75 px-3 py-1 text-[12px] text-text-secondary backdrop-blur">
                Scroll to see the rest of the page
              </div>
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
              <div className="absolute left-3 top-3 z-30 max-w-xs rounded-[14px] border border-amber/40 bg-surface/90 px-4 py-2 text-[14px] text-text-primary backdrop-blur">
                {gazeWarning}
              </div>
            )}
          </div>
        </section>

        <aside className="flex w-[240px] shrink-0 flex-col gap-3 overflow-y-auto lg:w-[300px]">
          <div className="overflow-hidden rounded-[20px] border border-white/10 bg-surface/70 backdrop-blur">
            <div className="relative aspect-video">
              <video ref={videoRef} autoPlay muted playsInline className="h-full w-full -scale-x-100 object-cover" />
              <span className="absolute left-3 top-3 flex items-center gap-1.5 rounded-full bg-bg/70 px-2.5 py-1 text-[12px] font-medium text-text-primary backdrop-blur">
                <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-accent" /> Your camera
              </span>
            </div>
            <div className="flex items-center justify-between px-4 py-3 text-[14px]">
              <span className="text-text-secondary">Eye tracking</span>
              <span className={`font-semibold ${!gazePoint ? "text-text-secondary" : gazePoint.onPage ? "text-accent" : "text-amber"}`}>
                {!gazePoint ? "Starting…" : gazePoint.onPage ? "On the page" : "Looking away"}
              </span>
            </div>
          </div>

          <div className="rounded-[20px] border border-white/10 bg-surface/70 p-5 backdrop-blur">
            <div className="text-[16px] font-semibold text-text-primary">Tips for a good test</div>
            <ul className="mt-3 space-y-2.5 text-[14px] leading-snug text-text-secondary">
              {["Sit where you sat during setup", "Use the page like a real visitor", "About a minute is plenty", "Press Finish when you're done"].map((t) => (
                <li key={t} className="flex gap-2.5"><span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-accent" />{t}</li>
              ))}
            </ul>
          </div>

          <div className="rounded-[20px] border border-white/10 bg-surface/70 p-5 backdrop-blur">
            <div className="text-[16px] font-semibold text-text-primary">Notes</div>
            <textarea
              value={noteDraft}
              onChange={(e) => setNoteDraft(e.target.value)}
              placeholder="Jot down anything you notice…"
              className="mt-3 h-24 w-full resize-none rounded-[14px] border border-white/10 bg-bg/60 p-3 text-[14px] text-text-primary outline-none transition-all placeholder:text-text-secondary/60 focus:border-accent/70 focus:ring-4 focus:ring-accent/15"
            />
            <div className="mt-2 flex justify-end">
              <button onClick={handleSaveNote} className="rounded-full border border-white/10 px-4 py-1.5 text-[13px] font-medium text-text-primary hover:border-accent/50 hover:text-accent">
                Save note
              </button>
            </div>
            {notes.length > 0 && (
              <div className="mt-3 space-y-2">
                {notes.map((n, i) => (
                  <div key={i} className="border-t border-white/10 pt-2 text-[13px] text-text-secondary">
                    <span className="font-mono text-text-primary">{n.at}</span> · {n.text}
                  </div>
                ))}
              </div>
            )}
          </div>
        </aside>
      </div>
      <canvas ref={canvasRef} style={{ display: "none" }} />
    </div>
  );
}
