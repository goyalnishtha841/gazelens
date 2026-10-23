import { useState } from "react";
import { useAuth } from "../context/AuthContext.jsx";
import AuthLayout, { Field } from "../components/AuthLayout.jsx";
import GoogleSignIn from "../components/GoogleSignIn.jsx";

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
    <AuthLayout
      title={<>Welcome <span className="font-serif font-normal italic text-accent">back</span></>}
      subtitle="Sign in to run a test or open your reports."
      onBackToHome={onBackToHome}
      footer={<>New to GazeLens?{" "}<button type="button" onClick={onSwitchToSignup} className="font-medium text-accent hover:opacity-80">Create an account</button></>}
    >
      {error && (
        <div className="mb-5 rounded-[14px] border border-coral/40 bg-coral/10 px-4 py-3 text-[14px] text-text-primary">{error}</div>
      )}
      <form onSubmit={handleSubmit} className="flex flex-col gap-5">
        <Field label="Email" type="email" required readOnly={submitting} value={email}
          onChange={(e) => setEmail(e.target.value)} placeholder="you@example.com" autoComplete="email" />
        <Field label="Password" type="password" required readOnly={submitting} value={password}
          onChange={(e) => setPassword(e.target.value)} placeholder="Your password" autoComplete="current-password" />
        <button type="submit" disabled={submitting} className="mt-2 h-12 w-full rounded-full bg-accent text-[16px] font-semibold text-[#0A0E14] transition-shadow hover:shadow-[0_0_30px_-6px_rgb(var(--color-accent)/0.7)] disabled:opacity-60">
          {submitting ? "Signing in…" : "Sign in"}
        </button>
      </form>
      <GoogleSignIn mode="signin" onError={setError} />
    </AuthLayout>
  );
}
