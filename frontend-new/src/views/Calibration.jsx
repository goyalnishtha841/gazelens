import { useState, useEffect, useCallback, useRef } from "react";
import { useAuth } from "../context/AuthContext.jsx";
import { startCalibration, submitCalibrationSamples, completeCalibration } from "../api/calibration.js";
import { Label } from "../components/Primitives.jsx";
import ThemeToggle from "../components/ThemeToggle.jsx";

// Ported from frontend/src/views/Calibration.jsx -- same backend contract,
// same 16-point default and dynamic grid shape, same on-screen-position
// measurement for ground truth. Only the visual language changed: the
// calibration target IS the product's gaze dot, not a generic progress ring.
const PATTERN = 16;
const GRID_SHAPE = { 9: [3, 3], 16: [4, 4] }[PATTERN];
const SECONDS_PER_POINT = 2.5;
const SETTLE_SECONDS = 0.6;
const CAPTURE_INTERVAL_MS = 130;
const FRAME_QUALITY = 0.7;
const RADIUS = 26;
const CIRCUMFERENCE = 2 * Math.PI * RADIUS;

function describeNote(note) {
  if (!note) return null;
  if (note.includes("no_face_detected")) {
    return "Face not detected -- center your face in frame and check lighting.";
  }
  if (note.includes("no_pupil_detected")) {
    return "Face found, but pupils weren't -- try even lighting, and remove glasses glare if you can.";
  }
  if (note.includes("decode_error")) {
    return "Camera frames aren't reaching the server correctly (technical error).";
  }
  return note;
}

