import { useState, useEffect, useCallback, useRef } from "react";
import { useAuth } from "../context/AuthContext.jsx";
import {
  startCalibration, submitCalibrationSamples, completeCalibration, validateGaze, CAMERA_CONSTRAINTS,
} from "../api/calibration.js";
import { motion } from "framer-motion";
import GazeField from "../components/GazeField.jsx";
import IrisMark from "../components/IrisMark.jsx";

// Ported from frontend/src/views/Calibration.jsx -- same backend contract,
// same 16-point default and dynamic grid shape, same on-screen-position
// measurement for ground truth. Only the visual language changed: the
// calibration target IS the product's gaze dot, not a generic progress ring.
const PATTERN = 16;
const GRID_SHAPE = { 9: [3, 3], 16: [4, 4] }[PATTERN];
const SECONDS_PER_POINT = 2.5;
const SETTLE_SECONDS = 0.6;
// The first dot also absorbs the participant settling in (on the first real
// run it was a 512px outlier against an ~80px median), so it is held longer
// and only its tail is captured.
const FIRST_POINT_EXTRA_SECONDS = 1.5;

// Dots are shown in a random order, not row by row. Row order lines up
// screen height with time, so any slow head drift (on the first real run,
// pitch crept from -14 to -17 degrees over the 43 s) gets learned as
// "head tilted down = looking low". The model then misplaces everything
// once the head has drifted further, which is what the accuracy check
// showed: top dots predicted near the bottom.
function shuffled(n) {
  const a = Array.from({ length: n }, (_, i) => i);
  for (let i = n - 1; i > 0; i -= 1) {
    const j = Math.floor(Math.random() * (i + 1));
    [a[i], a[j]] = [a[j], a[i]];
  }
  return a;
}

function pointSeconds(step) {
  return SECONDS_PER_POINT + (step === 0 ? FIRST_POINT_EXTRA_SECONDS : 0);
}

function settleSeconds(step) {
  return SETTLE_SECONDS + (step === 0 ? FIRST_POINT_EXTRA_SECONDS : 0);
}
const CAPTURE_INTERVAL_MS = 80;  // ~24 frames per dot: more samples to average out per-frame noise
const FRAME_QUALITY = 0.8;
const RADIUS = 26;

// Validation dots, as viewport fractions. Deliberately BETWEEN the
// calibration grid's points (x 0.2/0.4/0.6/0.8): accuracy measured on the
// points the model was fitted to would flatter it.
const VALIDATION_POINTS = [
  [0.5, 0.5], [0.3, 0.3], [0.7, 0.3], [0.3, 0.7], [0.7, 0.7],
];

const VERDICT_TEXT = {
  good: "Accurate enough to tell which button or link you were looking at.",
  fair: "Good enough for larger areas of a page. Small buttons might get mixed up.",
  poor: "The tracking was too far off to trust. A second try usually fixes it.",
  insufficient: "We couldn't see your eyes during the check. Let's run the setup again.",
};

const VERDICT_LOOK = {
  good: { label: "Good", color: "var(--color-accent)" },
  fair: { label: "Fair", color: "var(--color-amber)" },
  poor: { label: "Too low", color: "var(--color-coral)" },
  insufficient: { label: "Not measured", color: "var(--color-coral)" },
};

