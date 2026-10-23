import { useEffect, useRef, useState } from "react";
import { useAuth } from "../context/AuthContext.jsx";
import { fetchAuthConfig } from "../api/auth.js";

/**
 * "Continue with Google", in GazeLens's own style.
 *
 * Sign-in still goes through Google's official button (Google Identity
 * Services): it is rendered on top of ours, invisible, so every click lands
 * on Google's button and Google shows its account picker. Google draws that
 * button inside its own iframe, which the page can't restyle (that is where
 * the white frame and the "Sign in as ..." layout came from); ours underneath
 * is only the picture. The chosen account comes back as a signed ID token,
 * which the API verifies before signing the user in or creating their
 * account, named from their Google profile.
 *
 * Renders nothing when the server has no GOOGLE_CLIENT_ID
 * (GET /api/auth/config), so the feature stays off until configured.
 */
const GIS_SRC = "https://accounts.google.com/gsi/client";
// Google draws its button at most 400px wide, and 40-44px tall depending on
// whether it shows the plain or the personalised ("Sign in as ...") form.
// Ours is as wide as the form, so Google's (invisible) button is measured and
// stretched to cover all of it -- a click anywhere on ours lands on Google's.
const MAX_WIDTH = 400;
const OUR_HEIGHT = 48;
let gisLoading = null;

function loadGis() {
  if (window.google?.accounts?.id) return Promise.resolve();
  if (!gisLoading) {
    gisLoading = new Promise((resolve, reject) => {
      const s = document.createElement("script");
      s.src = GIS_SRC;
      s.async = true;
      s.onload = () => resolve();
      s.onerror = () => { gisLoading = null; reject(new Error("Couldn't reach Google. Check your connection.")); };
      document.head.appendChild(s);
    });
  }
  return gisLoading;
}

function GoogleMark() {
  return (
    <svg viewBox="0 0 48 48" width="20" height="20" aria-hidden="true">
      <path fill="#FFC107" d="M43.611 20.083H42V20H24v8h11.303c-1.649 4.657-6.08 8-11.303 8-6.627 0-12-5.373-12-12s5.373-12 12-12c3.059 0 5.842 1.154 7.961 3.039l5.657-5.657C34.046 6.053 29.268 4 24 4 12.955 4 4 12.955 4 24s8.955 20 20 20 20-8.955 20-20c0-1.341-.138-2.65-.389-3.917z" />
      <path fill="#FF3D00" d="M6.306 14.691l6.571 4.819C14.655 15.108 18.961 12 24 12c3.059 0 5.842 1.154 7.961 3.039l5.657-5.657C34.046 6.053 29.268 4 24 4 16.318 4 9.656 8.337 6.306 14.691z" />
      <path fill="#4CAF50" d="M24 44c5.166 0 9.86-1.977 13.409-5.192l-6.19-5.238A11.91 11.91 0 0 1 24 36c-5.202 0-9.619-3.317-11.283-7.946l-6.522 5.025C9.505 39.556 16.227 44 24 44z" />
      <path fill="#1976D2" d="M43.611 20.083H42V20H24v8h11.303a12.04 12.04 0 0 1-4.087 5.571l.003-.002 6.19 5.238C36.971 39.205 44 34 44 24c0-1.341-.138-2.65-.389-3.917z" />
    </svg>
  );
}

export default function GoogleSignIn({ mode = "signin", onError }) {
  const { loginWithGoogle } = useAuth();
  const [clientId, setClientId] = useState(null);
  const [ready, setReady] = useState(false);
  const [busy, setBusy] = useState(false);
  const slotRef = useRef(null);
  const boxRef = useRef(null);
  const [scale, setScale] = useState({ x: 1, w: MAX_WIDTH });
  const [googleHeight, setGoogleHeight] = useState(44);
  const errorRef = useRef(onError);
  errorRef.current = onError;

  useEffect(() => {
    let cancelled = false;
    fetchAuthConfig()
      .then((cfg) => { if (!cancelled) setClientId(cfg.google_client_id || null); })
      .catch(() => {});
    return () => { cancelled = true; };
  }, []);

  // Track our button's width so Google's can be stretched to match it.
  useEffect(() => {
    if (!clientId || !boxRef.current) return;
    const fit = () => {
      const width = boxRef.current?.offsetWidth || MAX_WIDTH;
      const w = Math.min(MAX_WIDTH, width);
      setScale({ x: width / w, w });
    };
    fit();
    const ro = new ResizeObserver(fit);
    ro.observe(boxRef.current);
    return () => ro.disconnect();
  }, [clientId]);

  // Google's button changes size when it swaps to the personalised form.
  useEffect(() => {
    const slot = slotRef.current;
    if (!clientId || !slot) return;
    const measure = () => { if (slot.offsetHeight) setGoogleHeight(slot.offsetHeight); };
    const ro = new ResizeObserver(measure);
    ro.observe(slot);
    return () => ro.disconnect();
  }, [clientId]);

  useEffect(() => {
    if (!clientId) return;
    let cancelled = false;
    loadGis()
      .then(() => {
        if (cancelled || !slotRef.current) return;
        window.google.accounts.id.initialize({
          client_id: clientId,
          ux_mode: "popup",
          callback: async ({ credential }) => {
            setBusy(true);
            errorRef.current?.(null);
            try {
              await loginWithGoogle(credential);
            } catch (err) {
              errorRef.current?.(err.message || "Google sign-in didn't work. Try again.");
            } finally {
              setBusy(false);
            }
          },
        });
        slotRef.current.innerHTML = "";
        window.google.accounts.id.renderButton(slotRef.current, {
          type: "standard",
          size: "large",
          shape: "pill",
          text: mode === "signup" ? "signup_with" : "signin_with",
          width: scale.w,
        });
        setReady(true);
      })
      .catch((err) => errorRef.current?.(err.message));
    return () => { cancelled = true; };
  }, [clientId, mode, loginWithGoogle, scale.w]);

  if (!clientId) return null;

  const label = busy ? "Signing you in…" : mode === "signup" ? "Sign up with Google" : "Continue with Google";

  return (
    <div className="mt-6">
      <div className="flex items-center gap-3 text-[13px] text-text-secondary">
        <span className="h-px flex-1 bg-white/10" />
        or
        <span className="h-px flex-1 bg-white/10" />
      </div>

      <div ref={boxRef} className={`group relative mt-6 h-12 w-full ${busy ? "pointer-events-none" : ""}`}>
        {/* What people see. */}
        <div
          aria-hidden="true"
          className={`flex h-full items-center justify-center gap-3 rounded-full border border-white/15 bg-white/[0.04] text-[15px] font-semibold text-text-primary transition-all group-hover:border-white/30 group-hover:bg-white/[0.08] group-focus-within:border-accent/70 group-focus-within:ring-4 group-focus-within:ring-accent/15 ${ready ? "" : "opacity-60"}`}
        >
          <GoogleMark />
          {label}
        </div>
        {/* What they click: Google's own button, invisible, on top. Its
            iframe keeps its own accessible name for screen readers. */}
        <div
          ref={slotRef}
          className="absolute left-0 top-0 opacity-[0.01]"
          style={{
            width: scale.w, colorScheme: "light",
            transform: `scale(${scale.x}, ${OUR_HEIGHT / googleHeight})`, transformOrigin: "top left",
          }}
        />
      </div>
    </div>
  );
}
