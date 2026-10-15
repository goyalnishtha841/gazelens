import { useState, useEffect, useCallback, useRef } from "react";
import { useAuth } from "../context/AuthContext.jsx";
import {
  startCalibration, submitCalibrationSamples, completeCalibration, validateGaze, CAMERA_CONSTRAINTS,
} from "../api/calibration.js";
import { Label } from "../components/Primitives.jsx";

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
const CAPTURE_INTERVAL_MS = 130;
const FRAME_QUALITY = 0.8;
const RADIUS = 26;

// Validation dots, as viewport fractions. Deliberately BETWEEN the
// calibration grid's points (x 0.2/0.4/0.6/0.8): accuracy measured on the
// points the model was fitted to would flatter it.
const VALIDATION_POINTS = [
  [0.5, 0.5], [0.3, 0.3], [0.7, 0.3], [0.3, 0.7], [0.7, 0.7],
];

const VERDICT_TEXT = {
  good: "Accurate enough to attribute gaze to individual page elements.",
  fair: "Usable for larger page regions; small buttons may be misattributed.",
  poor: "Too inaccurate to trust. Recalibrate before starting a session.",
  insufficient: "Your eyes weren't tracked during the check. Recalibrate.",
};
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
    setValidation(null);
    setValidationError(null);
    try {
      const stream = await navigator.mediaDevices.getUserMedia(CAMERA_CONSTRAINTS);
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
      setOrder(shuffled(PATTERN));
      setCurrentIndex(0);
      setProgress(0);
      setStatus("running");
    } catch (err) {
      setCameraError(err.message || "Couldn't start calibration.");
      streamRef.current?.getTracks().forEach((t) => t.stop());
    }
  }, [user]);

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
            summary = (await validateGaze(calibrationId, currentIndex, frames, targetX, targetY)).summary;
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

      try {
        if (frames.length > 0) {
          const result = await submitCalibrationSamples(calibrationId, order[currentIndex], frames, targetX, targetY);
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
          const result = await completeCalibration(calibrationId);
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

  // GazeLens is dark-only, so there is no theme control to place here.
  const themeCorner = null;

  // Signing out has to be reachable even when calibration is forced (first
  // login, or any reload -- calibrationSessionId isn't persisted, so this
  // screen can be the ONLY thing rendered, with no Nav anywhere in reach).
  // Left off the "running" state on purpose -- mid-capture isn't where you
  // want a stray click ending the session.
  const signOutLink = (
    <div className="absolute right-6 top-6 flex items-center gap-4">
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
          <Label>GazeLens calibration</Label>
          <h1 className="mt-4 font-sans text-[28px] font-semibold text-text-primary">Calibrate your gaze</h1>
          <p className="mt-3 text-[14px] leading-relaxed text-text-secondary">
            16 points will appear one at a time. Look directly at each one until it fills in, then hold
            your gaze until the next point appears.
          </p>
          <p className="mt-3 text-[13px] leading-relaxed text-text-secondary">
            Then 5 more points check how accurate it is. Takes about a minute and a half. Every gaze
            measurement in your session depends on this, so it's worth doing carefully.
          </p>
          <ul className="mx-auto mt-4 max-w-sm space-y-1 text-left text-[12px] leading-relaxed text-text-secondary">
            <li>· Sit about an arm's length from the screen, face square to the camera</li>
            <li>· Light your face evenly from the front; avoid a bright window behind you</li>
            <li>· Keep your head still and move only your eyes, here and during the session</li>
          </ul>
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
    const verdict = validationError ? "insufficient" : validation?.verdict ?? "insufficient";
    const blocked = verdict === "poor" || verdict === "insufficient";
    return (
      <div className="relative flex min-h-[calc(100vh-73px)] items-center justify-center">
        {captureRig}
        {exitLink}
        {signOutLink}
        <div className="max-w-md text-center">
          <Label>GazeLens calibration</Label>
          <h1 className="mt-4 font-sans text-[28px] font-semibold text-text-primary">
            {blocked ? "Calibration needs another try" : "Calibration complete"}
          </h1>
          <p className="mt-2 font-mono text-[12px] text-text-secondary">{calibrationId}</p>
          {quality && (
            <p className="mt-3 text-[13px] text-text-secondary">
              {Math.round(quality.detection_rate * 100)}% detection rate ·{" "}
              {Math.round(quality.point_coverage * 100)}% point coverage
            </p>
          )}
          <div className="mt-6 rounded-card border border-border px-4 py-4 text-left">
            <Label>Accuracy check</Label>
            {validation?.median_error_px != null && (
              <p className="mt-2 font-mono text-[22px] font-semibold text-text-primary">
                {Math.round(validation.median_error_px)} px
                <span className="ml-2 text-[12px] font-normal text-text-secondary">
                  median error · {validation.median_error_pct_diagonal.toFixed(1)}% of screen
                </span>
              </p>
            )}
            <p className={`mt-2 text-[13px] leading-relaxed ${blocked ? "text-accent" : "text-text-secondary"}`}>
              {validationError || VERDICT_TEXT[verdict]}
            </p>
          </div>
          {!usable && (
            <div className="mt-3 rounded-card border border-accent/40 px-4 py-3 text-left text-[13px] text-text-primary">
              {(quality?.reasons || []).join("; ") || "Calibration quality is below the usable threshold."}
            </div>
          )}
          <button
            onClick={blocked ? begin : () => onComplete?.(calibrationId)}
            className="mt-8 h-11 rounded-card bg-text-primary px-8 font-label-caps text-[13px] font-medium uppercase tracking-label text-bg transition-opacity hover:opacity-85"
          >
            {blocked ? "Recalibrate" : "Continue to dashboard"}
          </button>
          {!blocked && verdict === "fair" && (
            <button onClick={begin} className="mt-3 block w-full text-[12px] text-text-secondary hover:text-text-primary">
              Recalibrate for better accuracy
            </button>
          )}
        </div>
      </div>
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
          <Label>Accuracy check {currentIndex + 1} of {VALIDATION_POINTS.length}</Label>
          <p className="mx-auto mt-2 max-w-sm text-[12px] text-text-secondary">Same as before: look at each dot until it fills.</p>
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
            {i === order[currentIndex] && ring}
          </div>
        ))}
      </main>
    </div>
  );
}