export default function Calibration({ onComplete, onExit }) {
  const { user, logout } = useAuth();
  const [status, setStatus] = useState("idle"); // idle | running | done | error
  const [calibrationId, setCalibrationId] = useState(null);
  const [currentIndex, setCurrentIndex] = useState(0);
  const [progress, setProgress] = useState(0);
  const [cameraError, setCameraError] = useState(null);
  const [quality, setQuality] = useState(null);
  const [pointFeedback, setPointFeedback] = useState(null);
  const dotRef = useRef(null);

  const videoRef = useRef(null);
  const canvasRef = useRef(null);
  const streamRef = useRef(null);
  const frameBufferRef = useRef([]);
  const captureTimerRef = useRef(null);

  useEffect(() => () => {
    streamRef.current?.getTracks().forEach((t) => t.stop());
    clearInterval(captureTimerRef.current);
  }, []);

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

  const begin = useCallback(async () => {
    setCameraError(null);
    setPointFeedback(null);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ video: true });
      streamRef.current = stream;
      if (videoRef.current) {
        videoRef.current.srcObject = stream;
        await videoRef.current.play();
      }
    } catch {
      setCameraError("Couldn't access the webcam. Check browser permissions and that no other app is using it.");
      return;
    }

    try {
      const session = await startCalibration({
        participantId: user?.id || "unknown_participant",
        pattern: PATTERN,
        screenWidth: window.innerWidth,
        screenHeight: window.innerHeight,
      });
      setCalibrationId(session.session_id);
      setCurrentIndex(0);
      setProgress(0);
      setStatus("running");
    } catch (err) {
      setCameraError(err.message || "Couldn't start calibration.");
      streamRef.current?.getTracks().forEach((t) => t.stop());
    }
  }, [user]);

  useEffect(() => {
    if (status !== "running") return;
    const startTime = performance.now();
    const frame = requestAnimationFrame(function tick(now) {
      const elapsed = (now - startTime) / 1000;
      const pct = Math.min(elapsed / SECONDS_PER_POINT, 1);
      setProgress(pct);
      if (pct < 1) requestAnimationFrame(tick);
    });
    return () => cancelAnimationFrame(frame);
  }, [status, currentIndex]);

  useEffect(() => {
    if (status !== "running") return;
    frameBufferRef.current = [];
    const settleTimer = setTimeout(() => {
      captureTimerRef.current = setInterval(() => {
        const frame = captureFrame();
        if (frame) frameBufferRef.current.push(frame);
      }, CAPTURE_INTERVAL_MS);
    }, SETTLE_SECONDS * 1000);
    return () => {
      clearTimeout(settleTimer);
      clearInterval(captureTimerRef.current);
    };
  }, [status, currentIndex, captureFrame]);

  useEffect(() => {
    if (status !== "running" || progress < 1) return;
    let cancelled = false;
    clearInterval(captureTimerRef.current);

    (async () => {
      const frames = frameBufferRef.current;
      let targetX, targetY;
      if (dotRef.current) {
        const rect = dotRef.current.getBoundingClientRect();
        targetX = (rect.left + rect.width / 2) / window.innerWidth;
        targetY = (rect.top + rect.height / 2) / window.innerHeight;
      }

      try {
        if (frames.length > 0) {
          const result = await submitCalibrationSamples(calibrationId, currentIndex, frames, targetX, targetY);
          if (!cancelled) {
            setPointFeedback({ accepted: result.accepted, rejected: result.rejected, note: result.note });
          }
        }
      } catch (err) {
        if (!cancelled) {
          setCameraError(err.message || "Couldn't submit calibration samples.");
          setStatus("error");
          return;
        }
      }
      if (cancelled) return;

      if (currentIndex + 1 < PATTERN) {
        setCurrentIndex((i) => i + 1);
        setProgress(0);
      } else {
        streamRef.current?.getTracks().forEach((t) => t.stop());
        try {
          const result = await completeCalibration(calibrationId);
          if (!cancelled) {
            setQuality(result.quality);
            setStatus("done");
          }
        } catch (err) {
          if (!cancelled) {
            setCameraError(err.message || "Couldn't finish calibration.");
            setStatus("error");
          }
        }
      }
    })();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [progress]);

  const captureRig = (
    <>
      <video ref={videoRef} muted playsInline style={{ position: "fixed", width: 1, height: 1, opacity: 0, pointerEvents: "none" }} />
      <canvas ref={canvasRef} style={{ display: "none" }} />
    </>
  );

  const exitLink = onExit && (
    <button
      onClick={onExit}
      className="absolute left-6 top-6 flex items-center gap-1.5 text-[12px] text-text-secondary transition-colors hover:text-text-primary"
    >
      ← Dashboard
    </button>
  );

  // Theme toggle has to be reachable on every screen, including this one --
  // it's the only thing rendered during forced calibration (no Nav anywhere
  // in reach), so a standalone corner control is the only way to get it
  // there. Present in all four states, including "running": flipping the
  // theme mid-capture is harmless, unlike sign-out below.
  const themeCorner = (
    <div className="absolute right-6 top-6">
      <ThemeToggle />
    </div>
  );

  // Signing out has to be reachable even when calibration is forced (first
  // login, or any reload -- calibrationSessionId isn't persisted, so this
  // screen can be the ONLY thing rendered, with no Nav anywhere in reach).
  // Left off the "running" state on purpose -- mid-capture isn't where you
  // want a stray click ending the session.
  const signOutLink = (
    <div className="absolute right-6 top-6 flex items-center gap-4">
      <ThemeToggle />
      <button
        onClick={logout}
        className="text-[12px] text-text-secondary transition-colors hover:text-text-primary"
      >
        Sign out
      </button>
    </div>
  );
  if (status === "idle" || status === "error") {
    return (
      <div className="relative flex min-h-[calc(100vh-73px)] items-center justify-center">
        {captureRig}
        {exitLink}
        {signOutLink}
        <div className="max-w-md text-center">
          <Label>Fixation calibration</Label>
          <h1 className="mt-4 font-sans text-[28px] font-semibold text-text-primary">Calibrate your gaze</h1>
          <p className="mt-3 text-[14px] leading-relaxed text-text-secondary">
            16 points will appear one at a time. Look directly at each one until it fills in, then hold
            your gaze until the next point appears.
          </p>
          <p className="mt-3 text-[13px] leading-relaxed text-text-secondary">
            Takes about a minute. It can feel repetitive, but every gaze measurement in your session is
            checked against this — worth doing carefully.
          </p>
          {cameraError && (
            <div className="mt-6 rounded-card border border-accent/40 px-4 py-3 text-left text-[13px] text-text-primary">
              {cameraError}
            </div>
          )}
          <button
            onClick={begin}
            className="mt-8 h-11 rounded-card bg-text-primary px-8 font-label-caps text-[13px] font-medium uppercase tracking-label text-bg transition-opacity hover:opacity-85"
          >
            {status === "error" ? "Try again" : "Start calibration"}
          </button>
        </div>
      </div>
    );
  }

  if (status === "done") {
    const usable = quality?.usable ?? true;
    return (
      <div className="relative flex min-h-[calc(100vh-73px)] items-center justify-center">
        {captureRig}
        {exitLink}
        {signOutLink}
        <div className="max-w-md text-center">
          <Label>Fixation calibration</Label>
          <h1 className="mt-4 font-sans text-[28px] font-semibold text-text-primary">
            {usable ? "Calibration complete" : "Calibration complete, quality low"}
          </h1>
          <p className="mt-2 font-mono text-[12px] text-text-secondary">{calibrationId}</p>
          {quality && (
            <p className="mt-3 text-[13px] text-text-secondary">
              {Math.round(quality.detection_rate * 100)}% detection rate ·{" "}
              {Math.round(quality.point_coverage * 100)}% point coverage
            </p>
          )}
          {!usable && (
            <div className="mt-6 rounded-card border border-accent/40 px-4 py-3 text-left text-[13px] text-text-primary">
              {(quality?.reasons || []).join("; ") || "Calibration quality is below the usable threshold."}{" "}
              You can continue, but gaze accuracy will likely be poor.
            </div>
          )}
          <button
            onClick={() => onComplete?.(calibrationId)}
            className="mt-8 h-11 rounded-card bg-text-primary px-8 font-label-caps text-[13px] font-medium uppercase tracking-label text-bg transition-opacity hover:opacity-85"
          >
            Continue to dashboard
          </button>
        </div>
      </div>
    );
  }

  // running
  const dashOffset = CIRCUMFERENCE * (1 - progress);
  return (
    <div className="relative select-none overflow-hidden" style={{ cursor: "none" }}>
      {captureRig}
      {exitLink}
      {themeCorner}
      <div className="fixed left-1/2 top-10 z-10 -translate-x-1/2 text-center">
        <Label>Point {currentIndex + 1} of {PATTERN}</Label>
        {pointFeedback && (
          <p className={`mx-auto mt-2 max-w-sm text-[12px] leading-relaxed ${pointFeedback.accepted > 0 ? "text-text-secondary" : "text-accent"}`}>
            {pointFeedback.accepted > 0
              ? `Last point: ${pointFeedback.accepted}/${pointFeedback.accepted + pointFeedback.rejected} frames captured.`
              : describeNote(pointFeedback.note) || `Last point: 0/${pointFeedback.rejected} frames captured.`}
          </p>
        )}
      </div>

      <main
        className="relative z-0 grid"
        style={{
          height: "100vh", width: "100vw", padding: "12vh 10vw", boxSizing: "border-box",
          gridTemplateColumns: `repeat(${GRID_SHAPE[0]}, 1fr)`,
          gridTemplateRows: `repeat(${GRID_SHAPE[1]}, 1fr)`,
        }}
      >
        {Array.from({ length: PATTERN }).map((_, i) => (
          <div key={i} className="relative flex items-center justify-center">
            {i === currentIndex && (
              <div ref={dotRef} className="relative flex h-14 w-14 items-center justify-center">
                <svg className="h-full w-full -rotate-90" viewBox="0 0 60 60">
                  <circle cx="30" cy="30" r={RADIUS} fill="none" stroke="rgb(var(--color-border))" strokeWidth="2" />
                  <circle
                    cx="30" cy="30" r={RADIUS} fill="none" stroke="rgb(var(--color-accent))" strokeWidth="2"
                    strokeDasharray={CIRCUMFERENCE} strokeDashoffset={dashOffset} strokeLinecap="round"
                    style={{ transition: "stroke-dashoffset 80ms linear" }}
                  />
                </svg>
                <span className="absolute h-2.5 w-2.5 rounded-full bg-accent" />
              </div>
            )}
          </div>
        ))}
      </main>
    </div>
  );
}
