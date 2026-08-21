import { useState } from "react";
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

// Ported from frontend/src/App.jsx's gating pattern: logged-out visitors see
// the marketing area; a logged-in user with no calibration on file sees
// Calibration immediately (not buried in navigation) before anything else.
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
  const { logout } = useAuth();
  const [view, setView] = useState("home");
  const [calibrationSessionId, setCalibrationSessionId] = useState(null);
  // A real session whose report is open -- distinct from `view`, since it
  // can be reached either by clicking a row in Dashboard or by finishing a
  // Live Session recording, and should show over whatever view was active.
  const [openSessionId, setOpenSessionId] = useState(null);

  if (!calibrationSessionId) {
    return (
      <Calibration
        onComplete={(id) => {
          setCalibrationSessionId(id);
          setView("home");
        }}
      />
    );
  }

  if (view === "calibration") {
    return (
      <Calibration
        onComplete={(id) => {
          setCalibrationSessionId(id);
          setView("home");
        }}
        onExit={() => setView("home")}
      />
    );
  }

  let body;
  if (openSessionId) {
    body = <SessionReport sessionId={openSessionId} onBack={() => setOpenSessionId(null)} />;
  } else if (view === "home") {
    body = <Home onNavigate={setView} hasCalibration={!!calibrationSessionId} />;
  } else if (view === "session") {
    body = (
      <LiveSession
        calibrationSessionId={calibrationSessionId}
        onNavigate={setView}
        onSessionEnd={(sessionId) => {
          setOpenSessionId(sessionId);
          setView("dashboard");
        }}
      />
    );
  } else if (view === "status") {
    body = <SystemStatus hasCalibration={!!calibrationSessionId} onNavigate={setView} />;
  } else if (view === "dashboard") {
    body = (
      <Dashboard
        onNavigate={setView}
        onOpenSession={setOpenSessionId}
        hasCalibration={!!calibrationSessionId}
      />
    );
  } else {
    const Active = VIEWS[view] ?? Dashboard;
    body = <Active onNavigate={setView} />;
  }

  return (
    <div className="min-h-screen bg-bg text-text-primary">
      <Nav active={openSessionId ? null : view} onNavigate={(v) => { setOpenSessionId(null); setView(v); }} onLogout={logout} />
      <PageTransition viewKey={openSessionId ? `report-${openSessionId}` : view}>{body}</PageTransition>
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
