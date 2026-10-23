import { useState } from "react";
import { useAuth } from "../context/AuthContext.jsx";
import AuthLayout, { Field } from "../components/AuthLayout.jsx";
import GoogleSignIn from "../components/GoogleSignIn.jsx";

// Mirrors backend/api/security.py (PASSWORD_RULES, validate_new_password).
// The API enforces these too; this list only shows them as the user types.
function passwordChecks(password, email) {
  const local = (email.split("@")[0] || "").toLowerCase();
  return [
    { label: "At least 8 characters", ok: password.length >= 8 },
    { label: "An uppercase letter", ok: /[A-Z]/.test(password) },
    { label: "A lowercase letter", ok: /[a-z]/.test(password) },
    { label: "A number", ok: /\d/.test(password) },
    { label: "A symbol, like ! @ # $", ok: /[^A-Za-z0-9\s]/.test(password) },
    {
      label: "Doesn't contain your email name",
      ok: password.length > 0 && !(local.length >= 3 && password.toLowerCase().includes(local)),
    },
  ];
}

function cleanName(name) {
  return name.split(/\s+/).filter(Boolean).join(" ");
}

export default function SignUp({ onSwitchToSignin, onBackToHome }) {
  const { signup } = useAuth();
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);

  const name = cleanName(fullName);
  const nameOk = name.length >= 2 && /\p{L}/u.test(name);
  const checks = passwordChecks(password, email);
  const passwordOk = checks.every((c) => c.ok) && password === password.trim();

  async function handleSubmit(e) {
    e.preventDefault();
    if (!nameOk) {
      setError("Please enter your name.");
      return;
    }
    if (!passwordOk) {
      setError("Your password doesn't meet all the requirements yet.");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      await signup(email, password, name);
    } catch (err) {
      setError(err.message || "Couldn't create your account");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <AuthLayout
      title={<>Create your <span className="font-serif font-normal italic text-accent">account</span></>}
      subtitle="It takes a few seconds. Then a one-minute setup and you're ready."
      onBackToHome={onBackToHome}
      footer={<>Already have an account?{" "}<button type="button" onClick={onSwitchToSignin} className="font-medium text-accent hover:opacity-80">Sign in</button></>}
    >
      {error && (
        <div className="mb-5 rounded-[14px] border border-coral/40 bg-coral/10 px-4 py-3 text-[14px] text-text-primary">{error}</div>
      )}
      <form onSubmit={handleSubmit} className="flex flex-col gap-5">
        <Field label="Your name" type="text" required minLength={2} maxLength={80} readOnly={submitting} value={fullName}
          onChange={(e) => setFullName(e.target.value)} placeholder="Your full name" autoComplete="name" />
        <Field label="Email" type="email" required readOnly={submitting} value={email}
          onChange={(e) => setEmail(e.target.value)} placeholder="you@example.com" autoComplete="email" />
        <div className="flex flex-col gap-3">
          <Field label="Password" type="password" required readOnly={submitting} value={password}
            onChange={(e) => setPassword(e.target.value)} placeholder="Create a strong password" autoComplete="new-password"
            aria-describedby="password-rules" />
          <ul id="password-rules" className="grid grid-cols-1 gap-x-4 gap-y-1.5 text-[13px] sm:grid-cols-2" aria-live="polite">
            {checks.map((c) => (
              <li key={c.label} className={`flex items-center gap-2 ${c.ok ? "text-accent" : "text-text-secondary"}`}>
                <span aria-hidden="true" className={`flex h-4 w-4 shrink-0 items-center justify-center rounded-full border text-[10px] ${c.ok ? "border-accent bg-accent/15" : "border-white/20"}`}>
                  {c.ok ? "✓" : ""}
                </span>
                <span>{c.label}<span className="sr-only">{c.ok ? " (met)" : " (not met)"}</span></span>
              </li>
            ))}
          </ul>
        </div>
        <button type="submit" disabled={submitting || !nameOk || !passwordOk} className="mt-2 h-12 w-full rounded-full bg-accent text-[16px] font-semibold text-[#0A0E14] transition-shadow hover:shadow-[0_0_30px_-6px_rgb(var(--color-accent)/0.7)] disabled:cursor-not-allowed disabled:opacity-60">
          {submitting ? "Creating account…" : "Create account"}
        </button>
      </form>
      <GoogleSignIn mode="signup" onError={setError} />
    </AuthLayout>
  );
}
