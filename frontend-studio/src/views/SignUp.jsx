import { useState } from "react";
import { useAuth } from "../context/AuthContext.jsx";
import AuthLayout, { Field } from "../components/AuthLayout.jsx";

export default function SignUp({ onSwitchToSignin, onBackToHome }) {
  const { signup } = useAuth();
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);

  async function handleSubmit(e) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      await signup(email, password, fullName);
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
        <Field label="Your name" type="text" readOnly={submitting} value={fullName}
          onChange={(e) => setFullName(e.target.value)} placeholder="Optional" autoComplete="name" />
        <Field label="Email" type="email" required readOnly={submitting} value={email}
          onChange={(e) => setEmail(e.target.value)} placeholder="you@example.com" autoComplete="email" />
        <Field label="Password" type="password" required readOnly={submitting} value={password}
          onChange={(e) => setPassword(e.target.value)} placeholder="At least 8 characters" autoComplete="new-password" />
        <button type="submit" disabled={submitting} className="mt-2 h-12 w-full rounded-full bg-accent text-[16px] font-semibold text-[#0A0E14] transition-shadow hover:shadow-[0_0_30px_-6px_rgb(var(--color-accent)/0.7)] disabled:opacity-60">
          {submitting ? "Creating account…" : "Create account"}
        </button>
      </form>
    </AuthLayout>
  );
}
