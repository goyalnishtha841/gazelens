import { useCallback, useEffect, useMemo, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { adminLogin, adminOverview, adminUser, getAdminToken, setAdminToken } from "../api/admin.js";
import { Wordmark } from "../components/IrisMark.jsx";
import IrisMark from "../components/IrisMark.jsx";
import { useCountUp } from "../components/Primitives.jsx";
import { pageName } from "../lib/sessionData.js";

/*
 * Private admin page: every user and what they've been doing. Reached only
 * by its URL (see main.jsx) and unlocked by the admin password, which is
 * separate from every user account. Read-only.
 */

const STATUS = {
  created: { label: "Not started", cls: "bg-white/[0.06] text-text-secondary" },
  calibrated: { label: "Ready", cls: "bg-cool/15 text-cool" },
  recording: { label: "Recording", cls: "bg-amber/15 text-amber" },
  processing: { label: "Building report", cls: "bg-amber/15 text-amber" },
  complete: { label: "Report ready", cls: "bg-accent/15 text-accent" },
  failed: { label: "Failed", cls: "bg-coral/15 text-coral" },
};

const STATUS_DOT = {
  created: "bg-white/30", calibrated: "bg-cool", recording: "bg-amber",
  processing: "bg-amber", complete: "bg-accent", failed: "bg-coral",
};

const EVENT = {
  signup: { label: "signed up", dot: "bg-cool" },
  test_started: { label: "started a test on", dot: "bg-amber" },
  report_ready: { label: "got a report for", dot: "bg-accent" },
  test_failed: { label: "had a test fail on", dot: "bg-coral" },
};

function ago(iso) {
  if (!iso) return "–";
  const s = (Date.now() - new Date(iso).getTime()) / 1000;
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.floor(s / 60)} min ago`;
  if (s < 86400) return `${Math.floor(s / 3600)} h ago`;
  if (s < 86400 * 30) return `${Math.floor(s / 86400)} d ago`;
  return new Date(iso).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
}

function dateTime(iso) {
  return iso ? new Date(iso).toLocaleString(undefined, { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" }) : "–";
}

const btn = "rounded-full bg-accent font-semibold text-[#0A0E14] transition-shadow hover:shadow-[0_0_30px_-6px_rgb(var(--color-accent)/0.7)] disabled:opacity-60";

export default function Admin() {
  const [token, setToken] = useState(getAdminToken);

  const signOut = useCallback(() => { setAdminToken(null); setToken(null); }, []);
  const signIn = (t) => { setAdminToken(t); setToken(t); };

  useEffect(() => { document.title = "GazeLens admin"; }, []);

  return (
    <div className="relative isolate min-h-screen bg-bg text-text-primary">
      <div aria-hidden="true" className="pointer-events-none fixed inset-x-0 top-0 -z-10 h-[520px]" style={{ background: "radial-gradient(50% 60% at 50% 0%, rgb(var(--color-accent) / 0.1), transparent 70%)" }} />
      {token ? <Dashboard token={token} onSignOut={signOut} /> : <Gate onSignIn={signIn} />}
    </div>
  );
}

/* ---------------------------------------------------------------- gate */

function Gate({ onSignIn }) {
  const [password, setPassword] = useState("");
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  async function submit(e) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const r = await adminLogin(password);
      onSignIn(r.access_token);
    } catch (err) {
      setError(
        err.status === 404 ? "Admin access isn't switched on for this server. Set GAZELENS_ADMIN_PASSWORD and restart the API."
          : err.status === 429 ? err.message.replace(/^too many/, "Too many")
          : err.status === 401 ? "That password isn't right."
          : `Couldn't reach the server. ${err.message}`,
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center px-4">
      <motion.form
        onSubmit={submit}
        initial={{ opacity: 0, y: 16 }}
        animate={{ opacity: 1, y: 0 }}
        className="w-full max-w-[400px] rounded-[26px] border border-white/10 bg-surface/70 p-8 shadow-[0_40px_100px_-40px_rgba(0,0,0,0.9)] backdrop-blur-xl"
      >
        <div className="flex items-center justify-between">
          <Wordmark large />
          <span className="rounded-full bg-coral/15 px-2.5 py-1 text-[12px] font-semibold text-coral">Admin</span>
        </div>
        <h1 className="mt-8 text-[26px] font-bold tracking-tight">Restricted area</h1>
        <p className="mt-1 text-[15px] text-text-secondary">Enter the admin password to see users and activity.</p>
        <input
          type="password"
          autoFocus
          autoComplete="current-password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          placeholder="Admin password"
          className="mt-6 h-12 w-full rounded-[14px] border border-white/10 bg-bg/60 px-4 text-[15px] outline-none transition-all placeholder:text-text-secondary/60 focus:border-accent/70 focus:ring-4 focus:ring-accent/15"
        />
        {error && <div className="mt-4 rounded-[14px] border border-coral/40 bg-coral/10 px-4 py-3 text-[14px]">{error}</div>}
        <button type="submit" disabled={busy || !password} className={`mt-5 h-12 w-full text-[15px] ${btn}`}>
          {busy ? "Checking…" : "Unlock"}
        </button>
      </motion.form>
    </div>
  );
}

