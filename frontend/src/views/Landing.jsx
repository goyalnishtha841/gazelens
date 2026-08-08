const FEATURES = [
  {
    title: "Webcam gaze tracking",
    body: "No dedicated eye-tracking hardware required — GazeLens estimates gaze from an ordinary laptop webcam.",
  },
  {
    title: "Element-level attention metrics",
    body: "Dwell time, time-to-first-fixation, and revisit counts, attributed to specific UI elements — not just a heatmap.",
  },
  {
    title: "Evidence-verified recommendations",
    body: "Every recommendation is independently re-checked against raw session metrics by a Critic agent before it reaches the report.",
  },
];

export default function Landing({ onSignIn, onSignUp }) {
  return (
    <div className="min-h-screen bg-background relative overflow-hidden">
      <div className="relative max-w-4xl mx-auto px-6 py-20 entrance-animation">
        <div className="font-label-caps text-label-caps text-primary-container tracking-widest mb-4 text-center">
          GAZE-DRIVEN UX EVALUATION
        </div>
        <h1 className="font-display-lg text-display-lg text-center leading-tight mb-5">
          See what users actually look at.
          <br />
          Know why it matters.
        </h1>
        <p className="text-secondary text-body-lg text-center max-w-xl mx-auto mb-10">
          GazeLens turns a webcam into a usability-testing tool — tracking real attention, attributing
          it to specific UI elements, and generating evidence-backed recommendations instead of a
          heatmap you have to interpret yourself.
        </p>

        <div className="flex items-center justify-center gap-3 mb-20">
          <button
            onClick={onSignUp}
            className="bg-primary-container text-white font-label-caps text-label-caps tracking-widest px-6 py-3 hover:opacity-90 transition-opacity"
          >
            GET STARTED
          </button>
          <button
            onClick={onSignIn}
            className="border border-outline text-on-surface font-label-caps text-label-caps tracking-widest px-6 py-3 hover:bg-surface-container transition-colors"
          >
            SIGN IN
          </button>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-gutter">
          {FEATURES.map((f) => (
            <div key={f.title} className="bg-white border border-outline-variant p-5">
              <div className="h-0.5 w-6 bg-primary-container mb-3" />
              <h3 className="font-headline-sm text-headline-sm mb-2">{f.title}</h3>
              <p className="text-secondary text-body-md">{f.body}</p>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
