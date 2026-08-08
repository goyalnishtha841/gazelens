import { useState } from "react";
import { useAuth } from "../context/AuthContext.jsx";

export default function SignUp({ onSwitchToSignin }) {
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
      setError(err.message || "Couldn't create account");
    } finally {
      setSubmitting(false);
    }
  }

  const emailBorder = error ? "border-2 border-[#B23A2E]" : "border border-outline-variant";

  return (
    <div className="min-h-screen bg-background flex items-center justify-center px-4">
      <div className="bg-surface border border-outline-variant w-full max-w-[400px] p-8 entrance-animation">
        <div className="mb-8">
          <span className="font-label-caps text-label-caps text-primary mb-2 block tracking-[0.2em]">GAZELENS</span>
          <h1 className="font-headline-md text-headline-md text-on-surface">Create Account</h1>
        </div>

        {error && (
          <div className="bg-[#F6E6E4] border border-[#B23A2E]/20 p-3 mb-6 flex items-center gap-3">
            <span className="material-symbols-outlined text-[#B23A2E] text-[18px]">error</span>
            <p className="text-[#B23A2E] text-[12px] font-medium">{error}</p>
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-6">
          <div className="space-y-2">
            <label className="font-label-caps text-label-caps text-on-surface-variant">FULL NAME</label>
            <input
              type="text"
              readOnly={submitting}
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
              placeholder="e.g. Dr. Julian Vane"
              className={`w-full bg-surface-container-lowest border border-outline-variant px-4 py-3 focus:ring-0 focus:border-primary-container focus:border-2 outline-none ${submitting ? "opacity-60" : ""}`}
            />
          </div>
          <div className="space-y-2">
            <label className={`font-label-caps text-label-caps ${error ? "text-[#B23A2E]" : "text-on-surface-variant"}`}>
              EMAIL ADDRESS
            </label>
            <input
              type="email"
              required
              readOnly={submitting}
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="researcher@lab.edu"
              className={`w-full bg-surface-container-lowest ${emailBorder} px-4 py-3 focus:ring-0 focus:border-primary-container focus:border-2 outline-none ${submitting ? "opacity-60" : ""}`}
            />
          </div>
          <div className="space-y-2">
            <label className="font-label-caps text-label-caps text-on-surface-variant">PASSWORD</label>
            <input
              type="password"
              required
              minLength={8}
              readOnly={submitting}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="••••••••"
              className={`w-full bg-surface-container-lowest border border-outline-variant px-4 py-3 focus:ring-0 focus:border-primary-container focus:border-2 outline-none ${submitting ? "opacity-60" : ""}`}
            />
            <p className="font-label-caps text-[10px] text-secondary">at least 8 characters</p>
          </div>

          <button
            type="submit"
            disabled={submitting}
            className="w-full bg-primary-container text-on-primary font-label-caps text-label-caps py-4 transition-all flex items-center justify-center gap-3"
          >
            {submitting && <div className="loading-spinner" />}
            {submitting ? "CREATING ACCOUNT..." : "CREATE ACCOUNT"}
          </button>
        </form>

        <p className="mt-8 text-center text-secondary font-body-md text-[14px]">
          Already have an account?{" "}
          <button type="button" onClick={onSwitchToSignin} className="text-primary font-semibold hover:underline">
            Sign In
          </button>
        </p>
      </div>
    </div>
  );
}
