import { useEffect, useRef, useState } from "react";
import { findUsableCalibration, screenMatches } from "./api/calibration.js";
import { AuthProvider, useAuth } from "./context/AuthContext.jsx";
import Nav from "./components/Nav.jsx";
import PageTransition from "./components/PageTransition.jsx";
import Landing from "./views/Landing.jsx";
import SignIn from "./views/SignIn.jsx";
import SignUp from "./views/SignUp.jsx";
import Calibration from "./views/Calibration.jsx";
import Home from "./views/Home.jsx";
import Dashboard from "./views/Dashboard.jsx";
import SessionReport from "./views/SessionReport.jsx";
import LiveSession from "./views/LiveSession.jsx";
import SystemStatus from "./views/SystemStatus.jsx";
import GazeMap from "./views/GazeMap.jsx";
import Analytics from "./views/Analytics.jsx";
import Insights from "./views/Insights.jsx";
import Reports from "./views/Reports.jsx";

const VIEWS = {
  dashboard: Dashboard,
  gazemap: GazeMap,
  analytics: Analytics,
  insights: Insights,
  reports: Reports,
};

// Logged-out visitors see the marketing area. Signed-in users land on Home
// and can browse every past session and report without a camera; only
// starting a new test needs a usable calibration, and that is restored from
// the server on load rather than forgotten on every refresh.
function PublicArea() {
  const [authView, setAuthView] = useState("landing"); // landing | signin | signup

  return (
    <div className="min-h-screen bg-bg text-text-primary">
      {authView === "landing" && (
        <Nav active="landing" onNavigate={() => {}} onSignIn={() => setAuthView("signin")} loggedOut />
      )}
      <PageTransition viewKey={authView}>
        {authView === "signin" && (
          <SignIn onSwitchToSignup={() => setAuthView("signup")} onBackToHome={() => setAuthView("landing")} />
        )}
        {authView === "signup" && (
          <SignUp onSwitchToSignin={() => setAuthView("signin")} onBackToHome={() => setAuthView("landing")} />
        )}
        {authView === "landing" && <Landing onNavigate={() => setAuthView("signin")} />}
      </PageTransition>
    </div>
  );
}

function AuthenticatedApp() {
  const { logout, token } = useAuth();
  const [view, setView] = useState("home");
  // { id, screenWidth, screenHeight } -- the screen it was recorded on, since
  // a live session refuses a calibration from a differently sized window.
  const [calibration, setCalibration] = useState(null);
  // Where Calibration goes when it finishes (next) or is left (back).
  const [calibrationFlow, setCalibrationFlow] = useState({ next: "home", back: "home" });
  // A real session whose report is open -- distinct from `view`, since it
  // can be reached either by clicking a row in Dashboard or by finishing a
  // Live Session recording, and should show over whatever view was active.
  const [openSessionId, setOpenSessionId] = useState(null);
  const restoring = useRef(null);
  const [restoreDone, setRestoreDone] = useState(false);
  const [, setWindowSize] = useState(null);

  // Pick up the latest calibration that would still work here, so a reload
  // or a fresh sign-in doesn't mean sitting through the setup again.
  useEffect(() => {
    let cancelled = false;
    restoring.current = findUsableCalibration(token)
      .catch(() => null)
      .then((found) => {
        if (!cancelled) {
          if (found) setCalibration((current) => current ?? found);
          setRestoreDone(true);
        }
        return found;
      });
    return () => { cancelled = true; };
  }, [token]);

  // Resizing the window can make the calibration unusable (or usable again).
  useEffect(() => {
    const onResize = () => setWindowSize(`${window.innerWidth}x${window.innerHeight}`);
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, []);

  const usable = (c) => !!c && screenMatches(c.screenWidth, c.screenHeight);
  const hasCalibration = usable(calibration);
  // For Home / System status copy: null while the restore is still running.
  const calibrationStatus = hasCalibration ? true : restoreDone ? false : null;

  const openCalibration = (next, back) => {
    setCalibrationFlow({ next, back });
    setView("calibration");
  };

  const navigate = async (target) => {
    setOpenSessionId(null);
    if (target === "calibration") {
      const from = view === "calibration" ? "home" : view;
      openCalibration(from, from);
      return;
    }
    if (target === "session" && !hasCalibration) {
      // The restore may still be in flight right after sign-in.
      const restored = calibration ?? (await restoring.current);
      if (!usable(restored)) {
        openCalibration("session", view === "session" ? "home" : view);
        return;
      }
    }
    setView(target);
  };

  if (view === "calibration") {
    return (
      <div className="studio-calibration-original">
      <Calibration
        onComplete={(id) => {
          setCalibration({ id, screenWidth: window.innerWidth, screenHeight: window.innerHeight });
          setView(calibrationFlow.next);
        }}
        onExit={() => setView(calibrationFlow.back === "session" ? "home" : calibrationFlow.back)}
      />
      </div>
    );
  }

  let body;
  if (openSessionId) {
    body = <SessionReport sessionId={openSessionId} onBack={() => setOpenSessionId(null)} />;
  } else if (view === "home") {
    body = <Home onNavigate={navigate} onOpenSession={setOpenSessionId} hasCalibration={calibrationStatus} />;
  } else if (view === "session") {
    body = (
      <LiveSession
        calibrationSessionId={hasCalibration ? calibration.id : null}
        onNavigate={navigate}
        onSessionEnd={(sessionId) => {
          setOpenSessionId(sessionId);
          setView("dashboard");
        }}
      />
    );
  } else if (view === "status") {
    body = <SystemStatus hasCalibration={calibrationStatus} onNavigate={navigate} />;
  } else if (view === "dashboard") {
    body = (
      <Dashboard
        onNavigate={navigate}
        onOpenSession={setOpenSessionId}
        hasCalibration={hasCalibration}
      />
    );
  } else {
    const Active = VIEWS[view] ?? Dashboard;
    body = <Active onNavigate={navigate} onOpenSession={setOpenSessionId} />;
  }

  return (
    <div className="relative isolate min-h-screen bg-bg text-text-primary">
      <AppBackdrop />
      <Nav active={openSessionId ? null : view} onNavigate={navigate} onLogout={logout} />
      <PageTransition viewKey={openSessionId ? `report-${openSessionId}` : view}>{body}</PageTransition>
    </div>
  );
}

/** The landing page's atmosphere for signed-in pages: a soft teal glow at
 *  the top and a faint dot grid fading out downwards. Static on purpose --
 *  nothing should move behind a recording or a report. */
function AppBackdrop() {
  return (
    <div aria-hidden="true" className="pointer-events-none fixed inset-0 -z-10">
      <div className="absolute inset-x-0 top-0 h-[520px]" style={{ background: "radial-gradient(55% 70% at 50% 0%, rgb(var(--color-accent) / 0.10), transparent 70%)" }} />
      <div
        className="absolute inset-0"
        style={{
          backgroundImage: "radial-gradient(rgb(var(--color-text-secondary) / 0.16) 1px, transparent 1px)",
          backgroundSize: "30px 30px",
          maskImage: "linear-gradient(to bottom, black, transparent 75%)",
          WebkitMaskImage: "linear-gradient(to bottom, black, transparent 75%)",
        }}
      />
    </div>
  );
}

function AppShell() {
  const { user, loading } = useAuth();

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-bg">
        <div className="h-2 w-2 animate-pulse rounded-full bg-accent" />
      </div>
    );
  }

  return user ? <AuthenticatedApp /> : <PublicArea />;
}

export default function App() {
  return (
    <AuthProvider>
      <AppShell />
    </AuthProvider>
  );
}
