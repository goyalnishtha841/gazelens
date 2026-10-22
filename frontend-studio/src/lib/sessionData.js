import { useEffect, useState } from "react";
import { listSessions, getSessionReport } from "../api/client.js";

// Friendly names for the built-in test pages.
export const PAGE_NAME = {
  ecommerce_product_page: "Shop product page",
  form_page: "Sign-up form",
  dashboard_page: "Dashboard",
  login_page: "Login page",
  article_page: "News article",
};

/** A readable name for what a session tested: a sample page or a website. */
export function pageName(s) {
  if (!s) return "";
  if (s.target_url) return s.target_url.replace(/^https?:\/\//, "").replace(/\/$/, "");
  const key = s.ui_page || s.mode || "";
  if (PAGE_NAME[key]) return PAGE_NAME[key];
  const t = key.replace(/_/g, " ");
  return t.charAt(0).toUpperCase() + t.slice(1);
}

export function shortDate(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? "" : d.toLocaleDateString(undefined, { day: "numeric", month: "short" });
}

/** element id -> readable name, using the report's own labels. */
export function namer(report) {
  const labels = report?.pipeline_result?.element_labels || {};
  return (id) => (id === "__session__" ? "Whole page" : labels[id] || String(id).replace(/_/g, " "));
}

/**
 * Every finished session with its full report, newest first. The demo
 * pages (Gaze Map, Analytics, AI Insights, Reports) all read from this, so
 * they show the user's real results rather than sample data.
 */
export function useReports(token, limit = 20) {
  const [state, setState] = useState({ loading: true, error: null, items: [], total: 0 });
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const data = await listSessions(token, { limit: 100 });
        const sessions = data.sessions || [];
        const done = sessions.filter((s) => s.has_report).slice(0, limit);
        const reports = await Promise.all(
          done.map((s) => getSessionReport(token, s.id).then((r) => (r?.pipeline_result ? r : null)).catch(() => null)),
        );
        const items = done
          .map((s, i) => ({ session: s, report: reports[i] }))
          .filter((x) => x.report);
        if (!cancelled) setState({ loading: false, error: null, items, total: sessions.length });
      } catch (err) {
        if (!cancelled) setState({ loading: false, error: err.message || "Couldn't load your sessions", items: [], total: 0 });
      }
    })();
    return () => { cancelled = true; };
  }, [token, limit]);
  return state;
}