/* ---------------------------------------------------------------- dashboard */

function Dashboard({ token, onSignOut }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);
  const [query, setQuery] = useState("");
  const [openUser, setOpenUser] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setData(await adminOverview(token));
      setError(null);
    } catch (err) {
      if (err.status === 401 || err.status === 404) onSignOut();
      else setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [token, onSignOut]);

  useEffect(() => { load(); }, [load]);

  const users = useMemo(() => {
    const q = query.trim().toLowerCase();
    return (data?.users || []).filter((u) => !q || u.email.toLowerCase().includes(q));
  }, [data, query]);

  const t = data?.totals;

  return (
    <div className="mx-auto max-w-[1280px] px-4 pb-20 sm:px-8">
      <header className="flex h-[76px] items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <Wordmark large />
          <span className="rounded-full bg-coral/15 px-2.5 py-1 text-[12px] font-semibold text-coral">Admin</span>
        </div>
        <div className="flex items-center gap-2">
          {data && <span className="hidden text-[13px] text-text-secondary sm:inline">Updated {ago(data.generated_at)}</span>}
          <button onClick={load} disabled={loading} className="rounded-full border border-white/10 px-4 py-2 text-[14px] text-text-primary transition-colors hover:border-accent/50 hover:text-accent disabled:opacity-50">
            {loading ? "Refreshing…" : "Refresh"}
          </button>
          <button onClick={onSignOut} className="rounded-full px-4 py-2 text-[14px] text-text-secondary transition-colors hover:text-text-primary">Sign out</button>
        </div>
      </header>

      <div className="mt-6">
        <h1 className="text-[40px] font-bold leading-tight tracking-[-0.03em] sm:text-[48px]">
          Users &amp; <span className="font-serif font-normal italic text-accent">activity</span>
        </h1>
        <p className="mt-2 text-[16px] text-text-secondary">Everyone who has signed up, and what they've been testing.</p>
      </div>

      {error && <div className="mt-6 rounded-[16px] border border-coral/40 bg-coral/10 px-5 py-4 text-[15px]">Couldn't load the data. {error}</div>}
      {!data && !error && (
        <div className="flex flex-col items-center py-24"><IrisMark size={44} wander /><p className="mt-4 text-text-secondary">Loading…</p></div>
      )}

      {data && (
        <>
          <div className="mt-8 grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
            <Tile label="Users" value={t.users} note={`+${t.new_users_7d} this week`} />
            <Tile label="Active this week" value={t.active_users_7d} tone="text-accent" />
            <Tile label="Tests" value={t.tests} note={`${t.tests_7d} this week`} />
            <Tile label="Reports ready" value={t.reports} tone="text-accent" />
            <Tile label="Problems found" value={t.problems_found} tone="text-amber" />
            <Tile label="Failed tests" value={t.failed} tone={t.failed ? "text-coral" : "text-text-primary"} />
          </div>

          <div className="mt-4 grid gap-4 lg:grid-cols-[1.6fr_1fr]">
            <Panel title="Tests per day" note="Last 14 days">
              <DailyBars days={data.daily} />
            </Panel>
            <Panel title="What people test" note={`${t.website_tests} on their own websites · ${t.calibrations} camera setups`}>
              <StatusMix mix={data.status_mix} total={t.tests} />
            </Panel>
          </div>

          <div className="mt-4 grid items-start gap-4 lg:grid-cols-[1.6fr_1fr]">
            <div className="overflow-hidden rounded-[22px] border border-white/10 bg-surface/60 backdrop-blur">
              <div className="flex flex-wrap items-center justify-between gap-3 border-b border-white/10 p-5">
                <div>
                  <h2 className="text-[19px] font-semibold">All users</h2>
                  <p className="text-[13px] text-text-secondary">{users.length} of {data.users.length} · most recently active first</p>
                </div>
                <input
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder="Search by email"
                  className="h-10 w-full rounded-full border border-white/10 bg-bg/60 px-4 text-[14px] outline-none focus:border-accent/70 sm:w-60"
                />
              </div>
              <div className="overflow-x-auto">
                <table className="w-full min-w-[620px] text-left text-[14px]">
                  <thead className="text-[12px] uppercase tracking-[0.08em] text-text-secondary">
                    <tr>
                      {["User", "Last active", "Tests", "Problems", "Setups", "Latest test"].map((h) => (
                        <th key={h} className="whitespace-nowrap px-4 py-3 font-medium">{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {users.map((u) => (
                      <tr key={u.id} onClick={() => setOpenUser(u)} className="cursor-pointer border-t border-white/[0.06] transition-colors hover:bg-white/[0.03]">
                        <td className="px-4 py-3.5">
                          <div className="max-w-[200px] truncate font-medium text-text-primary" title={u.email}>{u.email}</div>
                          <div className="text-[12px] text-text-secondary">joined {ago(u.joined_at)}</div>
                        </td>
                        <td className="whitespace-nowrap px-4 py-3.5 text-text-secondary">{ago(u.last_active_at)}</td>
                        <td className="px-4 py-3.5 tabular-nums">
                          {u.tests}
                        </td>
                        <td className={`px-4 py-3.5 tabular-nums ${u.problems_found ? "text-amber" : "text-text-secondary"}`}>{u.problems_found}</td>
                        <td className="px-4 py-3.5 tabular-nums text-text-secondary">{u.calibrations}</td>
                        <td className="px-4 py-3.5">
                          {u.last_test ? (
                            <div className="flex items-center gap-2" title={`${pageName(u.last_test)} · ${(STATUS[u.last_test.status] || {}).label || u.last_test.status}`}>
                              <span className={`h-2 w-2 shrink-0 rounded-full ${STATUS_DOT[u.last_test.status] || "bg-white/30"}`} />
                              <span className="max-w-[140px] truncate">{pageName(u.last_test)}</span>
                            </div>
                          ) : <span className="text-text-secondary">No tests yet</span>}
                        </td>
                      </tr>
                    ))}
                    {users.length === 0 && (
                      <tr><td colSpan={6} className="px-5 py-10 text-center text-text-secondary">No users match "{query}".</td></tr>
                    )}
                  </tbody>
                </table>
              </div>
            </div>

            <Panel title="Recent activity" note="Newest first">
              <ol className="max-h-[560px] space-y-3 overflow-y-auto pr-1 [scrollbar-width:thin]">
                {data.events.map((e, i) => {
                  const ev = EVENT[e.kind] || { label: e.kind, dot: "bg-white/30" };
                  return (
                    <li key={i} className="flex gap-3 text-[14px]">
                      <span className={`mt-1.5 h-2 w-2 shrink-0 rounded-full ${ev.dot}`} />
                      <div className="min-w-0">
                        <div className="leading-snug">
                          <span className="font-medium text-text-primary">{e.email}</span>{" "}
                          <span className="text-text-secondary">{ev.label}</span>
                          {e.kind !== "signup" && <> <span className="text-text-primary">{pageName(e)}</span></>}
                          {e.issues != null && <span className="text-text-secondary"> · {e.issues} problem{e.issues === 1 ? "" : "s"}</span>}
                        </div>
                        <div className="text-[12px] text-text-secondary">{ago(e.at)}</div>
                      </div>
                    </li>
                  );
                })}
                {data.events.length === 0 && <li className="text-text-secondary">Nothing yet.</li>}
              </ol>
            </Panel>
          </div>
        </>
      )}

      <AnimatePresence>
        {openUser && <UserPanel token={token} user={openUser} onClose={() => setOpenUser(null)} />}
      </AnimatePresence>
    </div>
  );
}

function Tile({ label, value, note, tone = "text-text-primary" }) {
  const n = useCountUp(value, 800);
  return (
    <div className="rounded-[20px] border border-white/10 bg-surface/60 p-5 backdrop-blur">
      <div className={`text-[30px] font-bold tabular-nums tracking-tight ${tone}`}>{n}</div>
      <div className="mt-0.5 text-[14px] text-text-secondary">{label}</div>
      {note && <div className="mt-1 text-[12px] text-text-secondary/80">{note}</div>}
    </div>
  );
}

function Panel({ title, note, children }) {
  return (
    <div className="h-full rounded-[22px] border border-white/10 bg-surface/60 p-5 backdrop-blur">
      <div className="mb-4 flex items-baseline justify-between gap-3">
        <h2 className="text-[19px] font-semibold">{title}</h2>
        {note && <span className="text-[12px] text-text-secondary">{note}</span>}
      </div>
      {children}
    </div>
  );
}

function StatusChip({ status }) {
  const s = STATUS[status] || { label: status, cls: "bg-white/[0.06] text-text-secondary" };
  return <span className={`shrink-0 rounded-full px-2.5 py-0.5 text-[12px] font-medium ${s.cls}`}>{s.label}</span>;
}

function DailyBars({ days }) {
  const max = Math.max(1, ...days.map((d) => d.tests));
  return (
    <div className="flex h-[150px] items-end gap-1.5">
      {days.map((d, i) => (
        <div key={d.date} className="flex h-full flex-1 flex-col items-center justify-end" title={`${d.date}: ${d.tests} test(s)`}>
          {d.tests > 0 && <span className="mb-1 text-[11px] tabular-nums text-text-secondary">{d.tests}</span>}
          <motion.div
            className={`w-full max-w-[28px] rounded-t-[6px] ${d.tests ? "bg-gradient-to-t from-cool via-accent to-accent" : "bg-white/[0.05]"}`}
            initial={{ height: 0 }}
            animate={{ height: `${Math.max(4, (d.tests / max) * 110)}px` }}
            transition={{ duration: 0.7, delay: i * 0.03 }}
          />
          <span className="mt-1.5 text-[10px] text-text-secondary">{new Date(d.date).getDate()}</span>
        </div>
      ))}
    </div>
  );
}

function StatusMix({ mix, total }) {
  const rows = Object.entries(mix).sort((a, b) => b[1] - a[1]);
  if (!total) return <p className="text-[14px] text-text-secondary">No tests yet.</p>;
  return (
    <div className="space-y-3">
      {rows.map(([status, n]) => (
        <div key={status}>
          <div className="mb-1 flex justify-between text-[13px]">
            <StatusChip status={status} />
            <span className="tabular-nums text-text-secondary">{n} · {Math.round((100 * n) / total)}%</span>
          </div>
          <div className="h-2 overflow-hidden rounded-full bg-white/[0.05]">
            <motion.div className="h-full rounded-full bg-accent/70" initial={{ width: 0 }} animate={{ width: `${(100 * n) / total}%` }} transition={{ duration: 0.8 }} />
          </div>
        </div>
      ))}
    </div>
  );
}

function UserPanel({ token, user, onClose }) {
  const [detail, setDetail] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    let cancelled = false;
    adminUser(token, user.id).then((d) => !cancelled && setDetail(d)).catch((e) => !cancelled && setError(e.message));
    const onKey = (e) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => { cancelled = true; window.removeEventListener("keydown", onKey); };
  }, [token, user.id, onClose]);

  return (
    <>
      <motion.div className="fixed inset-0 z-40 bg-black/50 backdrop-blur-sm" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onClick={onClose} />
      <motion.aside
        role="dialog"
        aria-label={`Tests by ${user.email}`}
        initial={{ x: "100%" }} animate={{ x: 0 }} exit={{ x: "100%" }}
        transition={{ type: "spring", stiffness: 320, damping: 34 }}
        className="fixed inset-y-0 right-0 z-50 flex w-full max-w-[520px] flex-col border-l border-white/10 bg-surface shadow-[-30px_0_80px_-30px_rgba(0,0,0,0.9)]"
      >
        <div className="flex items-start justify-between gap-4 border-b border-white/10 p-6">
          <div className="min-w-0">
            <div className="truncate text-[20px] font-semibold">{user.email}</div>
            <div className="mt-1 text-[13px] text-text-secondary">
              Joined {dateTime(user.joined_at)} · {user.tests} tests · {user.calibrations} camera setups
            </div>
          </div>
          <button onClick={onClose} aria-label="Close" className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full border border-white/10 text-text-secondary hover:text-text-primary">✕</button>
        </div>
        <div className="flex-1 overflow-y-auto p-6">
          {error && <p className="text-coral">{error}</p>}
          {!detail && !error && <p className="text-text-secondary">Loading…</p>}
          {detail && detail.tests.length === 0 && <p className="text-text-secondary">This user hasn't run a test yet.</p>}
          <div className="space-y-3">
            {detail?.tests.map((s) => (
              <div key={s.id} className="rounded-[16px] border border-white/10 bg-bg/40 p-4">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <div className="truncate font-medium">{pageName(s)}</div>
                    <div className="text-[12px] text-text-secondary">{dateTime(s.created_at)} · <span className="font-mono">{s.id}</span></div>
                  </div>
                  <StatusChip status={s.status} />
                </div>
                <div className="mt-3 flex flex-wrap gap-2 text-[12px]">
                  <span className="rounded-full bg-white/[0.06] px-2.5 py-1">{s.gaze_points} gaze points</span>
                  {s.issues != null && <span className="rounded-full bg-amber/15 px-2.5 py-1 text-amber">{s.issues} problems{s.high_issues ? ` · ${s.high_issues} urgent` : ""}</span>}
                  {s.gaze_error_px != null && <span className="rounded-full bg-accent/15 px-2.5 py-1 text-accent">accuracy {s.accuracy} · {Math.round(s.gaze_error_px)} px</span>}
                  {s.target_url && <span className="rounded-full bg-cool/15 px-2.5 py-1 text-cool">own website</span>}
                </div>
                {s.error && <div className="mt-2 truncate text-[12px] text-coral" title={s.error}>{s.error}</div>}
              </div>
            ))}
          </div>
        </div>
      </motion.aside>
    </>
  );
}
