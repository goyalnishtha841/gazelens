import { useState } from "react";
import { useAuth } from "../context/AuthContext.jsx";

export default function SignIn({ onSwitchToSignup }) {
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

  const inputBorder = error ? "border-[#B23A2E]" : "border-outline";

  return (
    <div className="min-h-screen bg-background flex items-center justify-center px-4">
      <div className="w-full max-w-[400px] bg-white border border-outline p-8 flex flex-col entrance-animation">
        <div className="mb-8">
          <span className="font-label-caps text-label-caps text-primary-container tracking-widest block mb-2">
            GAZELENS
          </span>
          <h1 className="font-headline-md text-headline-md text-on-surface">Sign In</h1>
        </div>

        {error && (
          <div className="mb-6 p-4 bg-[#F6E6E4] border border-[#B23A2E] flex items-center gap-3">
            <span className="material-symbols-outlined text-[#B23A2E] text-[18px]">error</span>
            <p className="text-[#B23A2E] text-label-caps font-semibold">{error.toUpperCase()}</p>
          </div>
        )}

        <form onSubmit={handleSubmit} className="flex flex-col gap-6">
          <div className="flex flex-col gap-2">
            <label className="font-label-caps text-label-caps text-on-surface-variant">EMAIL ADDRESS</label>
            <input
              type="email"
              required
              readOnly={submitting}
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="researcher@university.edu"
              className={`h-12 px-4 border ${inputBorder} ${submitting ? "bg-surface-container-low" : "bg-white"} font-body-md transition-all duration-150`}
            />
          </div>
          <div className="flex flex-col gap-2">
            <label className="font-label-caps text-label-caps text-on-surface-variant">PASSWORD</label>
            <input
              type="password"
              required
              readOnly={submitting}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className={`h-12 px-4 border ${inputBorder} ${submitting ? "bg-surface-container-low" : "bg-white"} font-body-md transition-all duration-150`}
            />
          </div>

          <button
            type="submit"
            disabled={submitting}
            className={`h-12 bg-primary-container text-white font-label-caps text-label-caps tracking-widest flex items-center justify-center transition-all duration-150 hover:bg-[#16555C] ${submitting ? "gap-3 cursor-wait" : ""}`}
          >
            {submitting && <div className="loading-spinner" />}
            {submitting ? "SIGNING IN..." : "CONTINUE"}
          </button>
        </form>

        <div className={`mt-8 pt-6 border-t border-outline-variant flex justify-center ${submitting ? "opacity-40" : ""}`}>
          <p className="text-secondary text-label-caps">
            NEW TO GAZELENS?{" "}
            <button type="button" onClick={onSwitchToSignup} className="text-primary-container font-bold hover:underline">
              CREATE ACCOUNT
            </button>
          </p>
        </div>
      </div>
    </div>
  );
}
