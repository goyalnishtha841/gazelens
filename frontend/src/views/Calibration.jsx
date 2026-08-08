import { useState, useEffect, useCallback, useRef } from "react";
import { useAuth } from "../context/AuthContext.jsx";
import { startCalibration, submitCalibrationSamples, completeCalibration } from "../api/calibration.js";

const PATTERN = 9; // quick 3x3 grid -- backend also supports 16 (thorough); not exposed here yet
const SECONDS_PER_POINT = 2.5;
const SETTLE_SECONDS = 0.6; // let the participant's eyes land before capturing frames
const CAPTURE_INTERVAL_MS = 130; // ~15 frames/point, matching the backend's default samples_per_point
const FRAME_QUALITY = 0.7;
const RADIUS = 30;
const CIRCUMFERENCE = 2 * Math.PI * RADIUS;

export default function Calibration({ onComplete, onExit }) {
  const { user } = useAuth();
  const [status, setStatus] = useState("idle"); // idle | running | done | error
  const [calibrationId, setCalibrationId] = useState(null);
  const [currentIndex, setCurrentIndex] = useState(0);
  const [progress, setProgress] = useState(0); // 0-1
  const [cameraError, setCameraError] = useState(null);
  const [quality, setQuality] = useState(null);
  const mouseOffset = useRef({ x: 0, y: 0 });
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

  const begin = useCallback(async () => {
    setCameraError(null);
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

  // Progress ring timer for the current point.
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

  // Capture frames into a buffer once the participant has had time to settle
  // on the new target, until the point's display time is up.
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

  // When the ring completes, submit the buffered frames for this point and advance.
  useEffect(() => {
    if (status !== "running" || progress < 1) return;
    let cancelled = false;
    clearInterval(captureTimerRef.current);

    (async () => {
      const frames = frameBufferRef.current;
      // The actual on-screen position of the dot, not the server's generated
      // grid -- this grid's CSS layout doesn't necessarily match the formula
      // in backend/calibration/points.py, and the sample schema's target_x/
      // target_y override exists exactly for this (see SubmitSamplesRequest).
      let targetX, targetY;
      if (dotRef.current) {
        const rect = dotRef.current.getBoundingClientRect();
        targetX = (rect.left + rect.width / 2) / window.innerWidth;
        targetY = (rect.top + rect.height / 2) / window.innerHeight;
      }

      try {
        if (frames.length > 0) {
          await submitCalibrationSamples(calibrationId, currentIndex, frames, targetX, targetY);
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

  // Subtle mouse parallax on the dot -- same "organic feedback" touch as the export.
  useEffect(() => {
    function handleMouseMove(e) {
      if (!dotRef.current) return;
      const rect = dotRef.current.parentElement.getBoundingClientRect();
      const centerX = rect.left + rect.width / 2;
      const centerY = rect.top + rect.height / 2;
      const moveX = (e.clientX - centerX) / 40;
      const moveY = (e.clientY - centerY) / 40;
      mouseOffset.current = { x: moveX, y: moveY };
      dotRef.current.style.transform = `translate(${moveX}px, ${moveY}px)`;
    }
    document.addEventListener("mousemove", handleMouseMove);
    return () => document.removeEventListener("mousemove", handleMouseMove);
  }, []);

  // Hidden video/canvas used purely to pull frames off the webcam stream --
  // rendered in every state so the ref is ready before begin() plays it.
  const captureRig = (
    <>
      <video ref={videoRef} muted playsInline style={{ position: "fixed", width: 1, height: 1, opacity: 0, pointerEvents: "none" }} />
      <canvas ref={canvasRef} style={{ display: "none" }} />
    </>
  );

  if (status === "idle" || status === "error") {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center relative">
        {captureRig}
        {onExit && (
          <button
            onClick={onExit}
            className="absolute top-6 left-6 text-[11px] font-label-caps text-secondary hover:text-on-surface transition-colors flex items-center gap-1"
          >
            <span className="material-symbols-outlined text-[16px]">arrow_back</span>
            Dashboard
          </button>
        )}
        <div className="max-w-md text-center entrance-animation">
          <span className="font-label-caps text-label-caps text-on-surface-variant tracking-widest opacity-60 block mb-4">
            GAZELENS CALIBRATION
          </span>
          <h1 className="font-headline-md text-headline-md mb-3">Calibrate your gaze</h1>
          <p className="text-secondary text-body-md mb-8">
            You'll see 9 points appear one at a time. Fixate on each one until the ring fills in, then hold your
            gaze until the next point appears.
          </p>
          {cameraError && (
            <div className="text-sm text-[#B23A2E] bg-[#F6E6E4] border border-[#B23A2E] px-3 py-2 mb-6 text-left">
              {cameraError}
            </div>
          )}
          <button
            onClick={begin}
            className="bg-primary-container text-white px-6 py-3 font-label-caps text-label-caps tracking-widest hover:opacity-90 transition-opacity"
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
      <div className="min-h-screen bg-background flex items-center justify-center relative">
        {captureRig}
        {onExit && (
          <button
            onClick={onExit}
            className="absolute top-6 left-6 text-[11px] font-label-caps text-secondary hover:text-on-surface transition-colors flex items-center gap-1"
          >
            <span className="material-symbols-outlined text-[16px]">arrow_back</span>
            Dashboard
          </button>
        )}
        <div className="max-w-md text-center entrance-animation">
          <span className="font-label-caps text-label-caps text-on-surface-variant tracking-widest opacity-60 block mb-4">
            GAZELENS CALIBRATION
          </span>
          <h1 className="font-headline-md text-headline-md mb-3">
            {usable ? "Calibration Optimized" : "Calibration Complete — Quality Low"}
          </h1>
          <p className="text-secondary font-data-mono text-data-mono mb-2">{calibrationId}</p>
          {quality && (
            <p className="text-secondary text-body-md mb-4">
              {Math.round(quality.detection_rate * 100)}% detection rate ·{" "}
              {Math.round(quality.point_coverage * 100)}% point coverage
            </p>
          )}
          {!usable && (
            <div className="text-sm text-[#B23A2E] bg-[#F6E6E4] border border-[#B23A2E] px-3 py-2 mb-6 text-left">
              {(quality?.reasons || []).join("; ") || "Calibration quality is below the usable threshold."} You can
              continue, but gaze accuracy will likely be poor — consider fixing lighting and recalibrating.
            </div>
          )}
          <button
            onClick={() => onComplete?.(calibrationId)}
            className="bg-primary-container text-white px-6 py-3 font-label-caps text-label-caps tracking-widest hover:opacity-90 transition-opacity"
          >
            Continue to live session
          </button>
        </div>
      </div>
    );
  }

  const dashOffset = CIRCUMFERENCE - progress * CIRCUMFERENCE;
  const isSettling = progress < 0.15;

  return (
    <div className="overflow-hidden select-none" style={{ cursor: "none" }}>
      {captureRig}
      <div
        className="fixed inset-0 z-0 pointer-events-none"
        style={{
          backgroundImage: 'url("https://www.transparenttextures.com/patterns/felt.png")',
          opacity: 0.03,
        }}
      />

      <div className="fixed top-12 left-1/2 -translate-x-1/2 z-10 text-center">
        <span className="font-label-caps text-label-caps text-on-surface-variant tracking-widest opacity-60">
          GAZELENS CALIBRATION
        </span>
        <h1 className="font-label-caps text-label-caps text-on-surface-variant block mt-2">
          Point {currentIndex + 1} of {PATTERN}
        </h1>
      </div>

      <main
        className="relative z-10 grid grid-cols-3 grid-rows-3"
        style={{ height: "100vh", width: "100vw", padding: "10vh 10vw", boxSizing: "border-box" }}
      >
        {Array.from({ length: PATTERN }).map((_, i) => (
          <div key={i} className="flex items-center justify-center relative">
            {i === currentIndex && (
              <div className="flex flex-col items-center gap-3">
                <div className="font-label-caps text-[10px] text-primary opacity-40 animate-pulse">
                  FIXATE HERE
                </div>
                <div className="relative w-16 h-16 flex items-center justify-center">
                  <div className="absolute inset-0 border border-outline-variant opacity-20 rounded-full" />
                  <svg className="w-full h-full" viewBox="0 0 64 64">
                    <circle
                      className="text-primary-container"
                      cx="32"
                      cy="32"
                      fill="transparent"
                      r={RADIUS}
                      stroke="currentColor"
                      strokeWidth="3"
                      strokeDasharray={CIRCUMFERENCE}
                      strokeDashoffset={dashOffset}
                      style={{
                        transition: "stroke-dashoffset 0.1s linear",
                        transform: "rotate(-90deg)",
                        transformOrigin: "50% 50%",
                      }}
                    />
                  </svg>
                  <div
                    ref={dotRef}
                    className="absolute w-3 h-3 bg-primary-container rounded-full"
                    style={{
                      boxShadow: "0 0 20px rgba(31, 111, 120, 0.2)",
                      transition: "all 0.5s ease-in-out",
                      transform: isSettling ? "scale(1.3)" : "scale(1)",
                    }}
                  />
                </div>
              </div>
            )}
          </div>
        ))}
      </main>

      <button
        onClick={onExit}
        style={{ cursor: "pointer" }}
        className="fixed bottom-10 right-10 flex items-center gap-2 px-4 py-2 border border-outline-variant text-on-surface-variant hover:bg-surface-container transition-colors"
      >
        <span className="material-symbols-outlined text-sm">close</span>
        <span className="font-label-caps text-label-caps">Cancel Session</span>
      </button>
    </div>
  );
}
