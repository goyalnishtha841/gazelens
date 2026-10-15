import { useState } from "react";
import { useAuth } from "../context/AuthContext.jsx";
import { Label } from "../components/Primitives.jsx";
import { GazeTrailDecorative } from "../components/GazeTrail.jsx";

export default function SignIn({ onSwitchToSignup, onBackToHome }) {
  const { login } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);

  async function handleSubmit(e) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      await login(email, password);
    } catch (err) {
      setError(err.message || "Incorrect email or password");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="relative flex min-h-screen items-center justify-center px-4">
      {onBackToHome && (
        <button
          onClick={onBackToHome}
          className="absolute left-6 top-6 flex items-center gap-1.5 text-[12px] text-text-secondary transition-colors hover:text-text-primary"
        >
          ← Home
        </button>
      )}
      <div className="w-full max-w-[380px]">
        <div className="relative mb-8 h-16">
          <GazeTrailDecorative seed={3} points={4} edgeToEdge className="text-accent" />
        </div>
        <Label>GazeLens</Label>
        <h1 className="mt-2 font-sans text-[26px] font-semibold text-text-primary">Sign in</h1>

        {error && (
          <div className="mt-6 rounded-card border border-accent/40 px-4 py-3 text-[13px] text-text-primary">
            {error}
          </div>
        )}

        <form onSubmit={handleSubmit} className="mt-8 flex flex-col gap-5">
          <div className="flex flex-col gap-1.5">
            <Label>Email</Label>
            <input
              type="email"
              required
              readOnly={submitting}
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@example.com"
              className="h-11 rounded-card border border-border bg-surface px-3.5 text-[14px] text-text-primary outline-none transition-colors focus:border-accent"
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label>Password</Label>
            <input
              type="password"
              required
              readOnly={submitting}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="h-11 rounded-card border border-border bg-surface px-3.5 text-[14px] text-text-primary outline-none transition-colors focus:border-accent"
            />
          </div>

          <button
            type="submit"
            disabled={submitting}
            className="mt-2 h-11 rounded-card bg-text-primary font-label-caps text-[13px] font-medium uppercase tracking-label text-bg transition-opacity hover:opacity-85 disabled:opacity-60"
          >
            {submitting ? "Signing in…" : "Continue"}
          </button>
        </form>

        <div className="mt-8 border-t border-border pt-6 text-center text-[13px] text-text-secondary">
          New to GazeLens?{" "}
          <button type="button" onClick={onSwitchToSignup} className="text-accent hover:opacity-80">
            Create account
          </button>
        </div>
      </div>
    </div>
  );
}