const TIPS = [
  { title: "Sit an arm's length away", body: "Face the camera straight on, like a video call.", icon: <><circle cx="12" cy="8" r="4" /><path d="M4 21c1.5-4 4.5-6 8-6s6.5 2 8 6" /></> },
  { title: "Light from the front", body: "Avoid a bright window behind you.", icon: <><circle cx="12" cy="12" r="4" /><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" /></> },
  { title: "Move only your eyes", body: "Keep your head still, now and during the test.", icon: <><path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12z" /><circle cx="12" cy="12" r="3" /></> },
];
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
  const { user, token, logout } = useAuth();
  const [status, setStatus] = useState("idle"); // idle | running | validating | done | error
  const [calibrationId, setCalibrationId] = useState(null);
  // currentIndex counts steps; order[step] is the grid cell shown at that step
  const [currentIndex, setCurrentIndex] = useState(0);
  const [order, setOrder] = useState(() => shuffled(PATTERN));
  const [progress, setProgress] = useState(0);
  const [cameraError, setCameraError] = useState(null);
  const [quality, setQuality] = useState(null);
  const [pointFeedback, setPointFeedback] = useState(null);
  const [validation, setValidation] = useState(null);
  const [validationError, setValidationError] = useState(null);
  const dotRef = useRef(null);

  const videoRef = useRef(null);
  const canvasRef = useRef(null);
  const streamRef = useRef(null);
  const frameBufferRef = useRef([]);
  const captureTimerRef = useRef(null);

  useEffect(() => () => {
    streamRef.current?.getTracks().forEach((t) => t.stop());
    clearInterval(captureTimerRef.current);
    videoRef.current?.remove();
    videoRef.current = null;
  }, []);

  // The webcam <video> is created once and lives outside React's tree, so
  // switching between the intro, dots and accuracy-check screens can never
  // swap it for a fresh element with no stream (which silently produced
  // empty frames and "face seen in 0% of frames"). It's kept on screen at
  // 2px and near-zero opacity: browsers may stop decoding a fully invisible
  // video.
  function captureVideo() {
    if (videoRef.current && document.body.contains(videoRef.current)) return videoRef.current;
    const v = document.createElement("video");
    v.muted = true;
    v.playsInline = true;
    v.autoplay = true;
    v.setAttribute("playsinline", "");
    v.setAttribute("aria-hidden", "true");
    Object.assign(v.style, { position: "fixed", left: "0", bottom: "0", width: "2px", height: "2px", opacity: "0.01", pointerEvents: "none", zIndex: "-1" });
    document.body.appendChild(v);
    videoRef.current = v;
    return v;
  }

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
    setValidation(null);
    setValidationError(null);
    try {
      streamRef.current?.getTracks().forEach((t) => t.stop());
      const stream = await navigator.mediaDevices.getUserMedia(CAMERA_CONSTRAINTS);
      streamRef.current = stream;
      const video = captureVideo();
      video.srcObject = stream;
      await video.play().catch(() => {});
      // wait (briefly) until the camera is actually delivering frames
      const t0 = performance.now();
      while (video.readyState < 2 && performance.now() - t0 < 4000) {
        await new Promise((r) => setTimeout(r, 100));
      }
      if (video.readyState < 2) {
        throw new Error("camera-no-frames");
      }
    } catch (err) {
      streamRef.current?.getTracks().forEach((t) => t.stop());
      setCameraError(err?.message === "camera-no-frames"
        ? "The camera turned on but isn't sending a picture. Close other apps using it (Zoom, Teams, FaceTime), then try again."
        : "Couldn't access the webcam. Check browser permissions and that no other app is using it.");
      return;
    }

    try {
      const session = await startCalibration(token, {
        participantId: user?.id || "unknown_participant",
        pattern: PATTERN,
        screenWidth: window.innerWidth,
        screenHeight: window.innerHeight,
      });
      setCalibrationId(session.session_id);
      setOrder(shuffled(PATTERN));
      setCurrentIndex(0);
      setProgress(0);
      setStatus("running");
    } catch (err) {
      setCameraError(err.message || "Couldn't start calibration.");
      streamRef.current?.getTracks().forEach((t) => t.stop());
    }
  }, [user, token]);

  const capturing = status === "running" || status === "validating";

  useEffect(() => {
    if (!capturing) return;
    const startTime = performance.now();
    const frame = requestAnimationFrame(function tick(now) {
      const elapsed = (now - startTime) / 1000;
      const pct = Math.min(elapsed / pointSeconds(status === "running" ? currentIndex : -1), 1);
      setProgress(pct);
      if (pct < 1) requestAnimationFrame(tick);
    });
    return () => cancelAnimationFrame(frame);
  }, [capturing, status, currentIndex]);

  useEffect(() => {
    if (!capturing) return;
    frameBufferRef.current = [];
    const settleTimer = setTimeout(() => {
      captureTimerRef.current = setInterval(() => {
        const frame = captureFrame();
        if (frame) frameBufferRef.current.push(frame);
      }, CAPTURE_INTERVAL_MS);
    }, settleSeconds(status === "running" ? currentIndex : -1) * 1000);
    return () => {
      clearTimeout(settleTimer);
      clearInterval(captureTimerRef.current);
    };
  }, [capturing, status, currentIndex, captureFrame]);

  useEffect(() => {
    if (!capturing || progress < 1) return;
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

      if (status === "validating") {
        let summary = null;
        try {
          if (frames.length > 0) {
            summary = (await validateGaze(token, calibrationId, currentIndex, frames, targetX, targetY)).summary;
          }
        } catch (err) {
          if (!cancelled) {
            // 422 = the calibration couldn't train a model at all
            streamRef.current?.getTracks().forEach((t) => t.stop());
            setValidationError(err.message || "Couldn't check calibration accuracy.");
            setStatus("done");
          }
          return;
        }
        if (cancelled) return;
        if (summary) setValidation(summary);
        if (currentIndex + 1 < VALIDATION_POINTS.length) {
          setCurrentIndex((i) => i + 1);
          setProgress(0);
        } else {
          streamRef.current?.getTracks().forEach((t) => t.stop());
          setStatus("done");
        }
        return;
      }

      if (frames.length === 0 && currentIndex <= 1) {
        // Nothing captured for a whole dot: the camera isn't delivering
        // frames. Stop now with a clear message instead of finishing all 16.
        const v = videoRef.current;
        const track = streamRef.current?.getVideoTracks?.()[0];
        console.error("calibration: no frames", { readyState: v?.readyState, paused: v?.paused, size: [v?.videoWidth, v?.videoHeight], track: track?.readyState, muted: track?.muted });
        streamRef.current?.getTracks().forEach((t) => t.stop());
        setCameraError(track?.readyState === "ended" || track?.muted
          ? "The camera stopped sending a picture. Close other apps using it, then try again."
          : "We couldn't get a picture from your camera. Reload the page and try again.");
        setStatus("error");
        return;
      }

      try {
        if (frames.length > 0) {
          const result = await submitCalibrationSamples(token, calibrationId, order[currentIndex], frames, targetX, targetY);
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
        try {
          const result = await completeCalibration(token, calibrationId);
          if (!cancelled) {
            setQuality(result.quality);
            // Camera stays on: straight into the validation dots.
            setPointFeedback(null);
            setCurrentIndex(0);
            setProgress(0);
            setStatus("validating");
          }
        } catch (err) {
          if (!cancelled) {
            streamRef.current?.getTracks().forEach((t) => t.stop());
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
      <canvas ref={canvasRef} style={{ display: "none" }} />
    </>
  );

  const exitLink = onExit && (
    <button
      onClick={onExit}
      className="absolute left-5 top-5 z-10 rounded-full border border-white/10 bg-surface/50 px-4 py-2 text-[14px] text-text-secondary backdrop-blur transition-colors hover:text-text-primary"
    >
      ← Back
    </button>
  );

  // GazeLens is dark-only, so there is no theme control to place here.
  const themeCorner = null;

  // Signing out stays reachable here: this screen renders without the Nav.
  // Left off the "running" state on purpose -- mid-capture isn't where you
  // want a stray click ending the session.
  const signOutLink = (
    <button
      onClick={logout}
      className="absolute right-5 top-5 z-10 rounded-full border border-white/10 bg-surface/50 px-4 py-2 text-[14px] text-text-secondary backdrop-blur transition-colors hover:text-text-primary"
    >
      Sign out
    </button>
  );

  const btn = "rounded-full bg-accent font-semibold text-[#0A0E14] transition-shadow hover:shadow-[0_0_30px_-6px_rgb(var(--color-accent)/0.7)]";
  const shell = (children, glow = "var(--color-accent)") => (
    <div className="relative isolate flex min-h-screen items-center justify-center px-4 py-20">
      {captureRig}
      <GazeField className="-z-10" />
      <div aria-hidden="true" className="pointer-events-none absolute inset-x-0 top-0 -z-10 h-[560px]" style={{ background: `radial-gradient(50% 60% at 50% 0%, rgb(${glow} / 0.13), transparent 70%)` }} />
      {exitLink}
      {signOutLink}
      <motion.div
        initial={{ opacity: 0, y: 18 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.6, ease: [0.22, 1, 0.36, 1] }}
        className="w-full max-w-[720px] rounded-[28px] border border-white/10 bg-surface/70 p-8 text-center shadow-[0_40px_100px_-40px_rgba(0,0,0,0.9)] backdrop-blur-xl sm:p-12"
      >
        {children}
      </motion.div>
    </div>
  );

  if (status === "idle" || status === "error") {
    return shell(
      <>
        <div className="mx-auto flex w-fit"><IrisMark size={60} wander /></div>
        <h1 className="mt-6 text-[36px] font-bold leading-tight tracking-[-0.02em] text-text-primary sm:text-[44px]">
          Let's teach GazeLens <span className="font-serif font-normal italic text-accent">your eyes</span>
        </h1>
        <p className="mx-auto mt-4 max-w-lg text-[17px] leading-relaxed text-text-secondary">
          A dot will move around the screen. Just look at it until its ring fills up. It takes about a minute and a half, and it's what makes your results accurate.
        </p>
        <div className="mt-10 grid gap-3 text-left sm:grid-cols-3">
          {TIPS.map((t) => (
            <div key={t.title} className="rounded-[18px] border border-white/10 bg-bg/50 p-5">
              <span className="flex h-10 w-10 items-center justify-center rounded-[12px] bg-accent/15 text-accent">
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{t.icon}</svg>
              </span>
              <div className="mt-4 text-[16px] font-semibold text-text-primary">{t.title}</div>
              <div className="mt-1 text-[14px] leading-snug text-text-secondary">{t.body}</div>
            </div>
          ))}
        </div>
        {cameraError && (
          <div className="mt-6 rounded-[16px] border border-coral/40 bg-coral/10 px-4 py-3 text-left text-[15px] text-text-primary">{cameraError}</div>
        )}
        <button onClick={begin} className={`mt-10 h-12 px-8 text-[16px] ${btn}`}>
          {status === "error" ? "Try again" : "I'm ready, start"}
        </button>
        <p className="mt-4 text-[13px] text-text-secondary">Your browser will ask to use the camera. Click Allow when it does.</p>
      </>
    );
  }

  if (status === "done") {
    const usable = quality?.usable ?? true;
    const verdict = validationError ? "insufficient" : validation?.verdict ?? "insufficient";
    const blocked = verdict === "poor" || verdict === "insufficient";
    const look = VERDICT_LOOK[verdict] || VERDICT_LOOK.insufficient;
    const pct = validation?.median_error_pct_diagonal;
    // the ring fills more the smaller the error; 20% of the screen or worse is empty
    const fill = pct == null ? 0 : Math.max(0.04, Math.min(1, 1 - pct / 20));
    const R = 54;
    const C = 2 * Math.PI * R;
    return shell(
      <>
        <h1 className="text-[36px] font-bold leading-tight tracking-[-0.02em] text-text-primary sm:text-[44px]">
          {blocked ? <>Let's try that <span className="font-serif font-normal italic text-coral">once more</span></> : <>You're all <span className="font-serif font-normal italic text-accent">set</span></>}
        </h1>
        <p className="mx-auto mt-3 max-w-md text-[17px] leading-relaxed text-text-secondary">
          {validationError || VERDICT_TEXT[verdict]}
        </p>

        <div className="mx-auto mt-10 flex max-w-lg flex-col items-center gap-8 rounded-[22px] border border-white/10 bg-bg/50 p-6 sm:flex-row sm:text-left">
          <div className="relative h-[132px] w-[132px] shrink-0">
            <svg viewBox="0 0 132 132" className="h-full w-full -rotate-90">
              <circle cx="66" cy="66" r={R} fill="none" stroke="rgb(255 255 255 / 0.08)" strokeWidth="10" />
              <motion.circle
                cx="66" cy="66" r={R} fill="none" stroke={`rgb(${look.color})`} strokeWidth="10" strokeLinecap="round"
                strokeDasharray={C}
                initial={{ strokeDashoffset: C }}
                animate={{ strokeDashoffset: C * (1 - fill) }}
                transition={{ duration: 1.2, ease: [0.22, 1, 0.36, 1] }}
                style={{ filter: `drop-shadow(0 0 8px rgb(${look.color} / 0.6))` }}
              />
            </svg>
            <div className="absolute inset-0 flex flex-col items-center justify-center">
              <span className="text-[26px] font-bold tabular-nums text-text-primary">
                {validation?.median_error_px != null ? Math.round(validation.median_error_px) : "–"}
              </span>
              <span className="text-[12px] text-text-secondary">pixels off</span>
            </div>
          </div>
          <div>
            <span className="rounded-full px-3 py-1 text-[14px] font-semibold" style={{ color: `rgb(${look.color})`, background: `rgb(${look.color} / 0.15)` }}>
              Accuracy: {look.label}
            </span>
            <p className="mt-3 text-[15px] leading-relaxed text-text-secondary">
              {pct != null
                ? <>On average, where we think you looked was {pct.toFixed(1)}% of the screen away from the real spot.</>
                : <>We couldn't measure accuracy this time.</>}
            </p>
            {quality && (
              <p className="mt-2 text-[13px] text-text-secondary">
                Face seen in {Math.round(quality.detection_rate * 100)}% of frames · {Math.round(quality.point_coverage * 100)}% of dots captured
              </p>
            )}
          </div>
        </div>

        {!usable && (
          <div className="mx-auto mt-4 max-w-lg rounded-[16px] border border-coral/40 bg-coral/10 px-4 py-3 text-left text-[15px] text-text-primary">
            {(quality?.reasons || []).join("; ") || "The setup didn't capture enough good frames."}
          </div>
        )}

        <button onClick={blocked ? begin : () => onComplete?.(calibrationId)} className={`mt-10 h-12 px-8 text-[16px] ${btn}`}>
          {blocked ? "Redo the setup" : "Continue"}
        </button>
        {!blocked && verdict === "fair" && (
          <button onClick={begin} className="mx-auto mt-4 block text-[14px] text-text-secondary hover:text-text-primary">
            Redo it for better accuracy
          </button>
        )}
      </>,
      blocked ? "var(--color-coral)" : "var(--color-accent)",
    );
  }

  // running | validating
  const dashOffset = CIRCUMFERENCE * (1 - progress);
  const ring = (
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
  );

  if (status === "validating") {
    const [vx, vy] = VALIDATION_POINTS[currentIndex];
    return (
      <div className="relative select-none overflow-hidden" style={{ cursor: "none", height: "100vh", width: "100vw" }}>
        {captureRig}
        {themeCorner}
        <div className="fixed left-1/2 top-10 z-10 -translate-x-1/2 text-center">
          <span className="rounded-full border border-white/10 bg-surface/70 px-4 py-1.5 text-[14px] font-medium text-text-primary backdrop-blur">Checking accuracy · {currentIndex + 1} of {VALIDATION_POINTS.length}</span>
          <p className="mx-auto mt-3 max-w-sm text-[14px] text-text-secondary">Same as before: look at each dot until it fills.</p>
        </div>
        <div className="fixed -translate-x-1/2 -translate-y-1/2" style={{ left: `${vx * 100}vw`, top: `${vy * 100}vh` }}>
          {ring}
        </div>
      </div>
    );
  }

  return (
    <div className="relative select-none overflow-hidden" style={{ cursor: "none" }}>
      {captureRig}
      {exitLink}
      {themeCorner}
      <div className="fixed left-1/2 top-10 z-10 -translate-x-1/2 text-center">
        <span className="rounded-full border border-white/10 bg-surface/70 px-4 py-1.5 text-[14px] font-medium text-text-primary backdrop-blur">Dot {currentIndex + 1} of {PATTERN}</span>
        {pointFeedback && (
          <p className={`mx-auto mt-3 max-w-sm text-[14px] leading-relaxed ${pointFeedback.accepted > 0 ? "text-text-secondary" : "text-coral"}`}>
            {pointFeedback.accepted > 0
              ? `Nice. Got ${pointFeedback.accepted} of ${pointFeedback.accepted + pointFeedback.rejected} frames on the last dot.`
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
            {i === order[currentIndex] && ring}
          </div>
        ))}
      </main>
    </div>
  );
}
