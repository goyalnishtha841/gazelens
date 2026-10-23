import { useCallback, useEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import IrisMark from "./IrisMark.jsx";

/**
 * Explicit, in-app permission before the webcam is ever opened.
 *
 * The browser's own prompt says only "use your camera"; this one says why,
 * what leaves the device and what is kept, and nothing calls getUserMedia
 * until the person clicks Allow here. Asked every time the camera is about
 * to start (calibration, then each test), never remembered.
 *
 *   const { askCameraPermission, cameraConsentDialog } = useCameraConsent();
 *   if (!(await askCameraPermission({ purpose: "calibration" }))) return;
 *   ...getUserMedia...
 *   return <>{...}{cameraConsentDialog}</>;
 *
 * The claims below are what the backend does: frames are decoded in memory
 * (backend/api/pipeline.estimate_gaze_frame) and never written to disk; only
 * eye measurements (calibration) or gaze points (test) are stored; both
 * pages stop the camera tracks when they unmount.
 */
const PURPOSES = {
  calibration: {
    title: "Allow camera for setup?",
    why: "GazeLens needs your webcam to learn how your eyes move while you follow 16 dots on the screen.",
    kept: "Only measurements of your eyes (iris position, eyelids, head angle) are saved with your setup, never images, and only you can see them.",
  },
  session: {
    title: "Allow camera for this test?",
    why: "GazeLens needs your webcam to follow where you look on the page while you use it.",
    kept: "Only where you looked (gaze points) is saved with your test, and only you can see it.",
  },
};

const SENT = "Each camera frame is sent to the GazeLens server, measured and then discarded. No video or photos are saved.";
const OFF = "The camera turns off when you finish or leave the page.";

export function useCameraConsent() {
  const [request, setRequest] = useState(null); // { purpose, resolve } | null

  const askCameraPermission = useCallback(
    ({ purpose = "session" } = {}) => new Promise((resolve) => setRequest({ purpose, resolve })),
    []
  );

  const answer = useCallback((allowed) => {
    setRequest((current) => {
      current?.resolve(allowed);
      return null;
    });
  }, []);

  // A page that unmounts mid-question must not leave its caller waiting.
  useEffect(() => () => setRequest((current) => {
    current?.resolve(false);
    return null;
  }), []);

  const cameraConsentDialog = (
    <AnimatePresence>
      {request && <ConsentDialog purpose={request.purpose} onAnswer={answer} />}
    </AnimatePresence>
  );

  return { askCameraPermission, cameraConsentDialog };
}

function ConsentDialog({ purpose, onAnswer }) {
  const allowRef = useRef(null);
  const copy = PURPOSES[purpose] || PURPOSES.session;

  useEffect(() => {
    allowRef.current?.focus();
    const onKey = (e) => {
      if (e.key === "Escape") onAnswer(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onAnswer]);

  return (
    <motion.div
      className="fixed inset-0 z-[100] flex items-center justify-center bg-black/70 px-4 backdrop-blur-sm"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      onClick={() => onAnswer(false)}
    >
      <motion.div
        role="dialog"
        aria-modal="true"
        aria-labelledby="camera-consent-title"
        aria-describedby="camera-consent-why"
        className="w-full max-w-[460px] rounded-[24px] border border-white/10 bg-surface p-7 text-left shadow-[0_30px_80px_-20px_rgba(0,0,0,0.8)]"
        initial={{ opacity: 0, y: 12, scale: 0.98 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        exit={{ opacity: 0, y: 8, scale: 0.98 }}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex h-12 w-12 items-center justify-center rounded-full bg-accent/15">
          <IrisMark size={26} />
        </div>
        <h2 id="camera-consent-title" className="mt-5 text-[22px] font-semibold text-text-primary">{copy.title}</h2>
        <p id="camera-consent-why" className="mt-2 text-[15px] leading-relaxed text-text-secondary">{copy.why}</p>
        <ul className="mt-5 flex flex-col gap-3">
          {[SENT, copy.kept, OFF].map((p) => (
            <li key={p} className="flex gap-3 text-[14px] leading-relaxed text-text-primary">
              <span aria-hidden="true" className="mt-[7px] h-1.5 w-1.5 shrink-0 rounded-full bg-accent" />
              <span>{p}</span>
            </li>
          ))}
        </ul>
        <p className="mt-5 text-[13px] text-text-secondary">
          After you click Allow, your browser will also ask. Choose Allow there too.
        </p>
        <div className="mt-6 flex flex-col-reverse gap-3 sm:flex-row sm:justify-end">
          <button
            type="button"
            onClick={() => onAnswer(false)}
            className="h-11 rounded-full px-6 text-[15px] font-medium text-text-secondary hover:bg-white/[0.06] hover:text-text-primary"
          >
            Not now
          </button>
          <button
            ref={allowRef}
            type="button"
            onClick={() => onAnswer(true)}
            className="h-11 rounded-full bg-accent px-6 text-[15px] font-semibold text-[#0A0E14] transition-shadow hover:shadow-[0_0_30px_-6px_rgb(var(--color-accent)/0.7)]"
          >
            Allow camera
          </button>
        </div>
      </motion.div>
    </motion.div>
  );
}
