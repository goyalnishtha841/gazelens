import { useState } from "react";
import { AuthProvider, useAuth } from "./context/AuthContext.jsx";
import Landing from "./views/Landing.jsx";
import SignIn from "./views/SignIn.jsx";
import SignUp from "./views/SignUp.jsx";
import Calibration from "./views/Calibration.jsx";
import LiveSession from "./views/LiveSession.jsx";
import Dashboard from "./views/Dashboard.jsx";

function PublicArea() {
  const [view, setView] = useState("landing"); // "landing" | "signin" | "signup"

  if (view === "signin") return <SignIn onSwitchToSignup={() => setView("signup")} />;
  if (view === "signup") return <SignUp onSwitchToSignin={() => setView("signin")} />;
  return <Landing onSignIn={() => setView("signin")} onSignUp={() => setView("signup")} />;
}

function AuthenticatedApp() {
  const [activeView, setActiveView] = useState("dashboard");
  const [lastSessionId, setLastSessionId] = useState(null);
  const [calibrationSessionId, setCalibrationSessionId] = useState(null);

  if (activeView === "calibration") {
    return (
      <Calibration
        onComplete={(calibrationId) => {
          setCalibrationSessionId(calibrationId);
          setActiveView("session");
        }}
        onExit={() => setActiveView("dashboard")}
      />
    );
  }
  if (activeView === "session") {
    return (
      <LiveSession
        calibrationSessionId={calibrationSessionId}
        onNavigate={setActiveView}
        onSessionEnd={(sessionId) => {
          setLastSessionId(sessionId);
          setActiveView("dashboard");
        }}
      />
    );
  }
  return <Dashboard initialSessionId={lastSessionId} onNavigate={setActiveView} />;
}

function AppShell() {
  const { user, loading } = useAuth();

  if (loading) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center">
        <div className="w-6 h-6 border-2 border-outline-variant border-t-primary-container rounded-full animate-spin" />
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
