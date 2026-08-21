/**
 * Sample data shaped like the REAL backend output (see backend/attribution
 * SessionMetrics, backend/agents' finding/recommendation schemas, and the
 * actual PDF report generated for session ses_6637320201b2) -- not invented
 * numbers, so wiring this view to the real API later is a data-source swap,
 * not a redesign.
 */

export const project = {
  name: "Article Page",
  sessionId: "ses_6637320201b2",
  generated: "20 Aug 2026",
  mode: "test_ui",
};

export const overview = {
  attentionScore: 74.8,
  timeToFirstFocus: 2.4,
  coverage: 81,
  fixations: 14,
};

// Mirrors attribution's per-element metrics (dwell_time_pct, fixation_count,
// ttff_seconds, importance) for the article_page layout.
export const elements = [
  { id: "hero_image", label: "Hero image", dwellPct: 74.7, importance: "medium", box: { x: 0.1, y: 0.28, w: 0.8, h: 0.3 } },
  { id: "article_body", label: "Article body", dwellPct: 7.3, importance: "medium", box: { x: 0.1, y: 0.6, w: 0.55, h: 0.3 } },
  { id: "byline", label: "Byline", dwellPct: 0.4, importance: "low", box: { x: 0.1, y: 0.23, w: 0.5, h: 0.03 } },
  { id: "headline", label: "Headline", dwellPct: 0.2, importance: "high", box: { x: 0.1, y: 0.12, w: 0.8, h: 0.1 } },
  { id: "subscribe_cta", label: "Subscribe CTA", dwellPct: 0.0, importance: "high", box: { x: 0.3, y: 0.92, w: 0.35, h: 0.05 } },
  { id: "share_button", label: "Share button", dwellPct: 0.0, importance: "medium", box: { x: 0.1, y: 0.92, w: 0.15, h: 0.05 } },
  { id: "related_articles", label: "Related articles", dwellPct: 0.0, importance: "low", box: { x: 0.68, y: 0.6, w: 0.22, h: 0.3 } },
  { id: "nav_bar", label: "Nav bar", dwellPct: 0.0, importance: "low", box: { x: 0.05, y: 0.03, w: 0.9, h: 0.06 } },
];

// Real fixation sequence shape -- order matters (green first / red last in
// the PDF's own gaze-path convention), clustered exactly like the real
// session's scanpath (byline area, then hero_image, repeatedly).
export const scanpath = [
  { x: 0.42, y: 0.26 }, { x: 0.46, y: 0.25 }, { x: 0.5, y: 0.27 },
  { x: 0.44, y: 0.42 }, { x: 0.48, y: 0.44 }, { x: 0.52, y: 0.43 },
  { x: 0.45, y: 0.26 }, { x: 0.49, y: 0.28 },
  { x: 0.46, y: 0.44 }, { x: 0.5, y: 0.46 }, { x: 0.53, y: 0.45 },
  { x: 0.47, y: 0.27 }, { x: 0.51, y: 0.44 }, { x: 0.55, y: 0.43 },
];

// Matches backend/agents' finding schema (severity, issue, heuristic,
// evidence) exactly as it appears in the real PDF report.
export const findings = [
  {
    severity: "High",
    issue: "Primary CTA received minimal attention",
    element: "subscribe_cta",
    heuristic: "Visibility and visual hierarchy",
    evidence: "Received only 0.0% of total gaze time (threshold: 5.0%)",
  },
  {
    severity: "High",
    issue: "High-importance element received no attention at all",
    element: "headline",
    heuristic: "Accessibility",
    evidence: "Zero fixations across a 49.2s session -- a high-importance element received no attention at all, not just late attention",
  },
  {
    severity: "High",
    issue: "High-importance element received no attention at all",
    element: "subscribe_cta",
    heuristic: "Accessibility",
    evidence: "Zero fixations across a 49.2s session -- a high-importance element received no attention at all, not just late attention",
  },
  {
    severity: "Medium",
    issue: "Primary CTA received minimal attention",
    element: "share_button",
    heuristic: "Visibility and visual hierarchy",
    evidence: "Received only 0.0% of total gaze time (threshold: 5.0%)",
  },
  {
    severity: "Medium",
    issue: "Layout structure likely causing disorientation",
    element: "__session__",
    heuristic: "Consistency and standards",
    evidence: "Scanpath repeatedly jumped back to the same elements (threshold: 3 repeat jumps)",
  },
];

// Matches backend/agents' recommendation schema (confidence tier + score).
export const recommendations = [
  {
    element: "subscribe_cta",
    tier: "Strong",
    confidence: 0.6,
    text: "Increase contrast between the element and its background.",
    evidence: "Received only 0.0% of total gaze time (threshold: 5.0%)",
  },
  {
    element: "subscribe_cta",
    tier: "Strong",
    confidence: 0.6,
    text: "Review this element's placement and prominence.",
    evidence: "Zero fixations across a 49.2s session -- a high-importance element received no attention at all",
  },
  {
    element: "share_button",
    tier: "Strong",
    confidence: 0.6,
    text: "Increase contrast between the element and its background.",
    evidence: "Received only 0.0% of total gaze time (threshold: 5.0%)",
  },
  {
    element: "__session__",
    tier: "Weak",
    confidence: 0.3,
    text: "Simplify the layout so scanning order matches reading order.",
    evidence: "Scanpath repeatedly jumped back to the same elements (threshold: 3 repeat jumps)",
  },
];

export const workflow = [
  {
    step: "01",
    title: "Calibrate",
    body: "A short 16-point sequence trains a gaze model to your face, camera, and screen. Takes under a minute.",
  },
  {
    step: "02",
    title: "Record",
    body: "Point it at a test page or any live URL. Your webcam tracks real gaze in real time while someone uses it normally.",
  },
  {
    step: "03",
    title: "Attribute",
    body: "Raw coordinates get matched to the actual elements on the page: dwell time, first focus, revisits, full scanpath.",
  },
  {
    step: "04",
    title: "Reason",
    body: "A chain of agents turns those metrics into findings, and a critic independently re-verifies each one against the raw data.",
  },
];
